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


def test_left_only(lift: Lift):
    """Test cẩu TRÁI độc lập — cẩu phải không chạy."""
    dur = 1.5
    print(f"\n[TEST] CẨU TRÁI độc lập (ENA={config.ENA_CAU_T}, IN1={config.IN1_CAU_T}, IN2={config.IN2_CAU_T})")

    input("  Nhấn Enter → NÂNG trái...")
    lift._left_en.on(); lift._left_up.on(); lift._left_down.off()
    time.sleep(dur)
    lift._left_en.off(); lift._left_up.off()
    time.sleep(0.5)

    input("  Nhấn Enter → HẠ trái...")
    lift._left_en.on(); lift._left_up.off(); lift._left_down.on()
    time.sleep(dur)
    lift._left_en.off(); lift._left_down.off()
    print("  Xong cẩu trái.")


def test_right_only(lift: Lift):
    """Test cẩu PHẢI độc lập — cẩu trái không chạy."""
    dur = 1.5
    print(f"\n[TEST] CẨU PHẢI độc lập (IN3={config.IN3_CAU_P}, IN4={config.IN4_CAU_P})")

    input("  Nhấn Enter → NÂNG phải...")
    lift._right_up.on(); lift._right_down.off()
    time.sleep(dur)
    lift._right_up.off()
    time.sleep(0.5)

    input("  Nhấn Enter → HẠ phải...")
    lift._right_up.off(); lift._right_down.on()
    time.sleep(dur)
    lift._right_down.off()
    print("  Xong cẩu phải.")


def test_mcp3008_all(lift: Lift):
    """Đọc tất cả 8 channel MCP3008 real-time — tìm xem IR cắm channel nào."""
    from control.mcp3008_bus import get_mcp3008_bus
    bus = get_mcp3008_bus()
    if not bus.available:
        print("  ⚠ MCP3008 không khả dụng")
        return
    print("\n[TEST] Scan tất cả 8 channel MCP3008 — Ctrl+C để thoát")
    print("  Che tay/đặt vật vào cảm biến → xem channel nào thay đổi")
    print("  CH6=IR trái  CH7=IR phải  (theo config hiện tại)\n")
    i = 0
    while True:
        vals = bus.read_many(list(range(8)))
        adcs = [int(round(v * 1023)) for v in vals]
        i += 1
        row = "  ".join(f"CH{c}:{adcs[c]:4d}" for c in range(8))
        print(f"\r  [{i:4d}] {row}", end="", flush=True)
        time.sleep(0.2)


def test_ir_live(lift: Lift):
    print("\n[TEST] Đọc IR real-time — Ctrl+C để thoát")
    print(f"  Ngưỡng PALLET_THRESHOLD={config.PALLET_THRESHOLD} (ADC < ngưỡng = CÓ pallet)")
    if not lift.pallet.available:
        print("  ⚠ MCP3008 không khả dụng")
        return
    i = 0
    while True:
        left, right, ok = lift.pallet.read_status()
        left_adc, right_adc = lift.pallet.read_adc()
        i += 1
        if not ok:
            print(f"\r  [{i:4d}] LỖI đọc SPI/ADC                              ", end="", flush=True)
        else:
            l_bar = "██ CÓ " if left  else "░░ -- "
            r_bar = "██ CÓ " if right else "░░ -- "
            print(f"\r  [{i:4d}] Trái: {l_bar}(ADC {left_adc:4d})   Phải: {r_bar}(ADC {right_adc:4d})", end="", flush=True)
        time.sleep(0.2)


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


