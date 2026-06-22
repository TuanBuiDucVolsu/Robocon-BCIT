"""
Module điều khiển cơ cấu nâng/hạ 2 càng (trái/phải) kiểu xe nâng forklift.
Dùng gpiozero + time-based control (chưa có encoder/limit switch).
"""

import time
import logging

try:
    from gpiozero import DigitalOutputDevice, Device
    Device.ensure_pin_factory()
except Exception:
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        from gpiozero import DigitalOutputDevice
    except ImportError:
        from unittest.mock import MagicMock
        DigitalOutputDevice = MagicMock

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

        self._current_level = 0  # 0 = mặt sàn, 1 = tầng 1, 2 = tầng 2

    # ----------------------------------------------------------
    # Điều khiển động cơ càng
    # ----------------------------------------------------------

    def _raise(self, duration: float, speed: int = config.LIFT_SPEED):
        """Nâng càng lên trong <duration> giây."""
        logger.info("Nâng càng - duration=%.2fs, speed=%d", duration, speed)
        # Cẩu trái: nâng
        self._left_up.on()
        self._left_down.off()
        # Cẩu phải: enable + nâng
        self._right_en.on()
        self._right_up.on()
        self._right_down.off()

        time.sleep(duration)
        self._stop_motors()

    def _lower(self, duration: float, speed: int = config.DROP_SPEED):
        """Hạ càng xuống trong <duration> giây."""
        logger.info("Hạ càng - duration=%.2fs, speed=%d", duration, speed)
        # Cẩu trái: hạ
        self._left_up.off()
        self._left_down.on()
        # Cẩu phải: enable + hạ
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

    def pickup(self, shelf_level: int = 1):
        """
        Nâng pallet từ kệ. Trình tự:
        1. Đảm bảo càng ở vị trí thấp (dưới pallet)
        2. Nâng lên để nhấc pallet khỏi kệ
        """
        logger.info("Bắt đầu nhấc hàng - tầng kệ %d", shelf_level)
        # Hạ càng xuống thấp hơn tầng kệ để luồn vào dưới pallet
        approach_level = shelf_level - 1 if shelf_level > 0 else 0
        self.go_to_level(approach_level)
        time.sleep(0.2)

        # Nâng lên qua tầng kệ để nhấc pallet
        self.go_to_level(shelf_level)
        time.sleep(0.2)
        logger.info("Đã nhấc hàng thành công")

    def dropoff(self):
        """
        Hạ pallet xuống vị trí. Trình tự:
        1. Hạ chậm càng xuống mặt sàn
        2. Càng rút ra (robot lùi lại)
        """
        logger.info("Bắt đầu đặt hàng")
        self._lower(self._time_for_level(self._current_level), speed=config.DROP_SPEED)
        self._current_level = 0
        time.sleep(0.3)
        logger.info("Đã đặt hàng thành công")

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
