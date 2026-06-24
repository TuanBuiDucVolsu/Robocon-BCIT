"""
Module điều khiển cơ cấu nâng/hạ 2 càng (trái/phải) ĐỘC LẬP.
Mỗi càng 1 motor riêng → có thể thả riêng từng pallet.
2 cảm biến IR pallet (trái/phải) qua MCP3008 SPI (CH6, CH7).
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
from control.mcp3008_bus import Mcp3008Bus, get_mcp3008_bus

logger = logging.getLogger(__name__)


class PalletSensors:
    """Đọc 2 cảm biến IR pallet (trái/phải) qua MCP3008 SPI CH6+CH7."""

    def __init__(self, bus: Mcp3008Bus | None = None):
        self._bus = bus or get_mcp3008_bus()
        self.available = self._bus.available
        if self.available:
            logger.info("Pallet IR sensor sẵn sàng (MCP3008 CH%d+CH%d)",
                        config.PALLET_LEFT_CHANNEL, config.PALLET_RIGHT_CHANNEL)

    def _is_pallet(self, value: float) -> bool:
        """Giá trị analog thấp = có pallet (IR phản xạ mạnh)."""
        return value < (config.PALLET_THRESHOLD / 1023.0)

    def read_raw(self) -> tuple[float, float]:
        """Giá trị analog 0.0-1.0 (trái, phải)."""
        left, right = self._bus.read_many([
            config.PALLET_LEFT_CHANNEL,
            config.PALLET_RIGHT_CHANNEL,
        ])
        return left, right

    def read_adc(self) -> tuple[int, int]:
        left, right = self.read_raw()
        return int(round(left * 1023)), int(round(right * 1023))

    def read_status(self) -> tuple[bool, bool, bool]:
        """Trả về (có_trái, có_phải, đọc_ok)."""
        if not self.available:
            return False, False, False
        try:
            left_raw, right_raw = self.read_raw()
            if not self._bus.last_read_ok:
                logger.warning("Lỗi đọc MCP3008 — bỏ qua kết quả IR pallet")
                return False, False, False
            left = self._is_pallet(left_raw)
            right = self._is_pallet(right_raw)
            return left, right, True
        except Exception as e:
            logger.warning("Lỗi đọc pallet sensor: %s", e)
            return False, False, False

    def has_left(self) -> bool | None:
        left, _, ok = self.read_status()
        return left if ok else None

    def has_right(self) -> bool | None:
        _, right, ok = self.read_status()
        return right if ok else None

    def has_any(self) -> bool | None:
        left, right, ok = self.read_status()
        return (left or right) if ok else None

    def has_both(self) -> bool | None:
        left, right, ok = self.read_status()
        return (left and right) if ok else None

    def status(self) -> tuple[bool, bool]:
        left, right, ok = self.read_status()
        if not ok:
            return False, False
        return left, right

    def cleanup(self):
        pass


class Lift:
    """Điều khiển 2 càng nâng độc lập (trái và phải)."""

    def __init__(self, mcp_bus: Mcp3008Bus | None = None):
        self._mcp_bus = mcp_bus or get_mcp3008_bus()
        # Cẩu trái: IN3 = nâng, IN4 = hạ
        self._left_up = DigitalOutputDevice(config.IN3_CAU_T)
        self._left_down = DigitalOutputDevice(config.IN4_CAU_T)

        # Cẩu phải: ENA = bật/tắt, IN1 = nâng, IN2 = hạ
        self._right_en = DigitalOutputDevice(config.ENA_CAU_P)
        self._right_up = DigitalOutputDevice(config.IN1_CAU_P)
        self._right_down = DigitalOutputDevice(config.IN2_CAU_P)

        # 2 cảm biến IR pallet qua MCP3008 SPI
        self.pallet = PalletSensors(self._mcp_bus)

        self._current_level = 0
        self._left_dropped = False
        self._right_dropped = False

    # ----------------------------------------------------------
    # Điều khiển motor — riêng từng bên
    # ----------------------------------------------------------

    def _raise_left(self, duration: float):
        self._left_up.on()
        self._left_down.off()
        time.sleep(duration)
        self._left_up.off()

    def _lower_left(self, duration: float):
        self._left_up.off()
        self._left_down.on()
        time.sleep(duration)
        self._left_down.off()

    def _raise_right(self, duration: float):
        self._right_en.on()
        self._right_up.on()
        self._right_down.off()
        time.sleep(duration)
        self._right_en.off()
        self._right_up.off()

    def _lower_right(self, duration: float):
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
        logger.info("Nâng cả 2 càng - duration=%.2fs", duration)
        self._left_up.on()
        self._left_down.off()
        self._right_en.on()
        self._right_up.on()
        self._right_down.off()
        time.sleep(duration)
        self._stop_all()

    def _lower_both(self, duration: float):
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

    def pickup(self, shelf_level: int = 1, require_both: bool = True) -> bool:
        """
        Nâng pallet từ kệ. Retry nếu cảm biến không thấy.
        require_both=True (NV1): cần cả 2 IR. require_both=False (NV2): 1 IR là đủ.
        """
        self._left_dropped = False
        self._right_dropped = False

        for attempt in range(1, config.PICKUP_MAX_RETRIES + 1):
            logger.info("Nhấc hàng tầng %d — lần %d/%d (require_both=%s)",
                        shelf_level, attempt, config.PICKUP_MAX_RETRIES, require_both)
            approach_level = shelf_level - 1 if shelf_level > 0 else 0
            self.go_to_level(approach_level)
            time.sleep(0.2)
            self.go_to_level(shelf_level)
            time.sleep(config.PICKUP_VERIFY_DELAY)

            left, right, ok = self.pallet.read_status()
            if not ok:
                logger.warning("Lần %d: không đọc được cảm biến IR — thử lại", attempt)
                self.go_to_level(approach_level)
                time.sleep(0.3)
                continue

            logger.info("Cảm biến: trái=%s, phải=%s",
                        "CÓ" if left else "KHÔNG",
                        "CÓ" if right else "KHÔNG")

            if require_both:
                if left and right:
                    logger.info("Xác nhận: CẢ 2 pallet trên càng")
                    return True
                if left or right:
                    logger.warning("Chỉ có 1 pallet (%s) — không chấp nhận (cần cả 2)",
                                   "trái" if left else "phải")
            elif left or right:
                logger.info("Xác nhận: có pallet trên càng (NV2)")
                return True

            logger.warning("Lần %d: KHÔNG thấy pallet — thử lại", attempt)
            self.go_to_level(approach_level)
            time.sleep(0.3)

        logger.error("Thất bại sau %d lần thử nâng!", config.PICKUP_MAX_RETRIES)
        return False

    def _verify_released(self, side: str | None = None) -> bool:
        """Kiểm tra pallet đã rời càng. side=None → cả 2 bên."""
        if side == "left":
            has = self.pallet.has_left()
            label = "trái"
        elif side == "right":
            has = self.pallet.has_right()
            label = "phải"
        else:
            left, right, ok = self.pallet.read_status()
            if not ok:
                logger.error("Không đọc được cảm biến IR — không xác nhận drop")
                return False
            if not left and not right:
                return True
            logger.warning("Cảm biến vẫn thấy pallet (trái=%s, phải=%s)",
                           "CÓ" if left else "không", "CÓ" if right else "không")
            return False

        if has is None:
            logger.error("Không đọc được cảm biến IR %s — không xác nhận drop", label)
            return False
        if not has:
            logger.info("Xác nhận: pallet %s đã rời càng", label)
            return True
        logger.warning("Cảm biến %s vẫn thấy pallet", label)
        return False

    def dropoff(self) -> bool:
        """Hạ CẢ 2 pallet xuống (đồng bộ)."""
        logger.info("Đặt hàng — cả 2 càng")
        self._lower_both(self._time_for_level(self._current_level))
        self._current_level = 0
        self._left_dropped = True
        self._right_dropped = True
        time.sleep(0.3)
        return self._verify_released()

    # ----------------------------------------------------------
    # API — thả riêng từng bên
    # ----------------------------------------------------------

    def dropoff_left(self) -> bool:
        """Hạ càng TRÁI (thả pallet trái), giữ càng phải."""
        logger.info("Đặt hàng — chỉ càng TRÁI")
        duration = self._time_for_level(self._current_level)
        self._lower_left(duration)
        self._left_dropped = True
        time.sleep(0.2)
        return self._verify_released("left")

    def dropoff_right(self) -> bool:
        """Hạ càng PHẢI (thả pallet phải), giữ càng trái."""
        logger.info("Đặt hàng — chỉ càng PHẢI")
        duration = self._time_for_level(self._current_level)
        self._lower_right(duration)
        self._right_dropped = True
        time.sleep(0.2)
        return self._verify_released("right")

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
        """Sau giao kiện cuối: hạ càng còn lại về sàn."""
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
        self.pallet.cleanup()
