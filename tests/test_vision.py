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


def _ask_tier() -> int:
    """Hỏi TẦNG đang soi. Bắt buộc vì camera gắn cố định vào thân robot: tầng 1 và
    tầng 2 rơi vào 2 độ cao khác nhau trong khung, nên vùng quét dịch theo tầng
    (config.ROI_Y_CENTER). Soi nhầm tầng là soi một vùng khung hình khác hẳn cái mà
    main.py soi lúc thi đấu — đúng loại sai lầm khiến 'kiểm xong vẫn trượt'."""
    raw = input("  Đang soi TẦNG mấy? (1/2, mặc định 2): ").strip()
    tier = 1 if raw == "1" else 2
    print(f"  → Dùng vùng quét của TẦNG {tier}")
    return tier


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


def test_shape_analysis(vision: Vision):
    """Chụp ảnh và hiển thị số inlier ORB so với từng ảnh mẫu — dùng để kiểm tra
    ảnh mẫu (vision/templates/*.png) có đủ tốt không, không phải kết quả nhận diện
    cuối (đó là _classify_frame — ORB trước, HSV dự phòng)."""
    print("\n[TEST] So khớp ORB với ảnh mẫu...")
    if not vision._shape_matcher.ready:
        print("  ⚠️ Chưa có ảnh mẫu (hoặc thiếu OpenCV) — chạy "
              "`python3 -m tools.capture_templates` trước.")
        return

    frame = vision._capture_frame()
    if frame is None:
        print("  LỖI: Không chụp được ảnh!")
        return

    import cv2
    from vision.shape_match import MIN_INLIERS, MARGIN_RATIO, MIN_MATCHES_FOR_HOMOGRAPHY

    matcher = vision._shape_matcher
    print(f"\n  Ngưỡng: >={MIN_INLIERS} inlier VÀ >={MARGIN_RATIO}x kiện đứng thứ 2")
    print(f"  (dưới {MIN_MATCHES_FOR_HOMOGRAPHY} match thì không chạy được RANSAC → tính 0)\n")

    # Phải soi ĐÚNG cái mà lúc thi đấu robot soi: main.py dùng classify_pair(), tức
    # là CHIA ĐÔI khung rồi nhận diện từng nửa MỘT kiện. Bản cũ ở đây soi nguyên
    # khung (2 kiện) nên số inlier đẹp hơn hẳn thực tế — kiểm xong yên tâm mà vào
    # trận vẫn trượt.
    tier = _ask_tier()
    h, w = frame.shape[:2]
    mid = w // 2
    for ten, side, half in (("TRÁI", "left", frame[:, :mid]),
                            ("PHẢI", "right", frame[:, mid:])):
        roi = vision._crop_roi(half, tier)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        kp, des = matcher._orb.detectAndCompute(gray, None)
        # ĐÚNG bộ ảnh mẫu mà classify_pair() sẽ dùng cho tổ hợp này — soi bộ khác
        # là số inlier ở đây không liên quan gì tới lúc chạy thật
        templates = matcher.templates_for(tier, side)
        print(f"  --- Nửa {ten}: ROI {roi.shape[1]}x{roi.shape[0]}, "
              f"{len(kp) if kp else 0} keypoint, {len(templates)} ảnh mẫu ---")
        for label, (tkp, _t) in templates.items():
            print(f"        mẫu {label:12s}: {len(tkp)} keypoint")

        scores, raw = {}, {}
        for label, (tkp, tdes) in templates.items():
            good = matcher._good_matches(des, tdes)
            raw[label] = len(good)
            scores[label] = matcher._inlier_count(kp, tkp, good)

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        for label, inliers in ranked:
            factory = config.LABEL_TO_FACTORY.get(label, "?")
            flag = "✅" if inliers >= MIN_INLIERS else "  "
            bar = "█" * min(inliers, 40)
            print(f"   {flag} {label:12s} ({factory:18s}): {inliers:3d} inlier "
                  f"/ {raw[label]:3d} match {bar}")

        best, second = ranked[0][1], (ranked[1][1] if len(ranked) > 1 else 0)
        decided, _ = matcher.classify(roi, tier, side)
        print(f"   → Kết luận ORB: {decided or 'KHÔNG ĐỦ TỰ TIN (rơi về HSV)'}")
        if decided is None and best >= MIN_INLIERS:
            print(f"     Lý do: cách biệt chưa đủ ({best} vs {second}, cần >= "
                  f"{MARGIN_RATIO * max(second, 1):.1f}).")
            print("     Thường là do ảnh mẫu dính NỀN GIỐNG NHAU (kệ/pallet/tường):")
            print("     mọi mẫu cùng khớp vào phần nền nên không cái nào trội hẳn.")
        print()


