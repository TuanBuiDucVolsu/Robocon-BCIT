"""
Nhận diện kiện hàng bằng so khớp đặc trưng ORB (feature matching) — so theo HÌNH
DẠNG/HOẠ TIẾT decal (chip xanh dương, chip vàng, chữ "Al", QR code) thay vì chỉ
màu sắc như vision.py (_classify_by_color). Bền hơn nhiều với nền lạ (tường, dây
điện, bàn ghế...) vì màu nền trùng không tự nhiên tạo ra keypoint khớp hình dạng
được — vẫn thuần OpenCV cổ điển, không dùng model AI/deep learning, không cần huấn
luyện, đúng tinh thần "Camera AI xử lý cục bộ" của thể lệ.

Ảnh mẫu (template): ảnh chụp THẬT từng kiện hàng bằng camera của robot (KHÔNG phải
ảnh PDF thể lệ — ảnh PDF là đồ hoạ vector sạch, khác nhiều so với ảnh chụp thật dưới
ánh sáng/độ phân giải camera, so khớp sẽ kém chính xác hơn). Tạo bằng:
    python3 -m tools.capture_templates

⚠️ ẢNH MẪU PHẢI CHIA THEO (TẦNG, Ô) — đo trên robot thật:
    khớp ĐÚNG ô/tầng đã chụp mẫu : 65, 140, 172 inlier
    khớp ở ô hoặc tầng KHÁC      : 0, 4, 6 inlier
Chênh hơn một bậc độ lớn. Camera gắn cố định giữa thân nên kiện ô TRÁI được nhìn từ
sườn phải, ô PHẢI nhìn từ sườn trái, còn 2 tầng thì 2 góc chúc khác nhau — bốn tổ
hợp là bốn phối cảnh, một ảnh mẫu không phủ nổi. Ở cả 4 ô nhãn đúng vẫn đứng đầu
bảng, tức ORB không nhầm, chỉ là không đủ mạnh để qua ngưỡng ở vị trí lạ.

Bố cục thư mục:
    vision/templates/t2_left/{label}.png    ← bộ theo tổ hợp, ưu tiên dùng
    vision/templates/t2_right/{label}.png
    vision/templates/t1_left/{label}.png
    vision/templates/t1_right/{label}.png
    vision/templates/{label}.png            ← bộ PHẲNG cũ, chỉ dùng khi thiếu biến thể

Thiếu biến thể nào thì tự rơi về bộ phẳng — hệ thống vẫn chạy trong lúc chụp dần.
"""

import glob
import logging
import os

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

import config

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

SIDES = ("left", "right")
TIERS = (1, 2)


def variant_dirname(level: int, side: str) -> str:
    """Tên thư mục con của một tổ hợp (tầng, ô) — dùng chung với capture_templates."""
    return f"t{int(level)}_{side}"

