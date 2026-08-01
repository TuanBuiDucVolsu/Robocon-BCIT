"""
Công cụ chụp ảnh mẫu THẬT cho nhận diện bằng so khớp đặc trưng ORB
(vision/shape_match.py) — thay thế cách nhận diện bằng màu HSV thuần, bền hơn
nhiều với nền lạ (tường, dây điện, bàn ghế...) vì so theo HÌNH DẠNG/HOẠ TIẾT
decal thay vì chỉ màu sắc.

Dùng ảnh chụp THẬT bằng camera của robot — KHÔNG dùng ảnh trong PDF thể lệ
(docs/Hinh_kien_hang.pdf là đồ hoạ vector sạch, khác nhiều so với ảnh chụp thật
dưới ánh sáng/độ phân giải/nhiễu của camera, so khớp sẽ kém chính xác hơn nếu
dùng ảnh đó làm mẫu).

QUAN TRỌNG: ảnh mẫu phải loại bỏ nền phía sau (khung robot/tường/đồ vật) — nếu
lẫn vào, và khung cảnh đó đứng yên giống hệt lúc quét thật, RANSAC sẽ khớp nhầm
vào phần nền tĩnh với MỌI ảnh mẫu như nhau, mất khả năng phân biệt kiện hàng
(đã xảy ra thật — cả 4 mẫu cùng báo inlier cao khi test 1 kiện, xem CLAUDE.md).

Camera gắn cố định trên khung robot — khoảng cách tới bệ đặt kiện hàng không dễ
"lại gần" hơn bằng tay, nên kiện hàng thường chỉ chiếm phần nhỏ trong khung. Vì
vậy tool KHÔNG dùng crop tỉ lệ cố định — chụp 1 ảnh NỀN TRỐNG trước (Bước 0),
rồi với mỗi kiện, so sánh khác biệt với nền để tự động tìm đúng vùng có kiện
hàng và crop sát vùng đó, bất kể kiện hàng to/nhỏ trong khung.

Vùng tự phát hiện là CẢ hộp + pallet (4 kiện dùng chung 1 kiểu hộp/pallet giống
hệt nhau, chỉ khác decal dán trước mặt) — nếu dùng nguyên vùng đó làm ảnh mẫu,
ORB dễ bắt nhầm keypoint từ cạnh hộp/khe pallet (giống nhau ở mọi kiện) thay vì
decal, gây nhận nhầm giữa các kiện (đã xảy ra thật, xem CLAUDE.md). Nên sau khi
phát hiện, tool THU HẸP THÊM vào giữa (INNER_CROP_*) để chỉ giữ vùng decal. Tỉ
lệ cắt hiện tại là ước lượng — mở ảnh mẫu đã lưu ra xem còn dính cạnh hộp/pallet
không, chỉnh lại INNER_CROP_TOP/BOTTOM/SIDES nếu cần.

Lưu ảnh mẫu: vision/templates/{label}.png (grayscale).

Chạy trên Pi (đã cắm camera CSI):
    python3 -m tools.capture_templates                 # chụp cả 4 kiện
    python3 -m tools.capture_templates hana_micron      # chỉ chụp lại 1 kiện

Không có camera/OpenCV → in hướng dẫn rồi thoát.
"""

import os
import sys
import time

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

import config
from vision import Vision
from vision.shape_match import (ORB_FEATURES, MIN_MATCHES_FOR_HOMOGRAPHY, TEMPLATE_DIR,
                                SIDES, TIERS, variant_dirname)

# Ngưỡng chênh lệch pixel (0-255) để coi là "khác nền" — thấp hơn thì nhạy hơn
# nhưng dễ bắt cả nhiễu ánh sáng/rung camera; cao hơn thì chắc ăn hơn nhưng có
# thể bỏ sót viền mờ của kiện hàng.
DIFF_THRESHOLD = 30
# Diện tích tối thiểu (pixel) của vùng khác biệt để coi là kiện hàng thật —
# loại nhiễu lốm đốm nhỏ (rung tay, đổi sáng nhẹ) không phải kiện hàng.
MIN_ITEM_AREA = 1500
# Nới thêm quanh bounding box tìm được (pixel mỗi cạnh) — tránh cắt sát mép quá,
# mất viền decal.
BBOX_PADDING = 12
# Nếu không tách được vùng khác biệt rõ ràng (vd quên chụp nền, ánh sáng đổi quá
# nhiều) — dùng tạm crop tỉ lệ cố định này thay vì chụp cả nền vào ảnh mẫu.
FALLBACK_MARGIN = 0.32
# Nếu vùng phát hiện được chiếm hơn tỉ lệ này của cả khung — nghi ngờ dính nhầm
# nền (camera xê dịch giữa lúc chụp nền và lúc chụp kiện, ánh sáng đổi...), cảnh
# báo ngay lúc chụp thay vì để phát hiện sau khi xem ảnh.
MAX_ITEM_AREA_RATIO = 0.5

