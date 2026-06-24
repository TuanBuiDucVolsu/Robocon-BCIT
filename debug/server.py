"""
Giao diện web debug — điều khiển robot bằng tay khi luyện tập.
CHỈ DÙNG KHI DEBUG_MODE = True. KHÔNG DÙNG KHI THI ĐẤU.
"""

import os
import time
import logging
import threading

from flask import Flask, render_template, Response, jsonify, request

import config
from control import Motion, Lift
from control.motion import LineSensor
from control.mcp3008_bus import get_mcp3008_bus, reset_mcp3008_bus
from vision import Vision

logger = logging.getLogger(__name__)

# Singleton instances — chia sẻ giữa các route
_motion: Motion | None = None
_lift: Lift | None = None
_vision: Vision | None = None
_hw_error: str | None = None
_lock = threading.Lock()


def _init_hardware():
    """Khởi tạo phần cứng 1 lần duy nhất (lazy init)."""
    global _motion, _lift, _vision, _hw_error
    if _motion is not None or _hw_error is not None:
        return
    try:
        bus = get_mcp3008_bus()
        _motion = Motion(mcp_bus=bus)
        _lift = Lift(mcp_bus=bus)
        _vision = Vision()
        logger.info("Phần cứng đã khởi tạo thành công")
    except Exception as e:
        _hw_error = str(e)
        logger.warning("Không thể khởi tạo phần cứng: %s", e)