def test_classify_both_tiers(vision: Vision):
    """Quét CẢ 2 TẦNG liên tiếp — bài kiểm sát điều kiện thi đấu nhất.

    Đầu trận kệ có hàng ở CẢ 2 tầng. Đây là lúc lỗi vùng quét lộ ra: nếu ROI không
    dịch theo tầng thì nó vắt ngang cả 2, ôm 2 loại kiện cùng lúc và nhận diện sai
    theo kiểu rất khó lần ra. Quét từng tầng riêng rồi đối chiếu với thực tế.
    """
    print("\n[TEST] Nhận diện CẢ 2 TẦNG (sát điều kiện thi đấu)")
    print("  Kệ phải có đủ 2 kiện ở CẢ tầng 1 lẫn tầng 2 — đúng như đầu trận.")
    print(f"  Nhãn hợp lệ: {', '.join(config.LABEL_TO_FACTORY)}\n")

    expect = {}
    for tier in (2, 1):
        raw = input(f"  Tầng {tier} thực tế đang đặt gì? (trái,phải — Enter để bỏ đối chiếu): ")
        parts = [x.strip() for x in raw.strip().lower().split(",")]
        expect[tier] = tuple(parts) if len(parts) == 2 and all(parts) else None

    input("\n  Đặt robot đúng vị trí quét rồi nhấn Enter...")

    got, all_ok = {}, True
    for tier in (2, 1):
        label_l, label_r = vision.classify_pair(tier)
        got[tier] = (label_l, label_r)
        print(f"\n  --- TẦNG {tier} ---")
        print(f"    Robot đọc : trái={label_l or '?'}  phải={label_r or '?'}")
        if expect[tier] is None:
            if label_l is None or label_r is None:
                all_ok = False
                print("    ⚠ Không nhận đủ 2 kiện")
            continue
        exp_l, exp_r = expect[tier]
        print(f"    Thực tế   : trái={exp_l}  phải={exp_r}")
        ok = (label_l == exp_l and label_r == exp_r)
        all_ok = all_ok and ok
        print(f"    {'✅ KHỚP' if ok else '❌ SAI'}")

    # Hai tầng ra CÙNG kết quả trong khi hàng thật khác nhau = vùng quét không dịch
    # theo tầng (level bị đánh rơi ở đâu đó) — triệu chứng khác hẳn "nhận sai nhãn".
    if got[1] == got[2] and got[1] != (None, None) and expect[1] != expect[2]:
        all_ok = False
        print("\n  ❌ 2 tầng cho KẾT QUẢ GIỐNG HỆT nhau trong khi hàng thật khác nhau.")
        print("     Nhiều khả năng vùng quét KHÔNG dịch theo tầng — kiểm config.ROI_Y_CENTER")
        print("     và xem `level` có bị đánh rơi trên đường classify_pair → _crop_roi không.")

    print("\n  " + ("✅ CẢ 2 TẦNG ĐỀU ĐÚNG" if all_ok else "❌ CÒN SAI — xem lại ở trên"))


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

    # Soi ĐÚNG vùng classify_pair() soi (nửa trái + nửa phải), không phải giữa
    # nguyên khung — chỗ đó là khe giữa 2 kiện, robot không bao giờ nhìn tới.
    side = input("  Xem nửa nào? (t=TRÁI / p=PHẢI, mặc định TRÁI): ").strip().lower()
    tier = _ask_tier()
    roi_left, roi_right = vision.pair_rois(frame, tier)
    roi = roi_right if side == "p" else roi_left
    print(f"  Đang xem nửa {'PHẢI' if side == 'p' else 'TRÁI'} của khung hình")

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
    tier = _ask_tier()
    input("  Nhấn Enter để quét...")
    label_l, label_r = vision.classify_pair(tier)
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