def test_calibrate_lift(lift: Lift):
    """Calibrate độ cao tầng 1/2 và bù lệch trái/phải — lưu vào config.py."""
    import importlib

    step_time  = 0.05   # bước điều chỉnh thời gian (giây)
    step_extra = 0.05   # bước điều chỉnh bù lệch

    print("\n[CALIBRATE] Nâng/hạ lift — điều chỉnh timing, lưu config")
    print("  Nâng: t1+/t1- = tầng1  t2+/t2- = tầng2  l+/l- = bù trái nâng  r+/r- = bù phải nâng")
    print("  Hạ:   ll+/ll- = bù trái hạ  rl+/rl- = bù phải hạ")
    print("  Di chuyển: up1/up2/dn   Khai báo vị trí: set0/set1/set2   Đo thực: find1/find2")
    print("  s = lưu & thoát\n")

    level_names = {0: "SÀN", 1: "TẦNG 1", 2: "TẦNG 2"}
    print(f"  ⚠  Lift hiện đang ở đâu? Gõ set0 / set1 / set2 để khai báo trước khi di chuyển.")

    while True:
        importlib.reload(config)
        print(f"  [vị trí={level_names.get(lift._current_level, '?')}]  "
              f"shelf1={config.LIFT_TIME_SHELF_1:.3f}s  shelf2={config.LIFT_TIME_SHELF_2:.3f}s  "
              f"nâng: L={config.LIFT_LEFT_EXTRA:+.3f} R={config.LIFT_RIGHT_EXTRA:+.3f}  "
              f"hạ: L={config.LIFT_LEFT_LOWER_EXTRA:+.3f} R={config.LIFT_RIGHT_LOWER_EXTRA:+.3f}")

        cmd = input("  > ").strip().lower()

        if cmd == "s":
            print("  Đã lưu config.")
            break
        elif cmd == "set0":
            lift._current_level = 0; print("  Đã khai báo: SÀN")
        elif cmd == "set1":
            lift._current_level = 1; print("  Đã khai báo: TẦNG 1")
        elif cmd == "set2":
            lift._current_level = 2; print("  Đã khai báo: TẦNG 2")
        elif cmd == "up1":
            lift.go_to_level(1)
        elif cmd == "up2":
            lift.go_to_level(2)
        elif cmd == "dn":
            lift.go_to_level(0)
        elif cmd == "t1+":
            _save_config("LIFT_TIME_SHELF_1", config.LIFT_TIME_SHELF_1 + step_time)
        elif cmd == "t1-":
            _save_config("LIFT_TIME_SHELF_1", max(0.1, config.LIFT_TIME_SHELF_1 - step_time))
        elif cmd == "t2+":
            _save_config("LIFT_TIME_SHELF_2", config.LIFT_TIME_SHELF_2 + step_time)
        elif cmd == "t2-":
            _save_config("LIFT_TIME_SHELF_2", max(0.1, config.LIFT_TIME_SHELF_2 - step_time))
        elif cmd == "l+":
            _save_config("LIFT_LEFT_EXTRA", config.LIFT_LEFT_EXTRA + step_extra)
        elif cmd == "l-":
            _save_config("LIFT_LEFT_EXTRA", config.LIFT_LEFT_EXTRA - step_extra)
        elif cmd == "r+":
            _save_config("LIFT_RIGHT_EXTRA", config.LIFT_RIGHT_EXTRA + step_extra)
        elif cmd == "r-":
            _save_config("LIFT_RIGHT_EXTRA", config.LIFT_RIGHT_EXTRA - step_extra)
        elif cmd == "ll+":
            _save_config("LIFT_LEFT_LOWER_EXTRA", config.LIFT_LEFT_LOWER_EXTRA + step_extra)
        elif cmd == "ll-":
            _save_config("LIFT_LEFT_LOWER_EXTRA", config.LIFT_LEFT_LOWER_EXTRA - step_extra)
        elif cmd == "rl+":
            _save_config("LIFT_RIGHT_LOWER_EXTRA", config.LIFT_RIGHT_LOWER_EXTRA + step_extra)
        elif cmd == "rl-":
            _save_config("LIFT_RIGHT_LOWER_EXTRA", config.LIFT_RIGHT_LOWER_EXTRA - step_extra)
        elif cmd in ("find1", "find2"):
            target = 1 if cmd == "find1" else 2
            _find_level_by_hand(lift, target)
        else:
            print("  Lệnh không hợp lệ.")
            print("  t1+/t1-/t2+/t2-  l+/l-  r+/r-  up1/up2/dn  set0/set1/set2  find1/find2  s")


def _find_level_by_hand(lift: Lift, target_level: int):
    """Nâng từng bước nhỏ từ sàn, người dùng bấm Enter khi đúng độ cao → ghi thời gian."""
    key = "LIFT_TIME_SHELF_1" if target_level == 1 else "LIFT_TIME_SHELF_2"
    pulse = 0.05   # mỗi xung nâng 0.05 giây

    print(f"\n  [FIND LEVEL {target_level}] Đặt kệ trước càng. Hạ về sàn trước...")
    lift.go_to_level(0)
    lift._current_level = 0
    time.sleep(0.5)

    print(f"  Nhấn Enter liên tục để nâng từng bước {pulse}s.")
    print(f"  Khi càng VỪNG KHÍT dưới pallet tầng {target_level} → gõ 'ok' rồi Enter.")

    elapsed = 0.0
    while True:
        raw = input(f"  [{elapsed:.2f}s] Enter=nâng thêm / ok=ghi lại: ").strip().lower()
        if raw == "ok":
            break
        # nâng thêm 1 xung
        lift._left_en.on(); lift._left_up.on(); lift._left_down.off()
        lift._right_up.on(); lift._right_down.off()
        time.sleep(pulse)
        lift._stop_all()
        elapsed += pulse

    _save_config(key, elapsed)
    lift._current_level = target_level
    print(f"  Đã lưu {key} = {elapsed:.3f}s")


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
        "9": ("IR real-time (Ctrl+C để thoát)", test_ir_live),
        "a": ("Scan tất cả 8 channel MCP3008", test_mcp3008_all),
        "b": ("Cẩu TRÁI độc lập (nâng/hạ)", test_left_only),
        "c": ("Cẩu PHẢI độc lập (nâng/hạ)", test_right_only),
        "d": ("Calibrate độ cao + bù lệch (lưu config)", test_calibrate_lift),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-9, a/b/c/d): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func and key not in ("6", "7", "8", "9", "b", "c"):
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
