"""
Module nhận diện kiện hàng.

Phương pháp CHÍNH: so khớp đặc trưng ORB theo hình dạng/hoạ tiết decal
(shape_match.ShapeMatcher) — bền với nền lạ (tường, dây điện, bàn ghế...) vì so
theo HÌNH chứ không chỉ màu. Cần ảnh mẫu thật, tạo bằng
`python3 -m tools.capture_templates`.

Phương pháp DỰ PHÒNG: phân tích màu HSV (_classify_by_color) — dùng khi chưa có
ảnh mẫu ORB hoặc ORB không khớp đủ tự tin. 4 kiện hàng có màu chủ đạo khác nhau:
  - Samsung (01): xanh dương (chip xanh)
  - Foxconn (02): vàng (chip vàng đồng)
  - Amkor   (03): xám bạc (khối nhôm Al)
  - Hana    (04): đỏ/hồng (QR code viền đỏ)
Nhạy với nền lạ hơn ORB vì chỉ dựa vào màu — xem CLAUDE.md.

Cả 2 phương pháp đều thuần OpenCV cổ điển, không dùng model AI/deep learning,
không cần huấn luyện — xử lý cục bộ trên Pi, đúng thể lệ.
"""

import logging
import time

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None

import config
from .shape_match import ShapeMatcher, inliers_to_confidence

logger = logging.getLogger(__name__)


def _center_weight_map(shape):
    """
    Trọng số Gauss theo khoảng cách tới tâm ROI: tâm=1.0, biên giảm dần nhưng
    KHÔNG về 0 (không cắt cứng như tăng ROI_MARGIN — không mất góc ngoặc đỏ của
    Hana). Giảm ảnh hưởng của nền (kệ đen/pallet nâu) hay lấn ở rìa ROI khi kiện
    hàng nhỏ hoặc robot tiếp cận không canh giữa tuyệt đối.
    """
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    scale = min(h, w) / 2.0
    dist = np.sqrt(((yy - cy) / scale) ** 2 + ((xx - cx) / scale) ** 2)
    sigma = getattr(config, "CENTER_WEIGHT_SIGMA", 0.85)
    return np.exp(-(dist ** 2) / (2 * sigma ** 2))


