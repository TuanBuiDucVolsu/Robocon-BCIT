"""
Module điều khiển cơ cấu nâng/hạ 2 càng (trái/phải) ĐỘC LẬP.
Mỗi càng 1 motor riêng → có thể thả riêng từng pallet.
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
    """Điều khiển 2 càng nâng độc lập (trái và phải)."""

    def __init__(self):
        # Cẩu trái: IN3 = nâng, IN4 = hạ
        self._left_up = DigitalOutputDevice(config.IN3_CAU_T)
        self._left_down = DigitalOutputDevice(config.IN4_CAU_T)

        # Cẩu phải: ENA = bật/tắt, IN1 = nâng, IN2 = hạ
        self._right_en = DigitalOutputDevice(config.ENA_CAU_P)
        self._right_up = DigitalOutputDevice(config.IN1_CAU_P)
        self._right_down = DigitalOutputDevice(config.IN2_CAU_P)

        # Cảm biến IR xác nhận pallet trên càng
        self._pallet_sensor = DigitalInputDevice(config.PALLET_SENSOR_PIN, pull_up=True)

        self._current_level = 0       # Tầng hiện tại của cả 2 càng khi đồng bộ
        self._left_dropped = False    # Càng trái đã thả chưa
        self._right_dropped = False   # Càng phải đã thả chưa

    # ----------------------------------------------------------
    # Cảm biến pallet
    # ----------------------------------------------------------

    def has_pallet(self) -> bool:
        return not self._pallet_sensor.is_active

    # ----------------------------------------------------------
    # Điều khiển motor — riêng từng bên
    # ----------------------------------------------------------

    def _raise_left(self, duration: float):
        """Nâng càng TRÁI."""
        self._left_up.on()
        self._left_down.off()
        time.sleep(duration)
        self._left_up.off()

    def _lower_left(self, duration: float):
        """Hạ càng TRÁI."""
        self._left_up.off()
        self._left_down.on()
        time.sleep(duration)
        self._left_down.off()

    def _raise_right(self, duration: float):
        """Nâng càng PHẢI."""
        self._right_en.on()
        self._right_up.on()
        self._right_down.off()
        time.sleep(duration)
        self._right_en.off()
        self._right_up.off()

    def _lower_right(self, duration: float):
        """Hạ càng PHẢI."""
        self._right_en.on()
        self._right_up.off()
        self._right_down.on()
        time.sleep(duration)
        self._right_en.off()
        self._right_down.off()

    # ----------------------------------------------------------
    # Điều khiển motor — cả 2 bên đồng bộ
    # ----------------------------------------------------------

    def _raise_both(self, duration: float):
        """Nâng cả 2 càng đồng thời."""
        logger.info("Nâng cả 2 càng - duration=%.2fs", duration)
        self._left_up.on()
        self._left_down.off()
        self._right_en.on()
        self._right_up.on()
        self._right_down.off()
        time.sleep(duration)
        self._stop_all()

    def _lower_both(self, duration: float):
        """Hạ cả 2 càng đồng thời."""
        logger.info("Hạ cả 2 càng - duration=%.2fs", duration)
        self._left_up.off()
        self._left_down.on()
        self._right_en.on()
        self._right_up.off()
        self._right_down.on()
        time.sleep(duration)
        self._stop_all()

    def _stop_all(self):
        self._left_up.off()
        self._left_down.off()
        self._right_en.off()
        self._right_up.off()
        self._right_down.off()

    # ----------------------------------------------------------
    # API chính — nâng/hạ đồng bộ (cả 2 càng)
    # ----------------------------------------------------------

    def _time_for_level(self, level: int) -> float:
        if level == 0:
            return config.LIFT_TIME_FLOOR
        elif level == 1:
            return config.LIFT_TIME_SHELF_1
        elif level == 2:
            return config.LIFT_TIME_SHELF_2
        return config.LIFT_TIME_SHELF_1

    def go_to_level(self, target_level: int):
        """Di chuyển CẢ 2 càng đến tầng mục tiêu."""
        if target_level == self._current_level:
            return
        target_time = self._time_for_level(target_level)
        current_time = self._time_for_level(self._current_level)
        delta = target_time - current_time
        if delta > 0:
            self._raise_both(abs(delta))
        else:
            self._lower_both(abs(delta))
        self._current_level = target_level
        logger.info("Cả 2 càng đã đến tầng %d", target_level)

    def pickup(self, shelf_level: int = 1) -> bool:
        """Nâng CẢ 2 pallet từ kệ. Retry nếu cảm biến không thấy."""
        self._left_dropped = False
        self._right_dropped = False

        for attempt in range(1, config.PICKUP_MAX_RETRIES + 1):
            logger.info("Nhấc hàng tầng %d — lần %d/%d",
                        shelf_level, attempt, config.PICKUP_MAX_RETRIES)
            approach_level = shelf_level - 1 if shelf_level > 0 else 0
            self.go_to_level(approach_level)
            time.sleep(0.2)
            self.go_to_level(shelf_level)
            time.sleep(config.PICKUP_VERIFY_DELAY)
            if self.has_pallet():
                logger.info("Xác nhận: CÓ pallet trên càng")
                return True
            logger.warning("Lần %d: KHÔNG thấy pallet — thử lại", attempt)
            self.go_to_level(approach_level)
            time.sleep(0.3)

        logger.error("Thất bại sau %d lần thử nâng!", config.PICKUP_MAX_RETRIES)
        return False

    def dropoff(self) -> bool:
        """Hạ CẢ 2 pallet xuống (đồng bộ)."""
        logger.info("Đặt hàng — cả 2 càng")
        self._lower_both(self._time_for_level(self._current_level))
        self._current_level = 0
        self._left_dropped = True
        self._right_dropped = True
        time.sleep(0.3)
        if not self.has_pallet():
            logger.info("Xác nhận: pallet đã rời càng")
            return True
        logger.warning("Cảm biến vẫn thấy pallet sau khi hạ")
        return False

    # ----------------------------------------------------------
    # API mới — thả riêng từng bên
    # ----------------------------------------------------------

    def dropoff_left(self) -> bool:
        """Hạ càng TRÁI (thả pallet trái), giữ càng phải."""
        logger.info("Đặt hàng — chỉ càng TRÁI")
        duration = self._time_for_level(self._current_level)
        self._lower_left(duration)
        self._left_dropped = True
        time.sleep(0.2)
        logger.info("Càng trái đã hạ")
        return True

    def dropoff_right(self) -> bool:
        """Hạ càng PHẢI (thả pallet phải), giữ càng trái."""
        logger.info("Đặt hàng — chỉ càng PHẢI")
        duration = self._time_for_level(self._current_level)
        self._lower_right(duration)
        self._right_dropped = True
        time.sleep(0.2)
        logger.info("Càng phải đã hạ")
        return True

    def raise_after_drop(self, side: str):
        """Nâng lại càng đã thả (để di chuyển không va sàn)."""
        duration = self._time_for_level(self._current_level)
        if side == "left":
            logger.info("Nâng lại càng trái")
            self._raise_left(duration)
        elif side == "right":
            logger.info("Nâng lại càng phải")
            self._raise_right(duration)

    def stow_forks(self, dropped_side: str):
        """
        Sau giao kiện cuối cùng của cặp: càng vừa thả đã ở sàn,
        hạ càng còn lại (vẫn ở cao sau lần giao đầu) về mặt sàn.
        """
        duration = self._time_for_level(self._current_level)
        if dropped_side == "left":
            logger.info("Gập càng — hạ càng phải về sàn")
            self._lower_right(duration)
        else:
            logger.info("Gập càng — hạ càng trái về sàn")
            self._lower_left(duration)
        self._current_level = 0
        self._left_dropped = False
        self._right_dropped = False

    def reset(self):
        self.go_to_level(0)
        self._left_dropped = False
        self._right_dropped = False

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def cleanup(self):
        self._stop_all()
        self._left_up.close()
        self._left_down.close()
        self._right_en.close()
        self._right_up.close()
        self._right_down.close()
        self._pallet_sensor.close()
