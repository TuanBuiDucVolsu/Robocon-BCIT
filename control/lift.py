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

        # Không gán thẳng MagicMock: tham số vị trí đầu của nó là `spec`, nên
        # DigitalOutputDevice(5) sẽ sinh mock bị spec theo int (xem control/motion.py).
        def DigitalOutputDevice(*_args, **_kwargs):
            return MagicMock()

import config
from control.mcp3008_bus import Mcp3008Bus, get_mcp3008_bus

logger = logging.getLogger(__name__)

#: Tầng cao nhất của kệ (kệ 2 tầng). Dùng để suy ra thời gian home tối thiểu.
MAX_LEVEL = 2


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
        # Cẩu TRÁI (vật lý): mạch có ENA — ENA_CAU_T, IN1_CAU_T=nâng, IN2_CAU_T=hạ
        self._left_en   = DigitalOutputDevice(config.ENA_CAU_T)
        self._left_up   = DigitalOutputDevice(config.IN1_CAU_T)
        self._left_down = DigitalOutputDevice(config.IN2_CAU_T)

        # Cẩu PHẢI (vật lý): mạch 2 chân — IN3_CAU_P=nâng, IN4_CAU_P=hạ
        self._right_up   = DigitalOutputDevice(config.IN3_CAU_P)
        self._right_down = DigitalOutputDevice(config.IN4_CAU_P)

        # 2 cảm biến IR pallet qua MCP3008 SPI
        self.pallet = PalletSensors(self._mcp_bus)

        self._current_level = 0

    # ----------------------------------------------------------
    # Điều khiển motor — riêng từng bên
    # ----------------------------------------------------------

    def _raise_left(self, duration: float):
        self._left_en.on()
        self._left_up.on()
        self._left_down.off()
        time.sleep(duration)
        self._left_en.off()
        self._left_up.off()

    def _lower_left(self, duration: float):
        self._left_en.on()
        self._left_up.off()
        self._left_down.on()
        time.sleep(duration)
        self._left_en.off()
        self._left_down.off()

    def _raise_right(self, duration: float):
        self._right_up.on()
        self._right_down.off()
        time.sleep(duration)
        self._right_up.off()

    def _lower_right(self, duration: float):
        self._right_up.off()
        self._right_down.on()
        time.sleep(duration)
        self._right_down.off()

    # ----------------------------------------------------------
    # Quy đổi tầng → thời gian chạy (đã bù lệch 2 càng)
    # ----------------------------------------------------------

    # Phần càng đang cao HƠN mốc tầng, tính bằng giây chạy motor. Sinh ra từ
    # raise_to_insert() (+LIFT_INSERT_EXTRA) và lift_off() (+LIFT_PICKUP_RAISE_TIME)
    # — cả hai đều cố ý nằm NGOÀI thang tầng nên `_current_level` không đổi.
    # Nhưng lúc HẠ VỀ SÀN thì phải trả lại đúng bấy nhiêu, không thì càng dừng lơ
    # lửng và KIỆN KHÔNG RỜI CÀNG (IR báo "vẫn thấy pallet", drop_side trả ❌).
    # Đo trên robot 03/08: 0.20 + 0.30 = 0.50s dôi ra, thừa sức giữ kiện trên càng.
    # ⚠️ RIÊNG TỪNG CÀNG. Thả càng trái thì phần dôi của TRÁI được tiêu thụ, nhưng
    # kiện bên PHẢI vẫn đang treo ở độ cao dôi — xoá chung là lần thả thứ hai không
    # được bù và kiện đó không rời càng. Đo trên robot 03/08: cả hai lần thả đều báo
    # "Cảm biến vẫn thấy pallet".
    _du_cao_ben: dict[str, float] | None = None

    def _du_cao(self, side: str) -> float:
        """Phần càng `side` đang cao HƠN mốc tầng, tính bằng giây chạy motor."""
        if self._du_cao_ben is None:
            self._du_cao_ben = {"left": 0.0, "right": 0.0}
        return self._du_cao_ben.get(side, 0.0)

    def _cong_du_cao(self, secs: float) -> None:
        """Cộng cho CẢ HAI càng — hai bước sinh ra nó (nâng chuẩn bị luồn, nhấc
        bổng) đều chạy đồng thời hai bên."""
        if self._du_cao_ben is None:
            self._du_cao_ben = {"left": 0.0, "right": 0.0}
        for b in ("left", "right"):
            self._du_cao_ben[b] += secs

    def _xoa_du_cao(self, side: str) -> None:
        if self._du_cao_ben is None:
            self._du_cao_ben = {"left": 0.0, "right": 0.0}
        self._du_cao_ben[side] = 0.0

    def _level_time(self, level: int, side: str, raising: bool) -> float:
        """Thời gian để càng `side` đi từ SÀN lên `level` (mốc TUYỆT ĐỐI, đã bù).

        Bù là hằng số cộng vào mốc tuyệt đối, KHÔNG cộng vào từng lần chạy — nhờ vậy
        đi 0→1→2 không cộng dồn phần bù 2 lần (lỗi cũ), và nâng/hạ 1 càng lẻ dùng
        đúng cùng hệ số bù với khi chạy cả 2 càng (trước đây các hàm 1 càng bỏ qua
        bù hoàn toàn → càng trái chạy dư 0.45s ở tầng 1).
        """
        base = self._time_for_level(level)
        if base <= 0:
            return 0.0
        if raising:
            # Bù riêng theo TỪNG TẦNG nếu có khai báo — độ lệch 2 càng không tỉ lệ
            # với độ cao (dây curoa mỗi bên căng khác nhau, trượt tăng theo quãng
            # chạy). Xem config.LIFT_LEFT_EXTRA_BY_LEVEL.
            theo_tang = (getattr(config, "LIFT_LEFT_EXTRA_BY_LEVEL", None)
                         if side == "left"
                         else getattr(config, "LIFT_RIGHT_EXTRA_BY_LEVEL", None))
            chung = config.LIFT_LEFT_EXTRA if side == "left" else config.LIFT_RIGHT_EXTRA
            extra = (theo_tang or {}).get(level, chung)
        else:
            extra = (config.LIFT_LEFT_LOWER_EXTRA if side == "left"
                     else config.LIFT_RIGHT_LOWER_EXTRA)
        return max(0.0, base + extra)

    def _move_duration(self, side: str, from_level: int, to_level: int,
                       raising: bool) -> float:
        """Thời gian chạy càng `side` giữa 2 tầng (hiệu 2 mốc tuyệt đối)."""
        return abs(self._level_time(to_level, side, raising)
                   - self._level_time(from_level, side, raising))

    def min_home_duration(self) -> float:
        """Thời gian hạ TỐI THIỂU để càng CHẬM NHẤT chắc chắn chạm đáy từ tầng cao nhất.

        KHÔNG phải `LIFT_TIME_SHELF_2`: hạ còn cộng `LIFT_*_LOWER_EXTRA`, mà bù của
        2 càng khác nhau. Với giá trị hiện tại càng trái cần 4.2s trong khi
        LIFT_TIME_SHELF_2 chỉ 3.9s — so với 3.9s thì thấy "đạt" nhưng vẫn còn hở.
        """
        return max(self._move_duration(side, MAX_LEVEL, 0, raising=False)
                   for side in ("left", "right"))

    # ----------------------------------------------------------
    # Điều khiển motor — cả 2 bên đồng bộ
    # ----------------------------------------------------------

    def _move_both(self, from_level: int, to_level: int, them: float = 0.0):
        """Đưa CẢ 2 càng từ `from_level` sang `to_level`, dừng từng bên đúng lúc.

        `them` — phần DÔI RA ngoài thang tầng, cộng vào cả 2 bên. Xem Lift._du_cao.
        """
        raising = self._time_for_level(to_level) > self._time_for_level(from_level)
        left_dur = self._move_duration("left", from_level, to_level, raising) + them
        right_dur = self._move_duration("right", from_level, to_level, raising) + them
        logger.info("%s cả 2 càng (tầng %d→%d) - trái=%.2fs phải=%.2fs",
                    "Nâng" if raising else "Hạ", from_level, to_level, left_dur, right_dur)
        if raising:
            self._left_en.on(); self._left_up.on(); self._left_down.off()
            self._right_up.on(); self._right_down.off()
        else:
            self._left_en.on(); self._left_up.off(); self._left_down.on()
            self._right_up.off(); self._right_down.on()
        self._run_timed(left_dur, right_dur, raising=raising)

    def _run_timed(self, left_dur: float, right_dur: float, raising: bool):
        """Dừng từng bên đúng thời điểm để 2 càng lên/xuống bằng nhau."""
        if left_dur <= right_dur:
            time.sleep(max(left_dur, 0))
            self._left_en.off(); self._left_up.off(); self._left_down.off()
            time.sleep(max(right_dur - left_dur, 0))
            self._right_up.off(); self._right_down.off()
        else:
            time.sleep(max(right_dur, 0))
            self._right_up.off(); self._right_down.off()
            time.sleep(max(left_dur - right_dur, 0))
            self._left_en.off(); self._left_up.off(); self._left_down.off()

    def _stop_all(self):
        self._left_en.off()
        self._left_up.off()
        self._left_down.off()
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
            # KHÔNG im lặng: không có limit switch nên `_current_level` chỉ là NIỀM
            # TIN. Tin sai thì đây là chỗ càng đứng yên trong khi cả hệ thống tưởng
            # nó đã lên đúng tầng — rồi robot tiến vào và càng chui vào gầm kệ.
            logger.info("Càng đã ở tầng %d (theo _current_level) — KHÔNG chạy motor. "
                        "Nếu thực tế càng không ở đó thì mọi bước sau đều sai.",
                        target_level)
            return
        self._move_both(self._current_level, target_level)
        self._current_level = target_level
        logger.info("Cả 2 càng đã đến tầng %d", target_level)

    def raise_to_insert(self, shelf_level: int):
        """Nâng 2 càng lên NGANG tầng cần lấy, để chuẩn bị LUỒN vào pallet.

        Phải chạy TRƯỚC khi robot tiến vào — cơ cấu là xe nâng thật, càng luồn vào
        pallet rồi mới nhấc. Tiến vào lúc càng còn ở sàn thì nâng lên chỉ đi trong
        không khí trước mặt kệ, còn với tầng 2 thì đội thẳng vào mặt tầng 1.
        """
        them = getattr(config, "LIFT_INSERT_EXTRA", 0.0)
        logger.info("Nâng càng lên ngang tầng %d để chuẩn bị luồn%s", shelf_level,
                    f" (+{them:.2f}s cho mũi càng nhỉnh hơn đáy khe)" if them > 0 else "")
        self.go_to_level(shelf_level)
        if them > 0 and shelf_level > 0:
            # Phần dôi ra NGOÀI thang tầng, y như lift_off(): `_current_level` giữ
            # nguyên. Xem config.LIFT_INSERT_EXTRA.
            self._left_en.on(); self._left_up.on(); self._left_down.off()
            self._right_up.on(); self._right_down.off()
            time.sleep(them)
            self._stop_all()
            # Ghi nhận phần DÔI RA ngoài thang tầng. `_current_level` vẫn là tầng
            # đó, nhưng càng đang cao hơn mốc tầng `them` giây — và lúc HẠ XUỐNG
            # SÀN phải trả lại đúng bấy nhiêu, không thì càng dừng lơ lửng và kiện
            # KHÔNG RỜI CÀNG. Xem Lift._du_cao.
            self._cong_du_cao(them)

    def lift_off(self) -> None:
        """Nhấc thêm một đoạn ngắn để pallet RỜI mặt kệ, sau khi càng đã luồn vào.

        Không đi qua go_to_level(): đây là phần dôi ra NGOÀI thang tầng, chỉ vài
        phần mười giây. `_current_level` giữ nguyên — coi như vẫn ở tầng đó, chỉ
        cao hơn chút. Sai lệch tích luỹ (nếu có) được home_to_floor() xoá sạch.
        """
        secs = config.LIFT_PICKUP_RAISE_TIME
        if secs <= 0:
            return
        self._cong_du_cao(secs)
        logger.info("Nhấc bổng pallet khỏi mặt kệ (%.2fs)", secs)
        self._left_en.on(); self._left_up.on(); self._left_down.off()
        self._right_up.on(); self._right_down.off()
        time.sleep(secs)
        self._stop_all()

    def confirm_pickup(self, require_both: bool = True) -> bool:
        """Đọc IR xác nhận pallet đã thật sự nằm trên càng.

        Tách khỏi pickup() vì ở luồng mới, phần NÂNG và phần LUỒN nằm ở hai chỗ
        khác nhau (Lift nâng, Motion tiến) — chỉ còn phần xác nhận là của Lift.
        """
        time.sleep(config.PICKUP_VERIFY_DELAY)
        left, right, ok = self.pallet.read_status()
        if not ok:
            logger.error("Không đọc được cảm biến IR — KHÔNG coi là nhấc thành công")
            return False
        logger.info("Cảm biến: trái=%s, phải=%s",
                    "CÓ" if left else "KHÔNG", "CÓ" if right else "KHÔNG")
        if require_both:
            if left and right:
                logger.info("Xác nhận: CẢ 2 pallet trên càng")
                return True
            if left or right:
                logger.warning("Chỉ có 1 pallet (%s) — không chấp nhận (cần cả 2)",
                               "trái" if left else "phải")
            return False
        if left or right:
            logger.info("Xác nhận: có pallet trên càng (NV2)")
            return True
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
        self._move_both(self._current_level, 0, them=max(self._du_cao("left"),
                                                        self._du_cao("right")))
        self._current_level = 0
        self._xoa_du_cao("left"); self._xoa_du_cao("right")
        time.sleep(0.3)
        return self._verify_released()

    # ----------------------------------------------------------
    # API — thả riêng từng bên
    # ----------------------------------------------------------

    def dropoff_left(self) -> bool:
        """Hạ càng TRÁI (thả pallet trái), giữ càng phải."""
        logger.info("Đặt hàng — chỉ càng TRÁI")
        # + phần DÔI RA ngoài thang tầng (nâng chuẩn bị luồn, nhấc bổng). Thiếu nó
        # thì càng dừng lơ lửng trên sàn đúng bấy nhiêu và KIỆN KHÔNG RỜI CÀNG —
        # IR báo "vẫn thấy pallet", drop_side trả ❌. Xem Lift._du_cao.
        duration = (self._move_duration("left", self._current_level, 0, raising=False)
                    + self._du_cao("left"))
        self._lower_left(duration)
        self._xoa_du_cao("left")   # bên này đã chạm sàn; bên kia GIỮ NGUYÊN
        time.sleep(0.2)
        return self._verify_released("left")

    def dropoff_right(self) -> bool:
        """Hạ càng PHẢI (thả pallet phải), giữ càng trái."""
        logger.info("Đặt hàng — chỉ càng PHẢI")
        # + phần DÔI RA ngoài thang tầng (nâng chuẩn bị luồn, nhấc bổng). Thiếu nó
        # thì càng dừng lơ lửng trên sàn đúng bấy nhiêu và KIỆN KHÔNG RỜI CÀNG —
        # IR báo "vẫn thấy pallet", drop_side trả ❌. Xem Lift._du_cao.
        duration = (self._move_duration("right", self._current_level, 0, raising=False)
                    + self._du_cao("right"))
        self._lower_right(duration)
        self._xoa_du_cao("right")   # bên này đã chạm sàn; bên kia GIỮ NGUYÊN
        time.sleep(0.2)
        return self._verify_released("right")

    def raise_after_drop(self, side: str):
        """Nâng lại càng đã thả về ngang tầng càng còn lại (di chuyển không va sàn)."""
        duration = self._move_duration(side, 0, self._current_level, raising=True)
        if side == "left":
            logger.info("Nâng lại càng trái (%.2fs)", duration)
            self._raise_left(duration)
        elif side == "right":
            logger.info("Nâng lại càng phải (%.2fs)", duration)
            self._raise_right(duration)

    def stow_forks(self, dropped_side: str):
        """Sau giao kiện cuối: hạ càng CÒN LẠI về sàn."""
        other = "right" if dropped_side == "left" else "left"
        duration = self._move_duration(other, self._current_level, 0, raising=False)
        if other == "right":
            logger.info("Gập càng — hạ càng phải về sàn (%.2fs)", duration)
            self._lower_right(duration)
        else:
            logger.info("Gập càng — hạ càng trái về sàn (%.2fs)", duration)
            self._lower_left(duration)
        self._current_level = 0

    def home_from(self, level: int) -> float:
        """Số giây đủ để hạ về sàn khi ĐÃ BIẾT đang ở `level`, cộng biên dư.

        Hạ từ tầng 1 chỉ cần ~0.9s trong khi home theo tầng cao nhất chạy 4.0s —
        hơn 3 giây motor ghì vào đáy cơ khí một cách vô ích, và motor cẩu là
        DigitalOutputDevice nên ghì ở 100% duty, bào mòn dây curoa.
        """
        need = max(self._move_duration(side, level, 0, raising=False)
                   for side in ("left", "right"))
        margin = getattr(config, "LIFT_HOME_KNOWN_MARGIN", 1.6)
        floor = getattr(config, "LIFT_HOME_MIN_DURATION", 0.8)
        # Chặn TRẦN bằng chính bản đầy đủ: từ tầng cao nhất thì `need` đã là trường
        # hợp xấu nhất, nhân biên nữa sẽ ra DÀI HƠN home mặc định (1.6 × 4.0 = 6.4s)
        # — vô nghĩa, vì bản đầy đủ vốn đã đủ để chạm đáy từ bất kỳ tầng nào.
        cap = max(config.LIFT_HOME_DURATION, self.min_home_duration())
        return min(max(need * margin, floor), cap)

    def home_to_floor(self, duration: float | None = None,
                      from_level: int | None = None):
        """Ép hạ CẢ 2 càng chạm đáy cơ khí. KHÔNG có limit switch nên không có
        cách nào ĐO được đã chạm đáy thật — chỉ có thể chạy hạ liên tục lâu hơn
        hẳn thời gian tối đa cần thiết (config.LIFT_HOME_DURATION) để chắc chắn
        chạm đáy dù trước đó lift đang ở tầng nào / _current_level có đúng hay
        không. Khác go_to_level(0): hàm đó TIN _current_level (không làm gì nếu
        đã là 0), không xác minh vị trí thật — dùng home_to_floor() khi vị trí
        thật sự không chắc (đầu trận, sau lỗi/mất điện).

        `from_level` — tầng đang ở, CHỈ truyền khi tin được `_current_level`.
        Truyền thì chỉ chạy đủ cho tầng đó cộng biên (home_from), thay vì luôn
        chạy theo tầng cao nhất: hạ từ tầng 1 còn ~1.4s thay vì 4.0s, đỡ hơn 2.5
        giây motor ghì vào đáy mỗi lần — nguồn bào mòn dây curoa chính khi ngồi
        test menu (test_lift home lại sau MỖI option).

        ⚠️ ĐÁNH ĐỔI, đọc kỹ trước khi dùng: nếu `_current_level` SAI (thực tế đang
        ở tầng cao hơn), bản rút gọn sẽ KHÔNG hạ tới đáy, rồi vẫn khai `_current_level
        = 0` — sai lệch tồn tại tiếp mà không có tín hiệu nào báo. Chính rủi ro đó
        là lý do home mặc định chạy theo tầng cao nhất.
        Nên: luồng THI ĐẤU (Lift.reset ← main.py) KHÔNG truyền from_level, giữ
        nguyên hành vi an toàn cũ. Chỉ menu test và công cụ đo mới truyền.
        """
        if duration is None and from_level is not None:
            duration = self.home_from(from_level)
            logger.info("Home (biết đang ở tầng %d): hạ %.2fs thay vì %.2fs",
                        from_level, duration, config.LIFT_HOME_DURATION)
        elif duration is None:
            duration = config.LIFT_HOME_DURATION
            needed = self.min_home_duration()
            if duration < needed:
                logger.warning(
                    "LIFT_HOME_DURATION=%.2fs THIẾU — càng chậm nhất cần %.2fs để hạ từ "
                    "tầng %d về sàn (đã tính LIFT_*_LOWER_EXTRA). Dùng %.2fs; sửa config lại.",
                    duration, needed, MAX_LEVEL, needed)
                duration = needed
        logger.info("Home: hạ cả 2 càng liên tục %.1fs để ép chạm đáy cơ khí", duration)
        self._left_en.on(); self._left_up.off(); self._left_down.on()
        self._right_up.off(); self._right_down.on()
        time.sleep(duration)
        self._stop_all()
        self._current_level = 0
        self._xoa_du_cao("left"); self._xoa_du_cao("right")   # ép chạm đáy
        logger.info("Home xong — đã khai báo lại vị trí = SÀN")

    def reset(self):
        self.home_to_floor()

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def cleanup(self):
        self._stop_all()
        self._left_en.close()
        self._left_up.close()
        self._left_down.close()
        self._right_up.close()
        self._right_down.close()
        self.pallet.cleanup()
