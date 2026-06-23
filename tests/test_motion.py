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
    print("\n[TEST] Đọc cảm biến dò line (10 lần, cách 0.5s)...")
    for i in range(10):
        values = m.read_line_sensor()
        error = m.compute_line_error(values)
        active = sum(values)
        print(f"  Lần {i+1}: {values}  active={active}  error={error:.2f}")
        time.sleep(0.5)


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
    print("\n[TEST] Cảm biến siêu âm HC-SR04 (10 lần, cách 0.5s)...")
    print("  Di chuyển vật trước robot để xem khoảng cách thay đổi:")
    for i in range(10):
        dist = m.get_distance()
        if dist < 0:
            print(f"  Lần {i+1}: KHÔNG CÓ cảm biến siêu âm")
            break
        bar = "█" * int(min(dist, 50) / 2)
        print(f"  Lần {i+1}: {dist:6.1f}cm {bar}")
        time.sleep(0.5)


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


def main():
    print("=" * 50)
    print("TEST MODULE ĐỘNG CƠ DI CHUYỂN")
    print("=" * 50)

    m = Motion()

    tests = {
        "1": ("Tiến/Lùi", test_forward_backward),
        "2": ("Xoay trái/phải", test_turning),
        "3": ("Các mức tốc độ", test_speed_levels),
        "4": ("Đọc cảm biến dò line", test_line_sensor),
        "5": ("Bám line (chạy thực tế)", test_line_follow),
        "6": ("Cảm biến siêu âm (đo khoảng cách)", test_distance_sensor),
        "7": ("Tiếp cận + lùi khỏi kệ", test_approach_shelf),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-7): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func:
                    func(m)
        elif choice in tests and tests[choice][1]:
            tests[choice][1](m)
        else:
            print("Lựa chọn không hợp lệ.")
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        m.cleanup()
        print("\nĐã cleanup GPIO.")


if __name__ == "__main__":
    main()
