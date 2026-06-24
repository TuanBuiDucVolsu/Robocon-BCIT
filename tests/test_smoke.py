#!/usr/bin/env python3
"""
Smoke test tích hợp — chạy trên Pi + sa bàn thật.
Kiểm tra 1 lượt NV1 rút gọn hoặc từng đoạn luồng thi đấu.

  python3 tests/test_smoke.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control import Motion, Lift
from control.mcp3008_bus import reset_mcp3008_bus
from vision import Vision


def _pause(msg: str):
    input(f"\n  {msg}\n  Nhấn Enter để tiếp tục...")


def smoke_exit_and_navigate(m: Motion):
    print("\n[SMOKE 1] Exit start + navigate đến Kệ 3")
    print("  Đặt robot trong ô start, hướng 9h (về Kệ 3).")
    _pause("Sẵn sàng?")
    if not m.exit_start_zone():
        print("  ❌ exit_start_zone THẤT BẠI")
        return False
    print("  ✅ exit_start_zone OK")
    ok = m.execute_route(config.ROUTE_START_TO_SHELF_0)
    print(f"  {'✅' if ok else '❌'} execute_route(ROUTE_START_TO_SHELF_0): {ok}")
    return ok


def smoke_pickup_cycle(m: Motion, lift: Lift, vision: Vision):
    print("\n[SMOKE 2] Pickup 1 lượt (approach → classify_pair → pickup → retreat)")
    _pause("Đặt robot trước kệ có 2 kiện, càng level 0")

    if not m.approach_shelf():
        print("  ❌ approach_shelf TIMEOUT")
        return False
    print("  ✅ approach_shelf OK")

    label_l, label_r = vision.classify_pair()
    print(f"  classify_pair: trái={label_l}, phải={label_r}")
    if label_l is None or label_r is None:
        print("  ❌ classify_pair không đủ 2 kiện")
        m.retreat_from_shelf()
        return False
    print("  ✅ classify_pair OK")

    if not lift.pickup(shelf_level=1, require_both=True):
        print("  ❌ pickup THẤT BẠI (IR)")
        m.retreat_from_shelf()
        return False
    print("  ✅ pickup OK")

    if not m.retreat_from_shelf():
        print("  ⚠ retreat timeout (vẫn coi pickup OK)")
    else:
        print("  ✅ retreat OK")
    return True


def smoke_drop_single_side(lift: Lift):
    print("\n[SMOKE 3] Drop từng càng (NV1 — 2 nhà máy khác nhau)")
    _pause("Robot đang mang 2 kiện — đặt trước điểm thả thử")

    side = input("  Thả càng nào trước? (left/right) [left]: ").strip().lower() or "left"
    if side == "left":
        dropped = lift.dropoff_left()
    else:
        dropped = lift.dropoff_right()

    print(f"  dropoff_{side}: {'✅ IR OK' if dropped else '❌ fail'}")
    if dropped:
        lift.raise_after_drop(side)
        print(f"  ✅ raise_after_drop({side})")

    other = "right" if side == "left" else "left"
    ans = input(f"  Thả càng {other} + stow_forks? (y/N): ").strip().lower()
    if ans == "y":
        if other == "left":
            dropped2 = lift.dropoff_left()
        else:
            dropped2 = lift.dropoff_right()
        print(f"  dropoff_{other}: {'✅' if dropped2 else '❌'}")
        if dropped2:
            lift.stow_forks(other)
            print(f"  ✅ stow_forks({other})")
    return dropped


def smoke_nv2_pickup(lift: Lift, m: Motion):
    print("\n[SMOKE 4] NV2 — pickup 1 kiện (require_both=False)")
    _pause("Đặt robot trước kệ 4 / kho hàng rời")

    if not m.approach_shelf():
        print("  ❌ approach TIMEOUT")
        return False
    ok = lift.pickup(shelf_level=1, require_both=False)
    print(f"  pickup NV2: {'✅' if ok else '❌'}")
    m.retreat_from_shelf()
    return ok


def smoke_full_lap(m: Motion, lift: Lift, vision: Vision):
    print("\n[SMOKE FULL] 1 lượt rút gọn: exit → Kệ3 → pickup")
    print("  (Không giao hàng — dùng sau khi smoke từng phần đã OK)")
    _pause("Chuẩn bị sa bàn")
    if not smoke_exit_and_navigate(m):
        return
    smoke_pickup_cycle(m, lift, vision)
    print("\n  Hoàn tất smoke full (chưa test deliver/return).")


def main():
    print("=" * 50)
    print("SMOKE TEST TÍCH HỢP — Bảng O2")
    print("=" * 50)

    tests = {
        "1": ("Exit start + ROUTE_START → Kệ 3", None),
        "2": ("Pickup 1 lượt (approach + pair + nâng)", None),
        "3": ("Drop từng càng + raise_after_drop / stow", None),
        "4": ("NV2 pickup (require_both=False)", None),
        "5": ("Full rút gọn (1+2)", None),
    }

    print("\nChọn smoke test:")
    for k, (name, _) in tests.items():
        print(f"  {k}. {name}")

    choice = input("\nNhập số (1-5): ").strip()

    m = Motion()
    lift = Lift()
    vision = Vision()

    try:
        if choice == "1":
            smoke_exit_and_navigate(m)
        elif choice == "2":
            smoke_pickup_cycle(m, lift, vision)
        elif choice == "3":
            smoke_drop_single_side(lift)
        elif choice == "4":
            smoke_nv2_pickup(lift, m)
        elif choice == "5":
            smoke_full_lap(m, lift, vision)
        else:
            print("Lựa chọn không hợp lệ.")
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        m.cleanup()
        lift.cleanup()
        vision.cleanup()
        reset_mcp3008_bus()
        print("\nĐã cleanup.")


if __name__ == "__main__":
    main()
