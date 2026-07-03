"""
Module điều khiển động cơ di chuyển, cảm biến dò line, và cảm biến siêu âm.
Line sensor: QTR-8A (analog) qua MCP3008 (SPI ADC).
Dùng gpiozero (tương thích RPi 4 trên cả Bullseye lẫn Bookworm).
"""

import time
import logging

try:
    from gpiozero import PWMOutputDevice, DigitalOutputDevice, DistanceSensor, Device
    Device.ensure_pin_factory()
except Exception:
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        from gpiozero import PWMOutputDevice, DigitalOutputDevice, DistanceSensor
    except ImportError:
        from unittest.mock import MagicMock
        PWMOutputDevice = MagicMock
        DigitalOutputDevice = MagicMock
        DistanceSensor = MagicMock

import config
from control.mcp3008_bus import Mcp3008Bus, get_mcp3008_bus

logger = logging.getLogger(__name__)


class LineSensor:
    """Đọc QTR-8A 6 mắt qua MCP3008 SPI (analog 0.0-1.0)."""

    def __init__(self, bus: Mcp3008Bus | None = None):
        self._bus = bus or get_mcp3008_bus()
        self._channels = list(range(config.LINE_SENSOR_COUNT))
        self.available = self._bus.available

    @staticmethod
    def _threshold_norm() -> float:
        return config.LINE_THRESHOLD / 1023.0

    def read_raw(self) -> list[float]:
        """Đọc giá trị analog 0.0-1.0, chuẩn hoá sao cho 0.0 = đen/line, 1.0 = trắng/nền.

        Nếu config.LINE_BLACK_IS_HIGH=True (QTR-8A đọc đen ra giá trị cao) thì đảo
        tín hiệu ngay tại đây, để toàn bộ logic phía dưới giữ nguyên giả định
        "0.0 = trên line".
        """
        if not self.available:
            return [1.0] * config.LINE_SENSOR_COUNT
        raw = self._bus.read_many(self._channels)
        if not self._bus.last_read_ok:
            # Lỗi đọc SPI/ADC — trả giá trị trung tính "không thấy line" thay vì
            # đảo cực fallback thành "trên line" giả (tránh giao lộ giả).
            return [1.0] * config.LINE_SENSOR_COUNT
        if getattr(config, "LINE_BLACK_IS_HIGH", False):
            return [1.0 - v for v in raw]
        return raw

    @staticmethod
    def digital_from_raw(raw: list[float]) -> list[int]:
        threshold = LineSensor._threshold_norm()
        return [1 if v < threshold else 0 for v in raw]

    def read(self) -> list[int]:
        """Đọc digital (0/1) sau ngưỡng — tương thích API cũ."""
        return self.digital_from_raw(self.read_raw())

    def read_adc(self) -> list[int]:
        """Đọc giá trị ADC 0-1023 cho từng mắt."""
        return [int(round(v * 1023)) for v in self.read_raw()]

    def cleanup(self):
        pass


