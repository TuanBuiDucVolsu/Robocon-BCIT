"""
Module điều khiển động cơ di chuyển, cảm biến dò line, và cảm biến siêu âm.
Line sensor: QTR-8A (analog) qua MCP3008 (SPI ADC).
Dùng gpiozero (tương thích RPi 4 trên cả Bullseye lẫn Bookworm).
"""

import time
import logging

try:
    from gpiozero import PWMOutputDevice, DigitalOutputDevice, DistanceSensor, DigitalInputDevice, Device
    Device.ensure_pin_factory()
except Exception:
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        from gpiozero import PWMOutputDevice, DigitalOutputDevice, DistanceSensor, DigitalInputDevice
    except ImportError:
        from unittest.mock import MagicMock

        def _mock_device(*_args, **_kwargs):
            """Không có gpiozero (chạy test trên PC) → thiết bị giả rỗng.

            KHÔNG gán thẳng `PWMOutputDevice = MagicMock`: tham số vị trí ĐẦU TIÊN
            của MagicMock là `spec`, nên `PWMOutputDevice(17, frequency=100)` sinh ra
            mock bị spec theo `int` → `.off()` ném AttributeError giữa chừng và bộ
            test tự tắt (đã từng che mất test 'reset dừng motor ngay').
            """
            return MagicMock()

        PWMOutputDevice = _mock_device
        DigitalOutputDevice = _mock_device
        DistanceSensor = _mock_device
        DigitalInputDevice = _mock_device

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

    @property
    def last_read_ok(self) -> bool:
        """Lần đọc gần nhất có hợp lệ không (SPI/ADC lỗi → False)."""
        return self.available and self._bus.last_read_ok

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


