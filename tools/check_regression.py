#!/usr/bin/env python3
"""Bài test nào ĐÃ ĐẠT TRÊN ROBOT đang bị config hiện tại làm mất hiệu lực?

    python3 -m tools.check_regression          # bảng đầy đủ
    python3 -m tools.check_regression --ngan   # chỉ in phần đã hỏng

VÌ SAO CÓ FILE NÀY: sửa một hằng số thì rất dễ vô hiệu hoá âm thầm một bài test đã
chạy được, vì không chỗ nào ghi lại "bài X dựa vào hằng số nào". Đã xảy ra thật
nhiều lần trong một buổi:

  - nâng REVERSE_SPEED 35 → 40 làm REVERSE_RECENTER_TIME (đo ở 35%) tiến bù QUÁ vạch
    → xoay xong mất line, trong khi option 15 trước đó đã ĐẠT
  - nâng MOTOR_MIN_DUTY 25 → 30 mà quên rà APPROACH_SLOW_SPEED → mất lực lái
  - đổi CONFIDENCE_THRESHOLD làm một test đơn vị tự gãy tiền đề

Không thay thế được việc chạy lại trên robot. Nó chỉ trả lời đúng một câu: **phải
chạy lại bài nào**.

Sổ nghiệm thu: tests/da_nghiem_thu.json — chỉ thêm mục SAU KHI đã ĐẠT 3/3 trên robot.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

SO = Path(__file__).resolve().parent.parent / "tests" / "da_nghiem_thu.json"


def _bang(v) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (list, tuple)) else str(v)


def _khac(cu, moi) -> bool:
    if isinstance(cu, (list, tuple)) or isinstance(moi, (list, tuple)):
        return list(cu) != list(moi)
    if isinstance(cu, (int, float)) and isinstance(moi, (int, float)):
        return abs(float(cu) - float(moi)) > 1e-9
    return cu != moi


def kiem() -> list[dict]:
    """Trả danh sách mục kèm các hằng số đã đổi kể từ lúc mục đó ĐẠT."""
    du_lieu = json.loads(SO.read_text(encoding="utf-8"))
    ket = []
    for muc in du_lieu["muc"]:
        doi = []
        for ten, cu in muc["gia_tri"].items():
            if not hasattr(config, ten):
                doi.append((ten, _bang(cu), "KHÔNG CÒN TRONG CONFIG"))
                continue
            moi = getattr(config, ten)
            if _khac(cu, moi):
                doi.append((ten, _bang(cu), _bang(moi)))
        ket.append({**muc, "doi": doi})
    return ket


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ngan", action="store_true", help="chỉ in mục đã mất hiệu lực")
    args = p.parse_args()

    ket = kiem()
    hong = [m for m in ket if m["doi"]]

    print("=" * 78)
    print("  ĐỐI CHIẾU SỔ NGHIỆM THU VỚI CONFIG HIỆN TẠI")
    print("=" * 78)

    for muc in ket:
        if args.ngan and not muc["doi"]:
            continue
        dau = "❌ PHẢI CHẠY LẠI" if muc["doi"] else "✅ còn hiệu lực"
        print(f"\n{dau}  {muc['ten']}")
        print(f"   đạt ngày {muc['ngay']} — {muc['ket_qua']}")
        if muc.get("ghi_chu"):
            print(f"   ghi chú: {muc['ghi_chu']}")
        for ten, cu, moi in muc["doi"]:
            print(f"     • {ten}: lúc đạt {cu}  →  hiện tại {moi}")

    print("\n" + "=" * 78)
    if hong:
        print(f"  {len(hong)}/{len(ket)} bài ĐÃ MẤT HIỆU LỰC — hằng số chúng dựa vào đã đổi.")
        print("  Chạy lại trên robot rồi cập nhật tests/da_nghiem_thu.json (giá trị + ngày).")
        print("  ⚠️ ĐỪNG sửa file đó cho khớp config — như vậy là xoá mất bằng chứng.")
    else:
        print(f"  Cả {len(ket)} bài đều còn hiệu lực với config hiện tại.")
    print("=" * 78)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
