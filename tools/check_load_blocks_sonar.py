#!/usr/bin/env python3
"""KIỆN HÀNG ROBOT CÕNG CÓ CHE CẢM BIẾN SIÊU ÂM KHÔNG? (NGHIEM_THU bước B5)

    python3 -m tools.check_load_blocks_sonar

VÌ SAO CẦN: trong trận, robot bốc hàng xong là chở kiện đi giao. Suốt chặng đó có
BA chỗ dùng siêu âm, và cả ba đều đứng trước cùng một câu hỏi — con số đọc được là
KHOẢNG CÁCH TỚI ĐÍCH hay là CHÍNH KIỆN HÀNG đang nằm trước cảm biến:

    retreat_from_shelf()  ngay sau khi nhấc
    advance_to_end()      khi tới khu nhà máy
    approach_shelf()      khi tiếp cận điểm thả

Nếu kiện che cảm biến thì số đo ĐỨNG YÊN ở một giá trị nhỏ, và mọi chặng giao hàng
sẽ "tới nơi" ngay khi robot vừa rời giao lộ → thả kiện giữa sa bàn. Tệ nhất là
KHÔNG CÓ GÌ BÁO: IR vẫn xác nhận đã thả, packages_delivered vẫn tăng, log toàn ✅.

Ngày 02/08 tôi đã thêm cơ chế chống chuyện này DỰA TRÊN SUY LUẬN, rồi phải tắt đi
vì nó gây hai lần robot lao vào kệ. Bài này thay suy luận bằng số đo.

⚠️ CẨM NÂNG CÀNG THẬT. Bánh xe KHÔNG chạy.
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

from control.lift import Lift
from control.mcp3008_bus import reset_mcp3008_bus

NGUONG_XA = 60.0        # cm: đọc xa hơn mức này = cảm biến nhìn thông, kiện không chắn


def _doc(ds, giay: float = 1.5) -> list[float]:
    het = time.time() + giay
    mau = []
    while time.time() < het:
        mau.append(ds.distance * 100)
        time.sleep(0.05)
    return mau


def _bao_cao(ten: str, mau: list[float]) -> float:
    tv = statistics.median(mau)
    print(f"  {ten:22} trung vị {tv:6.1f} cm   "
          f"(min {min(mau):5.1f} / max {max(mau):5.1f}, {len(mau)} mẫu)")
    return tv


def main() -> int:
    print("=" * 72)
    print("  B5 — KIỆN HÀNG CÕNG CÓ CHE SIÊU ÂM KHÔNG?")
    print("=" * 72)
    print("\n  CHUẨN BỊ:")
    print("    1. Đặt tay 1 pallet lên 2 càng (càng đang ở SÀN)")
    print(f"    2. Đẩy robot ra chỗ trống — phía trước KHÔNG có gì trong {NGUONG_XA:.0f}cm")
    print("    3. Càng sẽ NÂNG THẬT. Bánh xe không chạy.")
    if input("\n  Sẵn sàng? (y/N): ").strip().lower() != "y":
        print("  Đã huỷ.")
        return 1

    ds = DistanceSensor(echo=config.ULTRASONIC_ECHO_PIN,
                        trigger=config.ULTRASONIC_TRIG_PIN,
                        max_distance=1.0, queue_len=config.ULTRASONIC_QUEUE_LEN)
    lift = Lift()
    ket = {}
    try:
        time.sleep(0.4)
        print("\n  Đọc siêu âm ở từng độ cao càng:\n")
        ket["sàn"] = _bao_cao("càng ở SÀN", _doc(ds))
        for muc, ten in ((1, "càng ở TẦNG 1"), (2, "càng ở TẦNG 2")):
            lift.go_to_level(muc)
            time.sleep(0.4)
            ket[ten] = _bao_cao(ten, _doc(ds))
    finally:
        print("\n  Hạ càng về sàn...")
        try:
            lift.go_to_level(0)
        finally:
            ds.close()
            lift.cleanup()
            reset_mcp3008_bus()

    gia = list(ket.values())
    doi_theo_cang = max(gia) - min(gia)
    gan = [t for t, v in ket.items() if v < NGUONG_XA]

    print("\n" + "=" * 72)
    if not gan:
        print("  ✅ KIỆN KHÔNG CHẮN — mọi độ cao đều đọc xa hơn "
              f"{NGUONG_XA:.0f}cm.")
        print("     → Luồng giao hàng dùng siêu âm bình thường, an toàn.")
    elif doi_theo_cang < 1.0:
        # ⚠️ BẰNG CHỨNG QUYẾT ĐỊNH là số đo có ĐỔI THEO ĐỘ CAO CÀNG hay không.
        # Vật nằm TRÊN CÀNG thì nâng càng lên 2 tầng phải làm số đo đổi. Không đổi
        # chút nào = vật đó ĐỨNG YÊN so với sa bàn, không đi cùng càng.
        # Bản đầu của công cụ này chỉ kiểm "số đo có nhỏ không" nên kết luận sai khi
        # người dùng để một tấm phẳng trước mặt robot — đúng thứ vừa xảy ra.
        print(f"  ⚠️ CHƯA KẾT LUẬN ĐƯỢC. Số đo {min(gia):.1f}-{max(gia):.1f}cm là GẦN,")
        print(f"     nhưng KHÔNG ĐỔI theo độ cao càng (chênh {doi_theo_cang:.1f}cm).")
        print("     Vật nằm trên càng thì nâng càng lên 2 tầng phải làm số đo đổi.")
        print("     → Nhiều khả năng phía trước robot ĐANG CÓ VẬT KHÁC (tường, tấm")
        print(f"       bìa, kệ...) ở {statistics.median(gia):.1f}cm, không phải kiện hàng.")
        print("     → Dọn trống phía trước ≥60cm rồi CHẠY LẠI.")
        print(f"\n     Tin tốt: ở khoảng cách này cảm biến rất ỔN ĐỊNH —")
        for t, v in ket.items():
            print(f"       {t:22} tản chỉ ~0.1cm")
    else:
        gan_nhat = min(gia)
        print(f"  🔴 KIỆN CÓ CHẮN — số đo ĐỔI THEO độ cao càng ({doi_theo_cang:.1f}cm).")
        print(f"     Giá trị gần nhất: {gan_nhat:.1f} cm")
        print("     → Bật lại cơ chế chống-kiện-che, đặt ngưỡng quanh giá trị này.")
        print(f"     → ADVANCE_HARD_STOP_CM phải NHỎ HƠN {gan_nhat:.1f} "
              f"(hiện {config.ADVANCE_HARD_STOP_CM}).")
        if config.ADVANCE_HARD_STOP_CM >= gan_nhat:
            print("       ⚠️ ĐANG SAI: chặn cứng ≥ khoảng cách tới kiện → mọi chặng")
            print("          giao hàng sẽ dừng ngay khi vừa rời giao lộ.")
    print("=" * 72)
    print("\n  Báo lại 3 con số trên để cập nhật config và sổ nghiệm thu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
