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
Lưu tại vision/templates/{label}.png.
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

# Số keypoint tối đa trích xuất mỗi ảnh — nhiều hơn thì chính xác hơn nhưng chậm hơn trên Pi.
ORB_FEATURES = 500
# Lowe's ratio test: match "tốt" khi khoảng cách gần nhất < LOWE_RATIO * khoảng cách gần nhì.
# Thấp hơn = khắt khe hơn (ít match nhiễu hơn nhưng cũng ít match thật hơn).
LOWE_RATIO = 0.75
# Số điểm khớp tối thiểu (sau ratio test) mới thử tính homography — RANSAC cần >=4 điểm.
MIN_MATCHES_FOR_HOMOGRAPHY = 8
# Số inlier RANSAC tối thiểu mới coi là nhận diện được kiện đó (đủ tự tin, không phải
# trùng hợp vài keypoint lẻ tẻ từ nền).
MIN_INLIERS = getattr(config, "SHAPE_MIN_INLIERS", 10)
RANSAC_REPROJ_THRESHOLD = 5.0
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
        self._templates = {}  # label -> (keypoints, descriptors)
        if cv2 is None or np is None:
            logger.warning("OpenCV/numpy không khả dụng — ShapeMatcher vô hiệu hoá")
            return
        self._orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._load_templates()

    # ----------------------------------------------------------
    # Nạp ảnh mẫu
    # ----------------------------------------------------------

    def _load_templates(self):
        if not os.path.isdir(TEMPLATE_DIR):
            logger.warning("Chưa có thư mục ảnh mẫu (%s) — chạy "
                            "`python3 -m tools.capture_templates` trên Pi trước", TEMPLATE_DIR)
            return
        for label in config.LABEL_TO_FACTORY:
            path = os.path.join(TEMPLATE_DIR, f"{label}.png")
            if not os.path.isfile(path):
                logger.warning("Thiếu ảnh mẫu: %s", path)
                continue
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                logger.warning("Không đọc được ảnh mẫu: %s", path)
                continue
            kp, des = self._orb.detectAndCompute(img, None)
            if des is None or len(kp) < MIN_MATCHES_FOR_HOMOGRAPHY:
                logger.warning("Ảnh mẫu %s quá ít đặc trưng (%d keypoint) — chụp lại nét hơn/gần hơn",
                                path, len(kp) if kp else 0)
                continue
            self._templates[label] = (kp, des)
        logger.info("Đã nạp %d/%d ảnh mẫu ORB", len(self._templates), len(config.LABEL_TO_FACTORY))

    @property
    def ready(self) -> bool:
        return self._orb is not None and len(self._templates) > 0

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
        ngẫu nhiên vài keypoint rời rạc từ nền lộn xộn)."""
        if len(good_matches) < MIN_MATCHES_FOR_HOMOGRAPHY:
            return len(good_matches)  # quá ít để tính homography, trả nguyên số good match (rất thấp)

        src_pts = np.float32([kp_query[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_train[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD)
        if mask is None:
            return 0
        return int(mask.sum())

    def classify(self, frame_bgr) -> tuple[str | None, int]:
        """So khớp 1 ảnh (đã cắt ROI) với các ảnh mẫu.
        Trả về (label, số_inlier) hoặc (None, số_inlier_cao_nhất) nếu không đủ tự tin."""
        if not self.ready:
            return None, 0

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        kp, des = self._orb.detectAndCompute(gray, None)
        if des is None or len(kp) < 2:
            return None, 0

        best_label, best_score = None, 0
        for label, (tkp, tdes) in self._templates.items():
            good = self._good_matches(des, tdes)
            score = self._inlier_count(kp, tkp, good)
            if score > best_score:
                best_label, best_score = label, score

        if best_score >= MIN_INLIERS:
            return best_label, best_score
        return None, best_score