# Số keypoint tối đa trích xuất mỗi ảnh — nhiều hơn thì chính xác hơn nhưng chậm hơn trên Pi.
# Nâng 500 → 900 cùng lúc với CAMERA_RESOLUTION 640x480 → 1296x972: ở độ phân giải mới
# ORB chạm ĐÚNG trần 500 trên một ROI (520x364), tức ảnh còn chi tiết mà bị cắt cụt.
# Giữ 500 là bỏ phí chính thứ vừa bỏ công tăng độ phân giải để có.
ORB_FEATURES = 900
# Lowe's ratio test: match "tốt" khi khoảng cách gần nhất < LOWE_RATIO * khoảng cách gần nhì.
# Thấp hơn = khắt khe hơn (ít match nhiễu hơn nhưng cũng ít match thật hơn).
LOWE_RATIO = 0.75
# Số điểm khớp tối thiểu (sau ratio test) mới thử tính homography — RANSAC cần >=4 điểm.
MIN_MATCHES_FOR_HOMOGRAPHY = 8
# Số inlier RANSAC tối thiểu mới coi là nhận diện được kiện đó (đủ tự tin, không phải
# trùng hợp vài keypoint lẻ tẻ từ nền).
MIN_INLIERS = getattr(config, "SHAPE_MIN_INLIERS", 10)
# Kiện thắng phải có inlier >= MARGIN_RATIO lần kiện đứng thứ 2 mới được chấp nhận —
# chặn trường hợp bệ trống/nền vẫn cho 1-2 nhãn gần chạm MIN_INLIERS nhưng sát nút
# nhau (không có cách biệt rõ ràng như khi thật sự cầm đúng kiện hàng).
MARGIN_RATIO = getattr(config, "SHAPE_MARGIN_RATIO", 1.8)
RANSAC_REPROJ_THRESHOLD = 5.0
# Trong một bộ, ảnh mẫu to nhất không được vượt quá bấy nhiêu lần ảnh nhỏ nhất.
# Vượt = buổi chụp đó đặt kiện xê dịch, chuẩn hoá sẽ cắt cụt tấm to (đã gặp ở bộ
# t1_right: 237x218 .. 915x530, chuẩn hoá về 237x172 làm hỏng hẳn tấm hana).
MAX_TEMPLATE_SIZE_SPREAD = 1.5
# Quy đổi số inlier -> "confidence" 0-1 CHỈ để hiển thị (web debug UI, log) thống nhất
# định dạng % với đường màu HSV — quyết định nhận diện thật vẫn dựa vào MIN_INLIERS thô,
# không dựa vào số quy đổi này.
CONFIDENCE_NORM = 40.0


def inliers_to_confidence(n: int) -> float:
    return min(1.0, n / CONFIDENCE_NORM)