class Vision:
    """Nhận diện kiện hàng — ORB (hình dạng) là chính, HSV màu là dự phòng."""

    def __init__(self):
        self._camera = None
        self._init_camera()
        self._shape_matcher = ShapeMatcher()
        if not self._shape_matcher.ready:
            logger.warning("ShapeMatcher (ORB) chưa sẵn sàng — sẽ dùng HSV màu làm chính "
                            "cho đến khi có ảnh mẫu (chạy `python3 -m tools.capture_templates`)")

    # ----------------------------------------------------------
    # Khởi tạo camera
    # ----------------------------------------------------------

    def _init_camera(self):
        if Picamera2 is None:
            logger.warning("picamera2 không khả dụng — camera bị vô hiệu hoá")
            return

        try:
            self._camera = Picamera2()
            # create_preview_configuration (không phải still) vì app chụp liên tục
            # nhiều lần/giây — chế độ still tối ưu cho 1 tấm ảnh đơn, AWB hội tụ
            # chậm/khác nên màu bị lệch khi dùng để chụp lặp lại như rpicam-hello preview.
            # picamera2 đặt tên format ngược trực giác: yêu cầu "RGB888" mới trả về
            # mảng thứ tự BGR mà OpenCV cần — đã xác nhận bằng test_vision.py test 8
            # (vật màu đỏ thuần: kênh 0 cao hơn kênh 2 khi xin "BGR888", tức mảng
            # thực ra là RGB). Đổi sang "RGB888" để có đúng thứ tự BGR.
            cam_config = self._camera.create_preview_configuration(
                main={"size": config.CAMERA_RESOLUTION, "format": "RGB888"}
            )
            self._camera.configure(cam_config)
            self._camera.start()
            time.sleep(2.0)  # chờ AWB/AE hội tụ trước khi chụp
            logger.info("Camera đã sẵn sàng (picamera2)")
        except Exception as e:
            logger.error("Lỗi khởi tạo camera: %s", e)
            self._camera = None

    # ----------------------------------------------------------
    # Chụp ảnh
    # ----------------------------------------------------------

    def _capture_frame(self):
        """Chụp 1 frame từ camera, trả về numpy array (BGR) hoặc None."""
        if self._camera is None:
            return None

        try:
            return self._camera.capture_array("main")
        except Exception as e:
            logger.warning("Không chụp được frame: %s", e)
            return None

    # ----------------------------------------------------------
    # Cắt ROI (dùng chung cho cả ORB lẫn HSV)
    # ----------------------------------------------------------

    def _crop_roi(self, frame):
        """Cắt vùng trung tâm (bỏ viền ngoài). ROI_MARGIN tinh chỉnh trong config."""
        h, w = frame.shape[:2]
        margin = getattr(config, "ROI_MARGIN", 0.2)
        margin_x = int(w * margin)
        margin_y = int(h * margin)
        return frame[margin_y:h - margin_y, margin_x:w - margin_x]

    # ----------------------------------------------------------
    # Nhận diện bằng hình dạng (ORB) — phương pháp CHÍNH
    # ----------------------------------------------------------

    def _classify_by_shape(self, frame) -> tuple[str | None, float]:
        """So khớp ROI với ảnh mẫu bằng ORB. Trả về (label, confidence quy đổi 0-1)
        hoặc (None, confidence) nếu không đủ tự tin (xem shape_match.MIN_INLIERS)."""
        roi = self._crop_roi(frame)
        label, inliers = self._shape_matcher.classify(roi)
        return label, inliers_to_confidence(inliers)

    # ----------------------------------------------------------
    # Phân tích màu HSV — phương pháp DỰ PHÒNG
    # ----------------------------------------------------------

    def _classify_by_color(self, frame) -> tuple[str, float]:
        """
        Phân tích màu HSV vùng trung tâm ảnh.
        Trả về (label, confidence).
        """
        roi = self._crop_roi(frame)

        # picamera2 format="RGB888" (xem _init_camera) trả về đúng thứ tự BGR mà OpenCV cần
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Trọng số theo khoảng cách tới tâm ROI — pixel giữa khung hình (nơi khối
        # hàng thật nằm) tính nặng hơn pixel ở rìa (nơi nền kệ/pallet hay lấn vào).
        # KHÔNG áp cho Hana: ngoặc đỏ của Hana nằm ở GÓC ROI (xem ROI_MARGIN ở
        # config.py) — trọng số tâm sẽ dập tắt đúng đặc điểm nhận diện của nó.
        center_weight = _center_weight_map(hsv.shape[:2])
        uniform_weight = np.ones_like(center_weight)
        no_center_weight = getattr(config, "NO_CENTER_WEIGHT_LABELS", ("hana_micron",))
        scores = {}

        for label, ranges in config.COLOR_RANGES.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for lower, upper in ranges:
                lower_np = np.array(lower, dtype=np.uint8)
                upper_np = np.array(upper, dtype=np.uint8)
                mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower_np, upper_np))
            weight = uniform_weight if label in no_center_weight else center_weight
            scores[label] = float((weight * (mask > 0)).sum() / weight.sum())

        # Ưu tiên màu sắc nét hơn Amkor (xám) để nền trắng/xám không "ăn" mất
        # kiện có màu. Chỉ rơi về Amkor khi không màu chromatic nào đạt ngưỡng.
        chromatic = {l: scores[l] for l in config.CHROMATIC_LABELS if l in scores}
        if chromatic:
            best_chroma = max(chromatic, key=chromatic.get)
            if chromatic[best_chroma] >= config.CONFIDENCE_THRESHOLD:
                best_label, best_score = best_chroma, chromatic[best_chroma]
            else:
                best_label = max(scores, key=scores.get)
                best_score = scores[best_label]
        else:
            best_label = max(scores, key=scores.get)
            best_score = scores[best_label]

        logger.debug("Tỷ lệ màu: %s -> %s",
                      {k: f"{v*100:.1f}%" for k, v in sorted(scores.items(), key=lambda x: -x[1])},
                      best_label)

        return best_label, best_score

    # ----------------------------------------------------------
    # Kết hợp ORB + HSV
    # ----------------------------------------------------------

    def _classify_frame(self, frame) -> tuple[str | None, float, bool]:
        """Nhận diện 1 frame: ORB trước (nếu đã có ảnh mẫu), rơi về HSV màu nếu ORB
        không đủ tự tin hoặc chưa có ảnh mẫu (xem shape_match.MIN_INLIERS).
        Trả về (label, confidence, from_orb). from_orb=True nghĩa là ORB đã TỰ quyết
        định đủ tự tin (MIN_INLIERS + MARGIN_RATIO trong ShapeMatcher.classify) — caller
        nên chấp nhận ngay, KHÔNG so confidence quy đổi với CONFIDENCE_THRESHOLD nữa
        (ngưỡng đó chỉ có ý nghĩa với thang % pixel của HSV, không phải thang ORB)."""
        if self._shape_matcher.ready:
            label, confidence = self._classify_by_shape(frame)
            if label is not None:
                return label, confidence, True
        label, confidence = self._classify_by_color(frame)
        return label, confidence, False

    # ----------------------------------------------------------
    # API chính
    # ----------------------------------------------------------

    def classify_package(self) -> tuple[str | None, float]:
        """
        Chụp ảnh và nhận diện kiện hàng bằng phân tích màu.
        Retry nếu confidence thấp.
        Trả về (label, confidence) hoặc (None, 0.0) nếu thất bại.
        """
        if cv2 is None or np is None:
            logger.error("OpenCV/numpy không khả dụng")
            return None, 0.0

        if self._camera is None:
            logger.error("Camera chưa sẵn sàng")
            return None, 0.0

        best_label = None
        best_conf = 0.0

        for attempt in range(1, config.MAX_SCAN_RETRIES + 1):
            frame = self._capture_frame()
            if frame is None:
                logger.warning("Lần %d: không chụp được ảnh", attempt)
                time.sleep(config.SCAN_RETRY_DELAY)
                continue

            label, confidence, from_orb = self._classify_frame(frame)
            logger.info("Lần %d: label=%s, confidence=%.1f%% (nguồn=%s)",
                        attempt, label, confidence * 100, "ORB" if from_orb else "HSV")

            if from_orb or confidence >= config.CONFIDENCE_THRESHOLD:
                return label, confidence

            if confidence > best_conf:
                best_label = label
                best_conf = confidence

            logger.warning("Confidence thấp (%.2f < %.2f), thử lại...",
                           confidence, config.CONFIDENCE_THRESHOLD)
            time.sleep(config.SCAN_RETRY_DELAY)

        logger.info("Kết quả tốt nhất sau %d lần: %s (%.1f%%)",
                     config.MAX_SCAN_RETRIES, best_label, best_conf * 100)
        if best_conf >= config.CONFIDENCE_THRESHOLD:
            return best_label, best_conf
        return None, best_conf

    def classify_pair(self) -> tuple[str | None, str | None]:
        """
        Quét 2 kiện hàng cạnh nhau trên cùng tầng kệ.
        Chia ảnh thành nửa trái + nửa phải, phân tích màu riêng.
        Trả về (label_trái, label_phải).
        """
        if cv2 is None or np is None or self._camera is None:
            logger.error("Vision chưa sẵn sàng")
            return None, None

        best_left, best_right = None, None
        best_conf_left, best_conf_right = 0.0, 0.0
        best_ok_left, best_ok_right = False, False

        for attempt in range(1, config.MAX_SCAN_RETRIES + 1):
            frame = self._capture_frame()
            if frame is None:
                time.sleep(config.SCAN_RETRY_DELAY)
                continue

            h, w = frame.shape[:2]
            mid = w // 2
            frame_left = frame[:, :mid]
            frame_right = frame[:, mid:]

            label_l, conf_l, from_orb_l = self._classify_frame(frame_left)
            label_r, conf_r, from_orb_r = self._classify_frame(frame_right)
            logger.info("Lần %d: trái=%s (%.1f%%, %s), phải=%s (%.1f%%, %s)",
                        attempt, label_l, conf_l * 100, "ORB" if from_orb_l else "HSV",
                        label_r, conf_r * 100, "ORB" if from_orb_r else "HSV")

            # ORB đã tự quyết định đủ tự tin — không so confidence quy đổi với
            # CONFIDENCE_THRESHOLD nữa (chỉ có ý nghĩa với % pixel của HSV).
            ok_l = from_orb_l or conf_l >= config.CONFIDENCE_THRESHOLD
            ok_r = from_orb_r or conf_r >= config.CONFIDENCE_THRESHOLD

            if conf_l > best_conf_left:
                best_left, best_conf_left, best_ok_left = label_l, conf_l, ok_l
            if conf_r > best_conf_right:
                best_right, best_conf_right, best_ok_right = label_r, conf_r, ok_r

            if ok_l and ok_r:
                return label_l, label_r

            time.sleep(config.SCAN_RETRY_DELAY)

        logger.info("Kết quả tốt nhất: trái=%s (%.1f%%), phải=%s (%.1f%%)",
                     best_left, best_conf_left * 100, best_right, best_conf_right * 100)

        left = best_left if best_ok_left else None
        right = best_right if best_ok_right else None
        return left, right

    def get_factory_name(self, label: str) -> str | None:
        """Chuyển label thành tên nhà máy tương ứng."""
        return config.LABEL_TO_FACTORY.get(label)

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def cleanup(self):
        if self._camera is not None:
            self._camera.stop()
            self._camera.close()
            logger.info("Đã đóng camera")
