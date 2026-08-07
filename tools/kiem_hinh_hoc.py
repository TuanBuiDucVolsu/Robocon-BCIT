#!/usr/bin/env python3
"""KIỂM RÀNG BUỘC HÌNH HỌC GIỮA CÁC HẰNG SỐ — chạy dưới 1 giây.

    python3 -m tools.kiem_hinh_hoc

VÌ SAO CẦN — đây là câu trả lời cho "sao lỗi cứ lặp đi lặp lại":

Các hằng số hình học RÀNG BUỘC LẪN NHAU, nhưng không chỗ nào ghi ra ràng buộc đó.
Chỉnh một cái là âm thầm phá một cái khác, và triệu chứng nổi lên ở CHẶNG HOÀN TOÀN
KHÁC — nên người sửa đi tìm nhầm chỗ, vá nhầm chỗ, rồi lỗi quay lại.

Đã xảy ra thật, chỉ trong hai ngày:

  06/08  ADVANCE_SHELF_STOP_CM 17 → 32 làm BACK_MIN_TRAVEL_CM (đặt cho mốc 17) trở
         nên quá rộng → mảng đen chân kệ bị đếm thành giao lộ → cả tuyến lệch MỘT
         HÀNG → robot xoay sớm và thả hàng ở vòng tròn logo.
  04/08  ESCAPE_MAX_CM đặt 8.0, trong khi chính thuật toán cần
         ESCAPE_MIN_CM(3) + ESCAPE_CLEAR_TIME(0.25s)×20cm/s = 8.0 → MỌI cú thoát
         giao lộ đều chạm trần và trả về thất bại, suốt hai ngày.

Không bài test mô phỏng nào bắt được hai lỗi trên — chúng không phải lỗi logic mà
là MÂU THUẪN SỐ HỌC. Công cụ này chỉ làm mấy phép so sánh, không dựng phần cứng giả.

CHẠY NÓ TRƯỚC VÀ SAU MỖI LẦN SỬA HẰNG SỐ.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

# --- Số ĐO TRÊN ROBOT, không phải giả định ---------------------------------
GIAO_LO_TOI_KE_CM = 35.4     # docs/SA_BAN.md 3b — đo trên bản in, giống cả 3 kệ
KHOANG_HAI_GIAO_LO_CM = 40.0  # hai hàng giao lộ
BE_RONG_VACH_CM = 2.0        # vạch line 20mm
MANG_DEN_CHAN_KE_CM = 5.0    # mảng đen đầu chặng lùi, đo 04/08 (tín hiệu giả ở 0.9-4.6cm)
# ⚠️ CÔNG THỨC CŨ SAI: nó lấy "mốc dừng − 18.6" làm khoảng cách tới giao lộ khi
# chặng LÙI bắt đầu, tức QUÊN MẤT bước LUỒN CÀNG nằm giữa. Robot không lùi từ mốc
# dừng mà từ (mốc dừng + quãng đã luồn vào), rồi lùi ra đúng quãng đó × 1.15. Nên
# phần thực sự bị mất chỉ là 0.15 × quãng luồn:
#     giao lộ cách = mốc dừng + luồn − 1.15×luồn = mốc dừng − 0.15×luồn
# Đo 06/08: luồn vào 525 và 578 xung = 14.6 và 16.1cm.
LUON_CANG_CM = 16.1          # đo 06/08: 578 xung
DOI_LUI_RA = 1.15            # retreat_from_shelf lùi quãng đã luồn × 1.15
# CÀNG NHÔ RA TRƯỚC THANH CẢM BIẾN — biết bằng hai lần chạy thật, không đo thước:
#     mốc 32.0 → hở  3.4cm → CÀNG LUỒN VÀO GẦM KỆ (07/08)
#     mốc 29.0 → hở  6.4cm → VẪN ĐÂM (07/08, lần hai)
#     mốc 24.0 → hở 11.4cm → không đâm
# Nên độ nhô của càng nằm giữa 6.4 và 11.4cm. Lấy 12.4 làm khoảng hở tối thiểu —
# dưới mức đã chứng minh an toàn.
# ⚠️ Con số này chỉ cần thiết vì lúc tiến vào CÀNG ĐANG Ở SÀN (bước nâng lên tầng
# chạy SAU advance). Nâng càng TRƯỚC khi tiến thì càng đi vào khe pallet chứ không
# vào gầm kệ, và mốc dừng có thể tiến sát hơn nhiều.
KHOANG_HO_TOI_THIEU_CM = 12.4
TOC_DO_CM_S = 20.0           # đo 06/08: escape 8.0cm trong ~0.40s


def _kiem(ten, dat, mo_ta, goi_y=""):
    return (ten, bool(dat), mo_ta, goi_y)


def cac_rang_buoc():
    c = config
    r = []

    # 1. Trần thoát giao lộ phải đủ cho chính thuật toán của nó
    can = c.ESCAPE_MIN_CM + c.ESCAPE_CLEAR_TIME * TOC_DO_CM_S
    r.append(_kiem(
        "ESCAPE_MAX_CM đủ cho sàn + khoảng xác nhận",
        c.ESCAPE_MAX_CM > can,
        f"trần {c.ESCAPE_MAX_CM} phải > {can:.1f} "
        f"(= sàn {c.ESCAPE_MIN_CM} + {c.ESCAPE_CLEAR_TIME}s × {TOC_DO_CM_S}cm/s)",
        "Không thì MỌI cú thoát giao lộ chạm trần và trả về thất bại."))

    # 2. Cổng đếm giao lộ không được bác giao lộ THẬT
    con_lai = KHOANG_HAI_GIAO_LO_CM - c.ESCAPE_MAX_CM
    r.append(_kiem(
        "FORWARD_MIN_TRAVEL_CM không bác giao lộ thật",
        c.FORWARD_MIN_TRAVEL_CM < con_lai,
        f"cổng {c.FORWARD_MIN_TRAVEL_CM} phải < {con_lai:.1f} "
        f"(= {KHOANG_HAI_GIAO_LO_CM} − trần escape {c.ESCAPE_MAX_CM})",
        "Bộ đếm quãng bắt đầu SAU escape, nên escape ăn vào phần này."))

    # 3. ...nhưng vẫn phải bác được mảng đen của chính giao lộ vừa rời
    r.append(_kiem(
        "FORWARD_MIN_TRAVEL_CM bác được vạch vừa rời",
        c.FORWARD_MIN_TRAVEL_CM > BE_RONG_VACH_CM,
        f"cổng {c.FORWARD_MIN_TRAVEL_CM} phải > bề rộng vạch {BE_RONG_VACH_CM}"))

    # 4. Cổng LÙI ở kệ — gắn chặt với mốc dừng
    giao_lo_o = c.ADVANCE_SHELF_STOP_CM - (DOI_LUI_RA - 1.0) * LUON_CANG_CM
    r.append(_kiem(
        "BACK_MIN_TRAVEL_CM không bác giao lộ thật (chặng lùi khỏi KỆ)",
        c.BACK_MIN_TRAVEL_CM < giao_lo_o,
        f"cổng {c.BACK_MIN_TRAVEL_CM} phải < {giao_lo_o:.1f} "
        f"(= mốc dừng {c.ADVANCE_SHELF_STOP_CM} − 0.15 × luồn càng {LUON_CANG_CM})",
        "⚠️ ĐỔI ADVANCE_SHELF_STOP_CM LÀ PHẢI TÍNH LẠI CỔNG NÀY."))

    r.append(_kiem(
        "BACK_MIN_TRAVEL_CM bác được mảng đen chân kệ",
        c.BACK_MIN_TRAVEL_CM > MANG_DEN_CHAN_KE_CM,
        f"cổng {c.BACK_MIN_TRAVEL_CM} phải > mảng đen chân kệ {MANG_DEN_CHAN_KE_CM}",
        "Không thì mảng đen bị đếm thành giao lộ → cả tuyến lệch MỘT HÀNG."))

    # 5. Mốc dừng ở kệ: đủ để bánh qua giao lộ, mà chưa chạm kệ
    r.append(_kiem(
        "ADVANCE_SHELF_STOP_CM đưa được TRỤC BÁNH qua giao lộ",
        c.ADVANCE_SHELF_STOP_CM > c.RECENTER_CM,
        f"mốc {c.ADVANCE_SHELF_STOP_CM} phải > {c.RECENTER_CM} "
        f"(độ lệch thanh cảm biến → trục bánh)",
        "12cm đầu chỉ để kéo trục bánh lên tới giao lộ, chưa đi được cm nào."))

    tran_an_toan = GIAO_LO_TOI_KE_CM - KHOANG_HO_TOI_THIEU_CM
    r.append(_kiem(
        "ADVANCE_SHELF_STOP_CM chừa đủ chỗ cho ĐỘ NHÔ CỦA CÀNG",
        c.ADVANCE_SHELF_STOP_CM <= tran_an_toan,
        f"mốc {c.ADVANCE_SHELF_STOP_CM} phải ≤ {tran_an_toan:.1f} "
        f"(= {GIAO_LO_TOI_KE_CM} − khoảng hở {KHOANG_HO_TOI_THIEU_CM})",
        "Càng NHÔ RA TRƯỚC thanh cảm biến nên nó chạm kệ trước. Mốc 32.0 (hở 3.4cm) "
        "đã làm càng luồn vào GẦM KỆ ngày 07/08; 29.0 (hở 6.4cm) thì không."))

    # 6. Hạ càng về sàn phải phủ được ca xấu nhất
    can_ha = c.LIFT_TIME_SHELF_2 + max(c.LIFT_LEFT_LOWER_EXTRA,
                                       c.LIFT_RIGHT_LOWER_EXTRA)
    r.append(_kiem(
        "LIFT_HOME_DURATION hạ được càng chậm nhất về sàn",
        c.LIFT_HOME_DURATION >= can_ha,
        f"{c.LIFT_HOME_DURATION} phải ≥ {can_ha:.2f} "
        f"(= tầng 2 {c.LIFT_TIME_SHELF_2} + bù hạ lớn nhất)",
        "Thiếu = càng KHÔNG chạm sàn, không limit switch nào báo, mọi tầng sau lệch."))

    # 7. Mọi tốc độ dùng với follow_line phải cách vùng chết
    ten_toc = ("SPEED_DEFAULT", "ADVANCE_SPEED", "APPROACH_SLOW_SPEED",
               "APPROACH_FAST_SPEED", "INSERT_SPEED", "REVERSE_SPEED")
    for t in ten_toc:
        v = getattr(c, t, None)
        if v is None:
            continue
        r.append(_kiem(
            f"{t} còn dư lực lái",
            v - c.MOTOR_MIN_DUTY >= 8,
            f"{t}={v} phải cách MOTOR_MIN_DUTY={c.MOTOR_MIN_DUTY} ít nhất 8",
            "Sát vùng chết = bánh trong đứng hẳn, robot xoay quanh nó thay vì lượn."))

    return r


def main() -> int:
    print("=" * 74)
    print("  KIỂM RÀNG BUỘC HÌNH HỌC GIỮA CÁC HẰNG SỐ")
    print("=" * 74)
    print("  Số nền (ĐO trên robot/bản in, không phải giả định):")
    print(f"    giao lộ → chân kệ      {GIAO_LO_TOI_KE_CM}cm")
    print(f"    hai hàng giao lộ       {KHOANG_HAI_GIAO_LO_CM}cm")
    print(f"    luồn càng vào pallet   {LUON_CANG_CM}cm (lùi ra = ×{DOI_LUI_RA})")
    print(f"    tốc độ bám line        {TOC_DO_CM_S}cm/s")
    print()

    hong = []
    for ten, dat, mo_ta, goi_y in cac_rang_buoc():
        print(f"  {'✅' if dat else '❌'}  {ten}")
        print(f"       {mo_ta}")
        if not dat:
            hong.append((ten, goi_y))
            if goi_y:
                print(f"       → {goi_y}")
    print()
    print("=" * 74)
    if not hong:
        print("  ✅ KHÔNG CÓ MÂU THUẪN. Các hằng số hình học đang nhất quán.")
        print("=" * 74)
        return 0
    print(f"  ❌ {len(hong)} MÂU THUẪN — sửa TRƯỚC khi chạy robot:")
    for ten, goi_y in hong:
        print(f"     • {ten}")
    print()
    print("  Đây là mâu thuẫn SỐ HỌC, không phải lỗi logic. Không bài test mô phỏng")
    print("  nào bắt được, và triệu chứng sẽ nổi lên ở một chặng KHÁC HẲN chỗ sai.")
    print("=" * 74)
    return 1


if __name__ == "__main__":
    sys.exit(main())