class ShapeMatcher:
    """So khớp ROI camera với ảnh mẫu 4 kiện hàng bằng ORB + BFMatcher + RANSAC homography."""

    def __init__(self):
        self._orb = None
        # key -> {label: (keypoints, descriptors)}
        #   key = (tầng, ô) cho bộ biến thể, hoặc None cho bộ phẳng dự phòng
        self._sets = {}
        if cv2 is None or np is None:
            logger.warning("OpenCV/numpy không khả dụng — ShapeMatcher vô hiệu hoá")
            return
        self._orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._load_templates()

    # ----------------------------------------------------------
    # Nạp ảnh mẫu
    # ----------------------------------------------------------

    @staticmethod
    def _center_crop(img, h, w):
        ih, iw = img.shape[:2]
        y0, x0 = (ih - h) // 2, (iw - w) // 2
        return img[y0:y0 + h, x0:x0 + w]

    def _load_dir(self, path, what):
        """Nạp một thư mục ảnh mẫu → {label: (kp, des)}. Thiếu file thì bỏ qua lặng lẽ
        với bộ biến thể (đang chụp dần), nhưng cảnh báo với bộ phẳng.

        ⚠️ CHUẨN HOÁ KÍCH THƯỚC trong cùng một bộ trước khi trích đặc trưng.
        Bốn ảnh mẫu của cùng một ô đều chứa CÙNG phần pallet + khung kệ ở nền, mà
        nền đó có mặt trong MỌI vùng quét. Nên tấm nào được cắt rộng hơn thì tự nhiên
        ăn thêm inlier miễn phí từ nền — tấm cắt SẠCH nhất lại thành tấm thiệt nhất.
        Đo thật ở bộ t2_left: samsung cắt sát (296px) thua sát nút amkor cắt rộng
        (395px) ngay trên ô đang đặt kiện samsung. Cắt tất cả về cùng cỡ thì cùng ô
        đó lên 1.8x, còn t2_right nhảy từ 1.2x lên 9.0x.
        """
        imgs = {}
        if not os.path.isdir(path):
            return {}
        for label in config.LABEL_TO_FACTORY:
            fp = os.path.join(path, f"{label}.png")
            if not os.path.isfile(fp):
                continue
            img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
            if img is None:
                logger.warning("Không đọc được ảnh mẫu: %s", fp)
                continue
            imgs[label] = img

        loaded = {}
        if imgs:
            hmin = min(i.shape[0] for i in imgs.values())
            wmin = min(i.shape[1] for i in imgs.values())
            hmax = max(i.shape[0] for i in imgs.values())
            wmax = max(i.shape[1] for i in imgs.values())
            # Lệch nhiều = buổi chụp đó đặt kiện xê dịch giữa các lần, chuẩn hoá sẽ
            # phải cắt rất sâu và làm hỏng những tấm to. Chụp lại rẻ hơn là chịu đựng.
            if wmax > wmin * MAX_TEMPLATE_SIZE_SPREAD or hmax > hmin * MAX_TEMPLATE_SIZE_SPREAD:
                logger.warning("[%s] ảnh mẫu LỆCH CỠ NẶNG (%dx%d .. %dx%d) — chuẩn hoá về "
                               "%dx%d sẽ cắt cụt những tấm to. Nên chụp lại cả bộ, đặt kiện "
                               "vào ĐÚNG một chỗ cho cả 4 loại.",
                               what, wmin, hmin, wmax, hmax, wmin, hmin)
            for label, img in imgs.items():
                img = self._center_crop(img, hmin, wmin)
                kp, des = self._orb.detectAndCompute(img, None)
                if des is None or len(kp) < MIN_MATCHES_FOR_HOMOGRAPHY:
                    logger.warning("Ảnh mẫu %s/%s quá ít đặc trưng (%d keypoint) — chụp lại "
                                   "nét hơn/gần hơn", what, label, len(kp) if kp else 0)
                    continue
                loaded[label] = (kp, des)

        total = len(config.LABEL_TO_FACTORY)
        if loaded:
            logger.info("Đã nạp %d/%d ảnh mẫu ORB [%s]", len(loaded), total, what)
        if 0 < len(loaded) < total:
            missing = [l for l in config.LABEL_TO_FACTORY if l not in loaded]
            logger.warning("[%s] THIẾU ảnh mẫu %s — những kiện đó không khớp được ORB "
                           "ở tổ hợp này", what, missing)
        return loaded

    def _load_templates(self):
        if not os.path.isdir(TEMPLATE_DIR):
            logger.warning("Chưa có thư mục ảnh mẫu (%s) — chạy "
                            "`python3 -m tools.capture_templates` trên Pi trước", TEMPLATE_DIR)
            return

        flat = self._load_dir(TEMPLATE_DIR, "bộ phẳng")
        if flat:
            self._sets[None] = flat

        for tier in TIERS:
            for side in SIDES:
                name = variant_dirname(tier, side)
                s = self._load_dir(os.path.join(TEMPLATE_DIR, name), name)
                if s:
                    self._sets[(tier, side)] = s

        variants = [k for k in self._sets if k is not None]
        if not variants:
            logger.warning("Chưa có bộ ảnh mẫu theo (tầng, ô) — đang dùng bộ PHẲNG cho mọi "
                           "vị trí. Đo thật cho thấy khớp sai vị trí chỉ được 0-6 inlier so "
                           "với 65-172 khi đúng vị trí; chạy `python3 -m tools.capture_templates` "
                           "cho từng tổ hợp để hết trượt.")
        elif len(variants) < len(TIERS) * len(SIDES):
            thieu = [variant_dirname(t, s) for t in TIERS for s in SIDES
                     if (t, s) not in self._sets]
            logger.warning("Mới có %d/%d bộ theo (tầng, ô) — còn thiếu %s, những tổ hợp đó "
                           "rơi về bộ phẳng", len(variants), len(TIERS) * len(SIDES), thieu)

    def _set_for(self, level=None, side=None):
        """Chọn bộ ảnh mẫu cho một (tầng, ô). Thiếu biến thể thì rơi về bộ phẳng."""
        if level is not None and side is not None:
            s = self._sets.get((int(level), side))
            if s and len(s) >= 2:
                return s
        return self._sets.get(None) or {}

    def templates_for(self, level=None, side=None):
        """Bộ ảnh mẫu THẬT SỰ dùng cho (tầng, ô) — công cụ chẩn đoán phải soi đúng bộ này."""
        return self._set_for(level, side)

    @property
    def ready(self) -> bool:
        """Cần ÍT NHẤT 2 ảnh mẫu trong một bộ nào đó.

        Với đúng 1 ảnh mẫu thì `second_score` luôn = 0, phép kiểm cách biệt
        (MARGIN_RATIO) thành `best >= 1.8` — tức là vô hiệu. Mọi kiện hàng đưa vào
        khung đều được gán chính cái nhãn duy nhất đó, và robot chở tất cả về một
        nhà máy. Thà rơi hẳn về HSV màu (phân biệt được cả 4) còn hơn.
        """
        return self._orb is not None and any(len(s) >= 2 for s in self._sets.values())

    # ----------------------------------------------------------
    # So khớp
    # ----------------------------------------------------------

    def _good_matches(self, des_query, des_train):
        """Lowe's ratio test — trả về list DMatch đã lọc."""
        if des_query is None or des_train is None:
            return []
        if len(des_query) < 2 or len(des_train) < 2:
            return []
        pairs = self._matcher.knnMatch(des_query, des_train, k=2)
        good = []
        for pair in pairs:
            if len(pair) != 2:
                continue
            m, n = pair
            if m.distance < LOWE_RATIO * n.distance:
                good.append(m)
        return good

    def _inlier_count(self, kp_query, kp_train, good_matches) -> int:
        """RANSAC homography — đếm inlier (khớp hình học nhất quán, không phải trùng hợp
        ngẫu nhiên vài keypoint rời rạc từ nền lộn xộn).

        Không đủ điểm để chạy RANSAC → trả 0, KHÔNG trả len(good_matches).

        Trước đây trả nguyên số good match với ghi chú "rất thấp" — đúng khi
        MIN_INLIERS còn là 10, nhưng ngưỡng đã hạ xuống 6 (config.SHAPE_MIN_INLIERS)
        trong khi MIN_MATCHES_FOR_HOMOGRAPHY vẫn là 8. Cửa sổ 6-7 match vì thế lọt
        thẳng qua ngưỡng mà CHƯA HỀ được kiểm nhất quán hình học — đúng loại trùng
        hợp ngẫu nhiên mà RANSAC sinh ra để loại. Nhận nhầm nhà máy thì mất 20 điểm
        và log vẫn báo thành công; quét trượt thì chỉ tốn 1 lần retry.
        """
        if len(good_matches) < MIN_MATCHES_FOR_HOMOGRAPHY:
            return 0

        src_pts = np.float32([kp_query[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_train[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD)
        if mask is None:
            return 0
        return int(mask.sum())

    def classify(self, frame_bgr, level=None, side=None) -> tuple[str | None, int]:
        """So khớp 1 ảnh (đã cắt ROI) với các ảnh mẫu của ĐÚNG tổ hợp (tầng, ô).
        Trả về (label, số_inlier) hoặc (None, số_inlier_cao_nhất) nếu không đủ tự tin.

        Cần cả 2 điều kiện: (1) vượt MIN_INLIERS tuyệt đối, VÀ (2) cách biệt rõ với
        kiện đứng thứ 2 (>= MARGIN_RATIO lần). Chỉ riêng ngưỡng tuyệt đối không đủ —
        đo thật trên Pi thấy khi bệ TRỐNG (không có kiện hàng nào), nền vẫn có thể
        cho 1 nhãn gần chạm ngưỡng trong khi nhãn thứ 2 sát nút ngay phía sau (vd 4
        so với 3) — dễ báo nhầm nếu ánh sáng đổi nhẹ đẩy qua ngưỡng. Kiện hàng thật
        luôn cách biệt rõ hơn hẳn (vd 7 so với 3)."""
        if self._orb is None:
            return None, 0
        templates = self._set_for(level, side)
        if len(templates) < 2:
            return None, 0

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        kp, des = self._orb.detectAndCompute(gray, None)
        if des is None or len(kp) < 2:
            return None, 0

        scores = {}
        for label, (tkp, tdes) in templates.items():
            good = self._good_matches(des, tdes)
            scores[label] = self._inlier_count(kp, tkp, good)

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        best_label, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0

        if best_score >= MIN_INLIERS and best_score >= MARGIN_RATIO * max(second_score, 1):
            return best_label, best_score
        return None, best_score
