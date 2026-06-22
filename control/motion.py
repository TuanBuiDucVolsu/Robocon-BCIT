"""
Module điều khiển động cơ di chuyển và cảm biến dò line.
Dùng gpiozero (tương thích RPi 4 trên cả Bullseye lẫn Bookworm).
"""

import time
import logging

try:
    from gpiozero import PWMOutputDevice, DigitalOutputDevice, Device
    Device.ensure_pin_factory()
except Exception:
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        from gpiozero import PWMOutputDevice, DigitalOutputDevice
    except ImportError:
        from unittest.mock import MagicMock
        PWMOutputDevice = MagicMock
        DigitalOutputDevice = MagicMock

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

    # ----------------------------------------------------------
    # Tiện ích chuyển đổi tốc độ
    # ----------------------------------------------------------

    @staticmethod
    def _pct(speed: float) -> float:
        """Chuyển tốc độ 0-100 sang 0.0-1.0 cho gpiozero."""
        return max(0.0, min(1.0, speed / 100.0))

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
        """Lùi thẳng (IN2 bật, IN1 tắt)."""
        logger.debug("Lùi - speed=%s", speed)
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.on()
        self._right_rev.on()

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
    # Bám line (Line following)
    # ----------------------------------------------------------

    def read_line_sensor(self) -> list[int]:
        return self._line_sensor.read()

    def compute_line_error(self, sensor_values: list[int]) -> float:
        """Tính độ lệch của line so với tâm robot (PD control)."""
        active = sum(sensor_values)
        if active == 0:
            return self._last_error  # Giữ hướng cũ nếu mất line

        weighted_sum = sum(
            w * v for w, v in zip(config.LINE_WEIGHTS, sensor_values)
        )
        error = weighted_sum / active
        return error

    def follow_line(self, base_speed: float = config.SPEED_DEFAULT) -> bool:
        """
        Thực hiện 1 bước bám line. Trả về True nếu phát hiện giao lộ.
        Gọi liên tục trong vòng lặp để robot bám line.
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

    def follow_line_until_intersection(self, base_speed: float = config.SPEED_DEFAULT):
        """Bám line cho đến khi gặp giao lộ."""
        while True:
            if self.follow_line(base_speed):
                return
            time.sleep(0.01)

    def navigate_intersections(self, count: int, base_speed: float = config.SPEED_DEFAULT):
        """Đi qua <count> giao lộ rồi dừng."""
        for i in range(count):
            logger.info("Đi đến giao lộ %d/%d", i + 1, count)
            # Tiến qua giao lộ hiện tại một chút trước khi bám line tiếp
            if i > 0:
                self.forward(base_speed)
                time.sleep(0.3)
            self.follow_line_until_intersection(base_speed)
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
