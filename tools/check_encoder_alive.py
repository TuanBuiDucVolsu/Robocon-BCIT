#!/usr/bin/env python3
"""ENCODER CÓ CÒN ĐẾM KHÔNG — 10 giây, trả lời một câu.

    python3 -m tools.check_encoder_alive

VÌ SAO CẦN: `WheelEncoder.available` chỉ nói GPIO có mở được không, KHÔNG nói dây
có còn cắm không. Rút hẳn dây encoder ra thì `available` vẫn True, số xung vẫn 0,
và mọi thứ đo bằng quãng đường im lặng biến thành "không bao giờ tới mốc":

  • advance vào kệ  → không bao giờ đủ ADVANCE_SHELF_STOP_CM → ĐÂM VÀO KỆ
  • ADVANCE_MAX_TRAVEL_CM (lưới an toàn cuối) → cũng chết theo, cùng một lý do
  • tien_bu_cm, xoay 90° bằng encoder, các chốt quãng của back_to_intersection

Đo trên robot 04/08: log in ra "dừng theo QUÃNG ĐƯỜNG 15.0cm — bỏ qua siêu âm"
rồi robot chạy thẳng vào kệ, không hề in dòng "ĐÃ ĐI ...cm". Đó là chữ ký của
encoder chết: nhánh nào cũng đúng, chỉ là con số không bao giờ nhúc nhích.

⚠️ BÁNH XE CHẠY THẬT ~1 giây. Kê robot lên vật cao cho bánh hổng đất cũng được —
bài này chỉ hỏi xung có về hay không, không đo quãng đường.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from control.motion import Motion

GIAY = 1.0
# Ở 40% trong 1 giây, bánh lành cho hàng trăm xung. Lấy 20 làm mức "có sống" —
# thấp hơn thế thì chỉ có thể là nhiễu, không phải bánh đang quay.
XUNG_TOI_THIEU = 20


def main() -> int:
    print("=" * 70)
    print("  ENCODER CÓ CÒN ĐẾM KHÔNG")
    print("=" * 70)
    print(f"\n  Chân GPIO: trái {config.ENCODER_LEFT_PIN}, "
          f"phải {config.ENCODER_RIGHT_PIN}")
    print(f"  Robot sẽ chạy thẳng {GIAY}s ở {config.SPEED_DEFAULT}%. "
          "Cần ~40cm trống, hoặc kê bánh hổng đất.")
    if input("\n  Enter để chạy (q để thoát): ").strip().lower() == "q":
        return 1

    m = Motion()
    try:
        print(f"\n  available: trái={m._encoder_left.available} "
              f"phải={m._encoder_right.available}  "
              "(chỉ nói GPIO mở được, KHÔNG nói dây còn cắm)")
        m._encoder_left.read_and_reset()
        m._encoder_right.read_and_reset()
        m.forward(config.SPEED_DEFAULT)
        time.sleep(GIAY)
        m.stop()
        time.sleep(0.3)          # xe hết chòng chành rồi mới đọc nốt
        trai = m._encoder_left.read_and_reset()
        phai = m._encoder_right.read_and_reset()
    finally:
        m.stop()
        m.cleanup()

    print("\n" + "=" * 70)
    print(f"  Bánh TRÁI (GPIO {config.ENCODER_LEFT_PIN}) : {trai} xung")
    print(f"  Bánh PHẢI (GPIO {config.ENCODER_RIGHT_PIN}) : {phai} xung")
    if config.ENCODER_PULSES_PER_CM > 0:
        print(f"  → quy ra {(trai + phai) / config.ENCODER_PULSES_PER_CM:.1f}cm "
              f"(với {config.ENCODER_PULSES_PER_CM} xung/cm)")

    chet = [ten for ten, v in (("TRÁI", trai), ("PHẢI", phai))
            if v < XUNG_TOI_THIEU]
    print()
    if not chet:
        print("  ✅ CẢ HAI ENCODER SỐNG. Việc dừng theo quãng đường là tin được.")
        print("     Vậy nếu robot vẫn đâm kệ thì lỗi nằm chỗ khác — gửi log lại.")
        ket = 0
    elif len(chet) == 2:
        print("  ❌ CẢ HAI ENCODER CHẾT — 0 xung.")
        print("     MỌI chốt theo quãng đường đang vô hiệu, kể cả lưới an toàn")
        print("     ADVANCE_MAX_TRAVEL_CM. Robot sẽ đâm kệ, không có gì chặn.")
        print("     Kiểm: dây encoder (thường là dây mảnh nhất, dễ tuột nhất),")
        print(f"     nguồn 5V cho encoder, chân GPIO {config.ENCODER_LEFT_PIN}"
              f"/{config.ENCODER_RIGHT_PIN}.")
        ket = 1
    else:
        print(f"  ❌ ENCODER {chet[0]} CHẾT, bên kia sống.")
        print("     _doc_xung() cộng CẢ HAI bánh, nên quãng đường đo được chỉ còn")
        print("     một nửa → robot đi GẤP ĐÔI mốc rồi mới dừng. Vào kệ = đâm.")
        ket = 1
    print("=" * 70)
    return ket


if __name__ == "__main__":
    sys.exit(main())
