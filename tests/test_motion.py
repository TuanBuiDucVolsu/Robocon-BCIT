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


def test_forward_find_and_follow(m: Motion):
    print(f"\n[TEST] Tiến thẳng 2 giây (speed={config.SPEED_DEFAULT})...")
    m.forward(config.SPEED_DEFAULT)
    time.sleep(1.5)

    print(f"  Tìm line (tối đa {config.EXIT_START_TIMEOUT}s)...")
    start = time.time()
    found = False
    while time.time() - start < config.EXIT_START_TIMEOUT:
        values = m.read_line_sensor()
        if sum(values) > 0:
            found = True
            break
        time.sleep(0.01)
    m.stop()

    if not found:
        print("  Không tìm thấy line!")
        return

    print("  Đã thấy line — bám line tối đa 5s (hoặc đến khi gặp giao lộ)...")
    start = time.time()
    while time.time() - start < 5:
        at_intersection, _ = m.follow_line()
        if at_intersection:
            print("  -> Phát hiện giao lộ! Dừng.")
            break
        time.sleep(0.01)
    m.stop()


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
    import navigation as nav

    print("\n[TEST] execute_route — route do navigation.plan() TÍNH RA")
    cases = {
        "1": ("Ô xuất phát → Kệ 3", nav.START_POSE, "SHELF0"),
        "2": ("Kệ 3 → Kệ 2", nav.pose_at("SHELF0"), "SHELF1"),
        "3": ("Kệ 3 → Foxconn (cùng hàng R0)", nav.pose_at("SHELF0"), "F_foxconn"),
        "4": ("Kệ 3 → Samsung (khác hàng, vòng cột kệ)", nav.pose_at("SHELF0"), "F_samsung"),
        "5": ("Kệ 2 → Foxconn (né đoạn đứt R2)", nav.pose_at("SHELF1"), "F_foxconn"),
        "6": ("Foxconn → Kệ 3 (quay về kho)", nav.pose_at("F_foxconn"), "SHELF0"),
        "7": ("Foxconn → Samsung (giữa 2 nhà máy)", nav.pose_at("F_foxconn"), "F_samsung"),
        "8": ("Foxconn → Kệ 4 → Liên hợp (NV2)", nav.pose_at("F_foxconn"), "LOOSE"),
    }
    for k, (name, src, dst) in cases.items():
        route, _ = nav.plan(src, dst)
        print(f"    {k}. {name}\n       {nav.route_to_text(route)}")
    sub = input(f"  Chọn route (1-{len(cases)}): ").strip()
    if sub not in cases:
        print("  Lựa chọn không hợp lệ.")
        return
    name, src, dst = cases[sub]
    route, new_pose = nav.plan(src, dst)
    print(f"  Route {name}: {route}")
    print(f"  Đặt robot tại: {nav.describe(src)}")
    input("  Nhấn Enter để chạy...")
    ok = m.execute_route(route)
    print(f"  Kết quả: {'THÀNH CÔNG' if ok else 'THẤT BẠI — mất line / timeout giao lộ'}")
    print(f"  Vị trí kỳ vọng sau route: {nav.describe(new_pose)}")


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


def _save_config(key: str, value: float):
    """Ghi đè giá trị một hằng số float trong config.py."""
    import re
    path = os.path.join(os.path.dirname(__file__), "..", "config.py")
    text = open(path).read()
    text = re.sub(
        rf"^({re.escape(key)}\s*=\s*)[\d.+-]+",
        lambda m: f"{m.group(1)}{value:.3f}",
        text, flags=re.MULTILINE
    )
    open(path, "w").write(text)


def test_encoder_live(m: Motion):
    """Đọc xung encoder 2 bánh real-time trong khi tiến — kiểm tra dây/đấu đúng kênh."""
    if not (m._encoder_left.available and m._encoder_right.available):
        print("  Encoder chưa sẵn sàng — kiểm tra ENCODER_LEFT_PIN/ENCODER_RIGHT_PIN trong config.py.")
        return

    print("\n[TEST] Đọc xung encoder real-time khi tiến — Ctrl+C để dừng")
    m.forward(config.SPEED_DEFAULT)
    try:
        while True:
            left, right = m.sample_wheel_pulses(0.2)
            print(f"  trái={left:3d} xung/0.2s   phải={right:3d} xung/0.2s")
    except KeyboardInterrupt:
        print("\n  Dừng.")
    finally:
        m.stop()


def test_calibrate_pwm_by_encoder(m: Motion):
    """So xung 2 bánh khi tiến thẳng → tự tính & lưu PWM_COMPENSATION (bánh phải)."""
    import importlib

    if not (m._encoder_left.available and m._encoder_right.available):
        print("  Encoder chưa sẵn sàng — kiểm tra ENCODER_LEFT_PIN/ENCODER_RIGHT_PIN trong config.py.")
        return

    print("\n[CALIBRATE] Đo xung 2 bánh khi tiến thẳng 1s, tự tính PWM_COMPENSATION")
    print("  Đặt robot lên đế (bánh không chạm đất) trước khi chạy.")
    print("  Chỉ chỉnh chiều TIẾN — chiều lùi vẫn phải tự chỉnh PWM_COMPENSATION_REV bằng tay.\n")

    while True:
        importlib.reload(config)
        print(f"  PWM_COMPENSATION hiện tại (bánh phải, tiến) = {config.PWM_COMPENSATION:.3f}")
        cmd = input("  Enter = tiến 1s và đo xung / q = thoát: ").strip().lower()
        if cmd == "q":
            break

        m.forward(config.SPEED_DEFAULT)
        left, right = m.sample_wheel_pulses(1.0)
        m.stop()

        print(f"  trái={left} xung   phải={right} xung")
        if left == 0 or right == 0:
            print("  Không đọc được xung ở 1 trong 2 bánh — kiểm tra dây encoder (C1/VCC/GND) trước khi calibrate.")
            continue

        ratio = left / right
        suggested = max(0.5, min(1.0, config.PWM_COMPENSATION * ratio))
        nhanh_hon = "phải" if right > left else "trái"
        print(f"  Bánh {nhanh_hon} đang quay nhanh hơn.")
        print(f"  Đề xuất PWM_COMPENSATION = {suggested:.3f} (hiện {config.PWM_COMPENSATION:.3f})")

        if input("  Lưu giá trị đề xuất vào config.py? (y/N): ").strip().lower() == "y":
            _save_config("PWM_COMPENSATION", suggested)
            print("  Đã lưu.")


