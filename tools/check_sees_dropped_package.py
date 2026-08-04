#!/usr/bin/env python3
"""SIÊU ÂM CÓ NHÌN THẤY KIỆN HÀNG ĐÃ THẢ DƯỚI SÀN KHÔNG?

    python3 -m tools.check_sees_dropped_package

VÌ SAO CẦN: mỗi nhà máy nhận 3 kiện, mà robot luôn thả từng kiện một. Kiện thứ 2 và
thứ 3 phải tránh những kiện đã nằm sẵn ở đó. Có hai cách xử lý, và câu trả lời của
phép đo này quyết định dùng cách nào:

    THẤY   → robot tự dừng trước kiện cũ. Không cần đếm, nhưng khoảng hở mặc định
             (~14cm) quá lớn, phải siết lại cho vừa khu 25cm.
    KHÔNG  → robot đâm thẳng vào kiện cũ. BẮT BUỘC phải đếm số kiện mỗi nhà máy và
             lùi điểm dừng theo.

Nghi ngờ trước khi đo: pallet chỉ cao 26mm, 4 khối mút xốp cao thêm 40mm — tổng
~66mm. Cảm biến có thể nằm CAO HƠN chùm sóng đi qua, và mút xốp thì hút âm rất kém
phản xạ. Nhưng đó là suy luận, không phải số đo.

CÁCH ĐO — A/B, không phải đọc một lần:
  đọc CÓ kiện, rồi bỏ kiện đi và đọc LẠI cùng chỗ đó.
Chênh lệch giữa hai lần mới là bằng chứng. Đọc một lần thì không phân biệt được
"thấy kiện" với "thấy thứ gì đó phía sau kiện".

⚠️ KHÔNG chạm motor, KHÔNG nâng càng. Robot đứng yên suốt.
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

CHENH_TOI_THIEU = 8.0     # cm: chênh giữa 2 lần đọc mới coi là "có thấy"


def _doc(ds, giay: float = 2.0) -> tuple[float, float]:
    het = time.time() + giay
    mau = []
    while time.time() < het:
        mau.append(ds.distance * 100)
        time.sleep(0.04)
    return statistics.median(mau), max(mau) - min(mau)


def main() -> int:
    print("=" * 72)
    print("  SIÊU ÂM CÓ THẤY KIỆN HÀNG ĐÃ THẢ DƯỚI SÀN KHÔNG?")
    print("=" * 72)
    print("\n  BƯỚC 1 — đặt như sau:")
    print("    • 1 kiện hàng ĐẦY ĐỦ (pallet + 4 khối) dưới sàn, trước mũi robot ~15cm")
    print("    • PHÍA SAU kiện đó KHÔNG có gì trong 60cm — cần khoảng trống để so")
    print("    • Càng ở SÀN, robot đứng yên")
    if input("\n  Đã đặt xong? (y/N): ").strip().lower() != "y":
        return 1

    ds = DistanceSensor(echo=config.ULTRASONIC_ECHO_PIN,
                        trigger=config.ULTRASONIC_TRIG_PIN,
                        max_distance=1.0, queue_len=config.ULTRASONIC_QUEUE_LEN)
    try:
        time.sleep(0.4)
        co, tan_co = _doc(ds)
        print(f"\n  CÓ kiện    : {co:6.1f} cm   (tản {tan_co:.1f})")

        print("\n  BƯỚC 2 — BỎ kiện hàng ra, KHÔNG động vào robot.")
        input("  Đã bỏ ra? Nhấn Enter: ")
        time.sleep(0.4)
        khong, tan_khong = _doc(ds)
        print(f"  KHÔNG kiện : {khong:6.1f} cm   (tản {tan_khong:.1f})")
    finally:
        ds.close()

    chenh = khong - co
    print("\n" + "=" * 72)
    print(f"  Chênh lệch: {chenh:+.1f} cm")
    if chenh >= CHENH_TOI_THIEU:
        print(f"\n  ✅ CÓ THẤY. Bỏ kiện đi thì số đo nhảy xa thêm {chenh:.1f}cm.")
        print("     Siêu âm nhìn kiện dưới sàn rất tốt — tốt hơn hẳn nhìn giá kệ.")
        print("")
        print("  ⚠️ NHƯNG VẪN PHẢI ĐẾM KIỆN. Phép đo này làm với càng Ở SÀN, KHÔNG")
        print("     mang gì. Lúc giao hàng robot ĐANG CÕNG KIỆN, và chính kiện đó")
        print("     chắn chùm sóng — đo 03/08: cõng hàng đọc 8-10cm suốt, thả xong")
        print("     cùng cảm biến đọc 100cm. Nên siêu âm 'thấy' được kiện cũ nhưng")
        print("     KHÔNG thấy vào đúng lúc cần.")
        print(f"     → Bật config.FACTORY_STACK_BACKOFF_CM (hiện "
              f"{config.FACTORY_STACK_BACKOFF_CM}) để robot lùi bớt theo số kiện")
        print("       đã có ở nhà máy đó.")
    else:
        print(f"\n  🔴 KHÔNG THẤY. Bỏ kiện đi mà số đo gần như không đổi "
              f"({chenh:+.1f}cm)")
        print("     → Chùm sóng đi QUA hoặc TRÊN kiện. Robot sẽ ĐÂM vào kiện đã thả.")
        print("     → BẮT BUỘC đếm số kiện đã giao ở TỪNG nhà máy và lùi điểm dừng")
        print("       theo, hoặc thả so le trái/phải bằng cách chọn càng theo số đó.")
        print("     → Siêu âm KHÔNG dùng được để tránh kiện — đừng trông vào nó.")
    print("=" * 72)
    print("\n  Báo lại 2 con số để chốt cách xử lý.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
