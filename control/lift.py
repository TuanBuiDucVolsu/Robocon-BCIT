"""
Module điều khiển cơ cấu nâng/hạ 2 càng (trái/phải) kiểu xe nâng forklift.
Dùng gpiozero + time-based control + cảm biến IR xác nhận pallet.
"""

import time
import logging

try:
    from gpiozero import DigitalOutputDevice, DigitalInputDevice, Device
    Device.ensure_pin_factory()
except Exception:
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        from gpiozero import DigitalOutputDevice, DigitalInputDevice
    except ImportError:
        from unittest.mock import MagicMock
        DigitalOutputDevice = MagicMock
        DigitalInputDevice = MagicMock

import config

logger = logging.getLogger(__name__)


class Lift:
    """Điều khiển 2 động cơ càng nâng (trái và phải) đồng bộ."""

    def __init__(self):
        # Cẩu trái: IN3 = nâng, IN4 = hạ
        self._left_up = DigitalOutputDevice(config.IN3_CAU_T)
        self._left_down = DigitalOutputDevice(config.IN4_CAU_T)

        # Cẩu phải: ENA = bật/tắt, IN1 = nâng, IN2 = hạ
        self._right_en = DigitalOutputDevice(config.ENA_CAU_P)
        self._right_up = DigitalOutputDevice(config.IN1_CAU_P)
        self._right_down = DigitalOutputDevice(config.IN2_CAU_P)

        # Cảm biến IR xác nhận pallet trên càng (active_low: LOW = có pallet)
        self._pallet_sensor = DigitalInputDevice(config.PALLET_SENSOR_PIN, pull_up=True)

        self._current_level = 0  # 0 = mặt sàn, 1 = tầng 1, 2 = tầng 2

    # ----------------------------------------------------------
    # Cảm biến pallet
    # ----------------------------------------------------------

    def has_pallet(self) -> bool:
        """Kiểm tra có pallet trên càng hay không (cảm biến IR)."""
        return not self._pallet_sensor.is_active

    # ----------------------------------------------------------
    # Điều khiển động cơ càng
    # ----------------------------------------------------------

    def _raise(self, duration: float, speed: int = config.LIFT_SPEED):
        """Nâng càng lên trong <duration> giây."""
        logger.info("Nâng càng - duration=%.2fs, speed=%d", duration, speed)
        self._left_up.on()
        self._left_down.off()
        self._right_en.on()
        self._right_up.on()
        self._right_down.off()

        time.sleep(duration)
        self._stop_motors()

    def _lower(self, duration: float, speed: int = config.DROP_SPEED):
        """Hạ càng xuống trong <duration> giây."""
        logger.info("Hạ càng - duration=%.2fs, speed=%d", duration, speed)
        self._left_up.off()
        self._left_down.on()
        self._right_en.on()
        self._right_up.off()
        self._right_down.on()

        time.sleep(duration)
        self._stop_motors()

    def _stop_motors(self):
        self._left_up.off()
        self._left_down.off()
        self._right_en.off()
        self._right_up.off()
        self._right_down.off()

    # ----------------------------------------------------------
    # API chính
    # ----------------------------------------------------------

    def _time_for_level(self, level: int) -> float:
        """Trả về thời gian nâng tương ứng với từng tầng."""
        if level == 0:
            return config.LIFT_TIME_FLOOR
        elif level == 1:
            return config.LIFT_TIME_SHELF_1
        elif level == 2:
            return config.LIFT_TIME_SHELF_2
        return config.LIFT_TIME_SHELF_1

    def go_to_level(self, target_level: int):
        """Di chuyển càng đến tầng mục tiêu (0 = sàn, 1 = tầng 1, 2 = tầng 2)."""
        if target_level == self._current_level:
            return

        target_time = self._time_for_level(target_level)
        current_time = self._time_for_level(self._current_level)
        delta = target_time - current_time

        if delta > 0:
            self._raise(abs(delta))
        else:
            self._lower(abs(delta))

        self._current_level = target_level
        logger.info("Càng đã đến tầng %d", target_level)

    def pickup(self, shelf_level: int = 1) -> bool:
        """
        Nâng pallet từ kệ. Có cơ chế retry nếu cảm biến không thấy pallet.
        Trả về True nếu nâng thành công, False nếu thất bại.
        """
        for attempt in range(1, config.PICKUP_MAX_RETRIES + 1):
            logger.info("Nhấc hàng tầng %d — lần %d/%d",
                        shelf_level, attempt, config.PICKUP_MAX_RETRIES)

            # Hạ càng xuống dưới pallet
            approach_level = shelf_level - 1 if shelf_level > 0 else 0
            self.go_to_level(approach_level)
            time.sleep(0.2)

            # Nâng lên để nhấc pallet
            self.go_to_level(shelf_level)
            time.sleep(config.PICKUP_VERIFY_DELAY)

            # Kiểm tra cảm biến
            if self.has_pallet():
                logger.info("Xác nhận: CÓ pallet trên càng")
                return True

            logger.warning("Lần %d: KHÔNG thấy pallet — thử lại", attempt)
            # Hạ xuống rồi nâng lại
            self.go_to_level(approach_level)
            time.sleep(0.3)

        logger.error("Thất bại sau %d lần thử nâng!", config.PICKUP_MAX_RETRIES)
        return False

    def dropoff(self) -> bool:
        """
        Hạ pallet xuống vị trí.
        Trả về True nếu đã hạ xong (cảm biến không còn thấy pallet).
        """
        logger.info("Bắt đầu đặt hàng")
        self._lower(self._time_for_level(self._current_level), speed=config.DROP_SPEED)
        self._current_level = 0
        time.sleep(0.3)

        if not self.has_pallet():
            logger.info("Xác nhận: pallet đã rời càng")
            return True

        logger.warning("Cảm biến vẫn thấy pallet sau khi hạ — có thể kẹt")
        return False

    def reset(self):
        """Đưa càng về vị trí thấp nhất (mặt sàn)."""
        self.go_to_level(0)

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def cleanup(self):
        self._stop_motors()
        self._left_up.close()
        self._left_down.close()
        self._right_en.close()
        self._right_up.close()
        self._right_down.close()
        self._pallet_sensor.close()
