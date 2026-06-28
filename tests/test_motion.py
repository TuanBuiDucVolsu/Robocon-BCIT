#!/usr/bin/env python3
"""
Test module motion.py — kiểm tra từng chức năng động cơ & cảm biến dò line.
Chạy trên Raspberry Pi 4 với phần cứng kết nối.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control import Motion
from control.mcp3008_bus import reset_mcp3008_bus


def test_forward_backward(m: Motion):
    print("\n[TEST] Tiến 2 giây...")
    m.forward(config.SPEED_DEFAULT)
    time.sleep(2)
    m.stop()
    time.sleep(1)

    print("[TEST] Lùi 2 giây...")
    m.backward(config.SPEED_DEFAULT)
    time.sleep(2)
    m.stop()
    time.sleep(1)


def test_turning(m: Motion):
    print("\n[TEST] Xoay trái 1.5 giây...")
    m.turn_left()
    time.sleep(1.5)
    m.stop()
    time.sleep(1)

    print("[TEST] Xoay phải 1.5 giây...")
    m.turn_right()
    time.sleep(1.5)
    m.stop()
    time.sleep(1)


def test_speed_levels(m: Motion):
    print("\n[TEST] Test các mức tốc độ...")
    for speed in [30, 50, 70, 100]:
        print(f"  Tốc độ {speed}%...")
        m.forward(speed)
        time.sleep(1)
    m.stop()


def test_line_sensor(m: Motion):
    print("\n[TEST] Đọc cảm biến dò line digital (10 lần, cách 0.5s)...")
    for i in range(10):
        values = m.read_line_sensor()
        error = m.compute_line_error(values)
        active = sum(values)
        print(f"  Lần {i+1}: {values}  active={active}  error={error:.2f}")
        time.sleep(0.5)


def test_line_sensor_raw(m: Motion):
    print(f"\n[TEST] Calibrate QTR-8A — raw ADC (ngưỡng LINE_THRESHOLD={config.LINE_THRESHOLD})")
    print("  Đặt từng mắt lên line đen / nền trắng để xem giá trị.")
    print("  Nhấn Ctrl+C để dừng.\n")
    try:
        while True:
            adc = m.read_line_sensor_adc()
            raw = m.read_line_sensor_raw()
            digital = m.read_line_sensor()
            adc_str = " ".join(f"{v:4d}" for v in adc)
            dig_str = "".join("█" if d else "░" for d in digital)
            err = m.compute_line_error_analog(raw)
            print(f"  ADC: [{adc_str}]  {dig_str}  err={err:+.2f}")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n  Dừng calibrate.")


def test_exit_start_zone(m: Motion):
    print("\n[TEST] Thoát ô start — exit_start_zone()")
    print("  Đặt robot trong ô start, quay mặt SANG TRÁI (9h, về Kệ 3).")
    input("  Nhấn Enter để bắt đầu...")
    success = m.exit_start_zone()
    values = m.read_line_sensor()
    print(f"  Kết quả: {'OK' if success else 'THẤT BẠI'} — sensor={values} active={sum(values)}")


def test_line_follow(m: Motion):
    print("\n[TEST] Bám line 10 giây (hoặc đến khi gặp giao lộ)...")
    start = time.time()
    while time.time() - start < 10:
        is_intersection, _ = m.follow_line()
        if is_intersection:
            print("  -> Phát hiện giao lộ! Dừng.")
            break
        time.sleep(0.01)
    m.stop()


def test_distance_sensor(m: Motion):
    print("\n[TEST] Cảm biến siêu âm HC-SR04 real-time — Ctrl+C để thoát")
    print("  Di chuyển vật trước robot để xem khoảng cách thay đổi:")
    i = 0
    while True:
        dist = m.get_distance()
        i += 1
        if dist < 0:
            print(f"\r  [{i:4d}] KHÔNG CÓ cảm biến siêu âm (GPIO {config.ULTRASONIC_TRIG_PIN}/{config.ULTRASONIC_ECHO_PIN})", end="", flush=True)
        else:
            bar = "█" * int(min(dist, 60) / 2)
            print(f"\r  [{i:4d}] {dist:6.1f}cm  {bar:<30}", end="", flush=True)
        time.sleep(0.2)


def test_approach_shelf(m: Motion):
    print(f"\n[TEST] Tiếp cận kệ (dừng ở {config.APPROACH_DISTANCE}cm)...")
    print("  Đặt vật/kệ phía trước robot.")
    input("  Nhấn Enter để bắt đầu...")
    success = m.approach_shelf()
    dist = m.get_distance()
    print(f"  Kết quả: {'ĐÃ ĐẾN' if success else 'TIMEOUT'} — khoảng cách {dist:.1f}cm")

    print(f"\n  Lùi ra ({config.RETREAT_DISTANCE}cm)...")
    success = m.retreat_from_shelf()
    dist = m.get_distance()
    print(f"  Kết quả: {'ĐÃ LÙI' if success else 'TIMEOUT'} — khoảng cách {dist:.1f}cm")


def test_turn_90(m: Motion):
    print(f"\n[TEST] Xoay 90° (TURN_TIME={config.TURN_TIME}s) — calibrate trên sa bàn")
    print("  Đặt robot song song line, quan sát có vuông góc không.")
    input("  Nhấn Enter để xoay TRÁI 90°...")
    m.turn_left_90()
    time.sleep(1)
    ans = input("  Góc ~90°? (y=OK / n=cần chỉnh TURN_TIME trong config.py): ").strip().lower()
    print(f"  Ghi nhận: {'OK' if ans == 'y' else 'Cần chỉnh TURN_TIME'}")

    input("  Nhấn Enter để xoay PHẢI 90° (về hướng cũ)...")
    m.turn_right_90()


def test_execute_route(m: Motion):
    print("\n[TEST] execute_route — điều hướng theo route config")
    print("  Route có sẵn:")
    routes = {
        "1": ("START → Kệ 3", config.ROUTE_START_TO_SHELF_0),
        "2": ("Giữa các kệ", config.ROUTE_BETWEEN_SHELVES),
        "3": ("Kệ → Samsung", config.ROUTE_SHELF_TO_FACTORY.get("samsung", [])),
        "4": ("Kệ 4 → Liên hợp (NV2)", config.ROUTE_LOOSE_TO_JOINT),
    }
    for k, (name, _) in routes.items():
        print(f"    {k}. {name}")
    sub = input("  Chọn route (1-4): ").strip()
    if sub not in routes:
        print("  Lựa chọn không hợp lệ.")
        return
    name, route = routes[sub]
    if not route:
        print("  Route rỗng!")
        return
    print(f"  Route {name}: {route}")
    input("  Đặt robot đúng vị trí xuất phát route. Nhấn Enter...")
    ok = m.execute_route(route)
    print(f"  Kết quả: {'THÀNH CÔNG' if ok else 'THẤT BẠI — mất line / timeout giao lộ'}")


def test_spi_line_and_ir(m: Motion):
    """Đọc line + IR liên tục — kiểm tra shared MCP3008 bus."""
    from control import Lift
    lift = Lift()
    print("\n[TEST] Shared SPI — line (CH0-5) + IR pallet (CH6-7) đồng thời")
    print("  Nhấn Ctrl+C để dừng.\n")
    try:
        while True:
            line = m.read_line_sensor_adc()
            left, right, ok = lift.pallet.read_status()
            line_str = " ".join(f"{v:3d}" for v in line)
            ir_str = (
                f"IR trái={'CÓ' if left else 'KHÔNG'} phải={'CÓ' if right else 'KHÔNG'}"
                if ok else "IR LỖI đọc"
            )
            print(f"  LINE [{line_str}]  {ir_str}")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n  Dừng.")
    finally:
        lift.cleanup()


def test_motor_diagnosis(m: Motion):
    """Chạy từng motor riêng lẻ để xác định motor nào bị ngược chiều."""
    speed = 50
    dur = 1.5

    print("\n[CHẨN ĐOÁN] Chạy từng motor riêng — quan sát bánh nào quay và chiều quay")
    print(f"  Tốc độ {speed}%, mỗi bước {dur}s\n")

    actions = [
        ("BÁNH TRÁI — tiến",  lambda: _run_left(m, speed, forward=True)),
        ("BÁNH TRÁI — lùi",   lambda: _run_left(m, speed, forward=False)),
        ("BÁNH PHẢI — tiến",  lambda: _run_right(m, speed, forward=True)),
        ("BÁNH PHẢI — lùi",   lambda: _run_right(m, speed, forward=False)),
    ]

    for label, fn in actions:
        input(f"  Nhấn Enter để chạy: {label} ...")
        fn()
        time.sleep(dur)
        m.stop()
        time.sleep(0.5)

    print("\n  Nếu TRÁI tiến nhưng bánh quay ngược → swap IN1_XE_T ↔ IN2_XE_T trong config.py")
    print("  Nếu PHẢI tiến nhưng bánh quay ngược → swap IN1_XE_P ↔ IN2_XE_P trong config.py")


def _run_left(m: Motion, speed: float, forward: bool):
    m._left_rev.value = 0
    m._right_fwd.value = 0
    m._right_rev.value = 0
    if forward:
        m._left_fwd.value = speed / 100
    else:
        m._left_fwd.value = 0
        m._left_rev.value = speed / 100


def _run_right(m: Motion, speed: float, forward: bool):
    m._left_fwd.value = 0
    m._left_rev.value = 0
    m._right_rev.value = 0
    if forward:
        m._right_fwd.value = speed / 100
    else:
        m._right_fwd.value = 0
        m._right_rev.value = speed / 100


def main():
    print("=" * 50)
    print("TEST MODULE ĐỘNG CƠ DI CHUYỂN")
    print("=" * 50)

    m = Motion()

    tests = {
        "1": ("Tiến/Lùi", test_forward_backward),
        "2": ("Xoay trái/phải", test_turning),
        "3": ("Các mức tốc độ", test_speed_levels),
        "4": ("Đọc cảm biến dò line (digital)", test_line_sensor),
        "5": ("Calibrate QTR-8A (raw ADC)", test_line_sensor_raw),
        "6": ("Thoát ô start (exit_start_zone)", test_exit_start_zone),
        "7": ("Bám line (chạy thực tế)", test_line_follow),
        "8": ("Cảm biến siêu âm (đo khoảng cách)", test_distance_sensor),
        "9": ("Tiếp cận + lùi khỏi kệ", test_approach_shelf),
        "10": ("Xoay 90° (calibrate TURN_TIME)", test_turn_90),
        "11": ("execute_route (route config)", test_execute_route),
        "12": ("Shared SPI: line + IR cùng lúc", test_spi_line_and_ir),
        "d": ("Chẩn đoán motor từng bánh riêng", test_motor_diagnosis),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-12, d): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func and key not in ("5", "10", "11", "12"):
                    func(m)
        elif choice in tests and tests[choice][1]:
            tests[choice][1](m)
        else:
            print("Lựa chọn không hợp lệ.")
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        m.cleanup()
        reset_mcp3008_bus()
        print("\nĐã cleanup GPIO.")


if __name__ == "__main__":
    main()
