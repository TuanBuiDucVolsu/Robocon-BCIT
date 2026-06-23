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


def test_pallet_sensor(lift: Lift):
    print("\n[TEST] Cảm biến IR pallet trái/phải (10 lần, cách 0.5s)...")
    if not lift.pallet.available:
        print("  ⚠ I2C pallet sensor không khả dụng — bỏ qua test đọc thực")
        return
    print("  Đặt/bỏ pallet trên từng càng để kiểm tra:")
    for i in range(10):
        left, right, ok = lift.pallet.read_status()
        if not ok:
            print(f"  Lần {i+1}: LỖI đọc I2C")
        else:
            print(f"  Lần {i+1}: trái={'CÓ ██' if left else 'KHÔNG ░░'}"
                  f"  phải={'CÓ ██' if right else 'KHÔNG ░░'}")
        time.sleep(0.5)


def test_pickup_dropoff(lift: Lift):
    print("\n[TEST] Pickup tầng 1 (cần cả 2 IR)...")
    success = lift.pickup(shelf_level=1, require_both=True)
    print(f"  Kết quả: {'THÀNH CÔNG' if success else 'THẤT BẠI'}")
    time.sleep(2)

    print("[TEST] Dropoff...")
    success = lift.dropoff()
    print(f"  Kết quả: {'ĐÃ HẠ' if success else 'CÓ THỂ KẸT / LỖI IR'}")
    time.sleep(1)


def test_pickup_shelf2(lift: Lift):
    print("\n[TEST] Pickup tầng 2 (cần cả 2 IR)...")
    success = lift.pickup(shelf_level=2, require_both=True)
    time.sleep(2)

    print("[TEST] Dropoff...")
    success = lift.dropoff()
    print(f"  Kết quả: {'ĐÃ HẠ' if success else 'CÓ THỂ KẸT / LỖI IR'}")
    time.sleep(1)


def main():
    print("=" * 50)
    print("TEST MODULE CƠ CẤU NÂNG/HẠ")
    print("=" * 50)

    lift = Lift()

    tests = {
        "1": ("Nâng/Hạ cơ bản", test_raise_lower),
        "2": ("Các tầng kệ (1 và 2)", test_shelf_levels),
        "3": ("Cảm biến IR pallet trái/phải", test_pallet_sensor),
        "4": ("Pickup/Dropoff tầng 1 (có xác nhận)", test_pickup_dropoff),
        "5": ("Pickup/Dropoff tầng 2 (có xác nhận)", test_pickup_shelf2),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-5): ").strip()

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
