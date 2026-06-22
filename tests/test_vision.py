#!/usr/bin/env python3
"""
Test module vision.py — kiểm tra camera & nhận diện kiện hàng bằng màu HSV.
Chạy trên Raspberry Pi 4 với camera CSI kết nối.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from vision import Vision


def test_camera_capture(vision: Vision):
    print("\n[TEST] Chụp ảnh từ camera...")
    frame = vision._capture_frame()
    if frame is not None:
        print(f"  Frame shape: {frame.shape}")
        print("  Camera hoạt động OK!")
        try:
            import cv2
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imwrite("test_capture.jpg", bgr)
            print("  Đã lưu ảnh: test_capture.jpg")
        except Exception as e:
            print(f"  Không lưu được ảnh: {e}")
    else:
        print("  LỖI: Không chụp được ảnh!")


def test_color_analysis(vision: Vision):
    """Chụp ảnh và hiển thị tỷ lệ từng màu — dùng để tinh chỉnh ngưỡng HSV."""
    print("\n[TEST] Phân tích màu HSV...")
    frame = vision._capture_frame()
    if frame is None:
        print("  LỖI: Không chụp được ảnh!")
        return

    import cv2
    import numpy as np

    h, w = frame.shape[:2]
    margin_x = int(w * 0.2)
    margin_y = int(h * 0.2)
    roi = frame[margin_y:h - margin_y, margin_x:w - margin_x]

    bgr = cv2.cvtColor(roi, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    total = roi.shape[0] * roi.shape[1]

    print(f"  ROI size: {roi.shape[1]}x{roi.shape[0]} ({total} pixels)")
    print(f"  Dải màu cấu hình:")

    for label, ranges in config.COLOR_RANGES.items():
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in ranges:
            lower_np = np.array(lower, dtype=np.uint8)
            upper_np = np.array(upper, dtype=np.uint8)
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower_np, upper_np))
        count = int(cv2.countNonZero(mask))
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        factory = config.LABEL_TO_FACTORY.get(label, "?")
        print(f"    {label:12s} ({factory:18s}): {pct:5.1f}% {bar}")

    # Lưu ảnh ROI để kiểm tra
    cv2.imwrite("test_roi.jpg", bgr)
    print("\n  Đã lưu ảnh ROI: test_roi.jpg")


def test_classify_single(vision: Vision):
    print("\n[TEST] Nhận diện 1 kiện hàng...")
    label, confidence = vision.classify_package()
    if label:
        factory = vision.get_factory_name(label)
        print(f"  Kết quả: {label} ({confidence*100:.1f}%)")
        print(f"  Nhà máy: {factory}")
    else:
        print("  LỖI: Không nhận diện được!")


def test_classify_multiple(vision: Vision):
    print("\n[TEST] Nhận diện liên tục 5 lần (cách 2 giây)...")
    for i in range(5):
        print(f"\n  --- Lần {i+1} ---")
        label, confidence = vision.classify_package()
        if label:
            factory = vision.get_factory_name(label)
            print(f"  Label: {label} ({confidence*100:.1f}%) -> {factory}")
        else:
            print("  Không nhận diện được")
        time.sleep(2)


def test_stability(vision: Vision):
    print(f"\n[TEST] Ngưỡng confidence hiện tại: {config.CONFIDENCE_THRESHOLD*100:.0f}%")
    print("Quét 10 lần để đánh giá độ ổn định...")
    results = {}
    for i in range(10):
        label, conf = vision.classify_package()
        if label:
            results.setdefault(label, []).append(conf)
        time.sleep(1)

    print("\nKết quả tổng hợp:")
    for label, confs in results.items():
        avg = sum(confs) / len(confs)
        print(f"  {label}: {len(confs)} lần, confidence TB={avg*100:.1f}%, "
              f"min={min(confs)*100:.1f}%, max={max(confs)*100:.1f}%")

    if len(results) == 1:
        print("  → Ổn định: chỉ nhận 1 loại duy nhất")
    else:
        print("  → CẢNH BÁO: nhận nhiều loại khác nhau — cần chỉnh ngưỡng HSV!")


def main():
    print("=" * 50)
    print("TEST NHẬN DIỆN MÀU HSV")
    print("=" * 50)
    print(f"Phương pháp: Phân tích màu HSV (không dùng AI)")
    print(f"Camera: {config.CAMERA_RESOLUTION}")

    vision = Vision()

    tests = {
        "1": ("Chụp ảnh camera", test_camera_capture),
        "2": ("Phân tích màu HSV (tinh chỉnh)", test_color_analysis),
        "3": ("Nhận diện 1 lần", test_classify_single),
        "4": ("Nhận diện liên tục (5 lần)", test_classify_multiple),
        "5": ("Đánh giá độ ổn định (10 lần)", test_stability),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-5): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func:
                    func(vision)
        elif choice in tests and tests[choice][1]:
            tests[choice][1](vision)
        else:
            print("Lựa chọn không hợp lệ.")
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        vision.cleanup()
        print("\nĐã cleanup camera.")


if __name__ == "__main__":
    main()