class WheelEncoder:
    """Đếm xung encoder bánh xe (JGA25-370, kênh C1) qua ngắt GPIO.

    Chỉ đếm xung trên MỘT kênh — không đọc chiều quay (chiều suy từ lệnh motor).
    Dùng để đo tốc độ quay thực tế của từng bánh (số xung/thời gian), phục vụ
    chẩn đoán/calibrate `PWM_COMPENSATION` — không tham gia vòng điều khiển
    thời gian thực (bám line vẫn dùng open-loop PWM_COMPENSATION cố định).

    ⚠️ JGA25-370 cho xung dày hơn nhiều so với đĩa khe quang (~1000 xung/s mỗi
    bánh ở tốc độ cao). Callback gpiozero có thể RỚT xung ở mức này. Chấp nhận
    được vì calibrate chỉ so TỈ LỆ trái/phải (2 bên rớt tương đương). Nếu thấy
    số giật thất thường thì chuyển riêng phần encoder sang pigpio.
    """

    def __init__(self, pin: int):
        self._count = 0
        try:
            self._device = DigitalInputDevice(pin)
            self._device.when_activated = self._on_pulse
            self.available = True
        except Exception as e:
            self._device = None
            self.available = False
            logger.warning("Encoder GPIO %d không khả dụng (%s)", pin, e)

    def _on_pulse(self):
        self._count += 1

    def read_and_reset(self) -> int:
        count = self._count
        self._count = 0
        return count

    def close(self):
        if self._device is not None:
            self._device.close()


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
        # Hàm kiểm "có phải bỏ dở việc đang làm không" — các vòng lặp dài (bám line,
        # tiếp cận, advance) poll hàm này để dừng NGAY khi trọng tài cho reset giữa
        # trận. Không có nó thì phải chờ hết timeout (tới 15s) mới phản ứng được.
        self.abort_check = None
        # Các bước của route gần nhất đã chạy XONG (dùng để tính lại vị trí khi route
        # chạy dở — xem execute_route / navigation.apply)
        self.last_route_progress: list = []

        # Encoder tốc độ bánh xe (JGA25-370 kênh C1) — đo lệch tốc độ 2 bánh
        self._encoder_left = WheelEncoder(config.ENCODER_LEFT_PIN)
        self._encoder_right = WheelEncoder(config.ENCODER_RIGHT_PIN)

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

    def _aborted(self) -> bool:
        """True nếu caller yêu cầu bỏ dở (reset giữa trận)."""
        if self.abort_check is None:
            return False
        try:
            if self.abort_check():
                self.stop()
                logger.warning("Bỏ dở thao tác đang chạy theo yêu cầu (reset)")
                return True
        except Exception as e:
            logger.warning("Lỗi abort_check: %s", e)
        return False

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
    # Encoder tốc độ bánh xe
    # ----------------------------------------------------------

    def sample_wheel_pulses(self, duration: float = None) -> tuple[int, int]:
        """Đếm xung encoder trái/phải trong `duration` giây.

        Gọi trong lúc bánh đang chạy (forward()/backward() trước đó) để đo
        tốc độ thực tế từng bánh — dùng cho chẩn đoán/calibrate PWM_COMPENSATION.
        """
        duration = config.ENCODER_SAMPLE_TIME if duration is None else duration
        self._encoder_left.read_and_reset()
        self._encoder_right.read_and_reset()
        time.sleep(duration)
        return self._encoder_left.read_and_reset(), self._encoder_right.read_and_reset()

    # ----------------------------------------------------------
    # Điều khiển cơ bản
    # ----------------------------------------------------------

    def forward(self, speed: float = config.SPEED_DEFAULT):
        logger.debug("Tiến - speed=%s", speed)
        self._left_rev.value = 0
        self._right_rev.value = 0
        self._left_fwd.value = self._pct(speed * config.PWM_COMPENSATION_LEFT)
        self._right_fwd.value = self._pct(speed * config.PWM_COMPENSATION)

    def backward(self, speed: float = config.SPEED_DEFAULT):
        logger.debug("Lùi - speed=%s", speed)
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.value = self._pct(speed * config.PWM_COMPENSATION_LEFT_REV)
        self._right_rev.value = self._pct(speed * config.PWM_COMPENSATION_REV)

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
        # Cả 4 chân đều là PWMOutputDevice → dùng chung `.value = 0` cho cả 4
        # (trước đây 2 chân lùi dùng `.off()`, khác kiểu không vì lý do gì).
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.value = 0
        self._right_rev.value = 0

    # ----------------------------------------------------------
    # Xuất phát — tìm line đầu tiên
    # ----------------------------------------------------------

    def exit_start_zone(self, speed: float = config.EXIT_START_SPEED,
                        timeout: float = config.EXIT_START_TIMEOUT) -> bool:
        """
        Thoát ô start (GAP — không có line trên R0).

        Robot đặt quay mặt sang trái (9h, về Kệ 3):
        1. Tiến thẳng cho đến khi chạm line ngang R0
        2. Bám line ngắn để căn giữa — KHÔNG đếm giao lộ ở đây
        Giao lộ do route của navigation.plan() đếm, tránh đếm kép.
        """
        logger.info("Thoát ô start — tiến thẳng tìm line R0 (speed=%d%%)", speed)
        start = time.time()
        self.forward(speed)

        found = False
        while time.time() - start < timeout:
            if self._aborted():
                return False
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
    # Dò nhánh line bên cạnh (xác định nửa sân)
    # ----------------------------------------------------------

    def probe_side_branch(self, direction: str = "right") -> bool | None:
        """
        Đang đứng TẠI một giao lộ: xoay 90° về phía `direction`, tiến ra khỏi giao lộ
        một đoạn ngắn để xem phía đó CÓ đường line đi tiếp không, rồi lùi lại và xoay
        về đúng tư thế cũ.

        Trả True = có line, False = không có, None = không kết luận được (cảm biến lỗi).

        VÌ SAO PHẢI TIẾN RA: ngay tại giao lộ thì đường line cắt ngang nằm dọc theo
        thanh cảm biến nên MỌI mắt đều thấy đen dù xoay kiểu gì — đọc ở đó không phân
        biệt được gì. Chỉ khi ra khỏi vùng giao nhau mới biết phía đó có line hay không.
        """
        if not self._line_sensor.available:
            logger.error("Không có cảm biến line — không dò được nhánh")
            return None

        logger.info("Dò nhánh line phía %s...", "PHẢI" if direction == "right" else "TRÁI")
        if direction == "right":
            self.turn_right_90()
        else:
            self.turn_left_90()

        # Tiến ra khỏi vùng 2 line cắt nhau
        self.forward(config.PROBE_SPEED)
        time.sleep(config.PROBE_TRAVEL_TIME)
        self.stop()
        time.sleep(0.1)

        # Lấy nhiều mẫu, chỉ cần một lần thấy line là đủ kết luận "có nhánh"
        found = False
        ok_any = False
        deadline = time.time() + config.PROBE_SAMPLE_TIME
        while time.time() < deadline:
            raw = self.read_line_sensor_raw()
            if self._line_sensor.last_read_ok:
                ok_any = True
                if sum(LineSensor.digital_from_raw(raw)) > 0:
                    found = True
                    break
            time.sleep(0.02)

        # Lùi về đúng chỗ cũ rồi xoay trả lại tư thế ban đầu
        self.backward(config.PROBE_SPEED)
        time.sleep(config.PROBE_TRAVEL_TIME)
        self.stop()
        if direction == "right":
            self.turn_left_90()
        else:
            self.turn_right_90()

        if not ok_any:
            logger.error("Dò nhánh: cảm biến line lỗi suốt — không kết luận")
            return None
        logger.info("Dò nhánh phía %s: %s line",
                    direction, "CÓ" if found else "KHÔNG có")
        return found

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
        """Chạy route do navigation.plan() sinh ra.

        Lệnh hợp lệ: ("forward", N) | ("back", N) | ("left",) | ("right",) | ("advance",).
        Route RỖNG = không có gì để đi (robot đã ở đích) → coi là thành công; caller
        tự quyết định có gọi hay không.
        """
        # Ghi lại các bước ĐÃ hoàn thành để caller biết robot dừng ở đâu khi route
        # chạy dở (xem navigation.apply). Không có cái này thì sau một lần mất line,
        # mọi tính toán vị trí phía sau đều sai mà không ai biết.
        self.last_route_progress = []

        if not route:
            logger.info("Route rỗng — robot đã ở đích, không cần di chuyển")
            return True

        for step in route:
            action = step[0]
            if action == "forward":
                # Gọi MỘT lần cho cả N giao lộ (chia nhỏ sẽ ép dừng ở từng cái, mất
                # hết cái lợi của chế độ chạy liền); tiến độ ghi qua callback.
                count = max(0, step[1])
                if count and not self.navigate_intersections(
                        count,
                        on_reached=lambda: self.last_route_progress.append(("forward", 1))):
                    return False
            elif action == "back":
                # Rút khỏi kệ/nhà máy mà không xoay 180° — cũng đi từng giao lộ một
                # để biết chính xác dừng ở đâu khi hỏng giữa chừng.
                for _ in range(max(0, step[1])):
                    if not self.back_to_intersection(1):
                        return False
                    self.last_route_progress.append(("back", 1))
            elif action == "left":
                self.turn_left_90()
                self.last_route_progress.append(step)
            elif action == "right":
                self.turn_right_90()
                self.last_route_progress.append(step)
            elif action == "advance":
                if not self.advance_to_end():
                    return False
                self.last_route_progress.append(step)
            else:
                logger.error("Lệnh route không hợp lệ: %s — dừng route", step)
                self.stop()
                return False
        return True

    def advance_to_end(self, base_speed: float = config.ADVANCE_SPEED,
                       timeout: float = config.ADVANCE_TIMEOUT) -> bool:
        """
        Bám line tới ĐIỂM CUỐI của line (vào kệ / khu nhà máy / Kệ 4).

        Khác navigate_intersections(): những chỗ này KHÔNG phải giao lộ — line chỉ
        đơn giản là hết, nên không đếm được. Dừng khi:
          1. Mất line liên tục config.LINE_END_CONFIRM_TIME giây → đã hết line, hoặc
          2. Siêu âm thấy mục tiêu ở gần (≤ APPROACH_SLOW_DISTANCE) → để
             approach_shelf() canh nốt đoạn cuối cho chính xác, hoặc
          3. Gặp giao lộ (bản đồ sai / robot đi lố) → dừng và báo thất bại.
        """
        logger.info("Bám line tới hết line (advance, speed=%d%%)", base_speed)
        # Lệnh advance luôn bắt đầu khi robot đang ĐỨNG TRÊN giao lộ (vừa dừng ở
        # giao lộ cuối của forward, hoặc vừa xoay tại giao lộ). Không thoát ra trước
        # thì follow_line() nhận ngay chính giao lộ đó và báo "đi lố".
        self._escape_intersection(base_speed)
        start = time.time()
        lost_since = None

        while time.time() - start < timeout:
            if self._aborted():
                return False
            dist = self.get_distance()
            if 0 <= dist <= config.APPROACH_SLOW_DISTANCE:
                self.stop()
                logger.info("Advance: đã tới gần mục tiêu (%.1fcm)", dist)
                return True

            at_intersection, values = self.follow_line(base_speed)
            if at_intersection:
                self.stop()
                logger.warning("Advance: gặp giao lộ — bản đồ hoặc vị trí không khớp")
                return False

            if sum(values) == 0:
                if lost_since is None:
                    lost_since = time.time()
                elif time.time() - lost_since >= config.LINE_END_CONFIRM_TIME:
                    self.stop()
                    logger.info("Advance: đã hết line — dừng tại điểm cuối")
                    return True
            else:
                lost_since = None

            time.sleep(0.01)

        self.stop()
        logger.warning("Advance: timeout sau %.1fs", timeout)
        return False

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
        target_seen = False

        while time.time() - start < config.APPROACH_TIMEOUT:
            if self._aborted():
                return False
            dist = self.get_distance(samples=3)  # median chống nhiễu HC-SR04
            if dist < 0:
                # Lỗi đọc mẫu này — KHÔNG hiểu nhầm thành "đã tới", thử lại
                time.sleep(0.02)
                continue
            if dist <= target_cm:
                self.stop()
                logger.info("Đã đến vị trí kệ — khoảng cách %.1fcm", dist)
                return True

            if dist <= config.APPROACH_DETECT_DISTANCE:
                target_seen = True
            elif not target_seen and time.time() - start > config.APPROACH_BLIND_TIMEOUT:
                # Chạy mù quá lâu mà chưa lần nào thấy mục tiêu trong tầm → DỪNG.
                # Không được chạy tiếp hết APPROACH_TIMEOUT: ở tốc độ này robot sẽ
                # lao ra khỏi sa bàn hoặc sang sân đối phương (bị reset −10 điểm).
                self.stop()
                logger.error("Tiếp cận: chạy mù %.1fs mà không thấy mục tiêu trong %.0fcm "
                             "(đo được %.1fcm) — dừng an toàn",
                             config.APPROACH_BLIND_TIMEOUT,
                             config.APPROACH_DETECT_DISTANCE, dist)
                return False

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
            if self._aborted():
                return False
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

    def follow_line(self, base_speed: float = config.SPEED_DEFAULT,
                    reverse: bool = False) -> tuple[bool, list[int]]:
        """Một nhịp bám line. reverse=True thì chạy LÙI mà vẫn bám line.

        ⚠️ Khi lùi PHẢI đảo dấu hiệu chỉnh. Thanh cảm biến gắn ở ĐẦU xe, lùi thì nó
        thành đuôi. Đặt y = lệch của cảm biến so với line, θ = lệch hướng, v = vận
        tốc, L = khoảng cách trục bánh → cảm biến, luật lái ω = -k·y:

            ẏ = v·θ − L·k·y ,  θ̇ = −k·y   →   det = v·k

        Hệ chỉ hội tụ khi det > 0, tức k phải CÙNG DẤU với v. Lùi (v < 0) mà giữ
        nguyên dấu k thì det < 0 — robot ngoáy đuôi mỗi lúc một mạnh rồi văng khỏi
        line. Đảo dấu là đủ để ổn định trở lại.
        """
        raw = self.read_line_sensor_raw()
        values = LineSensor.digital_from_raw(raw)
        active_count = sum(values)

        if active_count >= config.INTERSECTION_THRESHOLD:
            self.stop()
            logger.info("Phát hiện giao lộ (active=%d)", active_count)
            return True, values

        self._steer(raw, base_speed, reverse)
        return False, values

    def _steer(self, raw: list[float], base_speed: float, reverse: bool = False):
        """Một nhịp lái PD theo sai số line. Tách riêng để chế độ chạy liền
        (_navigate_continuous) dùng chung đúng luật lái với follow_line()."""
        error = self.compute_line_error_analog(raw)
        derivative = error - self._last_error
        correction = config.LINE_KP * error + config.LINE_KD * derivative
        self._last_error = error
        if reverse:
            correction = -correction
        self._drive(base_speed + correction, base_speed - correction, reverse)

    def _drive_straight(self, base_speed: float, reverse: bool = False):
        """Đi thẳng, KHÔNG lái — dùng khi đang cắt ngang vạch giao lộ (mọi mắt đều
        đen nên sai số line là số rác, để PD chạy theo sẽ giật)."""
        self._drive(base_speed, base_speed, reverse)

    def _drive(self, left_speed: float, right_speed: float, reverse: bool = False):
        """Đặt tốc độ 2 bánh (đã kẹp 0-100) kèm bù lệch — dùng ĐÚNG cùng hệ số như
        forward()/backward(), nếu không đi thẳng và bám line sẽ lệch nhau sau
        khi calibrate."""
        left_speed = max(0, min(100, left_speed))
        right_speed = max(0, min(100, right_speed))
        if reverse:
            self._left_fwd.value = 0
            self._right_fwd.value = 0
            self._left_rev.value = self._pct(left_speed * config.PWM_COMPENSATION_LEFT_REV)
            self._right_rev.value = self._pct(right_speed * config.PWM_COMPENSATION_REV)
        else:
            self._left_rev.value = 0
            self._right_rev.value = 0
            self._left_fwd.value = self._pct(left_speed * config.PWM_COMPENSATION_LEFT)
            self._right_fwd.value = self._pct(right_speed * config.PWM_COMPENSATION)

    def back_to_intersection(self, count: int = 1,
                             base_speed: float = config.REVERSE_SPEED,
                             timeout: float = config.REVERSE_TIMEOUT) -> bool:
        """LÙI dọc theo line qua `count` giao lộ (lệnh ("back", N) của navigation).

        Dùng để rút khỏi kệ / khu nhà máy mà KHÔNG phải xoay 180° — mỗi lần bỏ được
        2 lần xoay, và xoay là chi phí cố định lớn nhất của trận (~84s/70 lần).

        Khác `follow_line_until_intersection`: mất line thì DỪNG hẳn chứ không quét
        tìm lại. Đoạn điểm-cuối → giao lộ là đường liền, không có khoảng đứt nào; mất
        line ở đây nghĩa là đã lệch thật, mà quét tìm khi đang lùi thì dễ đâm vào kệ
        vừa rời.
        """
        if count <= 0:
            return True

        # Xoá sai số cũ TRƯỚC khi đổi chiều. `_last_error` đang giữ giá trị của lần
        # bám line khi TIẾN; giữ lại thì nhịp lùi đầu tiên có đạo hàm giả
        # (LINE_KD × chênh lệch) và robot giật một cái ngay lúc bắt đầu lùi.
        self._last_error = 0.0

        for i in range(count):
            if self._aborted():
                return False
            # Đang đứng NGAY TRÊN giao lộ vừa tới (trừ lần đầu, lúc đó ở điểm cuối).
            # Không lùi khỏi nó trước thì follow_line nhận lại chính giao lộ đó và
            # coi như đã đi xong chặng kế tiếp.
            if i > 0:
                self._escape_intersection(base_speed, reverse=True)
            logger.info("Lùi về giao lộ %d/%d (speed=%d%%)", i + 1, count, base_speed)
            start = time.time()
            lost_since = None
            reached = False

            while time.time() - start < timeout:
                if self._aborted():
                    return False
                at_intersection, values = self.follow_line(base_speed, reverse=True)
                if at_intersection:
                    reached = True
                    break
                if sum(values) == 0:
                    if lost_since is None:
                        lost_since = time.time()
                    elif time.time() - lost_since > config.LINE_GAP_COAST_TIME:
                        self.stop()
                        logger.error("Lùi: mất line quá %.1fs — dừng an toàn",
                                     config.LINE_GAP_COAST_TIME)
                        return False
                else:
                    lost_since = None
                time.sleep(0.01)

            self.stop()
            if not reached:
                logger.warning("Lùi: timeout sau %.1fs, không thấy giao lộ", timeout)
                return False

            # Thân xe đang nằm QUÁ giao lộ một đoạn = khoảng cách trục bánh → cảm biến
            # (tiến thì nằm trước giao lộ đúng bấy nhiêu). Tiến bù nếu đã calibrate.
            if config.REVERSE_RECENTER_TIME > 0:
                self.forward(base_speed)
                time.sleep(config.REVERSE_RECENTER_TIME)
                self.stop()

        # Trả sai số về 0 để lần bám line TIẾN kế tiếp không thừa hưởng đạo hàm của
        # pha lùi (dấu hiệu chỉnh 2 pha ngược nhau).
        self._last_error = 0.0
        return True

    def follow_line_until_intersection(self, base_speed: float = config.SPEED_DEFAULT,
                                       timeout: float = 15.0) -> bool:
        start = time.time()
        lost_since = None

        while time.time() - start < timeout:
            if self._aborted():
                return False
            at_intersection, values = self.follow_line(base_speed)
            if at_intersection:
                return True

            if sum(values) == 0:
                # Mất line: có thể là khoảng ĐỨT thật của sa bàn (ô xuất phát trên
                # hàng R0 ~245mm) chứ không phải lạc. Giữ nguyên lái và trôi thẳng
                # trong LINE_GAP_COAST_TIME giây trước khi kết luận là lạc — quét
                # tìm lại quá sớm sẽ làm robot quay ngang giữa khoảng đứt.
                if lost_since is None:
                    lost_since = time.time()
                elif time.time() - lost_since > config.LINE_GAP_COAST_TIME:
                    logger.warning("Mất line quá %.1fs (dài hơn khoảng đứt đã biết)! Quét tìm lại...",
                                   config.LINE_GAP_COAST_TIME)
                    if self._recover_line():
                        lost_since = None
                    else:
                        self.stop()
                        logger.error("Không tìm lại được line!")
                        return False
            else:
                lost_since = None

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

    def _escape_intersection(self, speed: float = config.SPEED_DEFAULT,
                             reverse: bool = False):
        """Chạy mù 0.3s để rời khỏi giao lộ đang đứng, trước khi bám line tiếp."""
        if reverse:
            self.backward(speed)
        else:
            self.forward(speed)
        time.sleep(0.3)
        self.stop()

    def navigate_intersections(self, count: int,
                               base_speed: float = config.SPEED_DEFAULT,
                               on_reached=None) -> bool:
        """Bám line qua `count` giao lộ.

        on_reached: gọi sau MỖI giao lộ đếm được — caller dùng để ghi tiến độ mà
            không phải chia nhỏ lời gọi (chia nhỏ sẽ ép dừng ở từng giao lộ, mất
            hết cái lợi của chế độ chạy liền).
        """
        if count <= 0:
            return True
        if getattr(config, "CONTINUOUS_INTERSECTIONS", False):
            return self._navigate_continuous(count, base_speed, on_reached)

        for i in range(count):
            if self._aborted():
                return False
            logger.info("Đi đến giao lộ %d/%d", i + 1, count)
            self._escape_intersection(base_speed)
            if not self.follow_line_until_intersection(base_speed):
                logger.error("Không tìm thấy giao lộ %d/%d!", i + 1, count)
                self.stop()
                return False
            if on_reached is not None:
                on_reached()
        self.stop()
        return True

    def _navigate_continuous(self, count: int, base_speed: float, on_reached=None) -> bool:
        """Đếm giao lộ mà KHÔNG dừng ở từng cái — chỉ dừng ở giao lộ CUỐI.

        Vì sao đáng làm: chế độ dừng-từng-cái tốn 0.3s chạy mù (_escape_intersection)
        cộng phanh + tăng tốc lại cho MỖI giao lộ. Kịch bản tệ nhất đi qua ~65 giao
        lộ, nên riêng phần đứng dậy ngồi xuống đã ăn hàng chục giây.

        Chống đếm trùng bằng TRỄ HAI NGƯỠNG: đếm khi số mắt thấy line ≥
        INTERSECTION_THRESHOLD, và chỉ cho phép đếm cái kế sau khi đã tụt xuống ≤
        INTERSECTION_CLEAR_THRESHOLD (đã ra khỏi vạch cắt). Một ngưỡng đơn sẽ rung
        quanh mép vạch và đếm một giao lộ thành nhiều.

        Khi ĐANG cắt ngang vạch thì mọi mắt đều đen → sai số bám line vô nghĩa, nên
        giữ thẳng lái cho tới lúc ra khỏi vạch thay vì để PD giật theo số rác.
        """
        clear_threshold = getattr(config, "INTERSECTION_CLEAR_THRESHOLD", 2)
        timeout = config.CONTINUOUS_TIMEOUT_PER_HOP * count
        start = time.time()
        seen = 0
        on_mark = False          # đang nằm trên vạch cắt, chưa ra khỏi
        lost_since = None

        logger.info("Đi qua %d giao lộ (chạy liền, không dừng giữa chừng)", count)
        while time.time() - start < timeout:
            if self._aborted():
                return False

            raw = self.read_line_sensor_raw()
            values = LineSensor.digital_from_raw(raw)
            active = sum(values)

            if active >= config.INTERSECTION_THRESHOLD:
                if not on_mark:
                    on_mark = True
                    seen += 1
                    logger.info("Qua giao lộ %d/%d", seen, count)
                    if on_reached is not None:
                        on_reached()
                    if seen >= count:
                        self.stop()
                        return True
                lost_since = None
                self._drive_straight(base_speed)      # cắt ngang: giữ thẳng lái
                time.sleep(0.01)
                continue

            if active <= clear_threshold:
                on_mark = False

            if active == 0:
                if lost_since is None:
                    lost_since = time.time()
                elif time.time() - lost_since > config.LINE_GAP_COAST_TIME:
                    logger.warning("Chạy liền: mất line quá %.1fs — quét tìm lại",
                                   config.LINE_GAP_COAST_TIME)
                    if not self._recover_line():
                        self.stop()
                        logger.error("Không tìm lại được line!")
                        return False
                    lost_since = None
            else:
                lost_since = None

            self._steer(raw, base_speed)
            time.sleep(0.01)

        self.stop()
        logger.error("Chạy liền: timeout sau %.1fs, mới qua %d/%d giao lộ",
                     timeout, seen, count)
        return False

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
        self._encoder_left.close()
        self._encoder_right.close()
        if self._distance_sensor:
            self._distance_sensor.close()