# _detect_item_bbox tách được CẢ kiện hàng (hộp giấy + pallet), không chỉ riêng
# mặt decal — 4 kiện dùng CHUNG 1 kiểu hộp + pallet (giống hệt nhau về hình dạng,
# chỉ khác decal dán trước mặt), nên ORB dễ bắt nhầm keypoint từ cạnh hộp/khe
# pallet (giống nhau ở mọi kiện) thay vì tập trung vào decal — gây nhận nhầm giữa
# các kiện (đã xảy ra thật, xem CLAUDE.md). Thu hẹp thêm vào giữa bbox đã phát
# hiện để loại bớt viền hộp/pallet, giữ lại đúng vùng decal. Cắt TRÊN/DƯỚI nhiều
# hơn TRÁI/PHẢI vì mép hộp hở (trên) và pallet (dưới) thường là phần thừa theo
# chiều dọc; decal thường chiếm gần hết chiều ngang mặt hộp.
# Giảm nhẹ tay hơn dự tính ban đầu (0.12/0.22/0.08) — thử thực tế cho thấy cắt
# quá tay làm MẤT LUÔN phần decal cần so khớp (inlier tụt hẳn, từ ~49 xuống ~8),
# hại nhiều hơn lợi so với việc dính chút viền hộp/pallet.
INNER_CROP_TOP = 0.06
INNER_CROP_BOTTOM = 0.10
INNER_CROP_SIDES = 0.04


def _prompt(msg: str):
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def _lock_camera_settings(vision: Vision) -> bool:
    """Khoá AE/AWB (phơi sáng + cân bằng trắng tự động) — nếu không khoá, camera có
    thể tự điều chỉnh nhẹ giữa lúc chụp nền và lúc chụp kiện hàng dù không có gì di
    chuyển, khiến so khác biệt (_detect_item_bbox) bắt nhầm vùng đổi sáng thay vì
    đúng chỗ có kiện hàng. Trả về True nếu khoá thành công."""
    try:
        vision._camera.set_controls({"AeEnable": False, "AwbEnable": False})
        time.sleep(0.5)  # để control mới có hiệu lực trước khi chụp nền tham chiếu
        return True
    except Exception as e:
        print(f"  ⚠️ Không khoá được AE/AWB ({e}) — camera có thể tự đổi sáng giữa")
        print("     các lần chụp, dễ làm sai vùng phát hiện.")
        return False


def _shrink_to_decal(bbox):
    """Thu hẹp bbox (kiện hàng đầy đủ: hộp + pallet) vào giữa, loại bớt viền hộp/
    pallet — xem INNER_CROP_* để hiểu tỉ lệ cắt mỗi cạnh."""
    x, y, w, h = bbox
    left = int(w * INNER_CROP_SIDES)
    right = int(w * INNER_CROP_SIDES)
    top = int(h * INNER_CROP_TOP)
    bottom = int(h * INNER_CROP_BOTTOM)
    return x + left, y + top, w - left - right, h - top - bottom


def _fallback_crop(frame):
    h, w = frame.shape[:2]
    mx, my = int(w * FALLBACK_MARGIN), int(h * FALLBACK_MARGIN)
    return frame[my:h - my, mx:w - mx]


def _detect_item_bbox(frame_item, frame_bg):
    """So khác biệt với ảnh nền trống, trả về (x,y,w,h) vùng có kiện hàng hoặc None
    nếu không tách được vùng nào đủ lớn."""
    gray_item = cv2.cvtColor(frame_item, cv2.COLOR_BGR2GRAY)
    gray_bg = cv2.cvtColor(frame_bg, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_item, gray_bg)
    _, mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < MIN_ITEM_AREA:
        return None

    x, y, w, h = cv2.boundingRect(largest)
    fh, fw = frame_item.shape[:2]
    x0 = max(0, x - BBOX_PADDING)
    y0 = max(0, y - BBOX_PADDING)
    x1 = min(fw, x + w + BBOX_PADDING)
    y1 = min(fh, y + h + BBOX_PADDING)
    return x0, y0, x1 - x0, y1 - y0