class Motion:
    """Điều khiển 2 động cơ bánh xe (trái/phải) với PWM qua L298N."""

    def __init__(self, mcp_bus: Mcp3008Bus | None = None):
        self._mcp_bus = mcp_bus or get_mcp3008_bus()

        # Bánh trái: IN1 = PWM (tiến), IN2 = PWM (lùi) — PWM cả 2 chiều để điều tốc
        self._left_fwd = PWMOutputDevice(config.IN1_XE_T, frequency=config.PWM_FREQUENCY)
        self._left_rev = PWMOutputDevice(config.IN2_XE_T, frequency=config.PWM_FREQUENCY)

        # Bánh phải: IN1 = PWM (tiến), IN2 = PWM (lùi)
        self._right_fwd = PWMOutputDevice(config.IN1_XE_P, frequency=config.PWM_FREQUENCY)
        self._right_rev = PWMOutputDevice(config.IN2_XE_P, frequency=config.PWM_FREQUENCY)

        self._line_sensor = LineSensor(self._mcp_bus)
        self._last_error = 0.0

        # Cảm biến siêu âm HC-SR04
        try:
            self._distance_sensor = DistanceSensor(
                echo=config.ULTRASONIC_ECHO_PIN,
                trigger=config.ULTRASONIC_TRIG_PIN,
                max_distance=1.0,
            )
            logger.info("Cảm biến siêu âm HC-SR04 đã sẵn sàng")
        except Exception as e:
            self._distance_sensor = None
            logger.warning("Cảm biến siêu âm không khả dụng (%s)", e)

    # ----------------------------------------------------------
    # Tiện ích
    # ----------------------------------------------------------

    @staticmethod
    def _pct(speed: float) -> float:
        return max(0.0, min(1.0, speed / 100.0))

    # ----------------------------------------------------------
    # Đo khoảng cách
    # ----------------------------------------------------------

    def get_distance(self, samples: int = 1) -> float:
        """Đo khoảng cách (cm). Trả -1.0 nếu không có cảm biến HOẶC lỗi đọc."""
        if self._distance_sensor is None:
            return -1.0
        try:
            if samples <= 1:
                return self._distance_sensor.distance * 100
            readings = [self._distance_sensor.distance * 100 for _ in range(samples)]
            readings.sort()
            return readings[len(readings) // 2]
        except Exception as e:
            logger.warning("Lỗi đọc cảm biến siêu âm: %s", e)
            return -1.0

    # ----------------------------------------------------------
    # Điều khiển cơ bản
    # ----------------------------------------------------------

    def forward(self, speed: float = config.SPEED_DEFAULT):
        logger.debug("Tiến - speed=%s", speed)
        self._left_rev.off()
        self._right_rev.off()
        self._left_fwd.value = self._pct(speed)
        self._right_fwd.value = self._pct(speed * config.PWM_COMPENSATION)

    def backward(self, speed: float = config.SPEED_DEFAULT):
        logger.debug("Lùi - speed=%s", speed)
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.value = self._pct(speed)
        self._right_rev.value = self._pct(speed * config.PWM_COMPENSATION)

    def turn_left(self, speed: float = config.SPEED_TURN):
        logger.debug("Xoay trái - speed=%s", speed)
        self._left_fwd.value = 0
        self._left_rev.value = self._pct(speed)
        self._right_rev.value = 0
        self._right_fwd.value = self._pct(speed * config.PWM_COMPENSATION)

    def turn_right(self, speed: float = config.SPEED_TURN):
        logger.debug("Xoay phải - speed=%s", speed)
        self._left_rev.value = 0
        self._left_fwd.value = self._pct(speed)
        self._right_fwd.value = 0
        self._right_rev.value = self._pct(speed * config.PWM_COMPENSATION)

    def stop(self):
        logger.debug("Dừng")
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.off()
        self._right_rev.off()

    # ----------------------------------------------------------
    # Xuất phát — tìm line đầu tiên
    # ----------------------------------------------------------

    def exit_start_zone(self, speed: float = config.EXIT_START_SPEED,
                        timeout: float = config.EXIT_START_TIMEOUT) -> bool:
        """
        Thoát ô start (GAP — không có line trên R0).

        Robot đặt quay mặt sang trái (9h, về Kệ 3):
        1. Tiến thẳng cho đến khi chạm line ngang R0
        2. Bám line ngắn để căn giữa (không đếm giao lộ — để ROUTE_START làm)
        Giao lộ được đếm trong ROUTE_START_TO_SHELF_0, tránh đếm kép.
        """
        logger.info("Thoát ô start — tiến thẳng tìm line R0 (speed=%d%%)", speed)
        start = time.time()
        self.forward(speed)

        found = False
        while time.time() - start < timeout:
            values = self.read_line_sensor()
            if sum(values) > 0:
                self.stop()
                logger.info("Chạm line R0! sensor=%s", values)
                found = True
                break
            time.sleep(0.01)

        if not found:
            self.stop()
            logger.error("KHÔNG tìm thấy line sau %.1fs! Kiểm tra hướng 9h / vị trí start.", timeout)
            return False

        logger.info("Căn giữa line (%.1fs)...", config.EXIT_START_ALIGN_TIME)
        align_start = time.time()
        while time.time() - align_start < config.EXIT_START_ALIGN_TIME:
            at_intersection, values = self.follow_line(speed)
            if at_intersection:
                logger.info("Chạm giao lộ khi căn line — dừng căn, ROUTE_START sẽ đếm")
                self.stop()
                break
            if sum(values) == 0:
                break
            time.sleep(0.01)

        self.stop()
        return True

    # ----------------------------------------------------------
    # Xoay 90° và điều hướng route
    # ----------------------------------------------------------

    def turn_left_90(self):
        logger.info("Xoay 90° trái")
        self.turn_left(config.SPEED_TURN)
        time.sleep(config.TURN_TIME)
        self.stop()

    def turn_right_90(self):
        logger.info("Xoay 90° phải")
        self.turn_right(config.SPEED_TURN)
        time.sleep(config.TURN_TIME)
        self.stop()

    def execute_route(self, route: list) -> bool:
        if not route:
            logger.warning("Route rỗng — không có bước điều hướng")
            return False

        for step in route:
            action = step[0]
            if action == "forward":
                count = step[1]
                if count > 0 and not self.navigate_intersections(count):
                    return False
            elif action == "left":
                self.turn_left_90()
            elif action == "right":
                self.turn_right_90()
            else:
                logger.warning("Lệnh route không hợp lệ: %s", step)
        return True

    # ----------------------------------------------------------
    # Tiếp cận kệ / lùi ra
    # ----------------------------------------------------------

    def approach_shelf(self, target_cm: float = config.APPROACH_DISTANCE) -> bool:
        """
        Tiếp cận kệ 2 pha: đi NHANH ở xa, chuyển CHẬM khi gần để dừng chính xác.
        Pha xa (> APPROACH_SLOW_DISTANCE): APPROACH_FAST_SPEED.
        Pha gần (≤ APPROACH_SLOW_DISTANCE): APPROACH_SLOW_SPEED.
        """
        if self._distance_sensor is None:
            logger.error("Không có cảm biến siêu âm — không thể tiếp cận kệ an toàn")
            return False

        logger.info("Tiếp cận kệ 2 pha — mục tiêu %.1fcm (nhanh %d%% → chậm %d%% dưới %.1fcm)",
                    target_cm, config.APPROACH_FAST_SPEED,
                    config.APPROACH_SLOW_SPEED, config.APPROACH_SLOW_DISTANCE)
        start = time.time()

        while time.time() - start < config.APPROACH_TIMEOUT:
            dist = self.get_distance(samples=3)  # median chống nhiễu HC-SR04
            if dist < 0:
                # Lỗi đọc mẫu này — KHÔNG hiểu nhầm thành "đã tới", thử lại
                time.sleep(0.02)
                continue
            if dist <= target_cm:
                self.stop()
                logger.info("Đã đến vị trí kệ — khoảng cách %.1fcm", dist)
                return True
            # Pha xa: nhanh; pha gần: chậm để dừng chính xác, không đâm kệ
            speed = (config.APPROACH_SLOW_SPEED
                     if dist <= config.APPROACH_SLOW_DISTANCE
                     else config.APPROACH_FAST_SPEED)
            self.forward(speed)
            time.sleep(0.02)

        self.stop()
        logger.warning("Timeout tiếp cận kệ sau %.1fs!", config.APPROACH_TIMEOUT)
        return False

    def retreat_from_shelf(self, target_cm: float = config.RETREAT_DISTANCE,
                           speed: float = config.APPROACH_SPEED) -> bool:
        if self._distance_sensor is None:
            logger.error("Không có cảm biến siêu âm — không thể lùi an toàn")
            return False

        logger.info("Lùi ra khỏi kệ — mục tiêu %.1fcm", target_cm)
        start = time.time()
        self.backward(speed)

        while time.time() - start < config.APPROACH_TIMEOUT:
            dist = self.get_distance(samples=3)  # median chống nhiễu HC-SR04
            if dist < 0:
                # Lỗi đọc mẫu này — KHÔNG hiểu nhầm thành "đã lùi đủ", thử lại
                time.sleep(0.02)
                continue
            if dist >= target_cm:
                self.stop()
                logger.info("Đã lùi đủ xa — khoảng cách %.1fcm", dist)
                return True
            time.sleep(0.02)

        self.stop()
        logger.warning("Timeout lùi ra sau %.1fs!", config.APPROACH_TIMEOUT)
        return False

    # ----------------------------------------------------------
    # Bám line (Line following)
    # ----------------------------------------------------------

    def read_line_sensor(self) -> list[int]:
        return self._line_sensor.read()

    def read_line_sensor_raw(self) -> list[float]:
        return self._line_sensor.read_raw()

    def read_line_sensor_adc(self) -> list[int]:
        return self._line_sensor.read_adc()

    def compute_line_error(self, sensor_values: list[int]) -> float:
        """PD digital — tương thích test/API cũ."""
        active = sum(sensor_values)
        if active == 0:
            return self._last_error
        weighted_sum = sum(
            w * v for w, v in zip(config.LINE_WEIGHTS, sensor_values)
        )
        return weighted_sum / active

    def compute_line_error_analog(self, raw: list[float]) -> float:
        """Weighted average từ analog — mượt hơn trên QTR-8A."""
        threshold = LineSensor._threshold_norm()
        strengths = [max(threshold - v, 0.0) for v in raw]
        total = sum(strengths)
        if total == 0:
            return self._last_error
        weighted = sum(w * s for w, s in zip(config.LINE_WEIGHTS, strengths))
        return weighted / total

    def follow_line(self, base_speed: float = config.SPEED_DEFAULT) -> tuple[bool, list[int]]:
        raw = self.read_line_sensor_raw()
        values = LineSensor.digital_from_raw(raw)
        active_count = sum(values)

        if active_count >= config.INTERSECTION_THRESHOLD:
            self.stop()
            logger.info("Phát hiện giao lộ (active=%d)", active_count)
            return True, values

        error = self.compute_line_error_analog(raw)
        derivative = error - self._last_error
        correction = config.LINE_KP * error + config.LINE_KD * derivative
        self._last_error = error

        left_speed = max(0, min(100, base_speed + correction))
        right_speed = max(0, min(100, base_speed - correction))

        self._left_rev.off()
        self._right_rev.off()
        self._left_fwd.value = self._pct(left_speed)
        self._right_fwd.value = self._pct(right_speed * config.PWM_COMPENSATION)

        return False, values

    def follow_line_until_intersection(self, base_speed: float = config.SPEED_DEFAULT,
                                       timeout: float = 15.0) -> bool:
        start = time.time()
        lost_count = 0

        while time.time() - start < timeout:
            at_intersection, values = self.follow_line(base_speed)
            if at_intersection:
                return True

            if sum(values) == 0:
                lost_count += 1
                if lost_count > 50:
                    logger.warning("Mất line! Quét tìm lại...")
                    if self._recover_line():
                        lost_count = 0
                    else:
                        self.stop()
                        logger.error("Không tìm lại được line!")
                        return False
            else:
                lost_count = 0

            time.sleep(0.01)

        self.stop()
        logger.warning("Timeout bám line sau %.1fs!", timeout)
        return False

    def _recover_line(self) -> bool:
        for direction in ["left", "right", "left"]:
            if direction == "left":
                self.turn_left(config.SPEED_SLOW)
            else:
                self.turn_right(config.SPEED_SLOW)

            start = time.time()
            while time.time() - start < 0.5:
                values = self.read_line_sensor()
                if sum(values) > 0:
                    self.stop()
                    logger.info("Tìm lại line thành công (quét %s)", direction)
                    return True
                time.sleep(0.01)

        self.stop()
        return False

    def _escape_intersection(self, speed: float = config.SPEED_DEFAULT):
        self.forward(speed)
        time.sleep(0.3)
        self.stop()

    def navigate_intersections(self, count: int,
                               base_speed: float = config.SPEED_DEFAULT) -> bool:
        if count <= 0:
            return True

        for i in range(count):
            logger.info("Đi đến giao lộ %d/%d", i + 1, count)
            self._escape_intersection(base_speed)
            if not self.follow_line_until_intersection(base_speed):
                logger.error("Không tìm thấy giao lộ %d/%d!", i + 1, count)
                self.stop()
                return False
        self.stop()
        return True

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def cleanup(self):
        self.stop()
        self._left_fwd.close()
        self._left_rev.close()
        self._right_fwd.close()
        self._right_rev.close()
        self._line_sensor.cleanup()
        if self._distance_sensor:
            self._distance_sensor.close()
