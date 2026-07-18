"""
Công cụ chụp ảnh mẫu THẬT cho nhận diện bằng so khớp đặc trưng ORB
(vision/shape_match.py) — thay thế cách nhận diện bằng màu HSV thuần, bền hơn
nhiều với nền lạ (tường, dây điện, bàn ghế...) vì so theo HÌNH DẠNG/HOẠ TIẾT
decal thay vì chỉ màu sắc.

Dùng ảnh chụp THẬT bằng camera của robot — KHÔNG dùng ảnh trong PDF thể lệ
(docs/Hinh_kien_hang.pdf là đồ hoạ vector sạch, khác nhiều so với ảnh chụp thật
dưới ánh sáng/độ phân giải/nhiễu của camera, so khớp sẽ kém chính xác hơn nếu
dùng ảnh đó làm mẫu).

Lưu ảnh mẫu: vision/templates/{label}.png (grayscale).

Chạy trên Pi (đã cắm camera CSI):
    python3 -m tools.capture_templates

Không có camera/OpenCV → in hướng dẫn rồi thoát.
"""

import os
import time

try:
    import cv2
except ImportError:
    cv2 = None

import config
from vision import Vision
from vision.shape_match import ORB_FEATURES, MIN_MATCHES_FOR_HOMOGRAPHY, TEMPLATE_DIR


def _prompt(msg: str):
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def main():
    if cv2 is None:
        print("❌ OpenCV không khả dụng — chạy lệnh này TRÊN Pi (đã cài theo requirements.txt).")
        return

    vision = Vision()
    if vision._camera is None:
        print("❌ Camera không khả dụng (đang chạy trên PC hoặc picamera2 lỗi?).")
        print("   Chạy lệnh này TRÊN Pi sau khi đã gắn camera CSI.")
        return

    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)

    print("=== CHỤP ẢNH MẪU CHO NHẬN DIỆN ORB ===\n")
    print("Với mỗi kiện: đặt MỘT MÌNH kiện hàng đó vào giữa khung hình, lấp đầy phần")
    print("lớn khung càng tốt (rõ nét, đủ sáng, không rung/mờ, càng ít nền lẫn vào")
    print("càng tốt) — ảnh mẫu càng rõ, so khớp lúc quét thật càng chính xác.")
    print("Nhấn Enter khi đã đặt xong và giữ yên.\n")

    for label in config.LABEL_TO_FACTORY:
        factory = config.LABEL_TO_FACTORY[label]
        _prompt(f"  → Đặt kiện '{label}' ({factory}) vào khung hình, nhấn Enter để chụp...")
        time.sleep(0.3)  # 1 nhịp để tay/máy ổn định sau khi buông phím

        frame = vision._capture_frame()
        if frame is None:
            print("    ❌ Không chụp được ảnh, thử lại từ đầu cho kiện này.")
            continue

        roi = vision._crop_roi(frame)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        kp, des = orb.detectAndCompute(gray, None)
        n_kp = len(kp) if kp else 0

        path = os.path.join(TEMPLATE_DIR, f"{label}.png")
        cv2.imwrite(path, gray)
        print(f"    Đã lưu: {path} ({gray.shape[1]}x{gray.shape[0]}, {n_kp} keypoint)")
        if n_kp < MIN_MATCHES_FOR_HOMOGRAPHY:
            print(f"    ⚠️ Quá ít keypoint (<{MIN_MATCHES_FOR_HOMOGRAPHY}) — decal có thể bị mờ/thiếu")
            print("       sáng/quá xa camera. Nên chụp lại: chạy tool lần nữa, chỉ kiện này")
            print("       cũng được (ghi đè đúng file), lại gần và đủ sáng hơn.")
        print()

    vision.cleanup()
    print("Xong. Kiểm tra lại bằng tests/test_vision.py (test nhận diện — ORB giờ là")
    print("phương pháp chính, HSV màu chỉ dự phòng khi ORB không đủ tự tin).")


if __name__ == "__main__":
    main()
