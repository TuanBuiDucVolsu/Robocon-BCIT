"""
Module nhận diện kiện hàng bằng phân tích màu HSV.
4 kiện hàng có màu chủ đạo khác nhau rõ ràng:
  - Samsung (01): xanh dương (chip xanh)
  - Foxconn (02): vàng (chip vàng đồng)
  - Amkor   (03): xám bạc (khối nhôm Al)
  - Hana    (04): đỏ/hồng (QR code viền đỏ)
Không cần model AI — chỉ dùng OpenCV.
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

logger = logging.getLogger(__name__)


class Vision:
    """Nhận diện kiện hàng bằng phân tích màu HSV từ camera."""

    def __init__(self):
        self._camera = None
        self._init_camera()

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
        """Chụp 1 frame từ camera, trả về numpy array (RGB) hoặc None."""
        if self._camera is None:
            return None

        try:
            return self._camera.capture_array("main")
        except Exception as e:
            logger.warning("Không chụp được frame: %s", e)
            return None

    # ----------------------------------------------------------
    # Phân tích màu HSV
    # ----------------------------------------------------------

    def _classify_by_color(self, frame) -> tuple[str, float]:
        """
        Phân tích màu HSV vùng trung tâm ảnh.
        Trả về (label, confidence).
        """
        h, w = frame.shape[:2]

        # Cắt vùng trung tâm (bỏ viền ngoài). ROI_MARGIN tinh chỉnh trong config.
        margin = getattr(config, "ROI_MARGIN", 0.2)
        margin_x = int(w * margin)
        margin_y = int(h * margin)
        roi = frame[margin_y:h - margin_y, margin_x:w - margin_x]

        # Chuyển RGB → BGR → HSV (picamera2 trả về RGB)
        bgr = cv2.cvtColor(roi, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        total_pixels = roi.shape[0] * roi.shape[1]
        scores = {}

        for label, ranges in config.COLOR_RANGES.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for lower, upper in ranges:
                lower_np = np.array(lower, dtype=np.uint8)
                upper_np = np.array(upper, dtype=np.uint8)
                mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower_np, upper_np))
            pixel_count = int(cv2.countNonZero(mask))
            scores[label] = pixel_count / total_pixels

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

            label, confidence = self._classify_by_color(frame)
            logger.info("Lần %d: label=%s, confidence=%.1f%%",
                        attempt, label, confidence * 100)

            if confidence > best_conf:
                best_label = label
                best_conf = confidence

            if confidence >= config.CONFIDENCE_THRESHOLD:
                return label, confidence

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

        for attempt in range(1, config.MAX_SCAN_RETRIES + 1):
            frame = self._capture_frame()
            if frame is None:
                time.sleep(config.SCAN_RETRY_DELAY)
                continue

            h, w = frame.shape[:2]
            mid = w // 2
            frame_left = frame[:, :mid]
            frame_right = frame[:, mid:]

            label_l, conf_l = self._classify_by_color(frame_left)
            label_r, conf_r = self._classify_by_color(frame_right)
            logger.info("Lần %d: trái=%s (%.1f%%), phải=%s (%.1f%%)",
                        attempt, label_l, conf_l * 100, label_r, conf_r * 100)

            if conf_l > best_conf_left:
                best_left, best_conf_left = label_l, conf_l
            if conf_r > best_conf_right:
                best_right, best_conf_right = label_r, conf_r

            if (conf_l >= config.CONFIDENCE_THRESHOLD and
                    conf_r >= config.CONFIDENCE_THRESHOLD):
                return label_l, label_r

            time.sleep(config.SCAN_RETRY_DELAY)

        logger.info("Kết quả tốt nhất: trái=%s (%.1f%%), phải=%s (%.1f%%)",
                     best_left, best_conf_left * 100, best_right, best_conf_right * 100)
        
        left = best_left if best_conf_left >= config.CONFIDENCE_THRESHOLD else None
        right = best_right if best_conf_right >= config.CONFIDENCE_THRESHOLD else None
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
