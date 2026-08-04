#!/usr/bin/env python3
"""CHỤP LẠI ĐÚNG THỨ CAMERA NHÌN THẤY Ở KỆ — rồi mở ảnh ra xem.

    python3 -m tools.chup_o_ke          # tầng 1
    python3 -m tools.chup_o_ke 2        # tầng 2

VÌ SAO CẦN: test vision cầm tay thì đúng, chạy thật thì sai. Khác nhau ở TƯ THẾ,
không ở thuật toán — nên tranh luận về ngưỡng HSV mà không nhìn khung hình thật
là đoán mò.

Bằng chứng mạnh nhất đã có trong log 04/08: CẢ HAI càng cùng ra `amkor` (50.6% và
58.3%). Luật sa bàn là mỗi cặp LUÔN là hai nhà máy khác nhau, nên hai kết quả
giống hệt nhau tự nó chứng minh camera KHÔNG nhìn vào hai nhãn riêng — nhiều khả
năng hai ROI cùng rơi vào một chỗ, hoặc rơi vào nền.

Và điểm dừng trước kệ VỪA ĐỔI hôm nay (ADVANCE_SHELF_STOP_CM 15.0 → 12.0, bỏ
bước thoát giao lộ ở chặng đầu). Khung hình đổi theo, nên ROI_Y_CENTER calibrate
từ trước có thể đã lệch tầng.

CÁCH DÙNG: cho robot chạy tới kệ như thi đấu (hoặc đẩy tay tới đúng chỗ nó dừng),
rồi chạy lệnh này. Ảnh lưu vào thư mục anh_ke/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from vision.vision import Vision

THU_MUC = Path(__file__).resolve().parent.parent / "anh_ke"


def main() -> int:
    tang = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    try:
        import cv2
    except ImportError:
        print("Cần opencv (cv2) để ghi ảnh.")
        return 1

    print("=" * 70)
    print(f"  CHỤP KHUNG HÌNH CAMERA Ở KỆ — TẦNG {tang}")
    print("=" * 70)
    print("  Robot phải ĐANG ĐỨNG đúng chỗ nó dừng khi bốc hàng.")
    if input("\n  Enter để chụp (q thoát): ").strip().lower() == "q":
        return 1

    v = Vision()
    try:
        frame = v._capture_frame()
        if frame is None:
            print("\n  ❌ Không chụp được — camera chưa sẵn sàng.")
            return 1

        THU_MUC.mkdir(exist_ok=True)
        trai, phai = v.pair_rois(frame, level=tang)
        cv2.imwrite(str(THU_MUC / f"tang{tang}_toan_khung.png"), frame)
        cv2.imwrite(str(THU_MUC / f"tang{tang}_roi_trai.png"), trai)
        cv2.imwrite(str(THU_MUC / f"tang{tang}_roi_phai.png"), phai)

        print(f"\n  Khung đầy đủ : {frame.shape[1]}x{frame.shape[0]}")
        print(f"  ROI trái     : {trai.shape[1]}x{trai.shape[0]}")
        print(f"  ROI phải     : {phai.shape[1]}x{phai.shape[0]}")
        print(f"\n  Đã lưu 3 ảnh vào {THU_MUC}/")

        # Chấm luôn để so ảnh với kết quả — cùng một khung hình, không chụp lại.
        print("\n  --- Kết quả nhận diện trên CHÍNH khung vừa lưu ---")
        for ten, roi in (("trái", trai), ("phải", phai)):
            nhan, tin = v._classify_by_color(roi, level=None)
            print(f"    {ten:5s}: {nhan}  ({tin * 100:.1f}%)")

        print("\n  MỞ ẢNH RA XEM. Ba câu hỏi, theo thứ tự:")
        print("    1. ROI trái và ROI phải có nhìn vào HAI kiện KHÁC NHAU không?")
        print("       Cùng một kiện = lỗi cắt khung, không phải lỗi ngưỡng màu.")
        print(f"    2. ROI có ĐÚNG TẦNG {tang} không, hay đang cắt vào tầng khác /")
        print("       vào khung kệ? Chỉnh config.ROI_Y_CENTER.")
        print("    3. Nhãn có nằm GỌN trong ROI không, hay bị nền lấn phần lớn?")
        print(f"       (ROI_Y_CENTER={getattr(config, 'ROI_Y_CENTER', None)}, "
              f"ROI_HEIGHT={getattr(config, 'ROI_HEIGHT', None)}, "
              f"ROI_MARGIN_X={getattr(config, 'ROI_MARGIN_X', None)})")
    finally:
        v.cleanup()
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
