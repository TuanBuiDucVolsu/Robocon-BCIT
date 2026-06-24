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
from control.mcp3008_bus import reset_mcp3008_bus


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
    print(f"\n[TEST] Cảm biến IR pallet (ngưỡng PALLET_THRESHOLD={config.PALLET_THRESHOLD})")
    if not lift.pallet.available:
        print("  ⚠ MCP3008 không khả dụng — bỏ qua test đọc thực")
        return
    print("  Đặt/bỏ pallet trên từng càng để kiểm tra:")
    for i in range(10):
        left, right, ok = lift.pallet.read_status()
        left_adc, right_adc = lift.pallet.read_adc()
        if not ok:
            print(f"  Lần {i+1}: LỖI đọc SPI/ADC")
        else:
            print(f"  Lần {i+1}: trái={'CÓ ██' if left else 'KHÔNG ░░'} (ADC {left_adc:4d})"
                  f"  phải={'CÓ ██' if right else 'KHÔNG ░░'} (ADC {right_adc:4d})")
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


def test_drop_single_side(lift: Lift):
    """Luồng NV1: thả 1 càng → nâng lại → thả càng còn lại → stow."""
    print("\n[TEST] Drop từng càng (dropoff_left/right + raise_after_drop + stow_forks)")
    print("  Cần robot đang mang 2 kiện (sau pickup).")
    side = input("  Thả càng nào trước? (left/right) [left]: ").strip().lower() or "left"

    if side == "left":
        dropped = lift.dropoff_left()
    else:
        dropped = lift.dropoff_right()
    print(f"  dropoff_{side}: {'THÀNH CÔNG' if dropped else 'THẤT BẠI / IR lỗi'}")

    if dropped:
        lift.raise_after_drop(side)
        print(f"  raise_after_drop({side}) — OK")

    other = "right" if side == "left" else "left"
    ans = input(f"  Tiếp tục thả càng {other}? (y/N): ").strip().lower()
    if ans != "y":
        return

    if other == "left":
        dropped2 = lift.dropoff_left()
    else:
        dropped2 = lift.dropoff_right()
    print(f"  dropoff_{other}: {'THÀNH CÔNG' if dropped2 else 'THẤT BẠI'}")

    if dropped2:
        lift.stow_forks(other)
        print(f"  stow_forks({other}) — cả 2 càng về sàn")


def test_pickup_nv2(lift: Lift):
    print("\n[TEST] Pickup NV2 — require_both=False (chỉ cần 1 IR)")
    print("  Đặt 1 kiện trên càng (kho hàng rời).")
    input("  Nhấn Enter để nâng...")
    success = lift.pickup(shelf_level=1, require_both=False)
    print(f"  Kết quả: {'THÀNH CÔNG' if success else 'THẤT BẠI'}")
    if success:
        ans = input("  Hạ thử (dropoff)? (y/N): ").strip().lower()
        if ans == "y":
            ok = lift.dropoff()
            print(f"  dropoff: {'OK' if ok else 'THẤT BẠI'}")


def test_dropoff_same_factory(lift: Lift):
    print("\n[TEST] dropoff() đồng bộ — 2 kiện cùng nhà máy")
    input("  Nhấn Enter sau khi robot mang 2 kiện...")
    ok = lift.dropoff()
    print(f"  Kết quả: {'ĐÃ HẠ (IR OK)' if ok else 'THẤT BẠI / IR vẫn thấy pallet'}")


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
        "6": ("Drop từng càng NV1 (left/right + stow)", test_drop_single_side),
        "7": ("Pickup NV2 (require_both=False)", test_pickup_nv2),
        "8": ("dropoff() 2 kiện cùng NM", test_dropoff_same_factory),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-8): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func and key not in ("6", "7", "8"):
                    func(lift)
        elif choice in tests and tests[choice][1]:
            tests[choice][1](lift)
        else:
            print("Lựa chọn không hợp lệ.")
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        lift.cleanup()
        reset_mcp3008_bus()
        print("\nĐã cleanup GPIO.")


if __name__ == "__main__":
    main()
