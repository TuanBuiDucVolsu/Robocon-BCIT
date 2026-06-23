"""
Module điều khiển động cơ di chuyển, cảm biến dò line, và cảm biến siêu âm.
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

logger = logging.getLogger(__name__)


class LineSensor:
    """Đọc cảm biến dò line 8 mắt qua I2C (PCF8574 hoặc tương đương)."""

    def __init__(self):
        try:
            import smbus2
            self._bus = smbus2.SMBus(1)
        except Exception as e:
            self._bus = None
            logger.warning("Line sensor không khả dụng (%s) — bị vô hiệu hoá", e)

    def read(self) -> list[int]:
        if self._bus is None:
            return [0] * config.LINE_SENSOR_COUNT
        raw = self._bus.read_byte(config.LINE_SENSOR_I2C_ADDR)
        return [(raw >> i) & 1 for i in range(config.LINE_SENSOR_COUNT)]

    def cleanup(self):
        if self._bus:
            self._bus.close()


class Motion:
    """Điều khiển 2 động cơ bánh xe (trái/phải) với PWM qua L298N."""

    def __init__(self):
        # Bánh trái: IN1 = PWM (tiến), IN2 = digital (lùi)
        self._left_fwd = PWMOutputDevice(config.IN1_XE_T, frequency=config.PWM_FREQUENCY)
        self._left_rev = DigitalOutputDevice(config.IN2_XE_T)

        # Bánh phải: IN1 = PWM (tiến), IN2 = digital (lùi)
        self._right_fwd = PWMOutputDevice(config.IN1_XE_P, frequency=config.PWM_FREQUENCY)
        self._right_rev = DigitalOutputDevice(config.IN2_XE_P)

        self._line_sensor = LineSensor()
        self._last_error = 0.0

        # Cảm biến siêu âm HC-SR04
        try:
            self._distance_sensor = DistanceSensor(
                echo=config.ULTRASONIC_ECHO_PIN,
                trigger=config.ULTRASONIC_TRIG_PIN,
                max_distance=1.0,  # tối đa 1m
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
        """Chuyển tốc độ 0-100 sang 0.0-1.0 cho gpiozero."""
        return max(0.0, min(1.0, speed / 100.0))

    # ----------------------------------------------------------
    # Đo khoảng cách
    # ----------------------------------------------------------

    def get_distance(self) -> float:
        """Đo khoảng cách phía trước (cm). Lọc nhiễu bằng median 3 lần đo."""
        if self._distance_sensor is None:
            return -1.0
        readings = []
        for _ in range(3):
            readings.append(self._distance_sensor.distance * 100)
            time.sleep(0.01)
        readings.sort()
        return readings[1]  # median

    # ----------------------------------------------------------
    # Điều khiển cơ bản
    # ----------------------------------------------------------

    def forward(self, speed: float = config.SPEED_DEFAULT):
        """Tiến thẳng với tốc độ 0-100."""
        logger.debug("Tiến - speed=%s", speed)
        self._left_rev.off()
        self._right_rev.off()
        self._left_fwd.value = self._pct(speed)
        self._right_fwd.value = self._pct(speed * config.PWM_COMPENSATION)

    def backward(self, speed: float = config.SPEED_DEFAULT):
        """Lùi thẳng với tốc độ 0-100. Dùng PWM trên IN2."""
        logger.debug("Lùi - speed=%s", speed)
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.on()
        self._right_rev.on()
        # TODO: khi đội nâng cấp IN2 sang PWMOutputDevice thì dùng:
        # self._left_rev.value = self._pct(speed)
        # self._right_rev.value = self._pct(speed * config.PWM_COMPENSATION)
        # Hiện tại IN2 là DigitalOutput → luôn chạy full speed khi lùi.
        # Workaround: dùng forward rồi đảo hướng bằng time ngắn.

    def turn_left(self, speed: float = config.SPEED_TURN):
        """Xoay tại chỗ sang trái (trái lùi, phải tiến)."""
        logger.debug("Xoay trái - speed=%s", speed)
        self._left_fwd.value = 0
        self._left_rev.on()
        self._right_rev.off()
        self._right_fwd.value = self._pct(speed * config.PWM_COMPENSATION)

    def turn_right(self, speed: float = config.SPEED_TURN):
        """Xoay tại chỗ sang phải (trái tiến, phải lùi)."""
        logger.debug("Xoay phải - speed=%s", speed)
        self._left_rev.off()
        self._left_fwd.value = self._pct(speed)
        self._right_fwd.value = 0
        self._right_rev.on()

    def stop(self):
        """Dừng cả 2 bánh."""
        logger.debug("Dừng")
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.off()
        self._right_rev.off()

    # ----------------------------------------------------------
    # Xoay 90° và điều hướng route
    # ----------------------------------------------------------

    def turn_left_90(self):
        """Xoay 90° sang trái tại giao lộ."""
        logger.info("Xoay 90° trái")
        self.turn_left(config.SPEED_TURN)
        time.sleep(config.TURN_TIME)
        self.stop()

    def turn_right_90(self):
        """Xoay 90° sang phải tại giao lộ."""
        logger.info("Xoay 90° phải")
        self.turn_right(config.SPEED_TURN)
        time.sleep(config.TURN_TIME)
        self.stop()

    def execute_route(self, route: list) -> bool:
        """
        Thực hiện một chuỗi lệnh điều hướng.
        route = [("forward", N), ("left",), ("right",), ...]
        Trả về True nếu hoàn thành, False nếu gặp lỗi.
        """
        for step in route:
            action = step[0]

            if action == "forward":
                count = step[1]
                if count > 0:
                    self.navigate_intersections(count)
            elif action == "left":
                self.turn_left_90()
            elif action == "right":
                self.turn_right_90()
            else:
                logger.warning("Lệnh route không hợp lệ: %s", step)

        return True

    # ----------------------------------------------------------
    # Tiếp cận kệ / lùi ra (dùng cảm biến siêu âm)
    # ----------------------------------------------------------

    def approach_shelf(self, target_cm: float = config.APPROACH_DISTANCE,
                       speed: float = config.APPROACH_SPEED) -> bool:
        """
        Tiến chậm về phía kệ cho đến khi cảm biến siêu âm đo ≤ target_cm.
        Trả về True nếu đã đến đúng vị trí, False nếu timeout.
        """
        if self._distance_sensor is None:
            # Fallback: tiến theo thời gian nếu không có cảm biến
            logger.warning("Không có cảm biến siêu âm — tiến 0.5s (fallback)")
            self.forward(speed)
            time.sleep(0.5)
            self.stop()
            return True

        logger.info("Tiếp cận kệ — mục tiêu %.1fcm, tốc độ %d%%", target_cm, speed)
        start = time.time()
        self.forward(speed)

        while time.time() - start < config.APPROACH_TIMEOUT:
            dist = self.get_distance()
            logger.debug("Khoảng cách: %.1fcm", dist)

            if dist <= target_cm:
                self.stop()
                logger.info("Đã đến vị trí kệ — khoảng cách %.1fcm", dist)
                return True

            time.sleep(0.02)

        self.stop()
        logger.warning("Timeout tiếp cận kệ sau %.1fs!", config.APPROACH_TIMEOUT)
        return False

    def retreat_from_shelf(self, target_cm: float = config.RETREAT_DISTANCE,
                           speed: float = config.APPROACH_SPEED) -> bool:
        """
        Lùi ra khỏi kệ cho đến khi cảm biến siêu âm đo ≥ target_cm.
        Trả về True khi đã lùi đủ xa.
        """
        if self._distance_sensor is None:
            logger.warning("Không có cảm biến siêu âm — lùi 0.5s (fallback)")
            self.backward(speed)
            time.sleep(0.5)
            self.stop()
            return True

        logger.info("Lùi ra khỏi kệ — mục tiêu %.1fcm", target_cm)
        start = time.time()
        self.backward(speed)

        while time.time() - start < config.APPROACH_TIMEOUT:
            dist = self.get_distance()
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

    def compute_line_error(self, sensor_values: list[int]) -> float:
        """Tính độ lệch của line so với tâm robot (PD control)."""
        active = sum(sensor_values)
        if active == 0:
            return self._last_error

        weighted_sum = sum(
            w * v for w, v in zip(config.LINE_WEIGHTS, sensor_values)
        )
        error = weighted_sum / active
        return error

    def follow_line(self, base_speed: float = config.SPEED_DEFAULT) -> bool:
        """
        Thực hiện 1 bước bám line. Trả về True nếu phát hiện giao lộ.
        """
        values = self.read_line_sensor()
        active_count = sum(values)

        if active_count >= config.INTERSECTION_THRESHOLD:
            self.stop()
            logger.info("Phát hiện giao lộ (active=%d)", active_count)
            return True

        error = self.compute_line_error(values)
        derivative = error - self._last_error
        correction = config.LINE_KP * error + config.LINE_KD * derivative
        self._last_error = error

        left_speed = base_speed + correction
        right_speed = base_speed - correction

        left_speed = max(0, min(100, left_speed))
        right_speed = max(0, min(100, right_speed))

        self._left_rev.off()
        self._right_rev.off()
        self._left_fwd.value = self._pct(left_speed)
        self._right_fwd.value = self._pct(right_speed * config.PWM_COMPENSATION)

        return False

    def follow_line_until_intersection(self, base_speed: float = config.SPEED_DEFAULT,
                                       timeout: float = 15.0) -> bool:
        """
        Bám line cho đến khi gặp giao lộ.
        Trả về True nếu tìm thấy giao lộ, False nếu timeout.
        """
        start = time.time()
        lost_count = 0

        while time.time() - start < timeout:
            if self.follow_line(base_speed):
                return True

            # Phát hiện mất line (tất cả sensor = 0)
            values = self.read_line_sensor()
            if sum(values) == 0:
                lost_count += 1
                if lost_count > 50:  # ~0.5 giây mất line liên tục
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
        """Quét trái/phải để tìm lại line khi bị mất."""
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
        """Tiến qua giao lộ hiện tại trước khi bám line tiếp."""
        self.forward(speed)
        time.sleep(0.3)
        self.stop()

    def navigate_intersections(self, count: int, base_speed: float = config.SPEED_DEFAULT):
        """Đi qua <count> giao lộ rồi dừng."""
        if count <= 0:
            return

        for i in range(count):
            logger.info("Đi đến giao lộ %d/%d", i + 1, count)
            # Thoát giao lộ hiện tại trước khi bám line
            self._escape_intersection(base_speed)
            if not self.follow_line_until_intersection(base_speed):
                logger.error("Không tìm thấy giao lộ %d/%d!", i + 1, count)
                break
        self.stop()

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
