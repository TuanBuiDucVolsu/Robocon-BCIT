#!/usr/bin/env python3
"""
Test module lift.py — kiểm tra cơ cấu nâng/hạ càng forklift.
Chạy trên Raspberry Pi 4 với phần cứng kết nối.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control import Lift


def test_raise_lower(lift: Lift):
    print("\n[TEST] Nâng lên tầng 1...")
    lift.go_to_level(1)
    time.sleep(2)

    print("[TEST] Hạ về mặt sàn...")
    lift.go_to_level(0)
    time.sleep(2)


def test_shelf_levels(lift: Lift):
    print("\n[TEST] Nâng lên tầng 1...")
    lift.go_to_level(1)
    time.sleep(2)

    print("[TEST] Nâng tiếp lên tầng 2...")
    lift.go_to_level(2)
    time.sleep(2)

    print("[TEST] Hạ về tầng 1...")
    lift.go_to_level(1)
    time.sleep(2)

    print("[TEST] Hạ về mặt sàn...")
    lift.go_to_level(0)
    time.sleep(1)


def test_pickup_dropoff(lift: Lift):
    print("\n[TEST] Mô phỏng pickup tầng 1...")
    lift.pickup(shelf_level=1)
    time.sleep(2)

    print("[TEST] Mô phỏng dropoff...")
    lift.dropoff()
    time.sleep(1)


def test_pickup_shelf2(lift: Lift):
    print("\n[TEST] Mô phỏng pickup tầng 2...")
    lift.pickup(shelf_level=2)
    time.sleep(2)

    print("[TEST] Mô phỏng dropoff...")
    lift.dropoff()
    time.sleep(1)


def main():
    print("=" * 50)
    print("TEST MODULE CƠ CẤU NÂNG/HẠ")
    print("=" * 50)

    lift = Lift()

    tests = {
        "1": ("Nâng/Hạ cơ bản", test_raise_lower),
        "2": ("Các tầng kệ (1 và 2)", test_shelf_levels),
        "3": ("Pickup/Dropoff tầng 1", test_pickup_dropoff),
        "4": ("Pickup/Dropoff tầng 2", test_pickup_shelf2),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-4): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func:
                    func(lift)
        elif choice in tests and tests[choice][1]:
            tests[choice][1](lift)
        else:
            print("Lựa chọn không hợp lệ.")
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        lift.cleanup()
        print("\nĐã cleanup GPIO.")


if __name__ == "__main__":
    main()
