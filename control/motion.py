"""
Module điều khiển động cơ di chuyển, cảm biến dò line, và cảm biến siêu âm.
Line sensor: QTR-8A (analog) qua MCP3008 (SPI ADC).
Dùng gpiozero (tương thích RPi 4 trên cả Bullseye lẫn Bookworm).
"""

import math
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
    def nguong_cho(raw: list[float]) -> float:
        """Ngưỡng đen/trắng cho MỘT lần đọc — tính từ chính dải sáng-tối của nó.

        VÌ SAO KHÔNG DÙNG NGƯỠNG CỐ ĐỊNH: QTR-8A đo PHẢN XẠ. Ánh sáng nền tối đi thì
        nền trắng phản xạ ít hơn, mọi giá trị tụt xuống — mắt ở RÌA vạch rơi xuống
        dưới ngưỡng cố định và bị đếm là đen. Đủ 4 mắt là báo GIAO LỘ GIẢ giữa đoạn
        thẳng. Đo trên robot buổi tối: hay nhầm giao lộ dù đang trên đường thẳng.
        Mà thể lệ ghi rõ ánh sáng ở sân thi KHÔNG đảm bảo ổn định.

        Không chữa được bằng cách nâng INTERSECTION_THRESHOLD lên 5: C0R0 là NGÃ BA,
        chỉ cho 4/6 mắt (vạch dọc chỉ kéo về một phía) — nâng lên là mất giao lộ thật.

        Ngưỡng tương đối = min + (max − min) × LINE_ADAPTIVE_FRACTION, nên nó trôi
        theo ánh sáng. Khi cả thanh cùng đen hoặc cùng trắng thì dải quá hẹp, công
        thức vô nghĩa — lúc đó rơi về ngưỡng tuyệt đối như cũ.
        """
        if not raw or not getattr(config, "LINE_ADAPTIVE", False):
            return LineSensor._threshold_norm()
        lo, hi = min(raw), max(raw)
        # ⛔ PHẢI CÓ CÁI GÌ ĐÓ ĐEN THẬT thì chia tỉ lệ mới có nghĩa.
        # Công thức tương đối chia trên dải sáng-tối của CHÍNH lần đọc đó, nên khi
        # cả thanh chỉ toàn xám nó vẫn bịa ra một ngưỡng nằm giữa đám xám.
        # Đo trên robot 03/08, robot đứng trên TẤM IN khu nhà máy:
        #     ADC [626, 750, 642, 863, 624, 555]   ngưỡng 667   → [1,0,1,0,1,1]
        # Không mắt nào đen (tối nhất 555/1023), nhưng 4 mắt bị gọi là "thấy line".
        # Hậu quả: advance tưởng VẪN ĐANG BÁM LINE nên không bao giờ thấy "hết
        # line" — robot chạy đè qua khu nhà máy rồi ra khỏi mép sa bàn (có ảnh).
        # Thể lệ: rời sa bàn = bị reset.
        if lo > config.LINE_STRICT_BLACK:
            return LineSensor._threshold_norm()
        dai_toi_thieu = config.LINE_ADAPTIVE_MIN_RANGE / 1023.0
        if hi - lo < dai_toi_thieu:
            return LineSensor._threshold_norm()
        return lo + (hi - lo) * config.LINE_ADAPTIVE_FRACTION

    @staticmethod
    def digital_from_raw(raw: list[float]) -> list[int]:
        threshold = LineSensor.nguong_cho(raw)
        return [1 if v < threshold else 0 for v in raw]

    @staticmethod
    def dem_den_dam(raw: list[float]) -> int:
        """Đếm số mắt đen ĐẬM — theo ngưỡng TUYỆT ĐỐI chặt, KHÔNG phải thích nghi.

        Dùng khi cần BẰNG CHỨNG một mảng in đen thật, chứ không chỉ cần tín hiệu.
        Ngưỡng thích nghi tự co theo dải sáng-tối của từng lần đọc, nên khi cả
        thanh cùng nhìn vào vùng nhạt thì mép mờ của vạch cũng bị đếm là đen.
        Lý do đầy đủ + số đo: config.LINE_STRICT_BLACK.
        """
        if not raw:
            return 0
        return sum(1 for v in raw if v <= config.LINE_STRICT_BLACK)

    @staticmethod
    def day_den_dam_dai_nhat(raw: list[float]) -> int:
        """Dãy mắt đen ĐẬM LIỀN NHAU dài nhất.

        Đếm tổng số mắt đen thôi thì chưa đủ. Đo trên robot 03/08, hai lần đọc cùng
        cho 4 mắt đen đậm nhưng chỉ một cái là giao lộ:

            hình in mascot   ADC [ 21, 515,   0,   0,   5, 917]   đen ở 1,_,3,4,5,_
            giao lộ C0R0     ADC [917, 914,   0,   0,   0,   0]   đen ở _,_,3,4,5,6

        Vạch line là một DẢI LIỀN, không thể có mắt sáng kẹp giữa hai mắt đen. Đứt
        quãng giữa thanh cảm biến là hình in, không phải vạch. Bộ lọc chỉ đếm tổng
        đã cho cái trên lọt qua và robot chốt nhầm pose = C0R0 khi còn cách ~20cm.
        """
        if not raw:
            return 0
        dai = tot = 0
        for v in raw:
            if v <= config.LINE_STRICT_BLACK:
                dai += 1
                tot = max(tot, dai)
            else:
                dai = 0
        return tot

    @staticmethod
    def la_giao_lo_that(raw: list[float]) -> bool:
        """Có phải GIAO LỘ THẬT không — hay chỉ là một mảng IN trên sa bàn.

        Hai điều kiện, và cả hai đều cần:
          1. đủ INTERSECTION_THRESHOLD mắt đen ĐẬM  (loại vạch thường bị ngưỡng
             thích nghi thổi lên)
          2. có ÍT NHẤT MỘT mắt ĐEN SÂU             (loại mảng in xam xám)

        Điều kiện 2 là thứ phân biệt được vòng tròn ROBOCON / tấm in nhà máy với
        giao lộ: vạch line in đen tuyền nên luôn có mắt đọc ~0, còn mảng in thì tối
        nhất cũng chỉ ~53. Số đo đầy đủ ở config.LINE_DEEP_BLACK.
        """
        if not raw:
            return False
        sau = sum(1 for v in raw if v <= config.LINE_DEEP_BLACK)
        return (LineSensor.dem_den_dam(raw) >= config.INTERSECTION_THRESHOLD
                and sau >= config.LINE_DEEP_BLACK_COUNT)

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
                # KHÔNG bỏ trống: mặc định của gpiozero là 9 mẫu → .distance là
                # trung vị của 540ms lịch sử, trễ ~270ms so với thực tế. Xem
                # config.ULTRASONIC_QUEUE_LEN.
                queue_len=config.ULTRASONIC_QUEUE_LEN,
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

    def get_distance(self) -> float:
        """Đo khoảng cách (cm). Trả -1.0 nếu không có cảm biến HOẶC lỗi đọc.

        Không tự lọc nhiễu ở đây nữa: gpiozero ĐÃ lấy trung vị sẵn trên
        config.ULTRASONIC_QUEUE_LEN mẫu. Bản trước gọi `.distance` 3 lần rồi lấy
        trung vị — nhưng 3 lần đọc đó chạy trong vài phần triệu giây, trong khi
        luồng nền của gpiozero chỉ cập nhật mỗi ~60ms, nên cả 3 lần trả về CÙNG
        MỘT giá trị. Phép lọc đó không làm gì cả, chỉ tạo cảm giác an toàn giả.
        """
        if self._distance_sensor is None:
            return -1.0
        try:
            return self._distance_sensor.distance * 100
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

    # Xoay tại chỗ: MỖI bánh phải dùng hệ số bù ĐÚNG CHIỀU nó đang chạy — bánh trái
    # lùi thì lấy *_LEFT_REV, bánh phải lùi thì lấy *_REV. Bản trước bỏ hẳn hệ số của
    # bánh trái và luôn lấy hệ số TIẾN cho bánh phải: hiện tại 4 hệ số đều 0.95/1.00
    # nên không thấy gì, nhưng TURN_TIME chỉ có MỘT hằng số dùng cho cả 2 chiều —
    # calibrate xong mà 2 hệ số lệch nhau thì một chiều xoay quá, chiều kia xoay thiếu,
    # và không cách nào chỉnh TURN_TIME cho khớp cả hai.
    def turn_left(self, speed: float = config.SPEED_TURN):
        logger.debug("Xoay trái - speed=%s", speed)
        self._left_fwd.value = 0
        self._left_rev.value = self._pct(speed * config.PWM_COMPENSATION_LEFT_REV)
        self._right_rev.value = 0
        self._right_fwd.value = self._pct(speed * config.PWM_COMPENSATION)

    def turn_right(self, speed: float = config.SPEED_TURN):
        logger.debug("Xoay phải - speed=%s", speed)
        self._left_rev.value = 0
        self._left_fwd.value = self._pct(speed * config.PWM_COMPENSATION_LEFT)
        self._right_fwd.value = 0
        self._right_rev.value = self._pct(speed * config.PWM_COMPENSATION_REV)

    def stop(self):
        logger.debug("Dừng")
        # Cả 4 chân đều là PWMOutputDevice → dùng chung `.value = 0` cho cả 4
        # (trước đây 2 chân lùi dùng `.off()`, khác kiểu không vì lý do gì).
        self._left_fwd.value = 0
        self._right_fwd.value = 0
        self._left_rev.value = 0
        self._right_rev.value = 0

    def stop_gently(self, from_speed: float, reverse: bool = False,
                    ramp: float | None = None, settle: float | None = None):
        """Giảm dần PWM rồi mới cắt — dùng ở những chỗ TƯ THẾ robot quan trọng.

        VÌ SAO: `stop()` đặt cả 4 chân về 0, mà EN của L298N nối cứng mức cao nên
        hai đầu motor cùng bị kéo xuống đất — đó là PHANH ĐỘNG, không phải thả
        trôi. Phanh gấp ở đây sinh mô-men giật; hai bánh không phanh giống hệt
        nhau, cộng 2 bánh caster tự xoay, là robot lệch đi vài độ ngay tại chỗ.
        Vài độ đó đủ làm càng không luồn thẳng vào khe pallet ở bước kế tiếp — mà
        bước kế tiếp không còn line để tự sửa nữa.

        Rồi `settle` đứng yên một nhịp cho khung xe hết chòng chành trước khi làm
        việc tiếp.

        ⚠️ ĐÁNH ĐỔI: giảm dần thì robot trôi thêm một đoạn so với phanh gấp. Đo
        lại `APPROACH_DISTANCE` sau khi bật cái này — nếu robot dừng sát kệ hơn
        trước thì hạ `STOP_RAMP_TIME` chứ đừng vội đổi `APPROACH_DISTANCE`, vì
        khoảng cách đó còn ràng buộc với vị trí khe pallet.
        """
        ramp = config.STOP_RAMP_TIME if ramp is None else ramp
        settle = config.STOP_SETTLE_TIME if settle is None else settle
        steps = max(1, int(getattr(config, "STOP_RAMP_STEPS", 4)))
        drive = self.backward if reverse else self.forward

        if ramp > 0 and from_speed > 0:
            for i in range(steps - 1, 0, -1):
                drive(from_speed * i / steps)
                time.sleep(ramp / steps)
        self.stop()
        if settle > 0:
            time.sleep(settle)

    # ----------------------------------------------------------
    # Xuất phát — tìm line đầu tiên
    # ----------------------------------------------------------

    def exit_start_zone(self, speed: float = config.EXIT_START_SPEED,
                        timeout: float = config.EXIT_START_TIMEOUT) -> bool:
        """
        Thoát ô start (GAP — không có line trên R0).

        Robot đặt quay mặt sang trái (9h, về Kệ 3):
        1. Tiến thẳng MÙ cho tới khi ĐI QUA HẾT vùng in (thấy đen rồi thấy sạch),
           hoặc hết `EXIT_START_BLIND_TIME` giây — cái nào tới trước
        2. Tiến tiếp cho đến khi chạm line ngang R0
        3. Bám line ngắn để căn giữa — KHÔNG đếm giao lộ ở đây
        Giao lộ do route của navigation.plan() đếm, tránh đếm kép.

        ⚠️ VÌ SAO CÓ BƯỚC MÙ (1): ô xuất phát nằm trong khoảng ĐỨT của R0, và chỗ
        đó in hình MASCOT — mặt robot màu đen tuyền. Quét trên bản in, dọc đúng vệt
        thanh cảm biến sẽ đi qua:

            −10cm → +10.2cm : MASCOT, tới 14/23 px đen  ← robot NGỒI TRÊN vùng này
            10.2  → 21.9cm  : sạch
            21.9cm →        : line R0 THẬT, đều đặn 7/23 px
            51.2cm          : giao lộ C0R0

        Không có bước mù thì `sum(values) > 0` đúng ngay mẫu ĐẦU TIÊN — robot dừng
        tại chỗ và "căn giữa" 1 giây trên mặt con mascot, rồi coi như đã ra tới R0.

        Cửa sổ mù phải kết thúc trong khoảng **10.2cm → 51.2cm** kể từ chỗ đặt:
        ngắn quá thì vẫn dính mascot, dài quá thì vượt qua giao lộ C0R0 mà không
        đếm được, và lệnh `("forward", 1)` sau đó sẽ chạy tới tận kệ mà không thấy
        giao lộ nào.

        Điểm kết thúc bám theo HÌNH IN chứ không theo đồng hồ: thấy đen rồi thấy
        SẠCH = vừa ra khỏi mascot, và sau mascot là 11.7cm sạch trước line thật.
        Nhờ vậy nó không phụ thuộc cm/s (chưa đo được) lẫn chỗ đặt robot trong ô
        400x400mm. `EXIT_START_BLIND_TIME` chỉ còn là CHẶN TRÊN, dùng khi robot
        được đặt ở chỗ không có hình in nào dưới cảm biến.
        """
        blind = getattr(config, "EXIT_START_BLIND_TIME", 0.0)
        # Bước căn giữa có thể chạy tới tận C0R0 — caller cần biết để lấy đúng pose.
        self.tren_giao_lo_dau = False
        # Cờ CHẮC CHẮN, không suy từ cảm biến: robot vừa rời ô xuất phát nên nó
        # KHÔNG đứng trên giao lộ nào. Chỉ ở đây mới biết chắc điều đó — mọi phép
        # thử bằng cảm biến đều sai ngay sau một cú xoay (ngã tư nhìn dọc nhánh
        # mới đọc ra y hệt vạch thẳng).
        self.vua_roi_o_xuat_phat = True
        logger.info("Thoát ô start — mù %.2fs (qua vùng in mascot) rồi tìm line R0 "
                    "(speed=%d%%)", blind, speed)
        start = time.time()
        self.forward(speed)

        found = False
        saw_art = False              # đã đi qua vùng in đen (mascot) chưa
        blind_done = blind <= 0
        while time.time() - start < timeout:
            if self._aborted():
                return False
            values = self.read_line_sensor()

            if not blind_done:
                # THOÁT SỚM khi đã qua hết vùng in: thấy đen rồi thấy SẠCH nghĩa là
                # vừa ra khỏi mascot, và sau mascot là 11.7cm sạch trước line R0
                # thật. Nhờ vậy điểm kết thúc cửa sổ mù bám theo HÌNH IN chứ không
                # theo đồng hồ — không còn phụ thuộc cm/s (thứ chưa đo được) lẫn chỗ
                # đặt robot trong ô 400x400mm. EXIT_START_BLIND_TIME tụt xuống chỉ
                # còn là CHẶN TRÊN cho trường hợp không thấy đen lần nào.
                if sum(values) > 0:
                    saw_art = True
                elif saw_art:
                    blind_done = True
                    logger.info("Thoát ô start: đã qua hết vùng in sau %.2fs — "
                                "bắt đầu tìm line R0", time.time() - start)
                if not blind_done and time.time() - start >= blind:
                    blind_done = True
                    logger.info("Thoát ô start: hết cửa sổ mù %.2fs (không thấy vùng "
                                "in nào) — bắt đầu tìm line R0", blind)
                if not blind_done:
                    time.sleep(0.01)
                    continue

            # ⛔ ĐÒI CÁC MẮT LIỀN NHAU. `sum(values) > 0` nhận bất kỳ hình dạng nào,
            # kể cả mắt CÁCH QUÃNG — mà vạch line rộng 20mm trên thanh trải 47mm thì
            # luôn cho một dãy LIỀN. Đo trên robot 04/08, nửa sân bên kia:
            #     Chạm line R0! sensor=[1, 0, 1, 0, 0, 1]   ← 1ms sau khi bắt đầu tìm
            # Ba mắt cách quãng, trên một mặt tối om (ADC cao nhất 284, trong khi nền
            # trắng bên nửa kia đọc 400-900). Robot căn giữa vào chỗ không có vạch
            # nào rồi đi mò cả sân. Đáng lẽ phải DỪNG và báo lỗi.
            raw_line = self.read_line_sensor_raw()
            lien = LineSensor.day_den_dam_dai_nhat(raw_line)
            if sum(values) > 0 and lien < config.EXIT_START_LINE_EYES:
                logger.info(
                    "Thoát ô start: bỏ qua tín hiệu %s — dãy đen ĐẬM LIỀN NHAU dài "
                    "nhất chỉ %d/%d. Vạch thật cho các mắt liền nhau; cách quãng là "
                    "nhiễu hoặc mặt tối, KHÔNG phải line. ADC %s",
                    values, lien, config.EXIT_START_LINE_EYES,
                    [int(round(v * 1023)) for v in raw_line])
                time.sleep(0.01)
                continue

            if sum(values) > 0:
                self.stop()
                logger.info("Chạm line R0! sensor=%s (dãy liền %d mắt)", values, lien)
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
                # ĐÒI BẰNG CHỨNG ĐẬM trước khi tin. Cờ này quyết định pose, mà
                # pose sai một giao lộ là robot đi lố vào kệ (hoặc dừng hẳn giữa
                # đường). Bước căn giữa lại là lúc robot XIÊN nhất, nên tín hiệu
                # giao lộ ở đây rất hay là mép mờ của chính vạch R0.
                # Số đo phân biệt hai ca: config.LINE_STRICT_BLACK.
                raw_gl = self.read_line_sensor_raw()
                dam = LineSensor.day_den_dam_dai_nhat(raw_gl)
                if dam < config.INTERSECTION_THRESHOLD:
                    logger.info(
                        "Căn line: tín hiệu giao lộ KHÔNG ĐỦ CHẮC (dãy đen đậm LIỀN "
                        "NHAU dài nhất %d/%d, ADC %s) — mép vạch khi robot còn xiên "
                        "hoặc hình in mascot, KHÔNG phải C0R0. Bỏ qua, căn tiếp.",
                        dam, config.INTERSECTION_THRESHOLD,
                        [int(round(v * 1023)) for v in raw_gl])
                    time.sleep(0.01)
                    continue
                # ⚠️ KHÔNG phải "ROUTE_START sẽ đếm" — route KHÔNG đếm được cái
                # giao lộ robot đang đứng lên (navigate_intersections mở đầu bằng
                # _escape_intersection). Lý do đầy đủ: navigation.pose_sau_xuat_phat.
                self.tren_giao_lo_dau = True
                logger.info("Chạm giao lộ khi căn line (dãy %d/%d mắt đen ĐẬM LIỀN NHAU) — robot "
                            "ĐANG ĐỨNG TRÊN C0R0. Caller lấy pose bằng "
                            "navigation.pose_sau_xuat_phat(motion.tren_giao_lo_dau).",
                            dam, config.INTERSECTION_THRESHOLD)
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
        # Dò mất ~2-4s và nằm ngay đầu trận — thiếu chỗ kiểm này thì bấm nút reset
        # trong lúc dò cũng phải chờ nó xoay/tiến/lùi xong mới phản ứng.
        if self._aborted():
            return None
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

        if self._aborted():
            return None
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

    def _xoay_90_bang_encoder(self, quay, ten: str) -> bool:
        """Xoay 90° đo bằng ENCODER. Trả False nếu chưa đo được vệt bánh.

        Xoay tại chỗ thì mỗi bánh lăn một cung π × vệt bánh / 4. Bộ đếm không đọc
        chiều quay, nhưng xoay tại chỗ hai bánh CÙNG sinh xung nên tổng xung =
        2 × cung × số xung mỗi cm. Lý do dùng cách này: config.WHEEL_TRACK_CM.
        """
        vet = getattr(config, "WHEEL_TRACK_CM", 0.0)
        xung_cm = getattr(config, "ENCODER_PULSES_PER_CM", 0.0)
        co_enc = (getattr(getattr(self, "_encoder_left", None), "available", False)
                  and getattr(getattr(self, "_encoder_right", None), "available", False))
        if vet <= 0 or xung_cm <= 0 or not co_enc:
            return False

        can = 2 * (math.pi * vet / 4) * xung_cm
        self._doc_xung()
        quay(config.SPEED_TURN)
        start, da = time.time(), 0
        cap = config.TURN_TIME * 3
        while da < can and time.time() - start < cap:
            if self._aborted():
                break
            da += self._doc_xung()
            time.sleep(0.005)
        self.stop()
        het_gio = da < can
        (logger.warning if het_gio else logger.info)(
            "Xoay 90° %s (encoder): %d/%.0f xung trong %.2fs%s", ten, da, can,
            time.time() - start,
            " — HẾT CHẶN TRÊN, chưa đủ cung. Bánh trượt hay encoder rớt xung?"
            if het_gio else "")
        return True

    def turn_left_90(self):
        if self._xoay_90_bang_encoder(self.turn_left, "trái"):
            return
        logger.info("Xoay 90° trái (%.2fs — chưa đo vệt bánh, chạy mù theo đồng hồ)",
                    config.TURN_TIME)
        self.turn_left(config.SPEED_TURN)
        time.sleep(config.TURN_TIME)
        self.stop()

    def turn_right_90(self):
        if self._xoay_90_bang_encoder(self.turn_right, "phải"):
            return
        logger.info("Xoay 90° phải (%.2fs — chưa đo vệt bánh, chạy mù theo đồng hồ)",
                    config.TURN_TIME)
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

        # Cờ "đang đứng trên C0R0" chỉ đúng NGAY SAU exit_start_zone. Nó được đọc
        # một lần để chọn pose, rồi phải hết hiệu lực — nhưng trước đây không ai xoá
        # nên nó bật suốt trận. Đo trên robot 03/08: ở giây 3.76 của chặng tới khu
        # Samsung, cơ chế "tự sửa C0R0" của advance kích hoạt CÁCH C0R0 CẢ SÂN.
        # Xoá ở CUỐI route đầu tiên, để chặng START (nơi cờ có nghĩa) vẫn dùng được.
        xoa_co_sau_route = getattr(self, "tren_giao_lo_dau", False)
        # Chỉ chặng forward ĐẦU TIÊN của route ĐẦU TIÊN sau exit_start_zone.
        vua_xuat_phat = getattr(self, "vua_roi_o_xuat_phat", False)

        # Route khởi hành TỪ ĐIỂM CUỐI (kệ / khu nhà máy) luôn mở đầu bằng LÙI —
        # bộ tìm đường không có cách nào khác để rút khỏi điểm cuối. Chặng `forward`
        # ĐẦU TIÊN của route đó vẫn còn ở trên tấm in nên cần cổng quãng đường; các
        # chặng sau thì không. Xem follow_line_until_intersection.
        # Rút khỏi điểm cuối có HAI dạng: LÙI (thường), hoặc QUAY ĐẦU 180° = hai lần
        # xoay CÙNG CHIỀU. Chỉ nhận dạng thứ nhất thì route quay đầu lọt lưới và
        # robot đếm tấm in dưới chân thành giao lộ. EDGE_COST_REVERSE = 0 khiến bộ
        # tìm đường không sinh dạng thứ hai nữa, nhưng giữ nhận diện cho chắc.
        tu_diem_cuoi = bool(route) and (
            route[0][0] == "back"
            or (len(route) > 1 and route[0][0] in ("left", "right")
                and route[0][0] == route[1][0]))

        try:
            for i, step in enumerate(route):
                action = step[0]
                # ⚠️ TRƯỚC KHI XOAY, đưa TÂM XOAY về đúng giao lộ.
                # Thanh cảm biến ở ĐẦU xe, trục bánh dẫn động cách nó 12cm về phía sau
                # (đo trên robot). Tiến tới giao lộ thì cảm biến nằm TRÊN vạch còn trục
                # còn cách vạch 12cm — xoay tại chỗ lúc đó là quay quanh một điểm nằm
                # TRƯỚC giao lộ, xoay xong thanh cảm biến văng ra vùng trắng.
                # Chiều LÙI đã có bước bù này sẵn (REVERSE_RECENTER_TIME) nên xoay sau
                # khi lùi vẫn ổn; chiều TIẾN thì chưa có gì. Đo trên robot (option 8):
                #     xoay sau khi LÙI  → rời giao lộ [0,0,0,1,1,0]  còn thấy line
                #     xoay sau khi TIẾN → rời giao lộ [0,0,0,0,0,0]  TRẮNG HẾT → gãy
                # Cả hai chiều đều cần tiến thêm ĐÚNG 12cm, nên dùng chung hằng số.
                if (action in ("left", "right") and i > 0
                        and route[i - 1][0] == "forward"):
                    # Giao lộ C1R0 có Kệ 4 (NV2) THÒ RA phía nam — đúng hướng robot
                    # chĩa mặt khi tới. Tiến bù đủ 12cm là húc vào nó. Caller đặt cờ
                    # `gan_ke4` khi tuyến này xoay ở đó. Xem config.RECENTER_CM_GAN_KE4.
                    _bu = (config.RECENTER_CM_GAN_KE4
                           if getattr(self, "gan_ke4", False)
                           else config.RECENTER_CM)
                    if _bu != config.RECENTER_CM:
                        logger.info("Tiến bù RÚT NGẮN %.1fcm (thường %.1f) — giao lộ "
                                    "này có Kệ 4 thò ra phía trước",
                                    _bu, config.RECENTER_CM)
                    if self.tien_bu_cm(_bu,
                                       config.REVERSE_RECENTER_SPEED, "trước khi xoay"):
                        pass
                    elif config.TURN_RECENTER_TIME > 0:
                        logger.info("Tiến bù %.2fs ở %d%% để tâm xoay về đúng giao lộ "
                                    "(CHƯA calibrate encoder — chạy mù theo đồng hồ)",
                                    config.TURN_RECENTER_TIME,
                                    config.REVERSE_RECENTER_SPEED)
                        self.forward(config.REVERSE_RECENTER_SPEED)
                        time.sleep(config.TURN_RECENTER_TIME)
                        self.stop()
                if action == "forward":
                    # Gọi MỘT lần cho cả N giao lộ (chia nhỏ sẽ ép dừng ở từng cái, mất
                    # hết cái lợi của chế độ chạy liền); tiến độ ghi qua callback.
                    count = max(0, step[1])
                    if count and not self.navigate_intersections(
                            count,
                            on_reached=lambda: self.last_route_progress.append(("forward", 1)),
                            roi_diem_cuoi=tu_diem_cuoi,
                            bo_escape_dau=vua_xuat_phat):
                        return False
                    tu_diem_cuoi = False        # chỉ chặng forward ĐẦU TIÊN
                    vua_xuat_phat = False
                elif action == "back":
                    # Rút khỏi kệ/nhà máy mà không xoay 180° — cũng đi từng giao lộ một
                    # để biết chính xác dừng ở đâu khi hỏng giữa chừng.
                    for _ in range(max(0, step[1])):
                        if not self.back_to_intersection(1):
                            return False
                        self.last_route_progress.append(("back", 1))
                elif action in ("left", "right"):
                    # ⛔ GIỮA MỘT CÚ QUAY ĐẦU 180° THÌ ĐỪNG QUÉT.
                    # Route rút khỏi hàng R4 có HAI cú xoay cùng chiều liên tiếp.
                    # Sau cú THỨ NHẤT robot quay mặt lên hướng KHÔNG HỀ CÓ VẠCH
                    # (R4 là hàng trên cùng) nên quét chắc chắn thất bại — mà
                    # _recover_line() lại xoay robot qua lại ±0.5s ba lần, THÊM sai
                    # lệch ngay trước cú xoay thứ hai. Đo trên robot 06/08, hai lượt
                    # liên tiếp đều: "Xoay trái xong nhưng KHÔNG thấy vạch nào" →
                    # "KHÔNG tìm lại được vạch" → xoay tiếp → chạy 45.9cm trên nền
                    # trắng. Quét ở đó vừa vô ích vừa CÓ HẠI.
                    giua_quay_dau = (i + 1 < len(route)
                                     and route[i + 1][0] == action)
                    if action == "left":
                        self.turn_left_90()
                    else:
                        self.turn_right_90()
                    if giua_quay_dau:
                        logger.info(
                            "Xoay %s: đây là cú ĐẦU của quay đầu 180° — KHÔNG quét "
                            "tìm vạch (hướng này không có vạch, quét chỉ làm lệch "
                            "thêm trước cú xoay thứ hai)",
                            "trái" if action == "left" else "phải")
                    else:
                        self._bat_lai_line_sau_xoay(
                            "trái" if action == "left" else "phải")
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
        finally:
            # Cờ chỉ đúng NGAY SAU exit_start_zone; hết route đầu là hết hiệu
            # lực. Đặt ở finally để mọi lối thoát (kể cả return False giữa
            # chừng) đều xoá — bỏ sót một lối là cờ sống tiếp cả trận.
            if xoa_co_sau_route:
                self.tren_giao_lo_dau = False
            self.vua_roi_o_xuat_phat = False

    def _bat_lai_line_sau_xoay(self, chieu: str) -> bool:
        """Xoay xong mà KHÔNG thấy vạch nào thì QUÉT TÌM LẠI NGAY, đừng đi.

        ⚠️ HỒI QUY 06/08, smoke option 9, chặng Samsung → Kệ 3. Hai cú xoay trái
        (quay đầu 180°) đều đủ xung — 714/713 và 716/713 — nhưng xoay xong cả sáu
        mắt đều SÁNG, không vạch nào dưới thanh cảm biến:
            5.9cm  ADC [923, 924, 724, 922, 931, 848]
           11.9cm  ADC [778, 751, 580, 828, 765, 694]
           17.9cm  ADC [577, 571, 408, 623, 578, 634]
           23.7cm  ADC [489, 480, 409, 575, 516, 541]
            → Mất line quá 1.2s! Quét tìm lại... → Không tìm lại được line!
        Robot chạy 23.7cm trên nền trắng trơn RỒI MỚI quét, và lúc đó đã quá xa
        để _recover_line() (quét ±0.5s tại chỗ) với tới.

        Xoay tại chỗ luôn có trượt ngang, và hai cú liên tiếp thì cộng dồn. Quét
        NGAY khi còn đứng cạnh vạch thì tìm lại được; đi 23cm rồi mới quét thì không.

        Chỉ hành động khi KHÔNG thấy gì — thấy vạch thì trả về ngay, không tốn giây nào.
        """
        if not getattr(config, "QUET_LAI_SAU_XOAY", True):
            return True
        try:
            values = self.read_line_sensor()
        except Exception:
            return True
        if sum(values) > 0:
            return True
        logger.warning(
            "Xoay %s xong nhưng KHÔNG thấy vạch nào (cảm biến %s) — quét tìm lại "
            "NGAY tại chỗ. Đi tiếp rồi mới quét là quá muộn: xoay tại chỗ có trượt "
            "ngang, càng đi càng xa vạch.", chieu, values)
        if self._recover_line():
            logger.info("Xoay %s: đã tìm lại được vạch", chieu)
            return True
        logger.error("Xoay %s: KHÔNG tìm lại được vạch ngay sau khi xoay — "
                     "tư thế sau cú xoay sai nhiều hơn tầm quét.", chieu)
        return False

    def _do_lai_khi_dung(self, dist_quyet: float,
                         base_speed: float) -> tuple[float, bool]:
        """Dừng hẳn rồi ĐO LẠI — số đo lúc ĐỨNG YÊN mới đáng tin.

        Lý do đầy đủ ở config.ULTRASONIC_VERIFY_TOLERANCE. Tóm tắt: cảm biến đo
        được 0.20cm độ lệch chuẩn khi đứng yên nhưng báo 4.6cm giữa lúc chạy với
        kệ ở 35cm — gai nhiễu do bấm giờ echo bằng phần mềm.

        Trả (số đo lúc đứng yên, có khớp với số lúc chạy không).
        """
        self.stop_gently(base_speed)
        # Chờ hàng đợi trung vị của gpiozero xả hết giá trị lúc còn đang chạy.
        time.sleep(config.ULTRASONIC_QUEUE_LEN * 0.06 + 0.05)
        that = self.get_distance()
        if that < 0:
            return that, True        # đọc lỗi → không bác bỏ được, cứ tin số cũ
        return that, abs(that - dist_quyet) <= config.ULTRASONIC_VERIFY_TOLERANCE

    def advance_to_end(self, base_speed: float = config.ADVANCE_SPEED,
                       timeout: float = config.ADVANCE_TIMEOUT) -> bool:
        """
        Bám line tới ĐIỂM CUỐI của line (vào kệ / khu nhà máy / Kệ 4).

        Khác navigate_intersections(): những chỗ này KHÔNG phải giao lộ — line chỉ
        đơn giản là hết, nên không đếm được. Dừng khi:
          1. Mất line liên tục config.LINE_END_CONFIRM_TIME giây → đã hết line, hoặc
          2. Siêu âm thấy mục tiêu ở gần (≤ APPROACH_SLOW_DISTANCE) → để
             approach_shelf() canh nốt đoạn cuối cho chính xác, hoặc
          3. Gặp giao lộ (bản đồ sai / robot đi lố) → dừng và báo thất bại, hoặc
          4. CHƯA TỪNG thấy line sau ADVANCE_ACQUIRE_TIME → robot không nằm trên
             line, báo THẤT BẠI.

        ⚠️ Điều kiện 4 tách khỏi điều kiện 1 vì hai tình huống khác hẳn nhau mà
        trước đây bị gộp: `lost_since` khởi tạo None nên robot KHÔNG NẰM TRÊN LINE
        ngay từ đầu cũng chạy đúng nhánh "hết line" và trả THÀNH CÔNG sau 0.25s.
        Gặp thật trong smoke option 1: bước dò nửa sân (probe_side_branch) chạy hở
        hoàn toàn — xoay phải, tiến 0.45s, lùi 0.45s, xoay trái — mà TURN_TIME mới
        xác nhận cho chiều TRÁI và bù PWM chiều LÙI thì chưa calibrate, nên robot
        quay về lệch khỏi vạch. advance kế đó báo "đã tới điểm cuối" sau 0.55s
        trong khi robot vẫn đứng ở giao lộ. Im lặng kiểu đó nguy hiểm hơn hẳn một
        lần thất bại: state machine tin là đã tới kệ và đi tiếp.

        "Hết line" chỉ có nghĩa khi TRƯỚC ĐÓ đã bám được line — mọi lệnh advance
        đều bắt đầu từ một giao lộ, nơi chắc chắn có line.
        """
        logger.info("Bám line tới hết line (advance, speed=%d%%)", base_speed)
        # Lệnh advance luôn bắt đầu khi robot đang ĐỨNG TRÊN giao lộ (vừa dừng ở
        # giao lộ cuối của forward, hoặc vừa xoay tại giao lộ). Không thoát ra trước
        # thì follow_line() nhận ngay chính giao lộ đó và báo "đi lố".
        # Đếm quãng TỪ TRƯỚC khi thoát giao lộ: mốc 35.4cm trong SA_BAN là tính từ
        # GIAO LỘ, mà escape đã đi mất một phần rồi. Bỏ phần đó là dừng muộn.
        self._doc_xung()
        xung_adv = 0
        quang_adv = 0.0
        cong_hang_som = getattr(self, "dang_cong_hang", False)
        do_duoc_quang_som = (config.ENCODER_PULSES_PER_CM > 0
                             and getattr(getattr(self, "_encoder_left", None),
                                         "available", False)
                             and getattr(getattr(self, "_encoder_right", None),
                                         "available", False))
        bo_escape = ((not cong_hang_som) and do_duoc_quang_som
                     and config.ADVANCE_SHELF_STOP_CM > 0)
        if bo_escape:
            # ⛔ KHÔNG THOÁT GIAO LỘ khi vào kệ — mốc dừng NGẮN HƠN cả quãng escape.
            # Đo trên robot 04/08: escape chạy 0.41s, nhịp tim đầu tiên của advance
            # đã báo 7.9cm. Mà càng chui vào gầm kệ khi bánh mới rời giao lộ 12cm.
            # Thoát giao lộ xong là đã đi quá nửa quãng cho phép rồi.
            self.forward(base_speed)
        else:
            self._escape_intersection(base_speed)
        xung_adv += self._doc_xung()
        start = time.time()
        lost_since = None
        nhip_luc = start         # lần cuối in nhịp tim quãng đường
        values = []              # nhánh "ĐI QUÁ XA" in nó ra, mà nó chỉ được gán ở
                                 # cuối vòng — vòng đầu sẽ NameError nếu quãng đã
                                 # vượt mốc ngay từ xung của escape.
        # Một lần đo siêu âm chập chờn là đủ để kết thúc advance và báo THÀNH CÔNG —
        # đây là chỗ duy nhất mà nhiễu gây "thành công giả". Đòi 2 nhịp liên tiếp thấy
        # gần mới tin (approach_shelf() phía sau lo nốt đoạn cuối, nên tốn thêm 1 nhịp
        # 10ms là không đáng kể).
        near_streak = 0
        # Đã bám được line lần nào chưa. Trước khi True thì "mất line" nghĩa là
        # KHÔNG TÌM THẤY, không phải "đã hết".
        acquired = False
        vet_adv = []             # vệt số đo siêu âm, để soi khi hỏng
        # ⛔ CÕNG HÀNG THÌ SIÊU ÂM VÔ DỤNG — bỏ hẳn mọi nhánh dựa vào nó.
        # Đo trên robot 03/08, chặng giao hàng: vừa rời giao lộ đã đọc 9.4cm rồi
        # 10.2cm; lùi 0.8s mà số chỉ đổi 1.6cm. Thả xong hàng và gập càng thì cùng
        # cảm biến đó đọc 100.0cm. Kiện hàng cõng trên càng CHẮN CHÙM SÓNG.
        # (Bài check_load_blocks_sonar trước đây kết luận "không chắn" là do chỉ
        # đặt PALLET TRẦN lên càng — thiếu 4 khối mút cao 40mm ở trên, chính chúng
        # mới là thứ chắn. Bài đo đó cần làm lại với KIỆN ĐẦY ĐỦ.)
        # Ở khu nhà máy vốn cũng chẳng có mặt phẳng nào để canh, nên điểm dừng đúng
        # là HẾT LINE — line kết thúc ở mép ô nhà máy.
        cong_hang = getattr(self, "dang_cong_hang", False)
        # ⛔ VÀO KỆ: dừng theo QUÃNG ĐƯỜNG, siêu âm KHÔNG còn quyền quyết định.
        # Bản trước đặt chốt quãng đường SAU các nhánh siêu âm trong vòng lặp nên
        # siêu âm vẫn quyết trước — với số đo 12.2cm cố định (cảm biến đang nhìn một
        # vật trên CHÍNH robot), advance dừng NGAY tại giao lộ rồi bước luồn càng
        # tiến mù 35cm vào kệ. Vá nửa vời còn tệ hơn không vá: log trông như đã sửa.
        do_duoc_quang = (config.ENCODER_PULSES_PER_CM > 0
                         and getattr(getattr(self, "_encoder_left", None),
                                     "available", False)
                         and getattr(getattr(self, "_encoder_right", None),
                                     "available", False))
        dung_bang_quang = ((not cong_hang) and do_duoc_quang
                           and config.ADVANCE_SHELF_STOP_CM > 0)
        bo_sieu_am = cong_hang or dung_bang_quang
        if cong_hang:
            logger.info("Advance: ĐANG CÕNG HÀNG — bỏ qua siêu âm, đi tới HẾT LINE")
        elif dung_bang_quang:
            logger.info("Advance: dừng theo QUÃNG ĐƯỜNG %.1fcm từ giao lộ — bỏ qua "
                        "siêu âm (ở kệ nó sai cả hai chiều)",
                        config.ADVANCE_SHELF_STOP_CM)
        # ⛔ TRỪ NGAY VÀO QUÃNG ĐI TỚI, đừng đi vào rồi lùi ra.
        # Mỗi nhà máy nhận 3 kiện (12 kiện / 4 nhà máy). Kiện đã thả nằm ĐÚNG trên
        # đường robot sắp đi vào, nên chốt quãng đường cố định sẽ húc vào nó. Bước
        # _lui_tranh_kien_cu() bên main lùi SAU KHI ĐÃ TỚI — tức đã va rồi mới lùi.
        # Trừ trước thì robot không bao giờ chạm vào kiện cũ.
        # Số kiện đã thả do main đặt vào `bot_quang_nha_may` (cm) trước khi chạy
        # route, cùng kiểu với cờ `dang_cong_hang`.
        bot_cm = max(0.0, float(getattr(self, "bot_quang_nha_may", 0.0) or 0.0))
        # Mốc riêng của khu (nếu đã đo) đè lên số chung — bốn khu cách giao lộ
        # những khoảng khác nhau. Xem config.ADVANCE_FACTORY_STOP_CM_RIENG.
        _goc = getattr(self, "moc_nha_may_rieng", None) or config.ADVANCE_FACTORY_STOP_CM
        moc_nha_may = _goc - bot_cm
        if cong_hang and bot_cm > 0:
            if moc_nha_may < config.ADVANCE_FACTORY_MIN_STOP_CM:
                logger.warning(
                    "Advance: mốc nhà máy sau khi trừ %.1fcm tránh kiện cũ chỉ còn "
                    "%.1fcm, DƯỚI sàn %.1f — kẹp lại. Khu nhà máy sâu 25cm mà mỗi "
                    "kiện chiếm 9cm, kiện thứ 3 KHÔNG lọt (docs/HAPPY_CASE.md).",
                    bot_cm, moc_nha_may, config.ADVANCE_FACTORY_MIN_STOP_CM)
                moc_nha_may = config.ADVANCE_FACTORY_MIN_STOP_CM
            logger.info("Advance: mốc nhà máy %.1f − %.1f (tránh kiện cũ) = %.1fcm",
                        config.ADVANCE_FACTORY_STOP_CM, bot_cm, moc_nha_may)

        thay_muc_tieu = False    # đã từng thấy vật trong APPROACH_DETECT_DISTANCE
        mat_vong = 0             # số nhịp kịch trần LIÊN TIẾP
        nhieu = 0                # số gai nhiễu đã bỏ qua
        bo_qua_dau = False       # đã dùng cửa sổ ân hạn đầu chưa
        da_quet = False          # đã quét tìm lại line chưa (1 lần)
        # (quãng advance đã khởi tạo TRƯỚC escape — xem trên)
        doi_luc = start          # lần cuối siêu âm ĐỔI giá trị

        while time.time() - start < timeout:
            if self._aborted():
                return False
            dist = self.get_distance()
            if (not vet_adv) or abs(dist - vet_adv[-1][1]) > 0.05:
                vet_adv.append((time.time() - start, dist))
                doi_luc = time.time()

            # ⚠️ KHÔNG DI CHUYỂN TRÊN SỐ ĐO CŨ — y như approach_shelf.
            # Đo trên robot 03/08: advance dừng ở 4.3cm thay vì 20cm, rồi
            # approach_shelf tiếp tục từ đó nên robot đã sát kệ trước khi pha tiếp
            # cận bắt đầu. Cùng nguyên nhân: gpiozero bấm giờ xung echo bằng PHẦN
            # MỀM nên luồng nền có lúc kẹt, số đo đứng yên trong khi robot vẫn chạy.
            # Trước đây tôi chỉ vá ở approach_shelf mà quên chỗ này — mà đây mới là
            # chỗ chạy TRƯỚC và đưa robot tới sát kệ.
            # Chỉ chặn khi số đo đang TRONG TẦM NGUY HIỂM. Số đo kịch trần (không
            # có tiếng vọng, ~100cm) cũng "không đổi" — chặn cả ca đó thì robot đứng
            # im vĩnh viễn. Ở xa thì số đo cũ vô hại vì còn lâu mới tới điểm dừng.
            if (not bo_sieu_am
                    and 0 <= dist <= config.APPROACH_SLOW_DISTANCE * 2
                    and time.time() - doi_luc > config.ULTRASONIC_STALE_TIME):
                self.stop()
                time.sleep(0.01)
                continue

            # ⛔ MÙ SIÊU ÂM — nhánh "hết line" ở kệ CHÍNH LÀ đâm vào kệ (vạch
            # kéo tới cách chân kệ 1mm), nên không có số đo là không được đi tiếp.
            if bo_sieu_am:
                pass                      # mọi nhánh siêu âm dưới đây đều bỏ qua
            elif dist >= config.ADVANCE_MAX_RANGE_CM:
                mat_vong += 1
            else:
                mat_vong = 0
                if dist <= config.APPROACH_DETECT_DISTANCE:
                    thay_muc_tieu = True

            if (not bo_sieu_am) and thay_muc_tieu \
                    and mat_vong >= config.ADVANCE_LOST_ECHO_COUNT:
                # Ca giết robot: thấy 30→25→22 rồi 100,100,100 mà vẫn chạy tiếp.
                self.stop_gently(base_speed)
                logger.warning(
                    "Advance: MẤT TIẾNG VỌNG — %d nhịp kịch trần liên tiếp sau khi "
                    "đã thấy mục tiêu. Dừng tại chỗ chứ KHÔNG đi tới hết line (ở kệ "
                    "thì hết line = đâm vào kệ). Vệt: %s",
                    mat_vong, " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet_adv[-10:]))
                return True

            if ((not bo_sieu_am) and (not thay_muc_tieu)
                    and time.time() - start >= config.ADVANCE_BLIND_TIMEOUT):
                self.stop()
                logger.error(
                    "Advance: CHƯA TỪNG thấy gì trong %.0fcm sau %.1fs — siêu âm mù. "
                    "Ở kệ thì mục tiêu chỉ cách giao lộ 35.4cm nên nhịp đầu đã phải "
                    "thấy. Không đi tới hết line. Vệt: %s",
                    config.APPROACH_DETECT_DISTANCE, config.ADVANCE_BLIND_TIMEOUT,
                    " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet_adv[-10:]))
                return False

            # ⛔ CHẶN CỨNG — đứng trên mọi logic khác.
            # Nhánh "đi tới khi hết line" VỀ BẢN CHẤT là đâm vào kệ: line kéo tới
            # cách chân kệ 1mm (SA_BAN.md 3b). Đây là lưới an toàn cuối cùng.
            # ⚠️ Đoạn này TỪNG BỊ XOÁ NHẦM khi gỡ cơ chế chống-kiện-che (4fe93e7):
            # lệnh xoá cắt từ dòng comment phía trên xuống và nuốt luôn nó. Test
            # viết cho nó lại không phân biệt được với nhánh "tới gần mục tiêu" nên
            # không ai biết, và robot lao vào kệ thêm nhiều lần.
            if (not bo_sieu_am) and 0 <= dist <= config.ADVANCE_HARD_STOP_CM:
                that, khop = self._do_lai_khi_dung(dist, base_speed)
                if (not khop) and that > config.ADVANCE_HARD_STOP_CM \
                        and nhieu < config.ULTRASONIC_MAX_GLITCH:
                    nhieu += 1
                    logger.warning(
                        "Advance: BỎ QUA GAI NHIỄU — lúc chạy báo %.1fcm nhưng đo "
                        "lại khi ĐỨNG YÊN được %.1fcm. Chạy tiếp (%d/%d).",
                        dist, that, nhieu, config.ULTRASONIC_MAX_GLITCH)
                    doi_luc = time.time()
                    continue
                logger.warning("Advance: CHẶN CỨNG ở %.1fcm (mốc %.1f). Vệt: %s",
                               dist, config.ADVANCE_HARD_STOP_CM,
                               " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet_adv[-10:]))
                return True

            if (not bo_sieu_am) and 0 <= dist <= config.APPROACH_SLOW_DISTANCE:
                near_streak += 1
                if near_streak >= 2:
                    that, khop = self._do_lai_khi_dung(dist, base_speed)
                    if (not khop) and that > config.APPROACH_SLOW_DISTANCE \
                            and nhieu < config.ULTRASONIC_MAX_GLITCH:
                        nhieu += 1
                        near_streak = 0
                        logger.warning(
                            "Advance: BỎ QUA GAI NHIỄU — lúc chạy báo %.1fcm nhưng "
                            "đo lại khi ĐỨNG YÊN được %.1fcm. Chạy tiếp (%d/%d).",
                            dist, that, nhieu, config.ULTRASONIC_MAX_GLITCH)
                        doi_luc = time.time()
                        continue
                    logger.info("Advance: đã tới gần mục tiêu (%.1fcm). Vệt: %s", dist,
                                " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet_adv[-10:]))
                    return True
            else:
                near_streak = 0

            xung_adv += self._doc_xung()
            if config.ENCODER_PULSES_PER_CM > 0:
                quang_adv = xung_adv / config.ENCODER_PULSES_PER_CM

            # ⛔ LƯỚI AN TOÀN CUỐI — siêu âm ĐANG SỐNG và báo quá gần thì DỪNG,
            # kể cả khi chốt quãng đường chưa tới mốc.
            # Chốt quãng đường không biết được nó XUẤT PHÁT SAI CHỖ. Đo 07/08:
            # advance khởi hành khi siêu âm đã 29.5cm (đáng lẽ 35.4 nếu đứng đúng
            # C0R0) — thiếu ~6cm, cộng vào cuối là ĐÂM KỆ, càng luồn vào gầm.
            # Điều kiện KHÔNG phải "tin siêu âm" mà là "siêu âm có đang sống
            # không": số đo phải đã GIẢM thật sự. Số kẹt (12.2cm bất kể robot ở
            # đâu — ca đã gặp) không bao giờ thoả điều kiện này.
            if (dung_bang_quang and config.ADVANCE_SONAR_PANIC_CM > 0
                    and len(vet_adv) >= 4):
                giam = vet_adv[-4][1] - dist
                if giam >= config.ADVANCE_SONAR_LIVE_DROP_CM \
                        and 0 < dist <= config.ADVANCE_SONAR_PANIC_CM:
                    self.stop_gently(base_speed)
                    logger.warning(
                        "Advance: DỪNG KHẨN — siêu âm còn %.1fcm (mốc %.1f) và nó "
                        "ĐANG SỐNG (giảm %.1fcm trong vệt gần đây, ≥%.1f). Mới đi "
                        "%.1f/%.1fcm nhưng chốt quãng đường không biết được nó xuất "
                        "phát sai chỗ. Vệt: %s",
                        dist, config.ADVANCE_SONAR_PANIC_CM, giam,
                        config.ADVANCE_SONAR_LIVE_DROP_CM,
                        quang_adv, config.ADVANCE_SHELF_STOP_CM,
                        " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet_adv[-8:]))
                    return True

            # NHỊP TIM — in quãng đường đang đếm được, đều đặn.
            # 04/08: encoder ĐO ĐƯỢC (365/368 xung trong 1s, check_encoder_alive),
            # mà advance vẫn không bao giờ chạm mốc 15cm rồi đâm kệ. Không có số
            # trong vòng lặp thì mọi giả thuyết đều là đoán. Rẻ: ~4 dòng/giây.
            if time.time() - nhip_luc >= config.ADVANCE_HEARTBEAT_TIME:
                nhip_luc = time.time()
                logger.info("Advance: %.2fs — %d xung = %.1fcm (mốc %.1f), "
                            "siêu âm %.1fcm, ADC %s", time.time() - start,
                            xung_adv, quang_adv, config.ADVANCE_SHELF_STOP_CM,
                            dist, self._adc_de_ghi())

            # ⛔ ENCODER CHẾT = KHÔNG CÓ GÌ CHẶN NỮA. Khi đã giao quyền dừng cho
            # quãng đường thì encoder là điểm chết duy nhất, và nó hỏng KHÔNG
            # TIẾNG ĐỘNG: mọi nhánh vẫn đúng, chỉ là con số không nhúc nhích nên
            # chẳng mốc nào bị chạm — kể cả ADVANCE_MAX_TRAVEL_CM, vì nó cũng đo
            # bằng chính encoder đó. Lý do + vệt log: ADVANCE_ENCODER_DEAD_TIME.
            if (dung_bang_quang
                    and time.time() - start >= config.ADVANCE_ENCODER_DEAD_TIME
                    and xung_adv < config.ADVANCE_ENCODER_DEAD_PULSES):
                self.stop()
                logger.error(
                    "Advance: ENCODER CHẾT — chạy %.1fs mà chỉ đếm %d xung (mốc "
                    "%d). Đang dừng theo QUÃNG ĐƯỜNG mà quãng không nhúc nhích "
                    "thì không mốc nào chặn được, kể cả lưới %.0fcm. DỪNG tại "
                    "chỗ chứ không đi tiếp vào kệ. Chẩn: "
                    "python3 -m tools.check_encoder_alive",
                    time.time() - start, xung_adv,
                    config.ADVANCE_ENCODER_DEAD_PULSES,
                    config.ADVANCE_MAX_TRAVEL_CM)
                return False
            # ⛔ CHỐT CHÍNH khi vào KHU NHÀ MÁY: cũng dừng theo QUÃNG ĐƯỜNG.
            # Cách cũ dò TẤM IN cho điểm dừng NGẪU NHIÊN — phép kiểm bị nhốt trong
            # nhánh `if at_intersection` nên chỉ được đánh giá ở những nhịp
            # follow_line() TÌNH CỜ báo giao lộ, mà cái đó dùng ngưỡng THÍCH NGHI
            # tự co giãn. Lý do đầy đủ + vệt số: config.ADVANCE_FACTORY_STOP_CM.
            if cong_hang and do_duoc_quang and moc_nha_may > 0 \
                    and moc_nha_may <= quang_adv:
                self.stop_gently(base_speed)
                logger.info(
                    "Advance: ĐÃ ĐI %.1fcm từ giao lộ (mốc %.1f%s) — dừng trong "
                    "khu nhà máy theo QUÃNG ĐƯỜNG, không dò tấm in (tấm in cho "
                    "điểm dừng ngẫu nhiên). ADC %s",
                    quang_adv, moc_nha_may,
                    "" if bot_cm <= 0 else
                    f" = {config.ADVANCE_FACTORY_STOP_CM:.1f} − {bot_cm:.1f} tránh "
                    f"kiện cũ", self._adc_de_ghi())
                return True

            # ⛔ CHỐT CHÍNH khi vào KỆ: dừng theo QUÃNG ĐƯỜNG, không theo siêu âm.
            # Siêu âm ở kệ sai cả hai chiều — xem config.ADVANCE_SHELF_STOP_CM.
            # Cõng hàng thì đang đi tới NHÀ MÁY, chốt đó do mảng in lo.
            if (not cong_hang) and 0 < config.ADVANCE_SHELF_STOP_CM <= quang_adv:
                self.stop_gently(base_speed)
                logger.info(
                    "Advance: ĐÃ ĐI %.1fcm từ giao lộ (mốc %.1f) — dừng trước kệ "
                    "theo QUÃNG ĐƯỜNG, không tin siêu âm. Vệt siêu âm: %s",
                    quang_adv, config.ADVANCE_SHELF_STOP_CM,
                    " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet_adv[-10:]) or "(trống)")
                return True

            if 0 < config.ADVANCE_MAX_TRAVEL_CM <= quang_adv:
                # Lưới an toàn ĐỘC LẬP với cảm biến line: xem
                # config.ADVANCE_MAX_TRAVEL_CM.
                self.stop()
                logger.error(
                    "Advance: ĐI QUÁ XA — %.1fcm (chặn %.1f) mà chưa tới điểm cuối. "
                    "DỪNG để không rời sa bàn. Cảm biến %s",
                    quang_adv, config.ADVANCE_MAX_TRAVEL_CM, values)
                return False

            at_intersection, values = self.follow_line(base_speed)
            if at_intersection and bo_escape:
                # Chặng vào kệ chỉ dài vài cm và KHÔNG có giao lộ nào để gặp —
                # cái vừa thấy là chính giao lộ robot đang đứng trên (ta cố tình
                # không thoát nó). Chạy tiếp cho tới khi đủ quãng.
                # follow_line() vừa gọi stop() nên phải ra lệnh chạy lại.
                self.forward(base_speed)
                acquired = True
                lost_since = None
                time.sleep(0.01)
                continue
            if at_intersection:
                # ĐẾM MẮT ĐEN ĐẬM trước đã — y như back_to_intersection.
                # Đo trên robot 03/08, chặng tới khu Samsung:
                #     ADC [834, 270, 0, 0, 0, 930]  ngưỡng 279  → 3 đen đậm
                #     ADC [591, 207, 0, 0, 0, 928]  ngưỡng 278  → 3 đen đậm
                # Vạch line THƯỜNG (mắt 3,4,5) bị NGƯỠNG THÍCH NGHI thổi thành giao
                # lộ: mắt 2 đọc 207-270, không đen, chỉ lọt dưới ngưỡng ~278. Hai
                # tín hiệu giả này làm advance thoát giao lộ oan hai lần rồi lạc.
                raw_gl = self.read_line_sensor_raw()
                dam_gl = LineSensor.dem_den_dam(raw_gl)

                # ĐANG CÕNG HÀNG = đang tới KHU NHÀ MÁY, nơi KHÔNG có giao lộ nào
                # để gặp. Line kết thúc vào MẢNG IN (ảnh nhà máy nền tối), nên mảng
                # tối đậm ở đây nghĩa là ĐÃ TỚI, không phải lỗi bản đồ.
                # Lý do + vệt ADC thật: config.ADVANCE_FACTORY_DARK_MIN_CM.
                sang_nhat = max(raw_gl) if raw_gl else 1.0
                if (cong_hang
                        and dam_gl >= config.ADVANCE_FACTORY_DARK_EYES
                        and sang_nhat <= config.ADVANCE_FACTORY_MAX_BRIGHT
                        and quang_adv >= config.ADVANCE_FACTORY_DARK_MIN_CM):
                    self.stop_gently(base_speed)
                    logger.info(
                        "Advance: ĐÃ VÀO KHU NHÀ MÁY — %d/%d mắt đen ĐẬM và mắt SÁNG "
                        "NHẤT chỉ %.0f (≤%.0f: cả vùng đều tối = tấm in, không phải "
                        "vạch line), sau khi đi %.1fcm. ADC %s",
                        dam_gl, config.ADVANCE_FACTORY_DARK_EYES, sang_nhat * 1023,
                        config.ADVANCE_FACTORY_MAX_BRIGHT * 1023, quang_adv,
                        [int(round(v * 1023)) for v in raw_gl])
                    return True

                if (dam_gl < config.ADVANCE_INTERSECTION_DAM
                        or min(raw_gl) > config.LINE_DEEP_BLACK):
                    logger.info(
                        "Advance: bỏ qua tín hiệu giao lộ ở %.2fs — chỉ %d/%d mắt đen "
                        "ĐẬM, ADC %s. Vạch thường bị ngưỡng thích nghi thổi lên.",
                        time.time() - start, dam_gl,
                        config.ADVANCE_INTERSECTION_DAM,
                        [int(round(v * 1023)) for v in raw_gl])
                    # follow_line() vừa gọi stop() — phải ra lệnh chạy lại, không thì
                    # vòng sau nó lại thấy, lại phanh, robot đứng im vĩnh viễn.
                    self.forward(base_speed)
                    acquired = True
                    lost_since = None
                    time.sleep(0.01)
                    continue

                # TỰ SỬA khi niềm tin "đang đứng trên C0R0" sai đúng một giao lộ.
                # Cờ đó do bước căn giữa của exit_start_zone() đặt, dựa trên MỘT
                # lần đọc cảm biến giữa lúc robot còn xiên — không có cách nào chắc
                # 100%. Nhưng nếu cờ đang bật mà advance lại GẶP một giao lộ, thì
                # suy ra được ngay: cái vừa gặp MỚI là C0R0, robot khi đó còn chưa
                # tới nơi. Đo trên robot 03/08: cờ bật nhầm vì hình in mascot cho 4
                # mắt đen (nhưng ĐỨT QUÃNG), robot dừng hẳn ở C0R0 thật.
                # Chỉ tự sửa MỘT lần — cờ bị tiêu thụ, lần sau vẫn báo lỗi như cũ.
                if (not bo_qua_dau) and time.time() - start <= config.ADVANCE_START_GRACE:
                    # Giao lộ gặp NGAY sau escape chỉ có thể là cái vừa thoát —
                    # escape thường chạm trần ESCAPE_MAX_TIME rồi bỏ cuộc. Lý do
                    # đầy đủ + số đo: config.ADVANCE_START_GRACE. Chỉ MỘT lần.
                    bo_qua_dau = True
                    logger.warning(
                        "Advance: gặp giao lộ sau %.2fs — trong cửa sổ ân hạn %.1fs "
                        "nên đây là CHÍNH giao lộ vừa thoát (escape chạm trần chứ "
                        "chưa ra hẳn). Thoát lại rồi đi tiếp. Cảm biến %s",
                        time.time() - start, config.ADVANCE_START_GRACE, values)
                    acquired = True
                    lost_since = None
                    self._escape_intersection(base_speed)
                    continue
                if getattr(self, "tren_giao_lo_dau", False):
                    self.tren_giao_lo_dau = False
                    logger.warning(
                        "Advance: gặp giao lộ sau %.2fs, nhưng cờ 'đang đứng trên "
                        "C0R0' ĐANG BẬT — niềm tin đó sai đúng một giao lộ, cái vừa "
                        "gặp MỚI là C0R0. Tự sửa: thoát nó rồi đi tiếp. Cảm biến %s",
                        time.time() - start, values)
                    acquired = True
                    lost_since = None
                    self._escape_intersection(base_speed)
                    continue
                self.stop()
                logger.warning("Advance: gặp giao lộ sau %.2fs — cảm biến %s, ADC %s. "
                               "Bản đồ hoặc vị trí không khớp",
                               time.time() - start, values,
                               self.read_line_sensor_adc())
                return False

            if sum(values) > 0:
                acquired = True
                lost_since = None
            elif not acquired:
                # Chưa bao giờ thấy line. Cho một khoảng ngắn để tìm, hết thì DỪNG —
                # không được chạy mù hết ADVANCE_TIMEOUT ở tốc độ này.
                if time.time() - start >= config.ADVANCE_ACQUIRE_TIME:
                    # QUÉT TÌM LẠI trước khi bỏ cuộc. follow_line_until_intersection()
                    # đã làm việc này từ lâu; advance_to_end thì chưa, nên nó bỏ cuộc
                    # ngay cả khi line chỉ nằm lệch vài centimet.
                    # Đo trên robot 03/08: robot đi ĐÚNG tới C1R1, xoay trái xong thì
                    # cảm biến rơi ra ngoài vạch (xoay tại chỗ có trượt ngang, mà lượt
                    # đó robot chạy chậm hẳn — xoay mất 1.59s so với 1.06s lúc không
                    # tải). Nó dừng luôn tại chỗ, không thả hàng, dù chỉ cần lệch vài
                    # cm là quét ra.
                    if not da_quet and self._recover_line():
                        da_quet = True
                        acquired = True
                        lost_since = None
                        start = time.time()     # cho lại thời gian tìm line
                        continue
                    self.stop()
                    logger.error(
                        "Advance: không thấy line trong %.2fs đầu%s — robot KHÔNG nằm "
                        "trên line. Không coi là đã tới điểm cuối.",
                        config.ADVANCE_ACQUIRE_TIME,
                        " (đã quét tìm lại nhưng không thấy)" if da_quet else "")
                    return False
            elif lost_since is None:
                lost_since = time.time()
            elif time.time() - lost_since >= config.LINE_END_CONFIRM_TIME:
                self.stop()
                # In VỆT kèm trạng thái cõng hàng: lối thoát này là lối DUY NHẤT
                # không dùng siêu âm, nên khi robot đi quá thì cần biết ngay nó vào
                # đây vì hết line thật hay vì cờ cõng hàng kẹt bật.
                logger.info(
                    "Advance: đã hết line — dừng tại điểm cuối (cõng hàng=%s, đi "
                    "%.1fcm). Vệt siêu âm: %s", cong_hang, quang_adv,
                    " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet_adv[-10:]) or "(trống)")
                return True

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
        # Mốc "gần nhất từng tới được" — dùng để phát hiện robot không tiến thêm nữa
        best_dist = float("inf")
        best_at = start
        nhieu_ap = 0             # số gai nhiễu đã bỏ qua
        da_vao_gan = False       # đã vào vùng gần chưa (chốt MỘT CHIỀU)
        # APPROACH_NO_PROGRESS_TIME = 1.2s được chọn cho vòng lặp 0.02s. Chế độ đi
        # từng nhịp tốn ~0.5s mỗi vòng, nên giữ nguyên 1.2s là chỉ còn 2 nhịp trước
        # khi nó kêu "kẹt" — dễ bỏ cuộc oan. Nới theo ĐÚNG NHỊP thay vì viết cứng
        # một số mới, để đổi APPROACH_STEP_TIME không âm thầm phá cơ chế này.
        moc_ket = config.APPROACH_NO_PROGRESS_TIME
        if getattr(config, "APPROACH_STEPPED", False):
            mot_nhip = (config.APPROACH_STEP_TIME
                        + config.ULTRASONIC_QUEUE_LEN * 0.06 + 0.05
                        + getattr(config, "STOP_SETTLE_TIME", 0.0))
            moc_ket = max(moc_ket, 4 * mot_nhip)
        # Tốc độ của nhịp GẦN NHẤT — stop_gently() cần biết đang chạy nhanh cỡ nào
        # để giảm dần từ đó. Khởi tạo cho vòng lặp đầu (chưa qua nhánh chọn tốc độ).
        speed = config.APPROACH_FAST_SPEED
        doi_luc = start          # lần cuối siêu âm ĐỔI giá trị
        # Vệt đo để soi khi hỏng. Siêu âm chạy chập chờn (gpiozero cảnh báo mỗi lần
        # khởi động: "use the pigpio pin factory for more accurate readings" — bấm
        # giờ xung echo bằng phần mềm nên bị hệ điều hành ngắt quãng). Chỉ nhìn con
        # số CUỐI thì không phân biệt được: nhiễu lẻ, đọc cao đều đều, hay mất tiếng
        # vọng. Ba nguyên nhân đó cách sửa khác hẳn nhau.
        vet = []

        while time.time() - start < config.APPROACH_TIMEOUT:
            if self._aborted():
                return False
            dist = self.get_distance()   # gpiozero đã lấy trung vị sẵn (ULTRASONIC_QUEUE_LEN)
            moi = (not vet) or abs(dist - vet[-1][1]) > 0.05
            if moi:
                vet.append((time.time() - start, dist))
                doi_luc = time.time()
            # ⚠️ KHÔNG CHẠY KHI SỐ ĐO ĐÃ CŨ. Đo trên robot: số đo ĐỨNG YÊN ở 16.3cm
            # suốt 0.7 giây rồi nhảy thẳng xuống 5.9 — robot chạy MÙ hết 0.7s đó và
            # vượt qua điểm dừng ~10cm. Cơ chế "không tiến thêm được" không bắt vì
            # nó chờ APPROACH_NO_PROGRESS_TIME = 1.2s.
            # Nguyên nhân gốc là gpiozero bấm giờ xung echo bằng PHẦN MỀM (cảnh báo
            # PWMSoftwareFallback mỗi lần khởi động) nên luồng nền có lúc kẹt.
            # Chưa cài được pigpio thì ít nhất ĐỪNG DI CHUYỂN trên dữ liệu cũ:
            # đứng chờ số mới. Đổi một cú vượt đà thành một nhịp khựng.
            # Chỉ chặn khi số đo đang TRONG TẦM NGUY HIỂM. Số đo kịch trần (không
            # có tiếng vọng, ~100cm) cũng "không đổi" — chặn cả ca đó thì robot đứng
            # im vĩnh viễn. Ở xa thì số đo cũ vô hại vì còn lâu mới tới điểm dừng.
            if (0 <= dist <= config.APPROACH_SLOW_DISTANCE * 2
                    and time.time() - doi_luc > config.ULTRASONIC_STALE_TIME):
                self.stop()
                time.sleep(0.01)
                continue
            if dist < 0:
                # Lỗi đọc mẫu này — KHÔNG hiểu nhầm thành "đã tới", thử lại
                time.sleep(0.02)
                continue
            # Dừng SỚM hơn mốc hình học một khoảng bù. Siêu âm của gpiozero trả về
            # trung vị ULTRASONIC_QUEUE_LEN mẫu × ~60ms → con số báo về QUÁ KHỨ
            # ~90ms, mà robot vẫn chạy trong 90ms đó; cộng nhiễu trung vị trên mặt
            # kệ gồ ghề là ra "lúc dừng đúng, lúc chui vào gầm kệ".
            # Lệch hẳn về phía DỪNG SỚM vì hai vế không cân nhau: dừng sớm thì
            # creep_until bò tiếp tới khi IR báo, không mất gì; dừng muộn thì càng
            # (còn ở SÀN lúc này) chui vào gầm kệ.
            if dist <= target_cm + config.APPROACH_STOP_MARGIN:
                # Giảm tốc rồi mới cắt: phanh gấp ở đây làm robot lệch vài độ, mà
                # bước luồn càng kế tiếp không còn line để tự sửa.
                self.stop_gently(speed)
                # ĐO LẠI sau khi đứng hẳn. Lúc chạy, siêu âm trễ ~90ms nên số nó
                # báo là quá khứ; đứng yên thì hàng đợi đầy toàn giá trị hiện tại,
                # không còn trễ — số này là khoảng cách THẬT, thay được cây thước.
                # Chênh lệch giữa hai số CHÍNH LÀ độ trôi, in ra mỗi lần chạy để
                # chỉnh APPROACH_STOP_MARGIN mà không phải đo tay.
                logger.info("Vệt siêu âm (%d mẫu đổi): %s", len(vet),
                            " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet[-18:]))
                time.sleep(config.ULTRASONIC_QUEUE_LEN * 0.06 + 0.05)
                that = self.get_distance()
                if (0 <= that and that - dist > config.ULTRASONIC_VERIFY_TOLERANCE
                        and nhieu_ap < config.ULTRASONIC_MAX_GLITCH):
                    # Gai nhiễu: xem config.ULTRASONIC_VERIFY_TOLERANCE.
                    nhieu_ap += 1
                    logger.warning(
                        "Tiếp cận: BỎ QUA GAI NHIỄU — lúc chạy báo %.1fcm nhưng đo "
                        "lại khi ĐỨNG YÊN được %.1fcm. Tiếp tục tiếp cận (%d/%d).",
                        dist, that, nhieu_ap, config.ULTRASONIC_MAX_GLITCH)
                    continue
                if that >= 0:
                    # Lệch quá 1cm thì WARNING, không phải INFO: dòng ✅ của smoke in
                    # ra bất kể, nên nếu chôn ở INFO thì "robot tiến quá vị trí" trông
                    # y hệt "chạy đúng". Đã gặp thật.
                    ghi = (logger.info if abs(that - target_cm) <= 1.0
                           else logger.warning)
                    ghi(
                        "Đã đến vị trí kệ — lúc quyết định báo %.1fcm, ĐO LẠI khi "
                        "đứng yên %.1fcm (trôi thêm %.1fcm). Mốc %.1f + bù %.1f. "
                        "%s", dist, that, dist - that, target_cm,
                        config.APPROACH_STOP_MARGIN,
                        "→ bù ĐÚNG" if abs(that - target_cm) <= 1.0 else
                        ("→ bù THỪA, hạ APPROACH_STOP_MARGIN %.1f cm"
                         % (that - target_cm) if that > target_cm else
                         "→ bù THIẾU, nâng APPROACH_STOP_MARGIN %.1f cm"
                         % (target_cm - that)))
                else:
                    logger.info("Đã đến vị trí kệ — khoảng cách %.1fcm "
                                "(mốc %.1f + bù trễ %.1f); đo lại lỗi",
                                dist, target_cm, config.APPROACH_STOP_MARGIN)
                # Lưới an toàn ĐỘC LẬP với điều hướng: xem
                # config.APPROACH_ARRIVAL_TOLERANCE.
                if 0 <= that < target_cm - config.APPROACH_ARRIVAL_TOLERANCE:
                    logger.error(
                        "Tiếp cận THẤT BẠI: đứng cách %.1fcm, GẦN hơn mục tiêu %.1fcm "
                        "tới %.1fcm (cho phép %.1f). Không phải sai số tiếp cận — có "
                        "gì đó TRƯỚC ĐÓ đã sai (pose lệch một giao lộ, route đi lố). "
                        "KHÔNG báo đã tới, vì bước luồn càng sau đây sẽ tiến MÙ theo "
                        "niềm tin còn cách %.1fcm và húc vào kệ.",
                        that, target_cm, target_cm - that,
                        config.APPROACH_ARRIVAL_TOLERANCE, target_cm)
                    return False
                return True

            # KHÔNG TIẾN THÊM ĐƯỢC → dừng, đừng húc tiếp.
            # "Thấy mục tiêu" không đồng nghĩa "đang lại gần": mũi càng chạm kệ,
            # cảm biến kẹt, hay bánh trượt đều cho số đo đứng yên ở một giá trị
            # trông rất hợp lý — và APPROACH_BLIND_TIMEOUT (chỉ bắt "không thấy
            # gì") để lọt hết. Đã có lần robot đẩy vào kệ trọn 5s ở 60% tốc độ vì
            # cảm biến báo đều đặn 21.8cm trong khi mục tiêu là 4cm.
            if dist < best_dist - config.APPROACH_NO_PROGRESS_CM:
                best_dist = dist
                best_at = time.time()
            elif time.time() - best_at > moc_ket:
                self.stop()
                logger.warning("Vệt siêu âm (%d mẫu đổi): %s", len(vet),
                               " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet[-18:]))
                logger.error("Tiếp cận: %.1fs không lại gần thêm được (đang %.1fcm, "
                             "cần %.1fcm) — DỪNG, nhiều khả năng càng đã chạm kệ. "
                             "Kiểm APPROACH_DISTANCE có đúng khoảng cách CẢM BIẾN→kệ "
                             "lúc càng vào đúng khe pallet không.",
                             moc_ket, dist, target_cm)
                return False

            if dist <= config.APPROACH_DETECT_DISTANCE:
                target_seen = True
            elif not target_seen and time.time() - start > config.APPROACH_BLIND_TIMEOUT:
                # Chạy mù quá lâu mà chưa lần nào thấy mục tiêu trong tầm → DỪNG.
                # Không được chạy tiếp hết APPROACH_TIMEOUT: ở tốc độ này robot sẽ
                # lao ra khỏi sa bàn hoặc sang sân đối phương (bị reset −10 điểm).
                self.stop()
                logger.warning("Vệt siêu âm (%d mẫu đổi): %s", len(vet),
                               " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet[-18:]))
                logger.error("Tiếp cận: chạy mù %.1fs mà không thấy mục tiêu trong %.0fcm "
                             "(đo được %.1fcm) — dừng an toàn",
                             config.APPROACH_BLIND_TIMEOUT,
                             config.APPROACH_DETECT_DISTANCE, dist)
                return False

            # Pha xa: nhanh; pha gần: chậm để dừng chính xác, không đâm kệ.
            # ⚠️ CHỐT MỘT CHIỀU. Robot chỉ TIẾN về phía kệ, không thể xa ra — nên
            # một số đo "xa hơn" SAU KHI đã vào vùng gần chỉ có thể là nhiễu.
            # Đo trên robot 03/08, option 5 tầng 2:
            #     0.28s:16.9  → chậm
            #     0.41s:22.0  → MỘT mẫu nhiễu vọt qua 20 → quay lại NHANH (60%)
            #     0.47s:16.6  → chậm lại
            #     0.60s: 9.5  → đã lố; đo lại lúc đứng yên: 5.5cm
            # Robot đi 16.5→5.5cm trong 0.6s (~18cm/s) trong khi lượt chạy tốt chỉ
            # ~7cm/s. Không chốt thì chỉ cần MỘT mẫu nhiễu ở đúng 2cm cuối là hỏng
            # cả lần tiếp cận — và đó là chỗ không còn đường sửa.
            if 0 <= dist <= config.APPROACH_SLOW_DISTANCE:
                da_vao_gan = True
            speed = (config.APPROACH_SLOW_SPEED if da_vao_gan
                     else config.APPROACH_FAST_SPEED)
            if da_vao_gan and getattr(config, "APPROACH_STEPPED", False):
                # ĐI TỪNG NHỊP RỒI DỪNG MÀ ĐO. Lý do + vệt số đo thật:
                # config.APPROACH_STEPPED. Vòng lặp phía trên đọc get_distance()
                # ở đầu mỗi vòng, nên sau khi dừng ở đây thì số đo kế tiếp là số
                # đo LÚC ĐỨNG YÊN — loại hẳn cả độ trễ hàng đợi lẫn nhiễu khi chạy.
                self._forward_guided(speed)
                time.sleep(config.APPROACH_STEP_TIME)
                self.stop_gently(speed)
                time.sleep(config.ULTRASONIC_QUEUE_LEN * 0.06 + 0.05)
                doi_luc = time.time()
            else:
                self._forward_guided(speed)
                time.sleep(0.02)

        self.stop()
        logger.warning("Timeout tiếp cận kệ sau %.1fs! Vệt siêu âm (%d mẫu đổi): %s",
                       config.APPROACH_TIMEOUT, len(vet),
                       " ".join(f"{t:.2f}s:{d:.1f}" for t, d in vet[-18:]))
        return False

    def _forward_guided(self, speed: float) -> None:
        """Tiến, CÓ LÁI theo line nếu còn thấy line; mất line thì chạy thẳng như cũ.

        Dùng cho 2 chỗ tiến sát kệ (approach_shelf, creep_until) vốn chạy thẳng MÙ.
        Đo trên robot: robot không đi thẳng nên trên quãng ~10cm cuối nó lệch dần,
        càng không luồn hết vào khe pallet, pallet không lên càng, IR không báo →
        bốc hàng hỏng. Chữa ở mắt xích ĐẦU (đi thẳng) chứ không phải mắt xích cuối
        (ngưỡng IR / INSERT_MIN_DISTANCE).

        An toàn kể cả khi line không kéo tới tận kệ: hết line thì rơi về forward(),
        đúng hành vi cũ. Cờ giao lộ của follow_line() bị BỎ QUA ở đây — sát kệ thì
        nền kệ có thể làm mọi mắt thấy đen, mà ta chỉ cần phần LÁI chứ không đếm.
        """
        if not self._line_sensor.available:
            self.forward(speed)
            return
        raw = self.read_line_sensor_raw()
        values = LineSensor.digital_from_raw(raw)
        n = sum(values)
        if n == 0:
            self.forward(speed)              # hết line → thẳng như cũ
        elif n >= config.INTERSECTION_THRESHOLD:
            # ⚠️ KHÔNG gọi follow_line() ở đây. follow_line() thấy giao lộ là gọi
            # self.stop() rồi trả về — tức DỪNG MOTOR ngay giữa pha tiếp cận kệ.
            # Sát kệ thì thanh cảm biến nằm trên VIỀN ĐEN của ô kệ in trên sa bàn
            # (vạch ngang rộng 240mm, SA_BAN.md 3b) nên mọi mắt đều đen — đo trên
            # robot: 6 dòng "Phát hiện giao lộ (active=6)" liên tiếp trong một pha
            # tiếp cận. Ở đây ta chỉ cần phần LÁI, không cần đếm giao lộ.
            # Mọi mắt đen thì sai số line là số rác → đi THẲNG, không lái, không dừng.
            self._drive_straight(speed)
        else:
            self._steer(raw, speed)

    def tien_bu_cm(self, cm: float, speed: float, ly_do: str = "") -> bool:
        """Tiến ĐÚNG `cm` centimet, đo bằng ENCODER. Trả True nếu đo được bằng encoder.

        Dùng cho bước tiến bù trước khi xoay: xoay 90° tại chỗ thì TRỤC BÁNH phải
        nằm trong ~±1.5cm của giao lộ, mà thanh cảm biến lại ở đầu xe cách trục
        ~12cm. Trước đây bù bằng THỜI GIAN — quãng đường đổi theo pin, ma sát và
        tải trên càng, nên lúc đúng lúc sai. Xem config.ENCODER_PULSES_PER_CM.

        Chưa calibrate hoặc encoder hỏng → trả False để caller rơi về cách cũ.
        """
        xung_cm = getattr(config, "ENCODER_PULSES_PER_CM", 0.0)
        co_enc = (getattr(getattr(self, "_encoder_left", None), "available", False)
                  and getattr(getattr(self, "_encoder_right", None), "available", False))
        if xung_cm <= 0 or not co_enc:
            return False

        # Trung bình 2 bánh: xung_cm chốt theo TỔNG 2 bánh nên dùng thẳng tổng.
        can = cm * xung_cm
        self._doc_xung()                      # xả bộ đếm của chặng trước
        self.forward(speed)
        start, da = time.time(), 0
        while da < can and time.time() - start < config.RECENTER_MAX_TIME:
            if self._aborted():
                break
            da += self._doc_xung()
            # ⛔ CÓ LÁI, KHÔNG CHẠY MÙ — đây là 12cm NGAY TRƯỚC MỘT CÚ XOAY, tức
            # đoạn quyết định tư thế của cả chặng sau.
            # Đội đo 04/08: test_motion option 10 cho ĐÚNG 90°, nhưng chạy thật ở
            # giao lộ Samsung robot quay ~135° rồi lạc. Cú xoay KHÔNG sai — tư thế
            # lúc xoay mới sai. Samsung ở R4 (nhà máy xa nhất) nên chặng lùi về nó
            # dài nhất, sai lệch hướng tích luỹ nhiều nhất; rồi 12cm chạy MÙ này
            # khuếch đại nốt, và robot xoay đủ 90° nhưng quanh một tư thế đã xiên
            # — so với vạch line thì thành ~135°.
            # Đúng bài học đã ghi cho _forward_guided: "Robot không đi thẳng tuyệt
            # đối nên nó lệch dần". Còn thấy line thì lái, mất line thì giữ nguyên
            # hành vi cũ (forward) nên không xấu đi ở chỗ không có vạch.
            # Cờ giao lộ của follow_line() bị BỎ QUA: ta đang đứng ngay trên giao
            # lộ nên nó báo liên tục, mà ở đây chỉ cần phần LÁI.
            if config.RECENTER_BAM_LINE:
                try:
                    tai_gl, gia_tri = self.follow_line(speed)
                    # ⛔ PHẢI RA LỆNH CHẠY LẠI khi follow_line thấy giao lộ.
                    # Nó tự gọi stop() ở đó, mà robot đang đứng NGAY TRÊN giao lộ
                    # (đó là cả mục đích của bước bù này) nên nó phanh ở MỌI vòng
                    # lặp. Đo trên robot 04/08 sau khi tôi thêm bám line vào đây:
                    #     Tiến bù (sau khi lùi) 12.0cm: 16/431 xung trong 5.01s
                    # 16 xung = robot đứng im suốt 5 giây rồi bỏ cuộc.
                    # Bẫy này CLAUDE.md đã ghi rõ; tôi bỏ qua GIÁ TRỊ TRẢ VỀ mà
                    # quên rằng nó đã kịp dừng motor.
                    if tai_gl or sum(gia_tri) == 0:
                        self.forward(speed)
                except Exception:
                    self.forward(speed)
            time.sleep(0.01)
        self.stop()
        het_gio = da < can
        (logger.warning if het_gio else logger.info)(
            "Tiến bù %s%.1fcm: %d/%.0f xung trong %.2fs%s",
            f"({ly_do}) " if ly_do else "", cm, da, can, time.time() - start,
            " — HẾT CHẶN TRÊN, chưa đủ quãng. Encoder rớt xung?" if het_gio else "")
        return True

    def _adc_de_ghi(self):
        """ADC 6 mắt để IN RA LOG — không bao giờ ném lỗi.

        Nhịp tim chỉ để quan sát, nó không được phép làm hỏng chặng đang chạy
        (hoặc làm đỏ các bài test dựng Motion tối giản, không có _line_sensor).
        """
        try:
            return self.read_line_sensor_adc()
        except Exception as e:
            return f"(khong doc duoc: {e})"

    def _doc_xung(self) -> int:
        """Tổng xung encoder 2 bánh kể từ lần gọi trước (đọc xong là RESET).

        Không cần biết bao nhiêu xung/cm — chỉ cần biết bánh CÓ QUAY không. Dùng
        làm chặn kẹt khi luồn càng, thay cho siêu âm (xem config.INSERT_STALL_TIME).
        """
        t = getattr(self, "_encoder_left", None)
        p = getattr(self, "_encoder_right", None)
        return ((t.read_and_reset() if t is not None else 0)
                + (p.read_and_reset() if p is not None else 0))

    def creep_until(self, check, speed: float = config.INSERT_SPEED,
                    timeout: float = config.INSERT_TIMEOUT,
                    min_distance: float = config.INSERT_MIN_DISTANCE) -> bool:
        """Tiến CHẬM cho tới khi `check()` trả True. Dùng để LUỒN CÀNG vào pallet.

        `check` là hàm không tham số do caller cung cấp — thường là "cả 2 IR đã
        thấy pallet". Motion cố tình KHÔNG biết nó đang đợi cái gì: cảm biến IR
        thuộc về Lift, và tách như vậy thì test được bằng một hàm giả.

        Vì sao không dùng siêu âm để canh điểm dừng: siêu âm đo khoảng cách tới
        MẶT KỆ, còn thứ cần biết là PALLET đã nằm trên càng chưa. Robot lệch ngang
        vài centimet, hay pallet đặt lệch trên kệ, là con số siêu âm sai ngay —
        IR thì không. Siêu âm ở đây chỉ còn làm CHẶN CỨNG (min_distance).

        Trả False khi hết `timeout` hoặc chạm `min_distance` mà `check` vẫn False.
        """
        co_encoder = (getattr(getattr(self, "_encoder_left", None), "available", False)
                      and getattr(getattr(self, "_encoder_right", None), "available", False))
        logger.info("Luồn càng: tiến %d%% tối đa %.1fs (chặn kẹt bằng %s)",
                    speed, timeout,
                    "ENCODER" if co_encoder else "TIMEOUT — encoder không khả dụng!")
        if not co_encoder:
            logger.warning("Luồn càng: KHÔNG có encoder — mất chặn cứng chống tì kệ. "
                           "Chỉ còn timeout %.1fs giữ.", timeout)
        start = time.time()
        self._doc_xung()          # xả bộ đếm, không tính xung của chặng trước
        xung_cua_so = 0
        moc_cua_so = start
        # Tổng quãng đã LUỒN VÀO, để lùi ra đúng bấy nhiêu. Xem retreat_from_shelf:
        # lùi mù theo THỜI GIAN đi được ít hơn hẳn khi cõng 2 kiện, nên robot lùi
        # ngắn quá rồi xoay lệch khỏi line (đo trên robot 03/08, option 5 — trong
        # khi option 18 chạy khớp vì bài đó không cõng gì).
        self.xung_da_luon = 0
        try:
            if check():
                logger.info("Luồn càng: đã đạt điều kiện ngay từ đầu")
                return True
        except Exception as e:
            logger.error("Luồn càng: lỗi đọc điều kiện dừng (%s) — không tiến", e)
            return False

        while time.time() - start < timeout:
            if self._aborted():
                return False

            # ⛔ CHẶN CỨNG BẰNG ENCODER, không phải siêu âm.
            # Lý do + số đo: config.INSERT_STALL_TIME. Tóm tắt: đặt robot cách kệ
            # ĐÚNG 12cm (thước), siêu âm báo 35.7cm — mặt trước giá kệ HỞ nên chùm
            # sóng lọt qua. Chặn cứng dựa vào nó vừa không bắt được lúc cần, vừa
            # bắn nhầm khi có gai nhiễu ngắn. Encoder không cần calibrate cm: càng
            # chạm kệ là bánh kẹt, xung im ngay.
            moi = self._doc_xung()
            xung_cua_so += moi
            self.xung_da_luon += moi
            if time.time() - moc_cua_so >= config.INSERT_STALL_TIME:
                if (time.time() - start >= config.INSERT_STALL_GRACE
                        and co_encoder and xung_cua_so < config.INSERT_STALL_PULSES):
                    self.stop()
                    logger.error(
                        "Luồn càng: BÁNH KHÔNG QUAY (%d xung trong %.1fs) mà IR chưa "
                        "báo — DỪNG. Càng đang tì vào kệ, hoặc trượt ra ngoài khe "
                        "pallet. Đi được %.2fs trước khi kẹt.",
                        xung_cua_so, config.INSERT_STALL_TIME, time.time() - start)
                    return False
                xung_cua_so = 0
                moc_cua_so = time.time()

            self._forward_guided(speed)
            time.sleep(0.02)

            # CHỈ bọc try quanh check() — đó là thứ duy nhất có thể lỗi đọc
            # (SPI/ADC). Bọc cả stop_gently() thì một lỗi PHANH sẽ bị báo nhầm
            # thành "lỗi đọc IR" và người sửa đi tìm sai chỗ.
            try:
                xong = check()
            except Exception as e:
                self.stop()
                logger.error("Luồn càng: lỗi đọc điều kiện dừng (%s) — dừng", e)
                return False
            if xong:
                # Càng ĐANG NẰM TRONG khe pallet — phanh gấp ở đây là giật cả
                # pallet, có thể làm nó tụt khỏi càng trước khi kịp nhấc.
                self.stop_gently(speed)
                logger.info("Luồn càng: điều kiện đạt sau %.2fs", time.time() - start)
                return True

        self.stop()
        con = self.get_distance()
        logger.warning("Luồn càng: hết %.1fs mà IR vẫn chưa báo có pallet — đang ở "
                       "%.1fcm (chặn %.1fcm). Còn cách chặn %.1fcm nghĩa là hết GIỜ "
                       "chứ không phải chạm chặn: bò quá chậm hoặc xuất phát quá xa.",
                       timeout, con, min_distance, max(0.0, con - min_distance))
        return False

    def retreat_from_shelf(self, target_cm: float = config.RETREAT_DISTANCE,
                           speed: float = config.APPROACH_SPEED,
                           quang_cm: float | None = None) -> bool:
        """Lùi ra khỏi kệ / khu nhà máy.

        `quang_cm` — lùi ĐÚNG bấy nhiêu centimet thay vì theo quãng đã luồn vào.
        Dùng khi rút khỏi NHÀ MÁY: ở đó robot không hề luồn càng nên quãng luồn của
        lần bốc trước không liên quan gì. Xem config.RETREAT_AFTER_DROP_CM.
        """
        if self._distance_sensor is None:
            logger.error("Không có cảm biến siêu âm — không thể lùi an toàn")
            return False

        logger.info("Lùi ra khỏi kệ — mục tiêu %.1fcm", target_cm)
        # ⛔ CÕNG HÀNG THÌ BỎ HẲN SIÊU ÂM ngay từ đầu, không chờ nhánh phát hiện
        # kẹt. Kiện trên càng chắn chùm sóng và số đo nhảy lung tung (đo 03/08:
        # 9.4 / 7.8 / 10.2 / 100.0 trong cùng một lượt) — vớ đúng một mẫu ≥ mục
        # tiêu là báo "đã lùi đủ xa" khi robot còn chưa nhúc nhích. Đó chính là
        # "lùi có một đoạn ngắn rồi tiến lên xoay, va vào kệ và lệch line".
        # Nhánh kẹt chỉ bật sau RETREAT_STUCK_TIME = 0.8s nên không kịp cứu.
        cong_hang = getattr(self, "dang_cong_hang", False)
        if cong_hang:
            logger.info(
                "Lùi ra: ĐANG CÕNG HÀNG — bỏ qua siêu âm, lùi theo %s",
                f"{quang_cm:.1f}cm chỉ định (rút khỏi NHÀ MÁY, không luồn càng)"
                if quang_cm is not None
                else f"quãng đã luồn vào ({getattr(self, 'xung_da_luon', 0)} xung)")
        self._doc_xung()          # xả bộ đếm trước khi đo quãng lùi
        lui_xung = 0
        start = time.time()
        self.backward(speed)
        dau = None          # khoảng cách đọc được lần đầu
        mu = False          # đã chuyển sang lùi mù chưa

        while time.time() - start < config.APPROACH_TIMEOUT:
            if self._aborted():
                return False
            troi = time.time() - start
            dist = self.get_distance()   # gpiozero đã lấy trung vị sẵn (ULTRASONIC_QUEUE_LEN)
            if dist < 0:
                # Lỗi đọc mẫu này — KHÔNG hiểu nhầm thành "đã lùi đủ", thử lại
                time.sleep(0.02)
                continue
            if dau is None:
                dau = dist
            if (not cong_hang) and (not mu) and dist >= target_cm:
                self.stop()
                logger.info("Đã lùi đủ xa — khoảng cách %.1fcm", dist)
                return True

            # Lưới an toàn khi siêu âm KHÔNG DÙNG ĐƯỢC (mất tiếng vọng, bị che bởi
            # vật lạ, cảm biến hỏng): số đo không TĂNG dù robot đang lùi → chuyển
            # sang lùi theo THỜI GIAN thay vì chạy hết timeout 5s.
            # ⚠️ Ban đầu tôi cho rằng nguyên nhân là KIỆN HÀNG cõng che cảm biến.
            # Đo lại ngày 02/08 (tools.check_load_blocks_sonar) thì SAI: kiện đọc
            # 74.6 / 76.8 / 72.6 cm ở sàn / tầng 1 / tầng 2 — không che gì cả.
            # Vụ lùi timeout thật ra do APPROACH_SPEED = 30 quá sát vùng chết (25),
            # cõng hàng thì không thắng nổi ma sát; nâng lên 40 là hết.
            # Giữ nhánh này vì nó rẻ và vẫn đúng cho MỌI nguyên nhân làm cảm biến
            # đứng số, nhưng đừng đọc nó như "kiện che cảm biến".
            if (not mu and troi >= config.RETREAT_STUCK_TIME
                    and dist - dau < config.RETREAT_STUCK_CM):
                mu = True
                logger.warning(
                    "Lùi ra: sau %.1fs mà khoảng cách chỉ đổi %.1fcm (%.1f→%.1f) — "
                    "siêu âm không dùng được. Chuyển sang lùi theo thời gian %.1fs.",
                    troi, dist - dau, dau, dist, config.RETREAT_BLIND_TIME)
            if mu or cong_hang:
                # Lùi ĐÚNG quãng đã luồn vào (× RETREAT_BACKOUT_MARGIN), đo bằng
                # encoder. Hằng số THỜI GIAN không dùng được ở đây: cõng 2 kiện thì
                # 1.5s đi được ít hơn hẳn lúc đi không, robot lùi ngắn quá rồi xoay
                # lệch khỏi line. Không cần hằng số mới — quãng luồn vào chính là
                # quãng phải lùi ra, và creep_until vừa đếm nó xong.
                if quang_cm is not None:
                    can = quang_cm * config.ENCODER_PULSES_PER_CM
                else:
                    can = (getattr(self, "xung_da_luon", 0)
                           * getattr(config, "RETREAT_BACKOUT_MARGIN", 1.15))
                if can > 0:
                    lui_xung += self._doc_xung()
                    if lui_xung >= can:
                        self.stop()
                        logger.info(
                            "Đã lùi %d/%.0f xung (%s) — rời kệ", lui_xung, can,
                            f"{quang_cm:.1f}cm chỉ định" if quang_cm is not None
                            else f"quãng đã luồn vào × {config.RETREAT_BACKOUT_MARGIN:.2f}")
                        return True
                    if troi < config.APPROACH_TIMEOUT:
                        time.sleep(0.01)
                        continue
                if troi >= config.RETREAT_BLIND_TIME:
                    self.stop()
                    logger.info("Đã lùi mù %.1fs — coi như đã rời kệ (KHÔNG có số "
                                "xung luồn vào để đối chiếu)", troi)
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
        # Phép ĐO thuần: line đang nằm ở đâu trên thanh cảm biến. ĐIỂM ĐẶT
        # (config.LINE_CENTER_OFFSET) thuộc về luật lái, trừ ở _steer() — để hàm này
        # còn dùng được cho chẩn đoán và hiển thị mà không bị pha tạp.
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
            logger.info("Phát hiện giao lộ (active=%d, cảm biến %s, ADC %s, ngưỡng %.0f)",
                        active_count, values,
                        [int(round(v * 1023)) for v in raw],
                        LineSensor.nguong_cho(raw) * 1023)
            return True, values

        self._steer(raw, base_speed, reverse)
        return False, values

    def _steer(self, raw: list[float], base_speed: float, reverse: bool = False):
        """Một nhịp lái PD theo sai số line. Tách riêng để chế độ chạy liền
        (_navigate_continuous) dùng chung đúng luật lái với follow_line()."""
        # Trừ ĐIỂM ĐẶT tại đây, không phải trong phép đo. Thanh cảm biến lắp lệch
        # tâm so với càng: đo trên robot 02/08, tư thế càng thẳng khe pallet cho sai
        # số THÔ +0.50 chứ không phải 0. Lái để đưa sai số thô về 0 là chủ động kéo
        # robot về chỗ SAI. Xem config.LINE_CENTER_OFFSET.
        error = self.compute_line_error_analog(raw) - config.LINE_CENTER_OFFSET
        derivative = error - self._last_error
        correction = config.LINE_KP * error + config.LINE_KD * derivative
        self._last_error = error
        if reverse:
            correction = -correction
        correction = self._clamp_correction(correction, base_speed)
        self._drive(base_speed + correction, base_speed - correction, reverse)

    @staticmethod
    def _clamp_correction(correction: float, base_speed: float) -> float:
        """Chặn hiệu chỉnh để bánh CHẬM không tụt xuống dưới vùng chết của motor.

        LINE_KP = 16 chỉnh cho SPEED_DEFAULT = 50. Nhưng bám line còn chạy ở 32%
        (APPROACH_SLOW_SPEED và INSERT_SPEED), mà vùng chết của JGA25-370 qua L298N
        là ~25%. Ở base 32, chỉ cần sai số line 0.44 (trên thang ±2.5, tức lệch vạch
        chưa tới 1cm) là hiệu chỉnh vượt 7 và bánh trong tụt xuống dưới 25 — nó ĐỨNG
        HẲN, robot xoay quanh nó thay vì lượn.

        Đo trên robot (smoke option 2): robot đi chệch hướng và một càng thọc sâu hơn
        càng kia. Tức cơ chế bám line thêm vào để CHỐNG lệch lại đang TẠO ra lệch.

        Kẹp đối xứng nên mất bớt lực lái ở tốc độ thấp: base 32 chỉ còn ±7. Đó là
        giới hạn VẬT LÝ, không phải lựa chọn — muốn lái mạnh hơn thì phải NÂNG
        base_speed để có thêm khoảng hở, chứ không phải bỏ kẹp.

        config.MOTOR_MIN_DUTY = 0 → tắt kẹp, về đúng hành vi cũ.
        """
        san = getattr(config, "MOTOR_MIN_DUTY", 0)
        bien = base_speed - san
        if san <= 0 or bien <= 0:
            return correction          # base đã dưới vùng chết — kẹp cũng vô nghĩa
        return max(-bien, min(bien, correction))

    def _drive_straight(self, base_speed: float, reverse: bool = False):
        """Đi thẳng, KHÔNG lái — dùng khi đang cắt ngang vạch giao lộ (mọi mắt đều
        đen nên sai số line là số rác, để PD chạy theo sẽ giật)."""
        self._drive(base_speed, base_speed, reverse)

    @staticmethod
    def _fit_to_range(left: float, right: float) -> tuple[float, float]:
        """Đưa 2 tốc độ vào dải 0-100 mà GIỮ ĐỘ CHÊNH giữa chúng.

        Độ chênh 2 bánh — chứ không phải trị số tuyệt đối — mới là thứ tạo ra góc lái.
        Kẹp thẳng từng bánh sẽ ĂN MẤT độ chênh đúng lúc cần nó nhất: sai số lớn nhất
        (|error|=2.5, LINE_KP=16 → correction 40) ở SPEED_DEFAULT=80 cho ra (120, 40),
        kẹp thành (100, 40) — chênh 60 thay vì 80, mất 25% lực lái ở khúc gấp. Ở tốc
        độ 50 hiện tại chưa bao giờ vượt dải nên không thấy; TĂNG tốc độ (đòn tối ưu
        số 1 của ngân sách 240s) là kích hoạt ngay.

        Trượt CẢ HAI bánh xuống/lên thay vì kẹp riêng → robot tự chậm lại ở khúc gấp
        mà vẫn ngoặt đủ.
        """
        over = max(left, right) - 100.0
        if over > 0:
            left -= over
            right -= over
        under = -min(left, right)
        if under > 0:
            left += under
            right += under
        # Còn vượt dải sau khi trượt = độ chênh yêu cầu rộng hơn cả dải PWM (phải đảo
        # chiều một bánh mới đạt) — đành kẹp.
        return max(0.0, min(100.0, left)), max(0.0, min(100.0, right))

    def _drive(self, left_speed: float, right_speed: float, reverse: bool = False):
        """Đặt tốc độ 2 bánh (đã kẹp 0-100) kèm bù lệch — dùng ĐÚNG cùng hệ số như
        forward()/backward(), nếu không đi thẳng và bám line sẽ lệch nhau sau
        khi calibrate."""
        left_speed, right_speed = self._fit_to_range(left_speed, right_speed)
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

        # ⛔ CỔNG QUÃNG ĐƯỜNG KHÁC NHAU GIỮA KỆ VÀ NHÀ MÁY — hình học hai chỗ khác hẳn.
        # Ở KỆ: robot dừng cách giao lộ ADVANCE_SHELF_STOP_CM (17.0), lùi ra khỏi kệ
        #   12.9cm trước → khi chặng lùi bắt đầu, giao lộ chỉ còn cách 4.1cm. Cổng
        #   phải NHỎ HƠN 4.1, nên hạ về 3.0 (04/08).
        # Ở NHÀ MÁY: mảng đen ngay đầu chặng lùi VƯỢT ĐƯỢC bộ lọc giao lộ. Đo trên
        #   robot 04/08, chặng lùi khỏi nhà máy: ADC [458, 0, 113, 0, 600, 45] cho
        #   4 mắt đen đậm + 3 mắt đen sâu → la_giao_lo_that() = True. Nó chỉ bị loại
        #   nhờ CỔNG QUÃNG ĐƯỜNG, vì xuất hiện ở 0.9cm. Hạ cổng chung xuống 3.0 làm
        #   biên tụt từ 4.1cm còn 2.1cm — robot lùi lệch một chút là mảng đó lọt,
        #   route đếm thừa một giao lộ và TOÀN BỘ chặng quay về sai.
        # Nên chỗ này giữ 5.0 (giá trị đã chạy đúng trước 04/08). Caller báo bằng
        # `motion.lui_khoi_nha_may`, cùng kiểu với cờ `dang_cong_hang`.
        moc_lui = (config.BACK_MIN_TRAVEL_FACTORY_CM
                   if getattr(self, "lui_khoi_nha_may", False)
                   else config.BACK_MIN_TRAVEL_CM)

        # ⛔ CHƯA CÓ VẠCH THÌ TÌM TRƯỚC, ĐỪNG LÙI MÙ.
        # Đo trên robot 07/08, chặng quay về từ Hana sau khi thả:
        #     Lùi: đã lùi 5.1cm ... coi như đã rời hẳn điểm cuối
        #     ERROR Lùi: mất line quá 1.2s — dừng an toàn
        #     Navigation thất bại — RETURN → kệ 0. Chạy được 0/10 bước
        # Robot dừng thả ở chỗ thanh cảm biến đã ra ngoài vạch (điểm dừng ở khu nhà
        # máy do MẢNG IN quyết định, mà mảng in có thể nằm quá cuối vạch). Lùi từ đó
        # là lùi mù: không có gì để bám, và chặng gãy ngay ở bước ĐẦU TIÊN của cả
        # tuyến quay về — mất luôn 3 lượt bốc còn lại.
        # Quét tìm tại chỗ trước khi lùi thì rẻ hơn nhiều so với hỏng cả tuyến.
        try:
            if sum(self.read_line_sensor()) == 0:
                logger.warning(
                    "Lùi: chưa có vạch nào dưới cảm biến — QUÉT TÌM tại chỗ trước "
                    "khi lùi. Lùi mù từ điểm cuối là gãy ngay bước đầu của cả tuyến "
                    "quay về.")
                if self._recover_line():
                    logger.info("Lùi: đã tìm được vạch, bắt đầu lùi")
                else:
                    logger.error(
                        "Lùi: KHÔNG tìm được vạch nào quanh chỗ đứng — điểm dừng ở "
                        "khu nhà máy đang nằm QUÁ CUỐI VẠCH. Hạ "
                        "ADVANCE_FACTORY_STOP_CM (hoặc đặt riêng cho khu này trong "
                        "ADVANCE_FACTORY_STOP_CM_RIENG) để robot dừng khi còn trên "
                        "vạch.")
        except Exception:
            pass
        if getattr(self, "lui_khoi_nha_may", False):
            logger.info("Lùi khỏi NHÀ MÁY — cổng quãng đường %.1fcm (kệ dùng %.1f)",
                        moc_lui, config.BACK_MIN_TRAVEL_CM)

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
            da_thay_vach = False   # đã đọc được VẠCH LINE THƯỜNG lần nào chưa
            # Cổng quãng đường CHỈ dùng được khi có encoder VÀ đã calibrate.
            # Thiếu một trong hai mà vẫn áp thì lui_cm luôn = 0 và mọi giao lộ đều
            # bị bác → robot lùi vô hạn. Bộ test bắt được đúng ca này.
            do_duoc_quang = (config.ENCODER_PULSES_PER_CM > 0
                             and getattr(getattr(self, "_encoder_left", None),
                                         "available", False)
                             and getattr(getattr(self, "_encoder_right", None),
                                         "available", False))
            self._doc_xung()       # xả bộ đếm — đo quãng lùi của CHẶNG NÀY
            lui_xung_gl = 0
            if not do_duoc_quang:
                logger.warning("Lùi: KHÔNG đo được quãng (encoder %s) — mất cổng "
                               "chống nhận nhầm mảng đen chân kệ, chỉ còn bằng chứng "
                               "'đã thấy vạch thường'.",
                               "chưa calibrate" if config.ENCODER_PULSES_PER_CM <= 0
                               else "không khả dụng")

            while time.time() - start < timeout:
                if self._aborted():
                    return False
                lui_xung_gl += self._doc_xung()
                at_intersection, values = self.follow_line(base_speed, reverse=True)
                # ⚠️ KHÔNG nhận giao lộ trong những giây đầu. Từ điểm cuối (kệ/nhà
                # máy) tới giao lộ là 35.4cm, mà robot đứng cách kệ ~12.9cm, nên cảm
                # biến phải lùi HƠN 20cm mới tới giao lộ thật — không thể có giao lộ
                # ngay lập tức. Nhận nhầm sớm thì bước TIẾN BÙ ngay sau đó (1.3s về
                # phía kệ) đẩy robot trở lại CHẠM KỆ. Đã gặp thật ở option 8.
                # Chỉ chấp nhận giao lộ SAU KHI đã thấy VẠCH LINE THƯỜNG ít nhất một
                # lần. Robot xuất phát từ điểm cuối (kệ/nhà máy), nơi có thể đang
                # ngồi trên một mảng đen — phải rời khỏi nó, đi qua đoạn vạch bình
                # thường, rồi mới có quyền nói "tới giao lộ".
                # ⚠️ Bản trước chặn bằng THỜI GIAN (0.6s). Sai lầm cùng loại đã mắc
                # nhiều lần trong ngày: hằng số thời gian phụ thuộc cm/s mà cm/s thì
                # chưa ai đo. Lùi nhanh hơn ước lượng là nó nuốt luôn giao lộ THẬT,
                # robot lùi tiếp — mà từ C0R0 về phía đông, giao lộ kế cách 100cm.
                # Đã gặp thật ở option 5: "lùi tự do ra một đoạn dài".
                # Bằng chứng "đã thấy vạch thường" không phụ thuộc tốc độ.
                if 0 < sum(values) < config.INTERSECTION_THRESHOLD:
                    da_thay_vach = True
                lui_cm = (lui_xung_gl / config.ENCODER_PULSES_PER_CM
                          if do_duoc_quang else None)
                # ⛔ LỐI THOÁT BẰNG QUÃNG ĐƯỜNG. Điều kiện "phải thấy vạch thường
                # trước" không có lối thoát: nếu robot KHÔNG BAO GIỜ gặp vạch thường
                # thì nó chặn VĨNH VIỄN và robot lùi mãi.
                # Đo trên robot 07/08, chặng lùi khỏi khu nhà máy: cảm biến giữ
                # nguyên [0,0,1,1,1,1] (ADC [906, 828, 0, 0, 0, 0]) — 4 mắt đen, tức
                # KHÔNG phải "vạch thường" theo định nghĩa < INTERSECTION_THRESHOLD.
                # Mọi tín hiệu bị bác với cùng một lý do, liên tục, không dứt.
                # Đi đủ cổng quãng đường thì robot đã RỜI HẲN điểm cuối — lo lắng
                # "còn ngồi trên mảng đen của điểm cuối" hết hiệu lực.
                if (not da_thay_vach) and lui_cm is not None and lui_cm >= moc_lui:
                    da_thay_vach = True
                    logger.info(
                        "Lùi: đã lùi %.1fcm (≥ cổng %.1f) mà chưa gặp vạch thường "
                        "lần nào — coi như đã rời hẳn điểm cuối, cho phép nhận giao "
                        "lộ. Cảm biến %s", lui_cm, moc_lui, values)
                if at_intersection and not da_thay_vach:
                    logger.info("Lùi: bỏ qua tín hiệu giao lộ ở %.2fs — CHƯA thấy vạch "
                                "line thường lần nào (mới lùi %s), robot có thể còn "
                                "trên mảng đen của điểm cuối. Cảm biến %s",
                                time.time() - start,
                                "?" if lui_cm is None else f"{lui_cm:.1f}cm", values)
                    at_intersection = False
                    # Cùng lý do như hai nhánh dưới: follow_line() vừa phanh.
                    self.backward(base_speed)
                # ĐẾM MẮT ĐEN ĐẬM (ngưỡng tuyệt đối), KHÔNG đòi liền nhau.
                # Ba chữ ký thu được trên robot 03/08, cùng chặng lùi này:
                #   vạch thường  ADC [228, 481,   0,   0,   0, 925]  → 3 đen đậm
                #   giao lộ thật ADC [  0, 703,   0,   0,   0, 926]  → 4 đen đậm
                #   chân kệ      ADC [504,   0, 106, 454,   0,   0]  → 4 đen đậm
                # Ca đầu là vạch line THƯỜNG bị NGƯỠNG THÍCH NGHI thổi thành giao
                # lộ: line thật chỉ ở mắt 3,4,5 còn mắt 1 đọc 228 — không đen, chỉ
                # lọt dưới ngưỡng 277. Đếm đen đậm bác được nó.
                # Ca ba (chân kệ) đen đậm thật nên đếm không bác được — đó là việc
                # của cổng quãng đường bên dưới. Hai bộ lọc bù cho nhau, và ĐÒI DÃY
                # LIỀN NHAU thì bác luôn cả ca hai (đã thử, robot lùi mất 3.2s).
                if at_intersection:
                    raw_gl = self.read_line_sensor_raw()
                    dam = LineSensor.dem_den_dam(raw_gl)
                    if not LineSensor.la_giao_lo_that(raw_gl):
                        logger.info(
                            "Lùi: bỏ qua tín hiệu giao lộ ở %.2fs — chỉ %d/%d mắt đen "
                            "ĐẬM, ADC %s. Vạch thường bị ngưỡng thích nghi thổi lên, "
                            "không phải giao lộ.",
                            time.time() - start, dam, config.INTERSECTION_THRESHOLD,
                            [int(round(v * 1023)) for v in raw_gl])
                        at_intersection = False
                        # ⚠️ PHẢI RA LỆNH CHẠY LẠI. follow_line() tự gọi stop() khi
                        # nó thấy giao lộ (đúng như _forward_guided đã phải né).
                        # Bác tín hiệu mà không lái tiếp thì vòng sau follow_line
                        # lại thấy, lại phanh — robot đứng im vĩnh viễn. Đo trên
                        # robot 03/08: kẹt ở 4.7cm suốt 8 giây rồi timeout.
                        self.backward(base_speed)

                if at_intersection and lui_cm is not None \
                        and lui_cm < moc_lui:
                    logger.info(
                        "Lùi: bỏ qua tín hiệu giao lộ ở %.2fs — mới lùi %.1fcm "
                        "(cần %.1f). Mảng đen chân kệ nằm ngay đầu chặng lùi, giao "
                        "lộ thì cách một đoạn. Cảm biến %s",
                        time.time() - start, lui_cm, moc_lui, values)
                    at_intersection = False
                    # Cùng lý do như trên: follow_line() vừa phanh, phải chạy lại.
                    self.backward(base_speed)

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
            if self.tien_bu_cm(config.RECENTER_CM, config.REVERSE_RECENTER_SPEED,
                               "sau khi lùi"):
                pass
            elif config.REVERSE_RECENTER_TIME > 0:
                # ⚠️ Dùng REVERSE_RECENTER_SPEED, KHÔNG dùng base_speed. Đoạn tiến bù
                # này chạy MÙ theo thời gian, nên quãng đường phụ thuộc thẳng vào tốc
                # độ — đổi tốc độ là hằng số thời gian đã calibrate mất hiệu lực.
                # Đã gặp thật: nâng REVERSE_SPEED 35 → 40 làm robot tiến bù quá vạch,
                # xoay xong thanh cảm biến đã qua khỏi giao lộ → mất line ở option 8.
                self.forward(config.REVERSE_RECENTER_SPEED)
                time.sleep(config.REVERSE_RECENTER_TIME)
                self.stop()

        # Trả sai số về 0 để lần bám line TIẾN kế tiếp không thừa hưởng đạo hàm của
        # pha lùi (dấu hiệu chỉnh 2 pha ngược nhau).
        self._last_error = 0.0
        return True

    def follow_line_until_intersection(self, base_speed: float = config.SPEED_DEFAULT,
                                       timeout: float = 15.0,
                                       roi_diem_cuoi: bool = False) -> bool:
        start = time.time()
        lost_since = None
        # Cổng quãng đường — chỉ dùng được khi có encoder VÀ đã calibrate. Thiếu
        # một trong hai mà vẫn áp thì di_cm luôn = 0 và MỌI giao lộ bị bác.
        do_duoc = (config.ENCODER_PULSES_PER_CM > 0
                   and getattr(getattr(self, "_encoder_left", None), "available", False)
                   and getattr(getattr(self, "_encoder_right", None), "available", False))
        # ⛔ CỔNG QUÃNG ĐƯỜNG CHỈ ÁP KHI CALLER BẢO "vừa rời điểm cuối".
        # Nó sinh ra để robot rời khu nhà máy không đếm TẤM IN dưới chân thành giao
        # lộ. Áp cho MỌI chặng thì phá chặng đầu tiên của trận: exit_start_zone() bỏ
        # robot lại rất gần C0R0, cổng 10cm bác luôn giao lộ THẬT đó — robot đi
        # tiếp, mảng đen chân kệ thành "giao lộ", advance khởi hành khi đã sát kệ và
        # LAO VÀO KỆ.
        #
        # ĐÃ THỬ VÀ LOẠI: tự nhận ra "đang trên tấm in" bằng ĐỘ SÁNG (không mắt nào
        # thấy nền trắng sạch). KHÔNG DÙNG ĐƯỢC — đo trên robot 03/08 ngay tại ô
        # xuất phát, mắt sáng nhất chỉ đọc 683 nên nó tưởng đang trên tấm in và bật
        # cổng, rồi robot lao vào kệ. Cạnh C0R0 các mắt "trắng" cũng chỉ 260-463.
        # Ánh sáng trên sa bàn biến động quá lớn để đặt một ngưỡng sáng cố định.
        #
        # Tín hiệu CẤU TRÚC thì chắc: chỉ route khởi hành TỪ ĐIỂM CUỐI mới bắt đầu
        # trên tấm in, và route đó LUÔN mở đầu bằng lệnh LÙI (bộ tìm đường không có
        # cách nào khác để rút khỏi điểm cuối). execute_route() biết nên nó truyền
        # xuống, và chỉ cho chặng `forward` ĐẦU TIÊN.
        do_duoc = do_duoc and roi_diem_cuoi
        self._doc_xung()
        nhip_luc = time.time()   # lần cuối in nhịp tim (xem trong vòng lặp)
        # Quãng mà tín hiệu giao lộ HIỆN TẠI bắt đầu (None = đang trên nền sạch).
        # Dùng để bác tín hiệu ĐÃ CÓ SẴN từ trước khi cổng mở — xem trong vòng lặp.
        bat_dau_tin_hieu = None
        di_xung = 0

        while time.time() - start < timeout:
            if self._aborted():
                return False
            di_xung += self._doc_xung()
            di_cm = di_xung / config.ENCODER_PULSES_PER_CM if do_duoc else None
            # NHỊP TIM — xem robot đi được bao xa và thanh cảm biến đang thấy gì.
            # 04/08: bước này vượt C0R0 tận 22cm rồi mới dừng, mà log chỉ có ĐÚNG
            # MỘT dòng "Phát hiện giao lộ" với ADC [0,0,0,0,0,0] (gầm kệ). Không có
            # dòng "Bỏ qua tín hiệu giao lộ" nào — tức C0R0 không hề được đưa ra
            # xét. Phải thấy chuỗi ADC dọc đường mới biết nó bỏ sót ở đâu.
            if time.time() - nhip_luc >= config.ADVANCE_HEARTBEAT_TIME:
                nhip_luc = time.time()
                logger.info("Đếm giao lộ: %.2fs — đi %s, ADC %s",
                            time.time() - start,
                            "?" if di_cm is None else f"{di_cm:.1f}cm",
                            self._adc_de_ghi())
            at_intersection, values = self.follow_line(base_speed)

            # ⛔ TÍN HIỆU PHẢI XUẤT HIỆN MỚI, không được là cái đã có sẵn từ trước
            # khi cổng mở. Đo trên robot 07/08:
            #     8.5cm ADC [0,0,0,0,0,763]  → bác (mới đi 8.5, cần 10.0)
            #     8.8 → 9.1 → 9.3 → 9.6 → 9.8cm, ADC [0,0,0,0,0,0] → bác, bác, bác...
            #    10.0cm ADC [0,0,0,0,0,0]    → NHẬN
            # Cùng MỘT mảng đen liên tục, bị bác 6 lần rồi được nhận đúng khoảnh
            # khắc cổng hết hạn. Cổng quãng đường không PHÂN BIỆT gì — nó chỉ HOÃN,
            # và quyết định cuối cùng do đồng hồ chứ không do bằng chứng.
            # Giao lộ THẬT thì tín hiệu phải MỚI XUẤT HIỆN: robot đi trên nền trắng
            # rồi gặp vạch. Mảng in thì tín hiệu đã nằm sẵn dưới cảm biến từ đầu.
            if not at_intersection:
                bat_dau_tin_hieu = None          # rời khỏi vùng đen, chờ tín hiệu MỚI
            elif bat_dau_tin_hieu is None:
                bat_dau_tin_hieu = di_cm         # mốc tín hiệu này BẮT ĐẦU

            if at_intersection and di_cm is not None \
                    and bat_dau_tin_hieu is not None \
                    and di_cm >= config.FORWARD_MIN_TRAVEL_CM \
                    and bat_dau_tin_hieu < config.FORWARD_MIN_TRAVEL_CM:
                logger.info(
                    "Bỏ qua tín hiệu giao lộ ở %.2fs — đã đi %.1fcm (đủ cổng %.1f) "
                    "NHƯNG tín hiệu này bắt đầu từ %.1fcm, tức CÓ SẴN từ trước khi "
                    "cổng mở. Giao lộ thật phải XUẤT HIỆN MỚI trên nền sạch; đây là "
                    "mảng in đang nằm dưới cảm biến. ADC %s",
                    time.time() - start, di_cm, config.FORWARD_MIN_TRAVEL_CM,
                    bat_dau_tin_hieu, self._adc_de_ghi())
                self.forward(base_speed)
                time.sleep(0.01)
                continue

            if at_intersection and di_cm is not None \
                    and di_cm < config.FORWARD_MIN_TRAVEL_CM:
                logger.info(
                    "Bỏ qua tín hiệu giao lộ ở %.2fs — mới đi %.1fcm (cần %.1f). "
                    "Tấm in khu nhà máy nằm ngay dưới chân robot; hai hàng giao lộ "
                    "cách nhau ~40cm. ADC %s",
                    time.time() - start, di_cm, config.FORWARD_MIN_TRAVEL_CM,
                    self.read_line_sensor_adc())
                self.forward(base_speed)
                time.sleep(0.01)
                continue
            if at_intersection:
                # ĐẾM MẮT ĐEN ĐẬM — chỗ ĐẾM GIAO LỘ cuối cùng còn thiếu bộ lọc này.
                # Ngưỡng thích nghi co theo dải sáng-tối của từng lần đọc, nên một
                # VẠCH LINE THƯỜNG mà mắt rìa đọc 200-400 cũng thành "4 mắt = giao
                # lộ". Ba chỗ đếm khác đã lọc; chỗ này thì chưa, và nó là chỗ NGUY
                # HIỂM NHẤT: đếm thừa một giao lộ là robot dừng SỚM MỘT HÀNG và
                # giao hàng vào NHÀ MÁY BÊN CẠNH.
                # Đo trên robot 03/08: định giao foxconn (R0) thì thả ở amkor (R1),
                # rồi kiện sau lệch tiếp sang samsung. IR vẫn xác nhận đã thả,
                # packages_delivered vẫn cộng — MẤT SẠCH ĐIỂM MÀ KHÔNG BÁO LỖI.
                raw_gl = self.read_line_sensor_raw()
                if LineSensor.la_giao_lo_that(raw_gl):
                    return True
                # ⚠️ IN ĐÚNG HAI ĐIỀU KIỆN mà la_giao_lo_that() thật sự dùng.
                # Bản cũ in "tối nhất 0 (cần ≤61)" — số đó ĐẠT, nên đọc log thấy
                # như bị bác oan, trong khi lý do thật là thiếu MẮT ĐEN ĐẬM. Đo
                # 06/08: "3/4 mắt đen ĐẬM, tối nhất 0 (cần ≤61)" làm mất thời gian
                # đuổi nhầm. Điều kiện là ĐẾM mắt, không phải mắt tối nhất.
                _dam = LineSensor.dem_den_dam(raw_gl)
                _sau = sum(1 for v in raw_gl if v <= config.LINE_DEEP_BLACK)
                logger.info(
                    "Bỏ qua tín hiệu giao lộ ở %.2fs — %d/%d mắt đen ĐẬM%s, "
                    "%d/%d mắt đen SÂU%s. ADC %s. Vạch thường hoặc MẢNG IN, KHÔNG đếm.",
                    time.time() - start,
                    _dam, config.INTERSECTION_THRESHOLD,
                    " (THIẾU)" if _dam < config.INTERSECTION_THRESHOLD else " ✓",
                    _sau, config.LINE_DEEP_BLACK_COUNT,
                    " (THIẾU)" if _sau < config.LINE_DEEP_BLACK_COUNT else " ✓",
                    [int(round(v * 1023)) for v in raw_gl])
                # follow_line() vừa gọi stop() khi thấy giao lộ — phải ra lệnh chạy
                # lại, không thì vòng sau nó lại thấy, lại phanh, robot đứng im.
                self.forward(base_speed)
                time.sleep(0.01)
                continue

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
        """Quét tìm lại vạch bằng cách xoay tại chỗ, biên độ TĂNG DẦN hai bên.

        ⚠️ BẢN CŨ CHỈ TÌM ĐƯỢC VẠCH BÊN TRÁI. Nó quét ["left","right","left"] với
        CÙNG 0.5s mỗi lượt:
            lượt 1  trái 0.5s  →  đang ở −32°
            lượt 2  phải 0.5s  →  chỉ vừa đủ QUAY VỀ 0°, chưa hề sang phải
            lượt 3  trái 0.5s  →  lại về −32°
        Tức nó không bao giờ nhìn sang PHẢI của hướng ban đầu. Log trên robot
        06/08 xác nhận: MỌI lần thành công đều ghi "(quét left)", không lần nào
        "right".

        Đó là lý do chặng quay về ở hàng R4 hỏng 100%: quay đầu 180° là hai cú xoay
        liên tiếp, độ trượt ngang cộng dồn vượt nửa bề rộng thanh cảm biến (2.35cm);
        lệch sang trái thì quét cứu được, lệch sang phải thì chịu.

        Biên độ mới (0.5 → 1.0 → 1.5s) phủ cả hai bên: sau lượt 2 robot ở +32°,
        sau lượt 3 ở −32°. Thanh cảm biến cách trục 12cm nên quét ngang tới ~6cm
        mỗi bên — thừa cho độ lệch của hai cú xoay.
        """
        for direction, giay in (("left", 0.5), ("right", 1.0), ("left", 1.5)):
            if direction == "left":
                self.turn_left(config.SPEED_SLOW)
            else:
                self.turn_right(config.SPEED_SLOW)

            start = time.time()
            while time.time() - start < giay:
                values = self.read_line_sensor()
                if sum(values) > 0:
                    self.stop()
                    logger.info("Tìm lại line thành công (quét %s %.1fs)",
                                direction, time.time() - start)
                    return True
                time.sleep(0.01)

        self.stop()
        return False

    def _escape_intersection(self, speed: float = config.SPEED_DEFAULT,
                             reverse: bool = False) -> bool:
        """Rời khỏi giao lộ đang đứng, trước khi bám line tiếp.

        Chạy tới khi CẢM BIẾN không còn báo giao lộ nữa, chặn trên bằng thời gian —
        chứ không chạy mù một khoảng thời gian cố định.

        Bản cũ chạy mù đúng 0.3s, một con số viết cứng chưa ai đo. Đo trên bản in:
        vạch dọc C0 chỉ rộng 20mm theo hướng robot đi, ra khỏi tâm ±1.2cm là cảm
        biến trở lại bình thường. Mà ADVANCE_SPEED = 40 nằm không xa vùng chết (25%
        đứng hẳn, 32% mới bò được), nên 0.3s rất có thể chỉ đi được 1.5-2cm — đúng
        ngay ranh giới. Gặp thật ở smoke option 1: robot dừng tại C0R0, advance
        không thoát nổi và báo "gặp giao lộ".

        Bám theo tín hiệu thì đúng ở mọi tốc độ, không cần biết cm/s (thứ chưa đo).
        Trả True nếu đã thoát, False nếu hết chặn trên mà cảm biến vẫn báo giao lộ —
        khi đó nhiều khả năng robot nằm trên một mảng đen lớn, không phải giao lộ.
        """
        # ⛔ KHÔNG ĐỨNG TRÊN GIAO LỘ THÌ ĐỪNG THOÁT. "Thoát giao lộ" chỉ có nghĩa
        # khi đang đứng trên một cái; không thì đây là một cú CHẠY MÙ ~0.4s
        # (ESCAPE_MIN_TIME + ESCAPE_CLEAR_TIME) — và quãng của 0.4s phụ thuộc PIN.
        # Đo trên robot 04/08, route START → SHELF0: exit_start_zone bỏ robot lại
        # RẤT GẦN C0R0 mà chưa tới, rồi navigate_intersections mở đầu bằng escape,
        # log "Rời giao lộ sau 0.41s". Pin đầy thì 0.41s đi ~8cm — đủ để bước qua
        # hẳn C0R0. Sau đó bước đếm giao lộ chẳng còn gì để gặp nên chạy tiếp tới
        # KỆ, đọc gầm kệ (ADC [0,0,0,0,0,0]) thành giao lộ. Thước đo: bánh xe dừng
        # cách C0R0 25cm. Pin yếu hôm trước, cùng 0.41s chỉ đi ~5cm nên dừng lại
        # trước C0R0 và mọi thứ chạy đúng — đúng bài học cũ: HẰNG SỐ THỜI GIAN GẮN
        # VỚI VIÊN PIN LÚC ĐO NÓ.
        # Bỏ qua ở đây an toàn vì chặng nào thật sự cần escape đều đã có CỔNG QUÃNG
        # ĐƯỜNG (FORWARD_MIN_TRAVEL_CM) chặn việc đếm lại chính giao lộ vừa đứng.
        drive = self.backward if reverse else self.forward
        drive(speed)
        start = time.time()
        cap = getattr(config, "ESCAPE_MAX_TIME", 1.2)
        san = getattr(config, "ESCAPE_MIN_TIME", 0.15)
        can_sach = getattr(config, "ESCAPE_CLEAR_TIME", 0.25)
        # ⛔ SÀN VÀ TRẦN ĐO BẰNG QUÃNG ĐƯỜNG, KHÔNG BẰNG ĐỒNG HỒ.
        # Đây là gốc của cú đâm kệ ngày 04/08. Sàn thời gian ESCAPE_MIN_TIME +
        # ESCAPE_CLEAR_TIME ≈ 0.4s là một cú CHẠY MÙ, và quãng của 0.4s gắn với
        # VIÊN PIN: pin yếu đi ~5cm, pin đầy đi ~8cm. Route START → SHELF0 để robot
        # lại rất gần C0R0 mà chưa tới; 8cm là bước qua hẳn nó, bước đếm giao lộ
        # chẳng còn gì để gặp nên chạy thẳng tới KỆ.
        # Vá lần trước — "không đứng trên giao lộ thì đừng thoát" — SAI: robot vừa
        # xoay 90° TẠI giao lộ thì nhìn dọc nhánh mới, ngã tư đọc ra y hệt vạch
        # thẳng ([0,0,0,1,1,0]). Escape bị bỏ qua ở các chặng đó, follow_line nhận
        # lại chính giao lộ đang đứng, route lệch một hàng, robot quay đầu ở chỗ
        # logo. Không có phép thử cảm biến nào đúng được ngay sau khi xoay.
        # Chốt bằng quãng đường thì không cần phép thử nào: 3cm đủ ra khỏi vạch
        # rộng 2cm, và 3cm thì không bao giờ nhảy qua được một giao lộ.
        do_duoc = (config.ENCODER_PULSES_PER_CM > 0
                   and getattr(getattr(self, "_encoder_left", None),
                               "available", False)
                   and getattr(getattr(self, "_encoder_right", None),
                               "available", False))
        if do_duoc:
            self._doc_xung()
        xung = 0
        san_cm = config.ESCAPE_MIN_CM
        tran_cm = config.ESCAPE_MAX_CM
        sach_tu = None
        thoat = False
        while time.time() - start < cap:
            if self._aborted():
                return False
            if do_duoc:
                xung += self._doc_xung()
                di_cm = xung / config.ENCODER_PULSES_PER_CM
                if di_cm >= tran_cm:
                    self.stop()
                    logger.warning(
                        "Rời giao lộ: CHẠM TRẦN %.1fcm sau %.1fcm — dừng chứ không "
                        "đi thêm. Cảm biến %s. ⚠️ Nếu dòng này xuất hiện ở MỌI "
                        "chặng thì trần đang NHỎ HƠN quãng tối thiểu thuật toán "
                        "cần (sàn %.1fcm + %.2fs xác nhận sạch) — xem "
                        "config.ESCAPE_MAX_CM, không phải lỗi cảm biến.",
                        tran_cm, di_cm, self.read_line_sensor(),
                        san_cm, can_sach)
                    return False
            else:
                di_cm = None
            du_san = (di_cm >= san_cm) if di_cm is not None \
                else (time.time() - start >= san)
            values = self.read_line_sensor()
            if sum(values) < config.INTERSECTION_THRESHOLD and du_san:
                # Đòi sạch LIÊN TỤC một khoảng, không phải vài nhịp. 3 nhịp chỉ là
                # 30ms — ở 40% duty robot mới nhích ~0.5cm, tức vừa chớm ra khỏi mép
                # vạch chứ chưa qua hẳn, lắc nhẹ là cán lại vào và follow_line đọc ra
                # giao lộ. Trong lúc chờ đủ khoảng này robot VẪN CHẠY nên nó ra hẳn.
                if sach_tu is None:
                    sach_tu = time.time()
                elif time.time() - sach_tu >= can_sach:
                    thoat = True
                    break
            else:
                sach_tu = None
            time.sleep(0.01)
        self.stop()
        dt = time.time() - start
        if thoat:
            # Bình thường ~0.4s. Lâu hơn hẳn = cảm biến CHẬP CHỜN giữa "giao lộ" và
            # "sạch", phải chờ mãi mới đủ khoảng sạch liên tục — dấu hiệu robot đang
            # nằm ở MÉP một mảng đen chứ không phải đã ra hẳn.
            if dt > config.ESCAPE_CLEAR_TIME * 2 + config.ESCAPE_MIN_TIME:
                logger.warning("Rời giao lộ mất tới %.2fs (cảm biến %s) — chập chờn, "
                               "robot có thể đang ở MÉP mảng đen chứ chưa ra hẳn", dt, values)
            else:
                logger.info("Rời giao lộ sau %.2fs, %s (cảm biến %s)", dt,
                            "?" if di_cm is None else f"{di_cm:.1f}cm", values)
        else:
            logger.warning("Rời giao lộ: hết %.2fs mà cảm biến vẫn báo giao lộ — "
                           "robot có thể đang nằm trên mảng đen lớn, không phải vạch", dt)
        return thoat

    def navigate_intersections(self, count: int,
                               base_speed: float = config.SPEED_DEFAULT,
                               on_reached=None,
                               roi_diem_cuoi: bool = False,
                               bo_escape_dau: bool = False) -> bool:
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
            if bo_escape_dau and i == 0:
                # Vừa rời ô XUẤT PHÁT: robot chắc chắn KHÔNG đứng trên giao lộ, và
                # C0R0 chỉ cách vài cm. escape ở đây là một cú chạy thừa đủ để bước
                # QUA LUÔN C0R0 — sau đó chẳng còn gì để đếm nên robot chạy thẳng
                # tới KỆ. Đo 04/08: bánh dừng cách C0R0 25cm, thanh cảm biến chui
                # vào gầm kệ và đọc ADC [0,0,0,0,0,0] thành "giao lộ".
                logger.info("Bỏ bước thoát giao lộ: vừa rời ô xuất phát, robot "
                            "không đứng trên giao lộ nào và C0R0 chỉ cách vài cm")
            else:
                self._escape_intersection(base_speed)
            # ⛔ CỔNG QUÃNG ĐƯỜNG áp cho MỌI chặng, TRỪ chặng ĐẦU của route không
            # khởi hành từ điểm cuối.
            #   i > 0  → luôn bật. Hai giao lộ thật cách nhau ~40cm, mà
            #            _escape_intersection() có lúc CHẠM TRẦN mà chưa ra hẳn khỏi
            #            mảng đen — không có cổng thì chặng sau ĐẾM LẠI CHÍNH giao lộ
            #            vừa thoát. Đo trên robot 03/08: chặng 2/2 nhận giao lộ chỉ
            #            ~0.5s sau khi bắt đầu, robot rẽ phải ở C0R2 thay vì C0R4 rồi
            #            thả hàng giữa logo ROBOCON.
            #   i = 0  → chỉ bật khi vừa rời điểm cuối (còn trên tấm in). Route
            #            START → SHELF0 mở đầu bằng forward và exit_start_zone bỏ
            #            robot lại RẤT GẦN C0R0; bật cổng ở đó là bác giao lộ thật
            #            và LAO VÀO KỆ.
            # ⛔ CỔNG QUÃNG ĐƯỜNG PHẢI BẬT Ở MỌI CHẶNG, TRỪ ĐÚNG MỘT CA.
            # Bản cũ: (roi_diem_cuoi or i > 0) — tức chặng i = 0 của MỌI route KHÔNG
            # rời điểm cuối đều KHÔNG có chặn nào. Mà chặng đó chạy NGAY SAU MỘT CÚ
            # XOAY: robot đang đứng trên chính giao lộ vừa xoay, mảng đen của nó nằm
            # dưới cảm biến, và nó được ĐẾM LUÔN. Đếm thừa một cái là toàn bộ route
            # lệch MỘT HÀNG — robot xoay sớm một hàng và thả hàng ở vòng tròn logo
            # (R2). Đội báo đúng hai triệu chứng đó, lặp lại nhiều ngày.
            # Ngoại lệ chỉ đúng cho MỘT ca: route rời Ô XUẤT PHÁT, nơi C0R0 nằm rất
            # gần nên cổng 10cm sẽ bác giao lộ THẬT (xem bo_escape_dau). Ca đó đã có
            # cờ riêng do exit_start_zone dựng, không cần suy từ i.
            ap_cong = roi_diem_cuoi or i > 0 or not bo_escape_dau
            if not self.follow_line_until_intersection(
                    base_speed, roi_diem_cuoi=ap_cong):
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
        # Bắt đầu coi như ĐANG nằm trên vạch: lệnh ("forward", N) luôn khởi hành khi
        # robot đứng NGAY TRÊN giao lộ (vừa dừng ở giao lộ trước, hoặc vừa xoay tại
        # đó). Để False thì nhịp đọc đầu tiên thấy đủ mắt đen và đếm luôn CHÍNH cái
        # giao lộ đang đứng → mọi chặng dừng sớm một giao lộ. Nhánh dừng-từng-cái
        # tránh được nhờ _escape_intersection() chạy mù 0.3s trước mỗi chặng; ở đây
        # dùng cờ thay vì chạy mù để không mất đi cái lợi về thời gian, và cách này
        # đúng cho cả trường hợp KHÔNG đứng trên giao lộ (chặng đầu sau exit_start_zone:
        # ít mắt đen → cờ tự hạ ngay nhịp đầu).
        on_mark = True
        lost_since = None

        logger.info("Đi qua %d giao lộ (chạy liền, không dừng giữa chừng)", count)
        while time.time() - start < timeout:
            if self._aborted():
                return False

            raw = self.read_line_sensor_raw()
            values = LineSensor.digital_from_raw(raw)
            active = sum(values)

            # Cùng bộ lọc như follow_line_until_intersection: ngưỡng thích nghi
            # thổi vạch thường thành giao lộ, và đếm thừa ở đây cũng làm robot dừng
            # sớm một hàng rồi giao nhầm nhà máy. Chế độ này đang TẮT
            # (CONTINUOUS_INTERSECTIONS) nhưng bật lên là dính y hệt.
            if (active >= config.INTERSECTION_THRESHOLD
                    and LineSensor.la_giao_lo_that(raw)):
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
