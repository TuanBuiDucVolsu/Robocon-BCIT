#!/usr/bin/env python3
"""
Debug đầu ra + căn tốc độ 2 bánh (KHÔNG cần encoder).

Chạy trên Pi, KÊ BÁNH KHỎI MẶT ĐẤT:
    python3 -m tools.motor_balance

Chức năng:
  1. In PWM thực mỗi bánh nhận (tiến/lùi) theo config hiện tại.
  2. Đếm vòng: chạy TỪNG bánh cùng 1 mức PWM trong N giây → bạn đếm số vòng →
     tool tính PWM_COMPENSATION lý tưởng.
  3/4. Chạy CẢ 2 bánh (tiến/lùi) để so trực quan bánh nào nhanh hơn.
"""

import sys
import time

sys.path.insert(0, ".")

import config
from control import Motion


def _rev(name):
    return getattr(config, name, config.PWM_COMPENSATION)


def show_outputs():
    s = config.SPEED_DEFAULT
    rev = _rev("PWM_COMPENSATION_REV")
    print("\n[ĐẦU RA PWM — theo config hiện tại]")
    print(f"  SPEED_DEFAULT = {s}%")
    print(f"  PWM_COMPENSATION     (tiến) = {config.PWM_COMPENSATION}")
    print(f"  PWM_COMPENSATION_REV (lùi)  = {rev}")
    print(f"\n  TIẾN :  trái = {s:5.1f}%   phải = {s * config.PWM_COMPENSATION:5.1f}%")
    print(f"  LÙI  :  trái = {s:5.1f}%   phải = {s * rev:5.1f}%")
    print("  (phải < trái = đang ghì bánh phải vì nó vốn nhanh hơn)")


def _spin_one(m: Motion, side: str, forward: bool, pwm: float, dur: float):
    m._left_fwd.value = 0
    m._left_rev.value = 0
    m._right_fwd.value = 0
    m._right_rev.value = 0
    v = pwm / 100.0
    if side == "left":
        (m._left_fwd if forward else m._left_rev).value = v
    else:
        (m._right_fwd if forward else m._right_rev).value = v
    time.sleep(dur)
    m.stop()


def count_match(m: Motion):
    pwm, dur = 60.0, 5.0
    print(f"\n[ĐẾM VÒNG] Cùng PWM {pwm:.0f}% trong {dur:.0f}s mỗi bánh.")
    print("  → Đánh dấu 1 chấm trên mỗi bánh để đếm vòng cho dễ.")

    input("  Enter: chạy BÁNH TRÁI...")
    _spin_one(m, "left", True, pwm, dur)
    nl = float(input("  Số vòng bánh TRÁI: ").strip() or 0)

    input("  Enter: chạy BÁNH PHẢI...")
    _spin_one(m, "right", True, pwm, dur)
    nr = float(input("  Số vòng bánh PHẢI: ").strip() or 0)

    if nl <= 0 or nr <= 0:
        print("  ⚠ Thiếu số liệu, bỏ qua.")
        return

    print(f"\n  Trái {nl:g} vòng | Phải {nr:g} vòng")
    if abs(nl - nr) < 0.01:
        print("  → 2 bánh bằng nhau: PWM_COMPENSATION = 1.0")
    elif nr > nl:
        print(f"  → Phải NHANH hơn. Đặt: PWM_COMPENSATION = {nl / nr:.3f}")
        print("    (ghì bánh phải xuống cho bằng trái)")
    else:
        print(f"  → Trái nhanh hơn (tỉ lệ phải/trái = {nr / nl:.3f}).")
        print("    Code chỉ ghì được bánh PHẢI → đặt PWM_COMPENSATION = 1.0,")
        print("    rồi giảm SPEED bánh trái bằng cơ khí, hoặc chấp nhận line-PD tự bù.")


def run_both(m: Motion, forward: bool):
    dur = 3.0
    lbl = "TIẾN" if forward else "LÙI"
    print(f"\n[CHẠY CẢ 2 — {lbl}] {dur:.0f}s. Quan sát bánh nào vượt.")
    input("  Enter để chạy...")
    (m.forward if forward else m.backward)(config.SPEED_DEFAULT)
    time.sleep(dur)
    m.stop()


def main():
    print("=" * 48)
    print("DEBUG / CĂN TỐC ĐỘ 2 BÁNH  — KÊ BÁNH KHỎI MẶT ĐẤT!")
    print("=" * 48)
    m = Motion()
    try:
        while True:
            print("\n  1. Xem đầu ra PWM mỗi bánh")
            print("  2. Đếm vòng → tính PWM_COMPENSATION")
            print("  3. Chạy cả 2 bánh — TIẾN")
            print("  4. Chạy cả 2 bánh — LÙI")
            print("  q. Thoát")
            c = input("  > ").strip().lower()
            if c == "1":
                show_outputs()
            elif c == "2":
                count_match(m)
            elif c == "3":
                run_both(m, True)
            elif c == "4":
                run_both(m, False)
            elif c == "q":
                break
            else:
                print("  Lệnh không hợp lệ.")
    except KeyboardInterrupt:
        print()
    finally:
        m.stop()
        m.cleanup()
        print("\nĐã cleanup GPIO.")


if __name__ == "__main__":
    main()