def test_cross_line_gap(m: Motion):
    """Vượt khoảng ĐỨT của line ở ô xuất phát — calibrate LINE_GAP_COAST_TIME.

    Sa bàn có 1 chỗ line đứt thật mà robot BẮT BUỘC đi qua: hàng R0 tại ô xuất phát
    (~245mm). Mất line thì robot giữ lái và trôi thẳng LINE_GAP_COAST_TIME giây rồi
    mới coi là lạc và quét tìm lại. Đặt quá ngắn = quay ngang giữa khoảng đứt.
    """
    print(f"\n[TEST] Vượt khoảng đứt line (LINE_GAP_COAST_TIME={config.LINE_GAP_COAST_TIME}s)")
    print("  Đặt robot trên hàng R0 phía KỆ, quay mặt về phía nhà máy (hướng ô xuất phát).")
    print("  Robot sẽ bám line qua khoảng đứt ô xuất phát tới giao lộ cột giữa.")
    input("  Nhấn Enter để chạy...")

    t0 = time.time()
    ok = m.navigate_intersections(1)
    print(f"  Kết quả: {'✅ qua được' if ok else '❌ mất line'} sau {time.time()-t0:.1f}s")
    if not ok:
        print(f"  → Tăng LINE_GAP_COAST_TIME (đang {config.LINE_GAP_COAST_TIME}s) hoặc giảm tốc độ.")
    else:
        print("  → Nếu robot có lúc quay ngang giữa khoảng trống thì vẫn nên tăng thêm.")


def test_probe_board_side(m: Motion):
    """Dò nửa sân: đứng TẠI giao lộ Kệ 3, xoay phải thử xem có nhánh line không."""
    import navigation as nav

    print("\n[TEST] Tự dò NỬA SÂN (dùng đầu mỗi trận)")
    print("  Đặt robot ĐÚNG TẠI giao lộ Kệ 3 (chỗ line dọc cột kệ gặp line ngang R0),")
    print("  quay mặt về phía KỆ — y như lúc thi đấu sau khi thoát ô xuất phát.")
    print(f"  Robot sẽ xoay phải 90°, tiến {config.PROBE_TRAVEL_TIME}s, đọc line, rồi lùi lại và xoay về.")
    input("  Nhấn Enter để dò...")

    found = m.probe_side_branch("right")
    if found is None:
        print("  ❌ Không kết luận được — cảm biến line lỗi.")
        return
    mirrored = not found
    print(f"  Kết quả: {'CÓ' if found else 'KHÔNG có'} nhánh line bên phải")
    print(f"  → Đang ở nửa {'GƯƠNG' if mirrored else 'CHUẨN'} "
          f"(BOARD_MIRRORED nên = {mirrored})")
    print(f"  config.BOARD_MIRRORED hiện tại = {config.BOARD_MIRRORED}"
          f"{'  ⚠ KHÁC kết quả dò' if bool(config.BOARD_MIRRORED) != mirrored else '  ✅ khớp'}")
    print("  (Khi thi đấu robot tự dò và tự nạp lại bản đồ — cờ trong config chỉ là dự phòng.)")
    nav.set_mirrored(mirrored)
    route, _ = nav.plan((nav.PROBE_NODE, nav.TOWARD_SHELVES), "SHELF0")
    print(f"  Route tiếp theo vào Kệ 3: {nav.route_to_text(route)}")


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
        "6": ("Tiến thẳng tìm line + bám line 5s/giao lộ", test_forward_find_and_follow),
        "7": ("Bám line (chạy thực tế)", test_line_follow),
        "8": ("Cảm biến siêu âm (đo khoảng cách)", test_distance_sensor),
        "9": ("Tiếp cận + lùi khỏi kệ", test_approach_shelf),
        "10": ("Xoay 90° (calibrate TURN_TIME)", test_turn_90),
        "11": ("execute_route (route config)", test_execute_route),
        "12": ("Shared SPI: line + IR cùng lúc", test_spi_line_and_ir),
        "13": ("Tự dò NỬA SÂN tại giao lộ Kệ 3", test_probe_board_side),
        "14": ("Vượt khoảng đứt line ô xuất phát", test_cross_line_gap),
        "d": ("Chẩn đoán motor từng bánh riêng", test_motor_diagnosis),
        "e": ("Đọc xung encoder real-time (Ctrl+C để thoát)", test_encoder_live),
        "f": ("Calibrate PWM_COMPENSATION bằng encoder (lưu config)", test_calibrate_pwm_by_encoder),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-14, d-f): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func and key not in ("5", "10", "11", "12", "13", "14", "e"):
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