def create_app() -> Flask:
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    # Khởi tạo phần cứng khi app bắt đầu
    with app.app_context():
        _init_hardware()

    # ----------------------------------------------------------
    # Bắt lỗi chung — luôn trả JSON, không trả HTML
    # ----------------------------------------------------------

    @app.errorhandler(Exception)
    def handle_error(e):
        logger.error("Lỗi API: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"ok": False, "error": "Endpoint không tồn tại"}), 404

    # ----------------------------------------------------------
    # Trang chính
    # ----------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html", config=config)

    # ----------------------------------------------------------
    # Điều khiển di chuyển
    # ----------------------------------------------------------

    @app.route("/api/move", methods=["POST"])
    def move():
        if _motion is None:
            return jsonify({"ok": False, "error": _hw_error or "Phần cứng chưa sẵn sàng"})

        data = request.get_json(force=True)
        action = data.get("action", "stop")
        speed = float(data.get("speed", config.SPEED_DEFAULT))

        with _lock:
            if action == "forward":
                _motion.forward(speed)
            elif action == "backward":
                _motion.backward(speed)
            elif action == "left":
                _motion.turn_left(speed)
            elif action == "right":
                _motion.turn_right(speed)
            else:
                _motion.stop()

        logger.info("Di chuyển: %s (speed=%.0f)", action, speed)
        return jsonify({"ok": True, "action": action})

    # ----------------------------------------------------------
    # Điều khiển nâng/hạ
    # ----------------------------------------------------------

    @app.route("/api/lift", methods=["POST"])
    def lift_control():
        if _lift is None:
            return jsonify({"ok": False, "error": _hw_error or "Phần cứng chưa sẵn sàng"})

        data = request.get_json(force=True)
        action = data.get("action")

        with _lock:
            if action == "up":
                level = min(_lift._current_level + 1, 2)
                _lift.go_to_level(level)
            elif action == "down":
                level = max(_lift._current_level - 1, 0)
                _lift.go_to_level(level)
            elif action == "pickup":
                shelf = int(data.get("shelf", 1))
                _lift.pickup(shelf)
            elif action == "dropoff":
                _lift.dropoff()
            elif action == "reset":
                _lift.reset()

        current = _lift._current_level
        logger.info("Nâng/hạ: %s -> tầng %d", action, current)
        return jsonify({"ok": True, "action": action, "level": current})

    # ----------------------------------------------------------
    # Cảm biến dò line
    # ----------------------------------------------------------

    @app.route("/api/line_sensor")
    def line_sensor():
        if _motion is None:
            return jsonify({
                "values": [0] * config.LINE_SENSOR_COUNT,
                "raw_adc": [1023] * config.LINE_SENSOR_COUNT,
                "error": 0.0,
                "active": 0,
                "is_intersection": False,
                "hw_error": _hw_error,
            })

        with _lock:
            raw = _motion.read_line_sensor_raw()
            values = LineSensor.digital_from_raw(raw)
            error = _motion.compute_line_error_analog(raw)
        active = sum(values)
        raw_adc = [int(round(v * 1023)) for v in raw]
        return jsonify({
            "values": values,
            "raw_adc": raw_adc,
            "error": round(error, 2),
            "active": active,
            "is_intersection": active >= config.INTERSECTION_THRESHOLD,
        })

    @app.route("/api/pallet_sensor")
    def pallet_sensor():
        if _lift is None:
            return jsonify({
                "left": False,
                "right": False,
                "left_adc": 1023,
                "right_adc": 1023,
                "ok": False,
                "hw_error": _hw_error,
            })

        with _lock:
            left, right, ok = _lift.pallet.read_status()
            left_adc, right_adc = _lift.pallet.read_adc()
        return jsonify({
            "left": left,
            "right": right,
            "left_adc": left_adc,
            "right_adc": right_adc,
            "ok": ok,
            "threshold": config.PALLET_THRESHOLD,
        })

    # ----------------------------------------------------------
    # Camera — stream MJPEG + chụp + nhận diện
    # ----------------------------------------------------------

    def _generate_mjpeg():
        """Generator trả về MJPEG stream từ camera."""
        if _vision is None or _vision._camera is None:
            return

        try:
            import cv2
        except ImportError:
            return

        while True:
            frame = _vision._capture_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            # Chuyển RGB (picamera2) sang BGR (OpenCV) để encode JPEG
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            else:
                frame_bgr = frame

            _, jpeg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            )
            time.sleep(0.05)  # ~20 FPS

    @app.route("/api/camera/stream")
    def camera_stream():
        return Response(
            _generate_mjpeg(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @app.route("/api/camera/capture")
    def camera_capture():
        if _vision is None or _vision._camera is None:
            return jsonify({"ok": False, "error": "Camera không khả dụng"}), 503

        frame = _vision._capture_frame()
        if frame is None:
            return jsonify({"ok": False, "error": "Không chụp được ảnh"}), 500

        try:
            import cv2
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            _, jpeg = cv2.imencode(".jpg", frame_bgr)
            return Response(jpeg.tobytes(), mimetype="image/jpeg")
        except ImportError:
            return jsonify({"ok": False, "error": "OpenCV không khả dụng"}), 500

    @app.route("/api/vision/classify", methods=["POST"])
    def classify():
        if _vision is None:
            return jsonify({"ok": False, "label": None, "confidence": 0,
                            "factory": None, "error": "Vision chưa sẵn sàng"})

        label, confidence = _vision.classify_package()
        factory = _vision.get_factory_name(label) if label else None
        return jsonify({
            "ok": label is not None,
            "label": label,
            "confidence": round(confidence * 100, 1),
            "factory": factory,
        })

    @app.route("/api/vision/classify_pair", methods=["POST"])
    def classify_pair():
        if _vision is None:
            return jsonify({"ok": False, "left": None, "right": None,
                            "error": "Vision chưa sẵn sàng"})

        label_l, label_r = _vision.classify_pair()
        factory_l = _vision.get_factory_name(label_l) if label_l else None
        factory_r = _vision.get_factory_name(label_r) if label_r else None
        return jsonify({
            "ok": label_l is not None and label_r is not None,
            "left": {"label": label_l, "factory": factory_l},
            "right": {"label": label_r, "factory": factory_r},
        })

    # ----------------------------------------------------------
    # Trạng thái & cấu hình
    # ----------------------------------------------------------

    @app.route("/api/status")
    def status():
        hw_ok = _motion is not None
        line_values = [0] * config.LINE_SENSOR_COUNT
        pallet = {"left": False, "right": False, "ok": False}
        if _motion and _lift:
            with _lock:
                line_values = _motion.read_line_sensor()
                left, right, ok = _lift.pallet.read_status()
                pallet = {"left": left, "right": right, "ok": ok}
        return jsonify({
            "hw_ok": hw_ok,
            "hw_error": _hw_error,
            "lift_level": _lift._current_level if _lift else 0,
            "line_sensor": line_values,
            "pallet": pallet,
            "camera_ready": _vision._camera is not None if _vision else False,
            "vision_method": "HSV color",
        })

    @app.route("/api/config")
    def get_config():
        return jsonify({
            "speed_default": config.SPEED_DEFAULT,
            "speed_slow": config.SPEED_SLOW,
            "speed_turn": config.SPEED_TURN,
            "lift_speed": config.LIFT_SPEED,
            "confidence_threshold": config.CONFIDENCE_THRESHOLD,
            "pwm_compensation": config.PWM_COMPENSATION,
        })

    # ----------------------------------------------------------
    # Cleanup khi tắt server
    # ----------------------------------------------------------

    @app.route("/api/shutdown", methods=["POST"])
    def shutdown():
        global _motion, _lift, _vision
        with _lock:
            if _motion:
                _motion.cleanup()
            if _lift:
                _lift.cleanup()
            if _vision:
                _vision.cleanup()
            reset_mcp3008_bus()
            _motion = _lift = _vision = None
        logger.info("Đã cleanup phần cứng")
        return jsonify({"ok": True})

    return app


def run_debug_server():
    """Khởi chạy server debug."""
    app = create_app()
    logger.info("Giao diện debug: http://0.0.0.0:%d", config.WEB_PORT)
    app.run(host="0.0.0.0", port=config.WEB_PORT, threaded=True, debug=False)
