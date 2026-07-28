"""
Công tắc gạt chọn NỬA SÂN — đọc bằng 1 chân GPIO.

VÌ SAO CẦN: hai nửa sa bàn là bản quay 180° của nhau nên mọi đường line giống hệt,
robot KHÔNG thể tự dò bằng cảm biến. Thứ khác nhau là cụm nhà máy nào nằm cùng hàng
ô xuất phát (Foxconn hay Samsung — xem navigation.py). Đặt sai thì robot giao Samsung
vào Foxconn: chạy vẫn mượt, IR vẫn xác nhận thả thành công, log vẫn sạch, chỉ là
điểm bằng 0. Đây là thao tác duy nhất trong hệ thống mà sai KHÔNG có tín hiệu báo lỗi.

Vì vậy dùng công tắc gạt chứ không phải hằng số trong file: trạng thái **nhìn thấy
được bằng mắt thường, không cần cấp nguồn**. Dán nhãn hai bên công tắc, cả đội liếc
một cái là kiểm chéo được sau khi bốc thăm.

ĐẤU DÂY (công tắc gạt 2 vị trí, SPST hay SPDT đều được):

    Chân giữa (common) ──→ GND
    Một cực            ──→ GPIO BOARD_SIDE_SWITCH_PIN
    Cực còn lại        ──→ để trống

    Gạt về phía có nối GPIO  → chân xuống GND (LOW) → config.BOARD_SIDE_SWITCH_CLOSED
    Gạt về phía kia          → thả nổi, điện trở kéo lên trong Pi giữ HIGH → nửa còn lại

Không lắp công tắc (BOARD_SIDE_SWITCH_PIN = None) → trả None, main dùng
config.FACTORY_AT_START_ROW làm dự phòng.
"""

import logging

try:
    from gpiozero import Button, Device
    Device.ensure_pin_factory()
except Exception:
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        from gpiozero import Button
    except ImportError:
        Button = None

import config

logger = logging.getLogger(__name__)

# Hai giá trị hợp lệ — trùng navigation.FACTORY_AT_START_ROW_CHOICES
SIDES = ("foxconn", "samsung")

# Sentinel: không truyền `pin` = lấy từ config. Phải phân biệt với pin=None (nghĩa
# là KHÔNG có công tắc) — nếu dùng chung None thì không cách nào tạo đối tượng
# "không có công tắc" khi config vẫn khai báo chân, và test/debug sẽ đọc nhầm.
_FROM_CONFIG = object()


class BoardSideSwitch:
    """Đọc công tắc gạt chọn nửa sân. Trả tên nhà máy CÙNG HÀNG ô xuất phát."""

    def __init__(self, pin=_FROM_CONFIG):
        if pin is _FROM_CONFIG:
            pin = getattr(config, "BOARD_SIDE_SWITCH_PIN", None)
        self.pin = pin
        self._button = None

        closed = getattr(config, "BOARD_SIDE_SWITCH_CLOSED", "samsung")
        if closed not in SIDES:
            logger.error("BOARD_SIDE_SWITCH_CLOSED không hợp lệ (%r) — dùng 'samsung'", closed)
            closed = "samsung"
        self.closed_side = closed
        self.open_side = SIDES[0] if closed == SIDES[1] else SIDES[1]

        if pin is None:
            logger.warning("Không khai báo BOARD_SIDE_SWITCH_PIN — sẽ dùng "
                           "config.FACTORY_AT_START_ROW thay cho công tắc")
            return
        if Button is None:
            logger.warning("gpiozero không khả dụng — không đọc được công tắc nửa sân")
            return
        try:
            self._button = Button(pin, pull_up=True, bounce_time=0.05)
            logger.info("Công tắc nửa sân sẵn sàng (GPIO %d): nối GND=%s, thả nổi=%s",
                        pin, self.closed_side, self.open_side)
        except Exception as e:
            self._button = None
            logger.error("Không mở được công tắc nửa sân trên GPIO %s: %s", pin, e)

    @property
    def available(self) -> bool:
        return self._button is not None

    def read(self) -> str | None:
        """Nhà máy cùng hàng ô xuất phát theo công tắc; None nếu không đọc được."""
        if self._button is None:
            return None
        try:
            # is_pressed = chân đang bị kéo xuống GND
            return self.closed_side if self._button.is_pressed else self.open_side
        except Exception as e:
            logger.error("Lỗi đọc công tắc nửa sân: %s", e)
            return None

    def close(self):
        if self._button is not None:
            self._button.close()
            self._button = None
