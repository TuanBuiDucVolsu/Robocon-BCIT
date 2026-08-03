#!/usr/bin/env python3
"""CHỐT SỐ XUNG ENCODER TRÊN MỖI CENTIMET

    python3 -m tools.calibrate_encoder_cm

VÌ SAO CẦN: bước tiến bù trước khi xoay phải đi ĐÚNG một quãng đường. Thanh cảm
biến ở đầu xe, trục bánh cách nó ~12cm; lùi tới khi cảm biến thấy giao lộ thì trục
đã vượt qua 12cm, phải tiến bù lại. Xoay 90° tại chỗ đòi trục bánh nằm trong
~±1.5cm của giao lộ (vạch rộng 20mm, thanh cảm biến trải 47mm) — lệch hơn là xoay
xong cảm biến văng ra vùng trắng.

Trước đây bù bằng THỜI GIAN (REVERSE_RECENTER_TIME = 1.3s). Quãng đường của một
hằng số thời gian đổi theo pin, ma sát sàn và tải trên càng — cõng 2 kiện thì nặng
hơn hẳn lúc đi không. Đo trên robot 03/08: lùi-rồi-tiến-để-xoay chạy KHÔNG ỔN
ĐỊNH, lúc xoay đúng vào line, lúc lùi ít quá, lúc tiến quá đà rồi va vào kệ.

Có số xung/cm thì bù được bằng QUÃNG ĐƯỜNG THẬT, không phụ thuộc mấy thứ trên.

CÁCH ĐO: robot tự chạy thẳng một nhịp ngắn, bạn đo bằng thước xem nó đi được bao
nhiêu cm. Lặp 3 lần, lấy TRUNG VỊ. Ba lần lệch nhau nhiều = encoder rớt xung, công
cụ sẽ nói ra chứ không im lặng chốt một số xấu.

⚠️ BÁNH XE CHẠY THẬT. Cần ~1m đường thẳng trống phía trước, mặt sàn GIỐNG sa bàn
   (thảm khác gạch khác — số này gắn với mặt sàn).
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from control.motion import Motion
from tests.config_editor import save_config

SO_LAN = 3
GIAY_CHAY = 1.2          # đủ dài để đọc thước cho chính xác, đủ ngắn để không lệch


def _mot_lan(m: Motion, lan: int) -> tuple[int, float] | None:
    print(f"\n  --- Lần {lan}/{SO_LAN} ---")
    print("  Đánh dấu vị trí HIỆN TẠI của robot (dán băng dính ở mép bánh).")
    if input("  Sẵn sàng chạy? (y/N): ").strip().lower() != "y":
        return None

    m._doc_xung()                      # xả bộ đếm
    m.forward(config.REVERSE_RECENTER_SPEED)
    time.sleep(GIAY_CHAY)
    m.stop()
    time.sleep(0.3)                    # cho xe hết chòng chành rồi mới đọc nốt xung
    xung = m._doc_xung()

    print(f"  Đếm được {xung} xung (tổng 2 bánh).")
    while True:
        tra_loi = input("  ĐO BẰNG THƯỚC: robot đi được bao nhiêu cm? ").strip()
        try:
            cm = float(tra_loi.replace(",", "."))
        except ValueError:
            print("  Nhập số, ví dụ 18.5")
            continue
        if cm <= 0:
            print("  Phải lớn hơn 0.")
            continue
        return xung, cm


def main() -> int:
    print("=" * 72)
    print("  CHỐT SỐ XUNG ENCODER / CENTIMET")
    print("=" * 72)
    print(f"\n  Robot sẽ chạy thẳng {GIAY_CHAY}s ở {config.REVERSE_RECENTER_SPEED}%,"
          f" {SO_LAN} lần.")
    print("  Cần ~1m trống phía trước, mặt sàn GIỐNG sa bàn thi đấu.")
    print(f"\n  Hiện tại: ENCODER_PULSES_PER_CM = {config.ENCODER_PULSES_PER_CM}"
          f"  ({'CHƯA calibrate' if config.ENCODER_PULSES_PER_CM <= 0 else 'đã có'})")

    m = Motion()
    try:
        if not (m._encoder_left.available and m._encoder_right.available):
            print("\n  ❌ Encoder KHÔNG khả dụng — kiểm chân GPIO "
                  f"{config.ENCODER_LEFT_PIN}/{config.ENCODER_RIGHT_PIN}.")
            return 1

        ket = []
        for lan in range(1, SO_LAN + 1):
            r = _mot_lan(m, lan)
            if r is None:
                print("  Đã huỷ.")
                return 1
            xung, cm = r
            ket.append(xung / cm)
            print(f"  → {xung / cm:.2f} xung/cm")
    finally:
        m.stop()
        m.cleanup()

    tv = statistics.median(ket)
    tan = max(ket) - min(ket)
    print("\n" + "=" * 72)
    print("  Ba lần: " + "  ".join(f"{v:.2f}" for v in ket))
    print(f"  Trung vị : {tv:.2f} xung/cm")
    print(f"  Tản      : {tan:.2f} ({tan / tv * 100:.0f}% so với trung vị)")

    # Encoder JGA25-370 cho xung rất dày và gpiozero có thể RỚT xung (đã ghi trong
    # WheelEncoder). Rớt không đều giữa các lần thì con số này vô dụng — nói thẳng
    # thay vì chốt bừa rồi để robot va vào kệ.
    if tan / tv > 0.15:
        print("\n  ❌ BA LẦN LỆCH NHAU QUÁ 15% — KHÔNG chốt.")
        print("     Encoder đang rớt xung không đều (JGA25-370 cho xung rất dày,")
        print("     callback gpiozero theo không kịp). Cách chữa: cài pigpio và")
        print("     chuyển riêng phần encoder sang đó, hoặc hạ tốc độ đo.")
        print("     Giữ nguyên cách bù theo thời gian cho tới khi số này ổn định.")
        return 1

    print(f"\n  ✅ ỔN. Với {tv:.2f} xung/cm thì tiến bù "
          f"{config.RECENTER_CM}cm = {tv * config.RECENTER_CM:.0f} xung.")
    print(f"\n  ⚠️ Kiểm lại RECENTER_CM = {config.RECENTER_CM} — đó là khoảng cách")
    print("     THANH CẢM BIẾN → TRỤC BÁNH. Đo bằng thước trên robot, đừng tin số cũ.")

    if input("\n  Ghi vào config.py? (y/N): ").strip().lower() == "y":
        save_config("ENCODER_PULSES_PER_CM", round(tv, 2))
        print(f"  Đã ghi ENCODER_PULSES_PER_CM = {tv:.2f}")
        print("  Chạy test_motion option 15 và 18 để xác nhận bước xoay đã ổn định.")
    else:
        print("  Không ghi. Đặt tay trong config.py nếu muốn.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
