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
            cv2.imwrite("test_capture.jpg", frame)
            print("  Đã lưu ảnh: test_capture.jpg")
        except Exception as e:
            print(f"  Không lưu được ảnh: {e}")
    else:
        print("  LỖI: Không chụp được ảnh!")


def test_color_order(vision: Vision):
    """Kiểm tra thứ tự kênh màu THẬT của frame — vision.py giả định BGR (comment ở
    _capture_frame), nhưng picamera2 đặt tên format 'BGR888'/'RGB888' hay gây nhầm
    (không phải lúc nào cũng khớp trực giác với thứ tự kênh trả về thực tế). Nếu bị
    đảo, mọi dải HSV trong config.COLOR_RANGES đều sai lệch có hệ thống."""
    print("\n[TEST] Kiểm tra thứ tự kênh BGR/RGB...")
    print("  Cầm 1 VẬT MÀU ĐỎ THUẦN (giấy đỏ, vải đỏ...) — KHÔNG dùng kiện hàng")
    print("  (decal nhiều màu/chi tiết sẽ làm kết quả không rõ ràng).")
    input("  → Đưa vật màu đỏ vào giữa khung hình, giữ yên, nhấn Enter...")

    frame = vision._capture_frame()
    if frame is None:
        print("  LỖI: Không chụp được ảnh!")
        return

    h, w = frame.shape[:2]
    margin = getattr(config, "ROI_MARGIN", 0.2)
    my, mx = int(h * margin), int(w * margin)
    roi = frame[my:h - my, mx:w - mx]

    ch0 = float(roi[:, :, 0].mean())
    ch1 = float(roi[:, :, 1].mean())
    ch2 = float(roi[:, :, 2].mean())
    print(f"  Kênh 0 (vision.py coi là B): TB = {ch0:.1f}")
    print(f"  Kênh 1 (G):                 TB = {ch1:.1f}")
    print(f"  Kênh 2 (vision.py coi là R): TB = {ch2:.1f}")

    if ch2 > ch0 + 15:
        print("\n  ✅ Kênh 2 (R) cao hơn hẳn kênh 0 (B) — ĐÚNG thứ tự BGR như code đang")
        print("     giả định. Không cần sửa gì trong _init_camera().")
    elif ch0 > ch2 + 15:
        print("\n  ⚠️ Kênh 0 cao hơn hẳn kênh 2 — mảng ĐANG LÀ RGB (bị đảo so với giả định")
        print("     BGR trong vision.py)! Mọi dải HSV trong config.COLOR_RANGES đều SAI có")
        print("     hệ thống (đỏ↔lam bị hoán đổi). Cần sửa vision.py: đổi format=\"BGR888\"")
        print("     thành format=\"RGB888\" trong _init_camera() (hoặc đảo kênh thủ công")
        print("     frame = frame[:, :, ::-1] trong _capture_frame), rồi calibrate lại từ đầu.")
    else:
        print("\n  ❓ Chênh lệch không rõ ràng — thử lại với vật màu đỏ THUẦN, sáng, đủ lớn")
        print("     để lấp gần hết khung hình, tránh ánh sáng ám vàng/trắng.")


def test_color_analysis(vision: Vision):
    """Chụp ảnh và hiển thị tỷ lệ từng màu — dùng để tinh chỉnh ngưỡng HSV."""
    print("\n[TEST] Phân tích màu HSV...")
    frame = vision._capture_frame()
    if frame is None:
        print("  LỖI: Không chụp được ảnh!")
        return

    import cv2
    import numpy as np
    from vision.vision import _center_weight_map

    h, w = frame.shape[:2]
    margin = getattr(config, "ROI_MARGIN", 0.2)
    margin_x = int(w * margin)
    margin_y = int(h * margin)
    roi = frame[margin_y:h - margin_y, margin_x:w - margin_x]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    total = roi.shape[0] * roi.shape[1]

    # Dùng ĐÚNG cách tính điểm mà _classify_by_color() dùng khi quét thật (kể cả
    # trọng số tâm) — nếu không, % hiển thị ở đây sẽ lệch với confidence thật lúc
    # robot chạy, gây tinh chỉnh sai ngưỡng.
    center_weight = _center_weight_map(hsv.shape[:2])
    uniform_weight = np.ones_like(center_weight)
    no_center_weight = getattr(config, "NO_CENTER_WEIGHT_LABELS", ("hana_micron",))

    print(f"  ROI size: {roi.shape[1]}x{roi.shape[0]} ({total} pixels)")
    print(f"  Dải màu cấu hình (đã áp trọng số tâm, trừ {no_center_weight}):")

    for label, ranges in config.COLOR_RANGES.items():
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in ranges:
            lower_np = np.array(lower, dtype=np.uint8)
            upper_np = np.array(upper, dtype=np.uint8)
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower_np, upper_np))
        weight = uniform_weight if label in no_center_weight else center_weight
        pct = (weight * (mask > 0)).sum() / weight.sum() * 100
        bar = "█" * int(pct / 2)
        factory = config.LABEL_TO_FACTORY.get(label, "?")
        print(f"    {label:12s} ({factory:18s}): {pct:5.1f}% {bar}")

    # Lưu ảnh ROI để kiểm tra
    cv2.imwrite("test_roi.jpg", roi)
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


def test_classify_pair(vision: Vision):
    print("\n[TEST] Nhận diện CẶP kiện (classify_pair — dùng trong NV1)...")
    print("  Hướng camera vào tầng kệ có 2 kiện cạnh nhau.")
    input("  Nhấn Enter để quét...")
    label_l, label_r = vision.classify_pair()
    if label_l and label_r:
        factory_l = vision.get_factory_name(label_l)
        factory_r = vision.get_factory_name(label_r)
        print(f"  Trái:  {label_l} → {factory_l}")
        print(f"  Phải: {label_r} → {factory_r}")
        print("  ✅ Nhận diện đủ 2 kiện")
    elif label_l or label_r:
        print(f"  ⚠ Chỉ nhận 1 bên: trái={label_l}, phải={label_r}")
    else:
        print("  ❌ Không nhận diện được cặp kiện")


def test_classify_pair_repeat(vision: Vision):
    print("\n[TEST] classify_pair liên tục 5 lần (độ ổn định cặp)...")
    for i in range(5):
        label_l, label_r = vision.classify_pair()
        ok = label_l is not None and label_r is not None
        print(f"  Lần {i+1}: trái={label_l or '?'}  phải={label_r or '?'}  "
              f"{'OK' if ok else 'THIẾU'}")
        time.sleep(1)


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
        "6": ("Nhận diện cặp 2 kiện (classify_pair)", test_classify_pair),
        "7": ("classify_pair liên tục 5 lần", test_classify_pair_repeat),
        "8": ("Kiểm tra thứ tự kênh BGR/RGB (chạy TRƯỚC khi tinh chỉnh màu)", test_color_order),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-8): ").strip()

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
