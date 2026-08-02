#!/usr/bin/env python3
"""ĐO ĐỘ ỔN ĐỊNH của cảm biến siêu âm — để SO hai cảm biến bằng số.

    python3 -m tools.check_sonar_jitter            # đo 10 giây
    python3 -m tools.check_sonar_jitter 20         # đo 20 giây

CÁCH DÙNG ĐỂ SO SÁNH: đặt robot ĐỨNG YÊN, mặt phẳng (tường/tấm bìa) trước mặt ở
khoảng 12-15cm — đúng khoảng cách robot dừng trước kệ. Chạy với cảm biến CŨ, ghi số.
Thay cảm biến MỚI, đặt lại ĐÚNG khoảng cách đó, chạy lại. So hai bảng.

Robot phải ĐỨNG YÊN: mọi dao động đọc được khi đứng yên đều là NHIỄU, không phải
chuyển động. Đó là thứ cần so.

VÌ SAO CẦN: đo trên robot 02/08, cùng một quãng tiếp cận cho độ trôi khi dừng tản
từ 0.7 đến 3.5cm giữa các lượt, và có lượt robot lao thẳng vào kệ. Nhưng "chạy không
ổn định" là cảm giác — không so được cảm biến nào tốt hơn, cũng không biết thay xong
có khá hơn thật không hay chỉ là may.

⚠️ KHÔNG chạm motor. Robot đứng yên suốt.
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

try:
    from gpiozero import DistanceSensor
except Exception as e:  # pragma: no cover - chỉ chạy trên Pi
    print(f"❌ Không dùng được gpiozero ({e}) — chạy lệnh này TRÊN Pi.")
    sys.exit(1)


def main() -> int:
    giay = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0

    print("=" * 72)
    print("  ĐỘ ỔN ĐỊNH CẢM BIẾN SIÊU ÂM")
    print("=" * 72)
    print(f"\n  Đặt robot ĐỨNG YÊN, mặt phẳng trước mặt ~12-15cm "
          f"(bằng khoảng cách dừng trước kệ).")
    print(f"  Đo {giay:.0f} giây. Robot KHÔNG di chuyển — mọi dao động đọc được")
    print(f"  đều là NHIỄU của cảm biến.")
    print(f"\n  ULTRASONIC_QUEUE_LEN = {config.ULTRASONIC_QUEUE_LEN} "
          f"(gpiozero đã lấy trung vị sẵn trên ngần này mẫu)")
    if input("\n  Sẵn sàng? (y/N): ").strip().lower() != "y":
        return 1

    ds = DistanceSensor(echo=config.ULTRASONIC_ECHO_PIN,
                        trigger=config.ULTRASONIC_TRIG_PIN,
                        max_distance=1.0, queue_len=config.ULTRASONIC_QUEUE_LEN)
    try:
        time.sleep(0.4)
        mau, het = [], time.time() + giay
        while time.time() < het:
            mau.append(ds.distance * 100)
            time.sleep(0.03)
    finally:
        ds.close()

    if len(mau) < 10:
        print("  ❌ Quá ít mẫu.")
        return 1

    tv = statistics.median(mau)
    lech = statistics.pstdev(mau)
    ngoai = [v for v in mau if abs(v - tv) > 2.0]
    kich_tran = [v for v in mau if v >= 99.0]

    print("\n" + "=" * 72)
    print(f"  Số mẫu          : {len(mau)}")
    print(f"  Trung vị        : {tv:6.1f} cm      ← khoảng cách thật")
    print(f"  Min / Max       : {min(mau):6.1f} / {max(mau):.1f} cm")
    print(f"  Độ lệch chuẩn   : {lech:6.2f} cm      ← ĐÂY LÀ SỐ ĐỂ SO 2 CẢM BIẾN")
    print(f"  Lệch > 2cm      : {len(ngoai):4d} mẫu ({len(ngoai)/len(mau)*100:.1f}%)")
    print(f"  Kịch trần 100cm : {len(kich_tran):4d} mẫu ({len(kich_tran)/len(mau)*100:.1f}%)"
          f"   ← mất tiếng vọng")

    print("\n  ĐÁNH GIÁ:")
    if lech <= 0.3 and not kich_tran:
        print("    ✅ RẤT ỔN. Dừng trước kệ sẽ lặp lại được.")
    elif lech <= 0.8:
        print("    ⚠ TẠM ĐƯỢC. Vẫn nên bù bằng APPROACH_STOP_MARGIN như hiện nay.")
    else:
        print("    ❌ QUÁ NHIỄU. Độ lệch này lớn hơn cả sai số cho phép khi dừng")
        print("       trước kệ — không hằng số nào bù được cho một cảm biến nhảy.")
    if kich_tran:
        print(f"    ❌ CÓ MẤT TIẾNG VỌNG ({len(kich_tran)} mẫu kịch trần). Kiểm góc đặt")
        print("       cảm biến, mặt phản xạ có vuông góc không, và dây ECHO.")
    print("\n  So với cảm biến kia: chạy lại lệnh này ở ĐÚNG khoảng cách, so ĐỘ LỆCH CHUẨN.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