def main():
    if cv2 is None or np is None:
        print("❌ OpenCV/numpy không khả dụng — chạy lệnh này TRÊN Pi (đã cài theo requirements.txt).")
        return

    vision = Vision()
    if vision._camera is None:
        print("❌ Camera không khả dụng (đang chạy trên PC hoặc picamera2 lỗi?).")
        print("   Chạy lệnh này TRÊN Pi sau khi đã gắn camera CSI.")
        return

    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    _lock_camera_settings(vision)

    target_labels = sys.argv[1:] if len(sys.argv) > 1 else list(config.LABEL_TO_FACTORY)
    invalid = [l for l in target_labels if l not in config.LABEL_TO_FACTORY]
    if invalid:
        print(f"❌ Nhãn không hợp lệ: {invalid}. Chọn trong: {list(config.LABEL_TO_FACTORY)}")
        return

    print("=== CHỤP ẢNH MẪU CHO NHẬN DIỆN ORB ===\n")
    if len(target_labels) < len(config.LABEL_TO_FACTORY):
        print(f"Chỉ chụp lại: {target_labels}\n")

    # Ảnh mẫu phải chia theo (TẦNG, Ô): camera gắn cố định giữa thân nên kiện ô trái
    # được nhìn từ sườn phải, ô phải nhìn từ sườn trái, hai tầng lại hai góc chúc.
    # Đo thật: khớp đúng tổ hợp được 65-172 inlier, khớp lệch tổ hợp chỉ 0-6.
    print("Ảnh mẫu chia theo TỔ HỢP (tầng, ô) — mỗi tổ hợp một bộ 4 loại.")
    print(f"Cần đủ {len(TIERS) * len(SIDES)} tổ hợp: "
          + ", ".join(variant_dirname(t, sd) for t in TIERS for sd in SIDES) + "\n")
    raw_t = input(f"  Chụp cho TẦNG mấy? ({'/'.join(str(t) for t in TIERS)}, mặc định 2): ").strip()
    level = 1 if raw_t == "1" else 2
    raw_s = input("  Ô nào? (t=TRÁI / p=PHẢI, mặc định TRÁI): ").strip().lower()
    side = "right" if raw_s == "p" else "left"
    out_dir = os.path.join(TEMPLATE_DIR, variant_dirname(level, side))
    os.makedirs(out_dir, exist_ok=True)
    print(f"  → Lưu vào {out_dir}")
    print(f"  → Đặt kiện ở TẦNG {level}, ô {'PHẢI' if side == 'right' else 'TRÁI'} "
          f"cho CẢ {len(target_labels)} loại. Đặt sai ô là bộ mẫu này vô dụng.\n")
    print("Tool tự tìm đúng vùng có kiện hàng bằng cách so khác biệt với ảnh nền")
    print("trống — không cần kiện hàng lấp đầy khung, nhưng BẮT BUỘC chụp nền trống")
    print("trước, và giữ camera/bệ đặt đứng yên suốt quá trình (không xê dịch giữa")
    print("các lần chụp — kể cả rung nhẹ tay cũng có thể làm sai lệch vùng phát hiện).\n")

    _prompt("  → Bước 0: dọn TRỐNG bệ đặt (không có kiện hàng nào), giữ nguyên camera/")
    print("     khung cảnh y như lúc quét thật, nhấn Enter...")
    frame_bg = vision._capture_frame()
    if frame_bg is None:
        print("  ❌ Không chụp được ảnh nền, dừng lại — thử chạy lại tool.")
        vision.cleanup()
        return
    bg_brightness = float(cv2.cvtColor(frame_bg, cv2.COLOR_BGR2GRAY).mean())
    print(f"     Độ sáng TB ảnh nền: {bg_brightness:.1f}\n")

    print("  ⚠️ Đặt ĐÚNG MỘT kiện mỗi lần. Lúc thi đấu robot dùng classify_pair():")
    print("     chia đôi khung hình rồi nhận diện từng nửa MỘT kiện — ảnh mẫu chụp")
    print("     cả 2 kiện sẽ không khớp được với nửa khung đó.\n")

    for label in target_labels:
        factory = config.LABEL_TO_FACTORY[label]
        o = "PHẢI" if side == "right" else "TRÁI"
        _prompt(f"  → Đặt MỘT kiện '{label}' ({factory}) vào TẦNG {level} ô {o}, nhấn Enter để chụp...")
        time.sleep(0.3)  # 1 nhịp để tay/máy ổn định sau khi buông phím

        frame = vision._capture_frame()
        if frame is None:
            print("    ❌ Không chụp được ảnh, thử lại từ đầu cho kiện này.")
            continue

        item_brightness = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
        brightness_diff = abs(item_brightness - bg_brightness)
        print(f"    Độ sáng TB: {item_brightness:.1f} (lệch {brightness_diff:.1f} so với nền)")
        if brightness_diff > 15:
            print("    ⚠️ Lệch sáng khá lớn so với lúc chụp nền — AE/AWB có thể chưa khoá được,")
            print("       vùng phát hiện dưới đây có thể không đáng tin.")

        bbox = _detect_item_bbox(frame, frame_bg)
        if bbox is not None:
            x, y, w, h = bbox
            fh, fw = frame.shape[:2]
            area_ratio = (w * h) / (fw * fh)
            print(f"    Tự phát hiện vùng kiện hàng: {w}x{h} tại ({x},{y}) "
                  f"({area_ratio*100:.0f}% khung)")
            if area_ratio > MAX_ITEM_AREA_RATIO:
                print(f"    ⚠️ Vùng phát hiện chiếm >{MAX_ITEM_AREA_RATIO*100:.0f}% khung — nghi")
                print("       ngờ dính nhầm nền (camera xê dịch so với lúc chụp nền ở Bước 0,")
                print("       hoặc ánh sáng đổi giữa 2 lần chụp). Nên chụp lại kiện này:")
                print(f"       `python3 -m tools.capture_templates {label}`")

            # Vùng rộng hơn cao rõ rệt = đang chụp CẢ 2 kiện cạnh nhau trên tầng kệ.
            # Lúc thi đấu main.py dùng classify_pair(): chia đôi khung rồi so từng
            # nửa MỘT kiện. Ảnh mẫu 2 kiện đem so với nửa khung 1 kiện thì quá nửa
            # đặc trưng của mẫu không có chỗ khớp — và phần khớp được lại rơi vào
            # nền/pallet dùng chung, thứ giống hệt nhau ở cả 4 mẫu.
            #
            # ⚠️ Ngưỡng 1.4 cũ BÁO ĐỘNG GIẢ liên tục. Một kiện = 1 pallet + 4 khối,
            # nhìn từ trước thấy HAI mặt khối cạnh nhau nên vốn dĩ đã nằm ngang.
            # Đo thật cùng một kiện ở 2 ô: t2_left 280x212 = 1.32 (lọt),
            # t2_right 272x184 = 1.48 (kêu oan) — mà chính bộ mẫu t2_right đó cho
            # 229 inlier. Hai kiện thật cạnh nhau thì rộng gấp đôi, tỉ lệ ~3.0, nên
            # 2.0 vẫn bắt được ca thật mà không kêu oan nữa. Cảnh báo lúc nào cũng
            # kêu thì người dùng quen tay bỏ qua, kể cả lần nó kêu đúng.
            if w > h * 2.0:
                print(f"    ⚠️ Vùng phát hiện rất RỘNG ({w}x{h}) — nhiều khả năng đang")
                print("       chụp CẢ 2 kiện cạnh nhau. Ảnh mẫu phải là MỘT kiện thôi:")
                print("       bỏ bớt 1 kiện khỏi bệ rồi chụp lại kiện này.")

            # Thu hẹp vào giữa — bbox trên là cả hộp+pallet, chỉ giữ lại vùng decal
            dx, dy, dw, dh = _shrink_to_decal((x, y, w, h))
            print(f"    Thu hẹp về vùng decal: {dw}x{dh} tại ({dx},{dy})")
            roi = frame[dy:dy + dh, dx:dx + dw]
        else:
            roi = _fallback_crop(frame)
            print("    ⚠️ Không tách được vùng khác biệt rõ ràng với nền — dùng crop mặc định")
            print("       (kiểm tra: đã chụp đúng nền trống ở Bước 0 chưa, camera có bị xê dịch")
            print("       giữa các lần chụp không, ánh sáng có đổi đột ngột không).")

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        kp, des = orb.detectAndCompute(gray, None)
        n_kp = len(kp) if kp else 0

        path = os.path.join(out_dir, f"{label}.png")
        cv2.imwrite(path, gray)
        print(f"    Đã lưu: {path} ({gray.shape[1]}x{gray.shape[0]}, {n_kp} keypoint)")
        if n_kp < MIN_MATCHES_FOR_HOMOGRAPHY:
            print(f"    ⚠️ Quá ít keypoint (<{MIN_MATCHES_FOR_HOMOGRAPHY}) — decal có thể bị mờ/thiếu")
            print(f"       sáng. Nên chụp lại: `python3 -m tools.capture_templates {label}`")
        print()

    vision.cleanup()
    print("Xong. Kiểm tra lại bằng tests/test_vision.py (test 9 — số inlier từng kiện,")
    print("rồi test 3/5/6/7 nhận diện thật).")


if __name__ == "__main__":
    main()