def test_left_right_mapping(vision: Vision):
    """Ảnh TRÁI/PHẢI có khớp càng TRÁI/PHẢI của robot không?

    Đây là lỗi IM LẶNG: nếu camera lắp lật hoặc gương thì classify_pair vẫn trả về
    2 nhãn hợp lệ, log vẫn báo OK, nhưng cả 2 kiện đi nhầm nhà máy. Không có cảm
    biến nào phát hiện được — chỉ kiểm bằng cách đặt 2 kiện KHÁC NHAU đã biết trước.
    """
    print("\n[TEST] Kiểm ánh xạ TRÁI/PHẢI của ảnh với càng robot")
    print("  Đặt 2 kiện KHÁC LOẠI lên tầng kệ, ghi nhớ bên nào là bên nào.")
    print("  (Bên trái = phía càng TRÁI của robot khi robot nhìn vào kệ)")

    expect_l = input("  Kiện thật bên TRÁI là gì? (samsung/foxconn/amkor/hana_micron): ").strip().lower()
    expect_r = input("  Kiện thật bên PHẢI là gì? : ").strip().lower()
    valid = set(config.LABEL_TO_FACTORY)
    if expect_l not in valid or expect_r not in valid:
        print(f"  Tên không hợp lệ. Hợp lệ: {', '.join(sorted(valid))}")
        return
    if expect_l == expect_r:
        print("  ⚠ Phải dùng 2 kiện KHÁC LOẠI thì mới phát hiện được lật trái/phải.")
        return

    tier = _ask_tier()
    input("  Đặt robot đúng vị trí quét rồi nhấn Enter...")
    label_l, label_r = vision.classify_pair(tier)
    print(f"\n  Robot đọc được : trái={label_l}  phải={label_r}")
    print(f"  Thực tế        : trái={expect_l}  phải={expect_r}")

    if label_l is None or label_r is None:
        print("  ❌ Không nhận đủ 2 kiện — sửa nhận diện trước rồi test lại phần này")
    elif label_l == expect_l and label_r == expect_r:
        print("  ✅ ĐÚNG — ảnh trái/phải khớp càng trái/phải")
    elif label_l == expect_r and label_r == expect_l:
        print("  ❌ BỊ LẬT TRÁI/PHẢI! Cả 2 kiện sẽ đi nhầm nhà máy mà log vẫn báo OK.")
        print("     → Kiểm lại hướng lắp camera, hoặc đảo 2 nửa ảnh trong classify_pair().")
    else:
        print("  ❌ Nhận diện SAI nhãn (chưa kết luận được lật hay không) — calibrate lại trước")


def test_classify_pair_repeat(vision: Vision):
    print("\n[TEST] classify_pair liên tục 5 lần (độ ổn định cặp)...")
    tier = _ask_tier()
    for i in range(5):
        label_l, label_r = vision.classify_pair(tier)
        ok = label_l is not None and label_r is not None
        print(f"  Lần {i+1}: trái={label_l or '?'}  phải={label_r or '?'}  "
              f"{'OK' if ok else 'THIẾU'}")
        time.sleep(1)


def main():
    print("=" * 50)
    print("TEST NHẬN DIỆN KIỆN HÀNG")
    print("=" * 50)
    print("Phương pháp: ORB (hình dạng, chính) + HSV màu (dự phòng) — không dùng AI")
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
        "t": ("Nhận diện CẢ 2 TẦNG (sát thi đấu nhất)", test_classify_both_tiers),
        "8": ("Kiểm tra thứ tự kênh BGR/RGB (chạy TRƯỚC khi tinh chỉnh màu)", test_color_order),
        "9": ("So khớp ORB với ảnh mẫu (chẩn đoán template)", test_shape_analysis),
        "l": ("Kiểm ánh xạ TRÁI/PHẢI ảnh ↔ càng robot", test_left_right_mapping),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-9, l, t): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func and key != "l":     # 'l' cần nhập tay tên kiện — chạy riêng
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
