#!/usr/bin/env python3
"""
Unit test cho LOGIC THUẦN của từng module — chạy trên PC, không cần GPIO/camera.

    python3 -m unittest tests.test_units -v

Khác `test_logic.py` (logic điều hướng + state machine) và `test_match_sim.py` (trọn
trận): file này khoá lại các hàm nhỏ mà SAI THÌ MẤT ĐIỂM NHƯNG KHÔNG BÁO LỖI:

  - Thời gian nâng/hạ từng càng (sai → càng lệch tầng, kẹp trượt pallet)
  - Xác nhận IR đã thả hàng    (sai → cộng điểm kiện chưa thả, hoặc bỏ kiện đã thả)
  - Quyết định nhận diện ORB   (sai → giao nhầm nhà máy)
  - Gộp kết quả classify_pair  (sai → cả 2 kiện đi nhầm)

Đây là nhóm hàm mà đo coverage cho thấy trước đây gần như không chạy dòng nào.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

# ⚠️ PHẢI đặt TRƯỚC khi import control.* — nếu không, chạy file này TRÊN PI sẽ điều
# khiển phần cứng THẬT. TestFollowLine gọi Motion.follow_line() để đọc ngược duty
# cycle 4 chân motor; chỉ cảm biến được giả lập, còn chân ra là PWMOutputDevice thật
# → BÁNH XE QUAY, và follow_line() không dừng motor nên nó quay tới tận cleanup().
# mockpwmpin là bắt buộc: MockPin thường không hỗ trợ PWM (PinPWMUnsupported).
# Dùng setdefault để test_motion.py / test_lift.py / tools.measure_pickup vẫn đặt đè
# được khi cần phần cứng thật.
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
os.environ.setdefault("GPIOZERO_MOCK_PIN_CLASS", "mockpwmpin")

import navigation
import config
from control.lift import MAX_LEVEL, Lift, PalletSensors
from control.motion import LineSensor, Motion
from tests.config_editor import save_config

try:
    import cv2 as _cv2
    import numpy as _np
except ImportError:
    _cv2 = _np = None


def _lift_stub() -> Lift:
    """Lift không đụng GPIO — chỉ dùng phần tính thời gian."""
    lift = object.__new__(Lift)
    lift._current_level = 0
    return lift


# ==========================================================
# 1. Thời gian nâng/hạ — mô hình bù theo VỊ TRÍ TUYỆT ĐỐI
# ==========================================================

class TestLiftTiming(unittest.TestCase):
    def setUp(self):
        self.lift = _lift_stub()

    def test_floor_is_zero(self):
        self.assertEqual(self.lift._time_for_level(0), 0.0)
        for side in ("left", "right"):
            for raising in (True, False):
                self.assertEqual(self.lift._level_time(0, side, raising), 0.0,
                                 "sàn luôn là mốc 0, không cộng bù")

    def test_unknown_level_falls_back_to_tier1(self):
        self.assertEqual(self.lift._time_for_level(99), config.LIFT_TIME_SHELF_1)

    def test_compensation_applied_to_absolute_mark(self):
        left = self.lift._level_time(1, "left", raising=True)
        self.assertAlmostEqual(left, config.LIFT_TIME_SHELF_1 + config.LIFT_LEFT_EXTRA)
        right = self.lift._level_time(1, "right", raising=True)
        self.assertAlmostEqual(right, config.LIFT_TIME_SHELF_1 + config.LIFT_RIGHT_EXTRA)

    def test_lowering_uses_its_own_compensation(self):
        up = self.lift._level_time(1, "left", raising=True)
        down = self.lift._level_time(1, "left", raising=False)
        self.assertNotEqual(up, down, "bù khi nâng và khi hạ là 2 hệ số khác nhau")
        self.assertAlmostEqual(down, config.LIFT_TIME_SHELF_1 + config.LIFT_LEFT_LOWER_EXTRA)

    def test_never_negative(self):
        saved = config.LIFT_LEFT_EXTRA
        try:
            config.LIFT_LEFT_EXTRA = -999.0
            self.assertEqual(self.lift._level_time(1, "left", raising=True), 0.0)
        finally:
            config.LIFT_LEFT_EXTRA = saved

    def test_compensation_not_double_counted(self):
        """REGRESSION: đi 0→1→2 phải bằng đi thẳng 0→2.

        Code cũ cộng phần bù vào TỪNG lần chạy nên 0→1→2 bị cộng bù 2 lần, càng lên
        thiếu hẳn một đoạn ở tầng 2.
        """
        for side in ("left", "right"):
            step = (self.lift._move_duration(side, 0, 1, raising=True)
                    + self.lift._move_duration(side, 1, 2, raising=True))
            direct = self.lift._move_duration(side, 0, 2, raising=True)
            self.assertAlmostEqual(step, direct, places=6,
                                   msg=f"{side}: bù bị cộng dồn khi đi qua tầng 1")

    def test_raise_after_drop_matches_pickup_raise(self):
        """REGRESSION: nâng lại càng sau khi thả phải bằng đúng lúc nâng lên tầng đó.

        Code cũ dùng _time_for_level() thô cho càng lẻ (bỏ qua bù) → càng trái chạy
        dư 0.45s, cao hơn hẳn càng phải sau mỗi lần thả.
        """
        for level in (1, 2):
            for side in ("left", "right"):
                pickup = self.lift._move_duration(side, 0, level, raising=True)
                after_drop = self.lift._move_duration(side, 0, level, raising=True)
                self.assertAlmostEqual(pickup, after_drop)
                # Bù có thể ĐÚNG BẰNG 0 sau khi calibrate — nghĩa là càng đó không
                # cần bù, hoàn toàn hợp lệ. Bản cũ khẳng định "đã bù thì phải KHÁC
                # thời gian thô" nên báo đỏ ngay khi ai đó chỉnh bù về 0, dù không
                # có gì sai. Thứ cần canh là thao tác càng lẻ có ĐI QUA đường bù
                # hay không, chứ không phải bù có khác 0 hay không.
                extra = (config.LIFT_LEFT_EXTRA if side == "left"
                         else config.LIFT_RIGHT_EXTRA)
                raw = self.lift._time_for_level(level)
                if abs(extra) > 1e-9:
                    self.assertNotAlmostEqual(
                        pickup, raw,
                        msg=f"{side} tầng {level}: bù={extra:+.3f} mà vẫn ra thời gian thô "
                            "— càng lẻ đang bỏ qua đường bù (đúng lỗi cũ)")
                else:
                    self.assertAlmostEqual(
                        pickup, raw, places=6,
                        msg=f"{side} tầng {level}: bù=0 thì phải bằng đúng thời gian thô")

    def test_move_duration_is_symmetric(self):
        for side in ("left", "right"):
            up = self.lift._move_duration(side, 0, 2, raising=True)
            down = self.lift._move_duration(side, 2, 0, raising=True)
            self.assertAlmostEqual(up, down, msg="hiệu 2 mốc nên đối xứng")


# ==========================================================
# 2. Cảm biến IR pallet — quyết định CỘNG ĐIỂM hay không
# ==========================================================

class TestHomeDuration(unittest.TestCase):
    """LIFT_HOME_DURATION phải đủ để hạ từ tầng cao nhất — kể cả phần bù HẠ.

    Càng không có limit switch: home là cách DUY NHẤT chuẩn lại mốc 0, và không có
    tín hiệu nào báo "đã chạm đáy". Hạ thiếu thì `_current_level` khai SÀN trong khi
    càng còn treo → mọi phép tính tầng sau đó lệch, không báo lỗi gì.

    Trước đây test tay + CLAUDE.md so với `LIFT_TIME_SHELF_2` suông. Sai: hạ còn
    cộng `LIFT_*_LOWER_EXTRA`, mà bù 2 càng khác nhau. Với số hiện tại càng trái
    cần 4.2s trong khi LIFT_TIME_SHELF_2 chỉ 3.9s → so với 3.9s thấy "đạt" mà vẫn hở.
    """

    def setUp(self):
        self.lift = _lift_stub()

    def test_covers_slowest_fork_lowering_from_top(self):
        need = self.lift.min_home_duration()
        for side in ("left", "right"):
            self.assertLessEqual(
                self.lift._move_duration(side, MAX_LEVEL, 0, raising=False),
                need + 1e-9,
                f"min_home_duration() không đủ cho càng {side}")

    def test_stricter_than_shelf2_alone(self):
        """Ngưỡng đúng phải ≥ LIFT_TIME_SHELF_2 — nếu bù hạ dương thì lớn hơn hẳn."""
        self.assertGreaterEqual(self.lift.min_home_duration(), config.LIFT_TIME_SHELF_2)
        with patch.object(config, "LIFT_LEFT_LOWER_EXTRA", 0.9):
            self.assertAlmostEqual(self.lift.min_home_duration(),
                                   config.LIFT_TIME_SHELF_2 + 0.9)

    def test_config_value_is_enough(self):
        """config.py hiện tại phải ĐẠT — chốt lại giá trị thật, không chỉ công thức."""
        need = self.lift.min_home_duration()
        self.assertGreaterEqual(
            config.LIFT_HOME_DURATION, need,
            f"LIFT_HOME_DURATION={config.LIFT_HOME_DURATION} < {need} cần để hạ hết cỡ")

    def test_home_from_known_level_is_much_shorter(self):
        """Biết chắc đang ở tầng nào thì home không cần chạy theo tầng CAO NHẤT.

        Motor cẩu là DigitalOutputDevice nên ghì ở 100% duty; hạ từ tầng 1 chỉ cần
        ~0.9s mà home mặc định chạy 4.0s → hơn 3 giây ghì vào đáy cơ khí mỗi lần,
        bào mòn dây curoa. Menu test_lift home lại sau MỖI option nên nó cộng dồn rất
        nhanh.
        """
        lift = _lift_stub()
        q0, q1, q2 = (lift.home_from(l) for l in (0, 1, 2))
        self.assertLess(q0, q1, "ở sàn phải nhanh hơn ở tầng 1")
        self.assertLess(q1, q2, "tầng 1 phải nhanh hơn tầng 2")
        self.assertLess(q1, config.LIFT_HOME_DURATION * 0.6,
                        "home từ tầng 1 phải rút được đáng kể, không thì vô nghĩa")

    def test_home_from_never_exceeds_full_home(self):
        """Chặn trần: nhân biên vào trường hợp xấu nhất sẽ ra DÀI HƠN bản đầy đủ.

        1.6 × 4.0 = 6.4s — vô nghĩa, vì bản đầy đủ vốn đã đủ chạm đáy từ mọi tầng.
        """
        lift = _lift_stub()
        cap = max(config.LIFT_HOME_DURATION, lift.min_home_duration())
        for level in (0, 1, MAX_LEVEL):
            self.assertLessEqual(lift.home_from(level), cap + 1e-9,
                                 f"tầng {level}: rút gọn dài hơn cả bản đầy đủ")

    def test_home_from_has_a_floor(self):
        """Ngay cả khi TIN là đang ở sàn vẫn phải chạy một chút — `_current_level`
        có thể lệch nhẹ, và chạy 0 giây thì home mất hết ý nghĩa."""
        lift = _lift_stub()
        self.assertGreaterEqual(lift.home_from(0), config.LIFT_HOME_MIN_DURATION - 1e-9)

    def test_from_level_bypasses_the_worst_case_clamp(self):
        """Nhánh rút gọn KHÔNG được bị phép kẹp theo tầng cao nhất kéo ngược lên.

        Phép kẹp đó sinh ra cho nhánh KHÔNG biết vị trí; áp cho nhánh biết vị trí thì
        rút gọn thành vô tác dụng.
        """
        lift = _lift_stub()
        for name in ("_left_en", "_left_up", "_left_down", "_right_up", "_right_down"):
            setattr(lift, name, MagicMock())
        with patch("time.sleep") as slept:
            lift.home_to_floor(from_level=1)
        self.assertAlmostEqual(slept.call_args[0][0], lift.home_from(1), places=6)
        self.assertLess(slept.call_args[0][0], lift.min_home_duration(),
                        "tiền đề: rút gọn phải NGẮN HƠN ngưỡng worst-case")

    def test_home_clamps_up_when_config_too_small(self):
        """Config thiếu thì home_to_floor() phải tự chạy ĐỦ, không hạ thiếu âm thầm."""
        lift = _lift_stub()
        for name in ("_left_en", "_left_up", "_left_down", "_right_up", "_right_down"):
            setattr(lift, name, MagicMock())
        need = lift.min_home_duration()
        with patch.object(config, "LIFT_HOME_DURATION", need - 1.0), \
             patch("control.lift.time.sleep") as slept:
            lift.home_to_floor()
        self.assertAlmostEqual(slept.call_args[0][0], need)
        self.assertEqual(lift._current_level, 0)


class TestSaveConfig(unittest.TestCase):
    """`save_config` phải BÁO khi không khớp, không im lặng không làm gì.

    Đây là hàm mà menu calibrate của test_motion/test_lift dùng để ghi config.py.
    Bản cũ (một bản trong mỗi file) gọi `re.sub` rồi ghi lại luôn: đổi tên hằng số
    hay viết giá trị bằng biểu thức là gõ `t1+`/`c+` mãi mà số không đổi, không lỗi.
    """

    def _tmp(self, text: str) -> str:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".py")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.unlink, path)
        return path

    def test_writes_value_and_keeps_comment(self):
        path = self._tmp("A = 1\nTURN_TIME = 0.5   # chú thích\nB = 2\n")
        self.assertTrue(save_config("TURN_TIME", 0.62, path))
        self.assertIn("TURN_TIME = 0.620   # chú thích", open(path).read())

    def test_handles_negative_values(self):
        path = self._tmp("LIFT_LEFT_EXTRA = -0.450\n")
        self.assertTrue(save_config("LIFT_LEFT_EXTRA", -0.5, path))
        self.assertIn("LIFT_LEFT_EXTRA = -0.500", open(path).read())

    def test_refuses_when_key_absent(self):
        path = self._tmp("A = 1\n")
        before = open(path).read()
        self.assertFalse(save_config("KHONG_CO", 1.0, path))
        self.assertEqual(open(path).read(), before, "không khớp thì KHÔNG được ghi")

    def test_refuses_when_key_duplicated(self):
        """2 chỗ khai cùng tên → không biết sửa chỗ nào, phải từ chối."""
        path = self._tmp("X = 1.0\nX = 2.0\n")
        before = open(path).read()
        self.assertFalse(save_config("X", 3.0, path))
        self.assertEqual(open(path).read(), before)

    def test_does_not_match_prefix_of_longer_name(self):
        path = self._tmp("LIFT_TIME_SHELF_1_BIS = 9.0\nLIFT_TIME_SHELF_1 = 1.2\n")
        self.assertTrue(save_config("LIFT_TIME_SHELF_1", 1.5, path))
        text = open(path).read()
        self.assertIn("LIFT_TIME_SHELF_1_BIS = 9.0", text)
        self.assertIn("LIFT_TIME_SHELF_1 = 1.500", text)

    def test_every_key_the_calibrate_menus_write_exists_in_config(self):
        """Mọi hằng số 2 menu calibrate ghi phải khớp ĐÚNG 1 chỗ trong config.py thật."""
        import re
        keys = set()
        for f in ("tests/test_lift.py", "tests/test_motion.py"):
            src = open(os.path.join(ROOT, f), encoding="utf-8").read()
            keys |= set(re.findall(r'save_config\(\s*"([A-Z_0-9]+)"', src))
            keys |= set(re.findall(r'"([A-Z_0-9]+)",\s*[+-]?step_', src))
        self.assertTrue(keys, "không tìm thấy hằng số nào — regex của test đã lạc hậu")
        cfg = open(os.path.join(ROOT, "config.py"), encoding="utf-8").read()
        for key in sorted(keys):
            with self.subTest(key=key):
                n = len(re.findall(rf"^{re.escape(key)}\s*=\s*[\d.+-]+", cfg, re.M))
                self.assertEqual(n, 1, f"{key} khớp {n} chỗ trong config.py (cần 1)")


class TestPalletSensors(unittest.TestCase):
    def _sensors(self, left_raw, right_raw, read_ok=True, available=True):
        bus = MagicMock()
        bus.available = available
        bus.last_read_ok = read_ok
        bus.read_many.return_value = [left_raw, right_raw]
        s = object.__new__(PalletSensors)
        s._bus = bus
        s.available = available
        return s

    def test_threshold(self):
        s = self._sensors(0, 0)
        below = (config.PALLET_THRESHOLD - 10) / 1023.0
        above = (config.PALLET_THRESHOLD + 10) / 1023.0
        self.assertTrue(s._is_pallet(below), "ADC thấp = có pallet")
        self.assertFalse(s._is_pallet(above))

    def test_reads_both_sides(self):
        low, high = 0.1, 0.9
        self.assertEqual(self._sensors(low, high).read_status(), (True, False, True))
        self.assertEqual(self._sensors(high, low).read_status(), (False, True, True))
        self.assertEqual(self._sensors(low, low).read_status(), (True, True, True))

    def test_read_error_reports_not_ok(self):
        left, right, ok = self._sensors(0.1, 0.1, read_ok=False).read_status()
        self.assertFalse(ok)
        self.assertFalse(left)
        self.assertFalse(right)

    def test_bus_unavailable_reports_not_ok(self):
        self.assertEqual(self._sensors(0.1, 0.1, available=False).read_status(),
                         (False, False, False))

    def test_helpers_return_none_on_error(self):
        """Đọc lỗi phải trả None, KHÔNG được trả False — False nghĩa là 'chắc chắn
        không có pallet', dùng nhầm sẽ báo thả hàng thành công khi thực ra không biết."""
        s = self._sensors(0.1, 0.1, read_ok=False)
        for fn in (s.has_left, s.has_right, s.has_any, s.has_both):
            self.assertIsNone(fn(), f"{fn.__name__} phải trả None khi đọc lỗi")

    def test_helpers_normal(self):
        s = self._sensors(0.1, 0.9)      # trái CÓ, phải KHÔNG
        self.assertTrue(s.has_left())
        self.assertFalse(s.has_right())
        self.assertTrue(s.has_any())
        self.assertFalse(s.has_both())
        self.assertEqual(s.status(), (True, False))


class TestVerifyReleased(unittest.TestCase):
    """_verify_released quyết định packages_delivered có tăng không = ĐIỂM SỐ."""

    def _lift(self, left, right, ok=True):
        lift = _lift_stub()
        lift.pallet = MagicMock()
        lift.pallet.read_status.return_value = (left, right, ok)
        lift.pallet.has_left.return_value = left if ok else None
        lift.pallet.has_right.return_value = right if ok else None
        return lift

    def test_both_released(self):
        self.assertTrue(self._lift(False, False)._verify_released())

    def test_one_still_on_fork_is_failure(self):
        self.assertFalse(self._lift(True, False)._verify_released())
        self.assertFalse(self._lift(False, True)._verify_released())

    def test_read_error_is_not_success(self):
        """SPI lỗi → KHÔNG được coi là đã thả (sẽ cộng điểm ảo)."""
        self.assertFalse(self._lift(False, False, ok=False)._verify_released())

    def test_single_side(self):
        self.assertTrue(self._lift(False, True)._verify_released("left"))
        self.assertFalse(self._lift(True, False)._verify_released("left"))
        self.assertTrue(self._lift(True, False)._verify_released("right"))
        self.assertFalse(self._lift(False, True)._verify_released("right"))

    def test_single_side_read_error(self):
        self.assertFalse(self._lift(False, False, ok=False)._verify_released("left"))
        self.assertFalse(self._lift(False, False, ok=False)._verify_released("right"))


# ==========================================================
# 3. Quyết định nhận diện ORB
# ==========================================================

class TestShapeMatcherDecision(unittest.TestCase):
    """classify() cần CẢ 2: vượt ngưỡng tuyệt đối VÀ cách biệt rõ với kiện thứ nhì."""

    def _matcher(self, scores):
        from vision.shape_match import ShapeMatcher
        m = object.__new__(ShapeMatcher)
        m._orb = MagicMock()
        m._matcher = MagicMock()
        m._sets = {None: {k: (MagicMock(), MagicMock()) for k in scores}}
        m._orb.detectAndCompute.return_value = ([MagicMock()] * 20, MagicMock())
        m._good_matches = lambda *a: []
        m._inlier_count = lambda kp, tkp, good: 0
        self._scores = scores
        return m

    def _classify(self, scores):
        from vision import shape_match
        m = self._matcher(scores)
        order = list(scores)
        it = iter(order)
        # trả điểm theo đúng thứ tự template được duyệt
        m._inlier_count = lambda kp, tkp, good, _it=it: scores[next(_it)]
        with patch.object(shape_match.cv2, "cvtColor", lambda *a, **k: MagicMock()):
            return m.classify(MagicMock())

    @unittest.skipIf(_cv2 is None, "cần cv2")
    def test_clear_winner_accepted(self):
        from vision.shape_match import MIN_INLIERS, MARGIN_RATIO
        scores = {"samsung": MIN_INLIERS + 5, "foxconn": 1, "amkor": 0, "hana_micron": 0}
        label, n = self._classify(scores)
        self.assertEqual(label, "samsung")
        self.assertEqual(n, MIN_INLIERS + 5)

    @unittest.skipIf(_cv2 is None, "cần cv2")
    def test_below_absolute_threshold_rejected(self):
        from vision.shape_match import MIN_INLIERS
        scores = {"samsung": MIN_INLIERS - 1, "foxconn": 0, "amkor": 0, "hana_micron": 0}
        label, _ = self._classify(scores)
        self.assertIsNone(label, "chưa đủ inlier tuyệt đối thì không được nhận")

    @unittest.skipIf(_cv2 is None, "cần cv2")
    def test_close_second_rejected(self):
        """Đủ inlier nhưng kiện thứ nhì bám sát → bệ trống/nền, không phải kiện thật."""
        from vision.shape_match import MIN_INLIERS
        scores = {"samsung": MIN_INLIERS + 2, "foxconn": MIN_INLIERS + 1,
                  "amkor": 0, "hana_micron": 0}
        label, _ = self._classify(scores)
        self.assertIsNone(label)

    def test_not_ready_returns_none(self):
        from vision.shape_match import ShapeMatcher
        m = object.__new__(ShapeMatcher)
        m._orb = None
        m._sets = {}
        self.assertEqual(m.classify(MagicMock()), (None, 0))

    def test_unverified_matches_never_count_as_inliers(self):
        """Dưới MIN_MATCHES_FOR_HOMOGRAPHY thì KHÔNG chạy được RANSAC → phải trả 0.

        MIN_INLIERS đã hạ xuống 6 còn MIN_MATCHES_FOR_HOMOGRAPHY vẫn 8, nên cửa sổ
        6-7 match từng lọt thẳng qua ngưỡng mà chưa hề được kiểm nhất quán hình học.
        """
        from vision.shape_match import (ShapeMatcher, MIN_INLIERS,
                                        MIN_MATCHES_FOR_HOMOGRAPHY)
        m = object.__new__(ShapeMatcher)
        for n in range(MIN_MATCHES_FOR_HOMOGRAPHY):
            with self.subTest(matches=n):
                self.assertEqual(m._inlier_count(None, None, [MagicMock()] * n), 0)
        # tiền đề của test: cửa sổ nguy hiểm thật sự tồn tại
        self.assertLess(MIN_INLIERS, MIN_MATCHES_FOR_HOMOGRAPHY,
                        "hai hằng số đã nhất quán thì test này hết ý nghĩa")

    def test_single_template_is_not_ready(self):
        """1 ảnh mẫu → second_score luôn 0 → kiểm cách biệt vô hiệu → MỌI kiện đều
        bị gán đúng cái nhãn đó và robot chở tất cả về một nhà máy."""
        from vision.shape_match import ShapeMatcher
        m = object.__new__(ShapeMatcher)
        m._orb = MagicMock()
        m._sets = {None: {"samsung": (MagicMock(), MagicMock())}}
        self.assertFalse(m.ready, "1 ảnh mẫu thì phải rơi hẳn về HSV")
        m._sets[None]["foxconn"] = (MagicMock(), MagicMock())
        self.assertTrue(m.ready)

    @unittest.skipIf(_cv2 is None or _np is None, "cần cv2 + numpy")
    def test_templates_normalised_to_same_size_within_a_set(self):
        """Ảnh mẫu trong CÙNG một bộ phải được cắt về cùng kích thước trước khi so.

        Bốn tấm của cùng một ô đều chứa cùng phần pallet + khung kệ ở nền, mà nền đó
        có trong MỌI vùng quét. Tấm nào cắt rộng hơn thì ăn thêm inlier miễn phí từ
        nền — tấm cắt SẠCH nhất lại thiệt nhất. Đo thật ở t2_left: samsung (296px)
        thua sát nút amkor (395px) ngay trên ô đang đặt samsung; cắt về cùng cỡ thì
        t2_right nhảy từ cách biệt 1.2x lên 9.0x.
        """
        import tempfile
        from vision.shape_match import ShapeMatcher
        m = object.__new__(ShapeMatcher)
        m._orb = _cv2.ORB_create(nfeatures=200)

        # 4 ảnh mẫu giả, kích thước lệch nhau, đủ hoạ tiết để ORB tìm được keypoint
        rng = _np.random.default_rng(0)
        sizes = {"samsung": (100, 120), "foxconn": (140, 180),
                 "amkor": (130, 160), "hana_micron": (150, 200)}
        with tempfile.TemporaryDirectory() as d:
            for label, (h, w) in sizes.items():
                img = rng.integers(0, 255, size=(h, w), dtype=_np.uint8)
                _cv2.imwrite(os.path.join(d, f"{label}.png"), img)
            loaded = m._load_dir(d, "test")

        self.assertEqual(len(loaded), 4, "phải nạp đủ 4 ảnh mẫu")
        # _load_dir trả (kp, des); kiểm gián tiếp qua toạ độ keypoint không vượt cỡ nhỏ nhất
        hmin = min(h for h, _w in sizes.values())
        wmin = min(w for _h, w in sizes.values())
        for label, (kp, _des) in loaded.items():
            for point in kp:
                self.assertLessEqual(point.pt[0], wmin,
                                     f"{label}: keypoint nằm ngoài bề rộng đã chuẩn hoá")
                self.assertLessEqual(point.pt[1], hmin,
                                     f"{label}: keypoint nằm ngoài chiều cao đã chuẩn hoá")

    def test_variant_set_chosen_by_tier_and_side(self):
        """classify() phải dùng ĐÚNG bộ ảnh mẫu của (tầng, ô) đang quét.

        Đo trên robot: khớp đúng tổ hợp được 65-172 inlier, khớp lệch tổ hợp chỉ
        0-6. Nếu `level`/`side` bị đánh rơi ở đâu đó trên đường
        classify_pair → _classify_by_shape → ShapeMatcher.classify thì mọi ô đều
        dùng chung một bộ và ta quay lại đúng mức 0-6 inlier đó.
        """
        from vision.shape_match import ShapeMatcher
        m = object.__new__(ShapeMatcher)
        m._orb = MagicMock()
        flat = {"a": (MagicMock(), MagicMock()), "b": (MagicMock(), MagicMock())}
        t2l = {"c": (MagicMock(), MagicMock()), "d": (MagicMock(), MagicMock())}
        m._sets = {None: flat, (2, "left"): t2l}

        self.assertIs(m.templates_for(2, "left"), t2l, "phải lấy bộ của tổ hợp")
        self.assertIs(m.templates_for(2, "right"), flat, "thiếu biến thể → bộ phẳng")
        self.assertIs(m.templates_for(1, "left"), flat, "sai tầng → bộ phẳng")
        self.assertIs(m.templates_for(), flat, "không truyền gì → bộ phẳng")

    def test_incomplete_variant_falls_back_to_flat(self):
        """Bộ biến thể chỉ có 1 ảnh mẫu thì KHÔNG được dùng.

        1 ảnh mẫu làm phép kiểm cách biệt vô hiệu (second_score luôn 0) — mọi kiện
        đều bị gán đúng nhãn đó. Thà rơi về bộ phẳng còn hơn.
        """
        from vision.shape_match import ShapeMatcher
        m = object.__new__(ShapeMatcher)
        m._orb = MagicMock()
        flat = {"a": (MagicMock(), MagicMock()), "b": (MagicMock(), MagicMock())}
        m._sets = {None: flat, (1, "right"): {"a": (MagicMock(), MagicMock())}}
        self.assertIs(m.templates_for(1, "right"), flat)

    def test_inliers_to_confidence_is_bounded(self):
        from vision.shape_match import inliers_to_confidence, CONFIDENCE_NORM
        self.assertEqual(inliers_to_confidence(0), 0.0)
        self.assertEqual(inliers_to_confidence(int(CONFIDENCE_NORM) * 10), 1.0)
        self.assertTrue(0 < inliers_to_confidence(int(CONFIDENCE_NORM // 2)) < 1)


# ==========================================================
# 4. Gộp kết quả 2 kiện — classify_pair
# ==========================================================

@unittest.skipIf(_cv2 is None or _np is None, "cần cv2 + numpy")
class TestClassifyPair(unittest.TestCase):
    def _vision(self, frames_results):
        """frames_results: list [(trái, phải)] cho từng lần chụp.
        mỗi phần tử = (label, confidence, from_orb)."""
        from vision.vision import Vision
        v = object.__new__(Vision)
        v._camera = MagicMock()
        v._shape_matcher = MagicMock(ready=True)
        v._capture_frame = lambda: _np.zeros((40, 40, 3), dtype=_np.uint8)
        seq = iter(frames_results)
        state = {"pair": None, "which": 0}

        def fake_classify(frame, level=None, side=None):
            # `level` = tầng (chọn vùng quét, config.ROI_Y_CENTER) và `side` = ô
            # trái/phải (chọn bộ ảnh mẫu ORB). classify_pair() truyền cả hai xuống.
            # Stub bỏ qua giá trị nhưng PHẢI nhận đủ, không thì test che mất chữ ký thật.
            if state["which"] % 2 == 0:
                state["pair"] = next(seq)
            res = state["pair"][state["which"] % 2]
            state["which"] += 1
            return res
        v._classify_frame = fake_classify
        return v

    def test_both_confident_first_try(self):
        v = self._vision([(("samsung", 0.9, True), ("foxconn", 0.9, True))])
        self.assertEqual(v.classify_pair(), ("samsung", "foxconn"))

    def test_orb_bypasses_confidence_threshold(self):
        """ORB tự quyết định đủ tự tin → không so với CONFIDENCE_THRESHOLD nữa
        (ngưỡng đó là thang % pixel của HSV, không phải thang ORB)."""
        low = config.CONFIDENCE_THRESHOLD / 2
        v = self._vision([(("samsung", low, True), ("foxconn", low, True))])
        self.assertEqual(v.classify_pair(), ("samsung", "foxconn"))

    def test_low_confidence_hsv_is_rejected(self):
        low = config.CONFIDENCE_THRESHOLD / 2
        attempts = [(("samsung", low, False), ("foxconn", low, False))] * 5
        v = self._vision(attempts)
        self.assertEqual(v.classify_pair(), (None, None))

    def test_one_side_recovers_on_retry(self):
        low = config.CONFIDENCE_THRESHOLD / 2
        attempts = [
            (("samsung", 0.9, True), ("foxconn", low, False)),   # phải chưa chắc
            (("samsung", 0.9, True), ("foxconn", 0.95, True)),   # lần 2 chắc
        ] * 3
        v = self._vision(attempts)
        self.assertEqual(v.classify_pair(), ("samsung", "foxconn"))

    def test_confident_orb_survives_a_higher_scoring_hsv_retry(self):
        """conf của ORB (inlier/40) và của HSV (tỉ lệ pixel) là HAI THANG khác nhau.

        Lỗi cũ: so confidence TRẦN nên một kết quả ORB ĐÃ chắc chắn bị lần quét sau
        ghi đè bằng kết quả HSV mơ hồ nhưng số cao hơn → trả None và bỏ cả tầng kệ.
        Quy tắc đúng là so theo (đã_đủ_tự_tin, confidence).

        ⚠️ Số ở đây suy theo TỈ LỆ của CONFIDENCE_THRESHOLD, không viết cứng. Cả hai
        cách viết cứng đều đã gãy một lần:
          - suy theo hiệu số (bản đầu): hạ ngưỡng 0.20 → 0.12 là tiền đề tự gãy
          - viết cứng 0.10 (bản sau)  : hạ ngưỡng 0.12 → 0.08 thì 0.10 KHÔNG còn
            nhỏ hơn ngưỡng, tiền đề lại gãy — chính là lần này
        Nhân tỉ lệ thì hai bất biến (hsv > orb, hsv < ngưỡng) đúng với MỌI ngưỡng
        dương, nên test chỉ đỏ khi LOGIC SO SÁNH sai, đúng việc nó sinh ra để làm.

        Lần này lọt vì máy dev KHÔNG có cv2 nên test bị skip ở đó; chỉ phantom mới
        chạy thật. Bộ test trên máy dev không phải là bằng chứng đủ.
        """
        t = config.CONFIDENCE_THRESHOLD
        orb_conf, hsv_conf = t * 0.4, t * 0.8   # HSV cao hơn nhưng KHÔNG đạt ngưỡng
        self.assertGreater(hsv_conf, orb_conf, "tiền đề của test")
        self.assertLess(hsv_conf, config.CONFIDENCE_THRESHOLD,
                        "tiền đề: HSV phải CHƯA đạt ngưỡng")
        attempts = [
            (("foxconn", orb_conf, True), ("amkor", 0.05, False)),   # trái: ORB chắc
            (("samsung", hsv_conf, False), ("amkor", 0.05, False)),  # trái: HSV mơ hồ
        ] * 3
        left, _right = self._vision(attempts).classify_pair()
        self.assertEqual(left, "foxconn")

    def test_no_camera_returns_none(self):
        from vision.vision import Vision
        v = object.__new__(Vision)
        v._camera = None
        self.assertEqual(v.classify_pair(), (None, None))

    def test_pair_rois_are_what_classify_pair_actually_reads(self):
        """Công cụ calibrate/chẩn đoán phải soi ĐÚNG 2 vùng này.

        Cắt ROI trên NGUYÊN khung ra một vùng khác hẳn — phủ lên khe giữa 2 kiện,
        chỗ robot không bao giờ nhìn tới. Calibrate ở đó = chốt màu của cái nền.
        """
        from vision.vision import Vision
        v = object.__new__(Vision)
        frame = _np.zeros((480, 640, 3), dtype=_np.uint8)

        left, right = v.pair_rois(frame)
        half_w = 640 // 2
        want_w = half_w - 2 * int(half_w * config.ROI_MARGIN)
        self.assertEqual(left.shape[1], want_w)
        self.assertEqual(right.shape[1], want_w)

        # ...và phải KHÁC hẳn ROI cắt trên nguyên khung
        full = v._crop_roi(frame)
        self.assertGreater(full.shape[1], left.shape[1] * 1.5,
                           "ROI nguyên khung rộng hơn hẳn — không thể thay thế nhau")

    def test_tier_roi_windows_do_not_overlap(self):
        """Vùng quét 2 tầng phải TÁCH HẲN nhau.

        Camera gắn cố định vào thân robot nên tầng 1 và tầng 2 nằm ở 2 độ cao khác
        nhau trong khung. Kệ lúc thi đấu có hàng ở CẢ HAI tầng, nên nếu 2 vùng này
        chồng lấn thì ROI ôm 2 loại kiện cùng lúc → HSV trộn màu 2 kiện, ORB so một
        vùng 2 decal với ảnh mẫu 1 decal. Đây là lỗi ĐÃ GẶP THẬT: ROI cắt giữa cố
        định (y 96..384) vắt ngang cả 2 tầng, nhận diện không bao giờ đúng.
        """
        from vision.vision import Vision
        v = object.__new__(Vision)
        frame = _np.zeros((480, 640, 3), dtype=_np.uint8)

        rois = {}
        for tier in (1, 2):
            left, right = v.pair_rois(frame, tier)
            self.assertEqual(left.shape, right.shape, f"2 nửa tầng {tier} phải cùng cỡ")
            rois[tier] = left.shape[0]

        # Chiều cao vùng quét đúng ROI_HEIGHT, và 2 tầng phải cho ra 2 vùng KHÁC nhau
        want_h = int(480 * config.ROI_HEIGHT)
        self.assertEqual(rois[1], want_h)
        self.assertEqual(rois[2], want_h)

        # Kiểm 2 cửa sổ dọc không đè lên nhau (tính lại đúng công thức _crop_roi)
        def window(tier):
            c = int(480 * config.ROI_Y_CENTER[tier])
            y0 = max(0, min(480 - want_h, c - want_h // 2))
            return y0, y0 + want_h

        top2, bot2 = window(2)
        top1, bot1 = window(1)
        self.assertLess(bot2, top1,
                        f"vùng tầng 2 ({top2}..{bot2}) phải KẾT THÚC trước vùng tầng 1 "
                        f"({top1}..{bot1}) — chồng nhau là ôm 2 loại kiện cùng lúc")
        self.assertLessEqual(bot1, 480, "vùng tầng 1 không được tràn khỏi khung")

    def test_tier_roi_differs_from_legacy_center_crop(self):
        """Truyền tầng phải cho vùng KHÁC hẳn lúc không truyền.

        Nếu giống nhau nghĩa là `level` bị bỏ qua ở đâu đó trên đường
        classify_pair → pair_rois → _crop_roi, và mọi thứ lại quay về lỗi cũ.
        """
        from vision.vision import Vision
        v = object.__new__(Vision)
        frame = _np.zeros((480, 640, 3), dtype=_np.uint8)
        legacy, _ = v.pair_rois(frame)
        tiered, _ = v.pair_rois(frame, 2)
        self.assertNotEqual(legacy.shape, tiered.shape,
                            "ROI theo tầng phải khác ROI cắt giữa cố định")

    def test_split_pair_halves_do_not_overlap(self):
        from vision.vision import Vision
        v = object.__new__(Vision)
        frame = _np.zeros((480, 640, 3), dtype=_np.uint8)
        left, right = v.split_pair(frame)
        self.assertEqual(left.shape[1] + right.shape[1], 640)


# ==========================================================
# 5. Tính sai số bám line
# ==========================================================

class TestLineError(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Motion chiếm chân GPIO — tạo MỘT lần cho cả class, tránh "pin in use"
        cls.m = Motion()

    @classmethod
    def tearDownClass(cls):
        cls.m.cleanup()

    def setUp(self):
        self.m._last_error = 0.0

    def test_digital_error_sign(self):
        n = config.LINE_SENSOR_COUNT
        left = [1] + [0] * (n - 1)
        right = [0] * (n - 1) + [1]
        self.assertLess(self.m.compute_line_error(left), 0, "lệch trái phải ra số âm")
        self.assertGreater(self.m.compute_line_error(right), 0)

    def test_centered_is_near_zero(self):
        n = config.LINE_SENSOR_COUNT
        mid = [0] * n
        mid[n // 2 - 1] = 1
        mid[n // 2] = 1
        self.assertAlmostEqual(self.m.compute_line_error(mid), 0.0, places=6)

    def test_no_line_keeps_last_error(self):
        self.m._last_error = 1.7
        self.assertEqual(self.m.compute_line_error([0] * config.LINE_SENSOR_COUNT), 1.7)
        self.assertEqual(
            self.m.compute_line_error_analog([1.0] * config.LINE_SENSOR_COUNT), 1.7)

    def test_analog_error_sign(self):
        n = config.LINE_SENSOR_COUNT
        on, off = 0.0, 1.0
        left = [on] + [off] * (n - 1)
        right = [off] * (n - 1) + [on]
        self.assertLess(self.m.compute_line_error_analog(left), 0)
        self.assertGreater(self.m.compute_line_error_analog(right), 0)

    def test_analog_weights_by_strength_not_just_on_off(self):
        """2 mắt cùng thấy line nhưng ĐẬM khác nhau → analog nghiêng về mắt đậm hơn,
        digital thì chia đều. Đây là lý do bám line dùng bản analog."""
        n = config.LINE_SENSOR_COUNT
        threshold = config.LINE_THRESHOLD / 1023.0
        raw = [1.0] * n
        raw[0] = 0.0                 # mắt 0: thấy line rất đậm
        raw[1] = threshold * 0.5     # mắt 1: thấy mờ hơn
        analog = self.m.compute_line_error_analog(raw)

        digital = self.m.compute_line_error([1, 1] + [0] * (n - 2))
        w0, w1 = config.LINE_WEIGHTS[0], config.LINE_WEIGHTS[1]

        self.assertTrue(w0 < analog < w1, f"phải nằm giữa {w0} và {w1}, được {analog}")
        self.assertLess(analog, digital,
                        "analog phải nghiêng về mắt thấy đậm hơn, digital chia đều")


# ==========================================================
# 6. Bám line khi LÙI — lệnh ("back", N)
# ==========================================================

class TestFollowLineReverse(unittest.TestCase):
    """Lùi mà giữ nguyên dấu hiệu chỉnh thì robot ngoáy đuôi rồi văng khỏi line.

    Thanh cảm biến ở ĐẦU xe, lùi thì nó thành đuôi. Với luật lái ω = −k·y, ma trận
    trạng thái (y, θ) có det = v·k, nên k phải CÙNG DẤU vận tốc mới hội tụ. Xem
    Motion.follow_line — test này canh đúng cái dấu đó.
    """

    @classmethod
    def setUpClass(cls):
        cls.m = Motion()

    @classmethod
    def tearDownClass(cls):
        cls.m.cleanup()

    def _drive(self, reverse):
        """Đặt line lệch hẳn sang PHẢI rồi đọc PWM 4 chân."""
        n = config.LINE_SENSOR_COUNT
        raw = [1.0] * (n - 1) + [0.0]           # 0.0 = trên line
        self.m._last_error = 0.0
        self.m.read_line_sensor_raw = lambda: raw
        self.m.follow_line(base_speed=40, reverse=reverse)
        return (self.m._left_fwd.value, self.m._right_fwd.value,
                self.m._left_rev.value, self.m._right_rev.value)

    def test_forward_uses_forward_pins_only(self):
        lf, rf, lr, rr = self._drive(reverse=False)
        self.assertEqual((lr, rr), (0, 0), "tiến mà vẫn cấp điện chân lùi")
        self.assertGreater(lf, rf, "line lệch phải → bánh trái nhanh hơn để bẻ phải")

    def test_reverse_uses_reverse_pins_only(self):
        lf, rf, lr, rr = self._drive(reverse=True)
        self.assertEqual((lf, rf), (0, 0), "lùi mà vẫn cấp điện chân tiến")
        self.assertGreater(lr + rr, 0, "lùi phải có điện ở chân lùi")

    def test_reverse_flips_the_correction(self):
        _lf, _rf, lr, rr = self._drive(reverse=True)
        fl, fr, _, _ = self._drive(reverse=False)
        self.assertLess(lr, rr,
                        "lùi phải ĐẢO dấu hiệu chỉnh so với tiến, không thì hệ phân kỳ")
        self.assertGreater(fl, fr, "tiền đề: khi tiến thì bánh trái nhanh hơn")

    def test_intersection_detected_while_reversing(self):
        n = config.LINE_SENSOR_COUNT
        self.m.read_line_sensor_raw = lambda: [0.0] * n       # mọi mắt thấy line
        at_intersection, _values = self.m.follow_line(base_speed=40, reverse=True)
        self.assertTrue(at_intersection, "lùi vẫn phải nhận ra giao lộ")


class _EncoderGia:
    def __init__(self, xung: int, available: bool = True):
        self.xung = xung
        self.available = available

    def read_and_reset(self) -> int:
        return self.xung


class TestTienBuCm(unittest.TestCase):
    """Tiến bù trước khi xoay phải đo bằng QUÃNG ĐƯỜNG, không phải đồng hồ.

    ⚠️ Xoay 90° tại chỗ đòi TRỤC BÁNH nằm trong ~±1.5cm của giao lộ (vạch rộng
    20mm, thanh cảm biến trải 47mm). Thanh cảm biến ở đầu xe cách trục ~12cm, nên
    lùi tới khi cảm biến thấy giao lộ là trục đã vượt qua 12cm.
    REVERSE_RECENTER_TIME là hằng số THỜI GIAN: quãng đường của nó đổi theo pin, ma
    sát sàn và tải trên càng. Đo trên robot 03/08: lùi-rồi-tiến-để-xoay chạy không
    ổn định — lúc xoay đúng vào line, lúc lùi ít quá, lúc tiến quá đà va vào kệ.
    """

    def _motion(self, xung_moi_lan: int, co_encoder: bool = True):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m.stop = MagicMock()
        m.forward = MagicMock()
        m._encoder_left = _EncoderGia(xung_moi_lan, co_encoder)
        m._encoder_right = _EncoderGia(xung_moi_lan, co_encoder)
        return m

    def test_uncalibrated_falls_back_to_the_old_timed_nudge(self):
        """ENCODER_PULSES_PER_CM = 0 → trả False để caller dùng cách cũ."""
        m = self._motion(10)
        with patch.object(config, "ENCODER_PULSES_PER_CM", 0.0):
            self.assertFalse(m.tien_bu_cm(12.0, 35))
        m.forward.assert_not_called()

    def test_missing_encoder_falls_back_too(self):
        m = self._motion(10, co_encoder=False)
        with patch.object(config, "ENCODER_PULSES_PER_CM", 5.0):
            self.assertFalse(m.tien_bu_cm(12.0, 35))
        m.forward.assert_not_called()

    def test_stops_once_the_pulse_target_is_reached(self):
        """Đủ xung là DỪNG — không chạy tiếp cho hết chặn trên."""
        m = self._motion(10)
        with patch.object(config, "ENCODER_PULSES_PER_CM", 5.0):
            t0 = time.time()
            self.assertTrue(m.tien_bu_cm(12.0, 35))     # cần 60 xung, 10/nhịp
        self.assertLess(time.time() - t0, config.RECENTER_MAX_TIME,
                        "chạy hết chặn trên = không hề đếm xung")
        m.stop.assert_called()

    def test_dead_encoder_still_stops_at_the_time_cap(self):
        """Encoder im (0 xung) thì phải dừng ở chặn trên, không chạy vô hạn."""
        m = self._motion(0)
        with patch.object(config, "ENCODER_PULSES_PER_CM", 5.0):
            with patch.object(config, "RECENTER_MAX_TIME", 0.4):
                with self.assertLogs("control.motion", level="WARNING") as nk:
                    self.assertTrue(m.tien_bu_cm(12.0, 35))
        self.assertIn("HẾT CHẶN TRÊN", "\n".join(nk.output))
        m.stop.assert_called()


class TestXoay90BangEncoder(unittest.TestCase):
    """Xoay 90° đo bằng encoder — TẮT cho tới khi đo được vệt bánh."""

    def _motion(self, xung_moi_lan: int, co_encoder: bool = True):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m.stop = MagicMock()
        m.turn_left = MagicMock()
        m.turn_right = MagicMock()
        m._encoder_left = _EncoderGia(xung_moi_lan, co_encoder)
        m._encoder_right = _EncoderGia(xung_moi_lan, co_encoder)
        return m

    def test_disabled_until_the_wheel_track_is_measured(self):
        """WHEEL_TRACK_CM = 0 → giữ NGUYÊN cách cũ theo TURN_TIME.

        Thêm một cơ chế xoay mới ngay trước ngày thi mà bật sẵn là đánh cược. Nó
        chỉ bật khi có số đo thật, và cho tới lúc đó hành vi không đổi một chút nào.
        """
        m = self._motion(10)
        with patch.object(config, "WHEEL_TRACK_CM", 0.0):
            with patch.object(config, "ENCODER_PULSES_PER_CM", 35.94):
                m.turn_left_90()
        m.turn_left.assert_called_once()      # vẫn xoay, nhưng bằng đồng hồ
        self.assertEqual(m._encoder_left.xung, 10)

    def test_uses_the_arc_length_when_measured(self):
        """Có vệt bánh thì dừng theo XUNG, không theo TURN_TIME."""
        import math
        vet, xung_cm = 20.0, 35.94
        can = 2 * (math.pi * vet / 4) * xung_cm
        m = self._motion(int(can))            # đủ ngay nhịp đầu
        with patch.object(config, "WHEEL_TRACK_CM", vet):
            with patch.object(config, "ENCODER_PULSES_PER_CM", xung_cm):
                t0 = time.time()
                m.turn_right_90()
        self.assertLess(time.time() - t0, config.TURN_TIME,
                        "vẫn chờ hết TURN_TIME = không hề đếm xung")
        m.turn_right.assert_called_once()

    def test_slipping_wheels_stop_at_the_time_cap(self):
        """Bánh trượt / encoder im thì phải dừng, không xoay vô hạn."""
        m = self._motion(0)
        with patch.object(config, "WHEEL_TRACK_CM", 20.0):
            with patch.object(config, "ENCODER_PULSES_PER_CM", 35.94):
                with self.assertLogs("control.motion", level="WARNING") as nk:
                    m.turn_left_90()
        self.assertIn("HẾT CHẶN TRÊN", "\n".join(nk.output))
        m.stop.assert_called()


class TestRetreatTheoQuangLuonVao(unittest.TestCase):
    """Lùi khỏi kệ = lùi ĐÚNG quãng đã luồn vào, đo bằng encoder.

    ⚠️ HỒI QUY (option 5, robot 03/08): siêu âm bị kiện cõng chắn nên retreat rơi
    về lùi mù RETREAT_BLIND_TIME = 1.5s. Nhưng 1.5s lúc cõng 2 kiện đi được ít hơn
    hẳn lúc đi không, nên robot lùi NGẮN QUÁ rồi tiến lên xoay thì chệch khỏi line.
    Option 18 chạy khớp vì bài đó không cõng gì — đúng cái bẫy của hằng số thời gian.
    Không cần hằng số mới: creep_until() vừa đếm xong quãng luồn vào.
    """

    def _motion(self, xung_moi_lan: int, xung_da_luon: int):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m._distance_sensor = MagicMock()
        m.stop = MagicMock()
        m.backward = MagicMock()
        m.get_distance = lambda *a, **k: 9.4      # bị kiện chắn — đứng số
        m._encoder_left = _EncoderGia(xung_moi_lan)
        m._encoder_right = _EncoderGia(0)
        m.xung_da_luon = xung_da_luon
        return m

    def test_backs_out_by_the_measured_creep_distance(self):
        m = self._motion(xung_moi_lan=200, xung_da_luon=400)
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertTrue(m.retreat_from_shelf())
        ghi = "\n".join(nk.output)
        self.assertIn("quãng đã luồn vào", ghi)
        self.assertNotIn("lùi mù", ghi)

    def test_carrying_ignores_a_lucky_sonar_sample_that_says_far_enough(self):
        """⚠️ HỒI QUY: cõng hàng thì số đo ≥ mục tiêu KHÔNG có nghĩa là đã lùi đủ.

        Số đo lúc bị kiện chắn nhảy lung tung (đo 03/08: 9.4 / 7.8 / 10.2 / 100.0
        trong cùng một lượt). Vớ đúng một mẫu ≥ 12.9 là retreat báo "đã lùi đủ xa"
        khi robot còn chưa nhúc nhích — rồi tiến lên xoay thì va vào kệ và lệch line.
        """
        m = self._motion(xung_moi_lan=200, xung_da_luon=400)
        m.get_distance = lambda *a, **k: 99.0     # kịch trần: "quá đủ xa"
        m.dang_cong_hang = True
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertTrue(m.retreat_from_shelf())
        ghi = "\n".join(nk.output)
        self.assertIn("ĐANG CÕNG HÀNG", ghi)
        self.assertIn("quãng đã luồn vào", ghi)
        self.assertNotIn("Đã lùi đủ xa", ghi)

    def test_not_carrying_still_trusts_the_sonar(self):
        """Không cõng hàng (bốc lỗi) thì siêu âm vẫn dùng bình thường."""
        m = self._motion(xung_moi_lan=200, xung_da_luon=0)
        m.get_distance = lambda *a, **k: 99.0
        m.dang_cong_hang = False
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertTrue(m.retreat_from_shelf())
        self.assertIn("Đã lùi đủ xa", "\n".join(nk.output))

    def test_falls_back_to_time_when_there_is_no_creep_measurement(self):
        """Không có số xung luồn vào (vd bốc hàng lỗi) → vẫn lùi mù như cũ."""
        m = self._motion(xung_moi_lan=0, xung_da_luon=0)
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertTrue(m.retreat_from_shelf())
        self.assertIn("lùi mù", "\n".join(nk.output))


class TestCreepStallGuard(unittest.TestCase):
    """Chặn cứng khi luồn càng phải dùng ENCODER, không phải siêu âm.

    ⚠️ Đo trên robot 03/08: đặt robot cách kệ ĐÚNG 12cm (bằng thước), siêu âm báo
    35.7cm với σ = 3.24cm và 10.7% mẫu lệch > 2cm. Mặt trước giá kệ in 3D HỞ nên
    chùm sóng lọt qua và dội về từ vật cách ~36cm phía sau. Cùng cảm biến đó ở chỗ
    trống đọc σ = 0.20cm trên 997 mẫu — nó KHÔNG hỏng, nó chỉ không thấy cái kệ.
    Chặn cứng dựa vào số đo đó vừa không bắt được lúc cần, vừa bắn nhầm khi gặp
    gai nhiễu ngắn (đã thấy 4.6cm giả). Encoder không cần calibrate cm: càng tì
    vào kệ là bánh kẹt, xung im ngay.
    """

    def _motion(self, xung: int, co_encoder: bool = True, check=None):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m.stop = MagicMock()
        m.stop_gently = MagicMock()
        m._forward_guided = MagicMock()
        m.get_distance = lambda: 100.0
        m._encoder_left = _EncoderGia(xung, co_encoder)
        m._encoder_right = _EncoderGia(xung, co_encoder)
        return m

    def test_wheels_not_turning_stops_instead_of_pushing_into_the_shelf(self):
        m = self._motion(xung=0)
        with self.assertLogs("control.motion", level="ERROR") as nk:
            self.assertFalse(m.creep_until(lambda: False, timeout=3.0))
        self.assertIn("BÁNH KHÔNG QUAY", "\n".join(nk.output))
        m.stop.assert_called()

    def test_healthy_pulses_do_not_trip_the_guard(self):
        """Bánh quay bình thường thì phải bò tiếp tới khi IR báo."""
        m = self._motion(xung=50)
        moc = time.time()
        # IR báo sau khi đã qua cửa sổ xét kẹt — chứng minh guard không cắt ngang.
        ok = m.creep_until(
            lambda: time.time() - moc > config.INSERT_STALL_TIME + 0.2, timeout=3.0)
        self.assertTrue(ok, "guard đã cắt oan dù bánh vẫn quay")

    def test_grace_window_covers_motor_spin_up(self):
        """Nhịp đầu bánh chưa quay là bình thường — không được bắt kẹt ngay."""
        m = self._motion(xung=0)
        moc = time.time()
        m.creep_until(lambda: False, timeout=3.0)
        self.assertGreaterEqual(time.time() - moc, config.INSERT_STALL_GRACE,
                                "bắt kẹt trước khi motor kịp khởi động")

    def test_missing_encoder_does_not_false_trip(self):
        """Không có encoder thì KHÔNG được coi là kẹt — chỉ còn timeout giữ."""
        m = self._motion(xung=0, co_encoder=False)
        t0 = time.time()
        self.assertFalse(m.creep_until(lambda: False, timeout=1.0))
        self.assertGreaterEqual(time.time() - t0, 0.9,
                                "phải chạy hết timeout, không cắt sớm vì tưởng kẹt")


class TestApproachShelf(unittest.TestCase):
    """Dừng trước kệ phải lệch về phía SỚM, và phải THỰC SỰ chạy được.

    Không có test nào gọi approach_shelf() nên đã lọt một lần: motion.py tham chiếu
    config.APPROACH_STOP_MARGIN trong khi hằng số đó chưa được thêm vào config —
    cả 4 bộ test vẫn xanh, chỉ nổ khi chạm robot thật.
    """

    def _motion(self, distances):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m._distance_sensor = MagicMock()
        seq = list(distances)
        m.get_distance = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
        m.stop = MagicMock()
        m.stop_gently = MagicMock()
        m.forward = MagicMock()
        m._forward_guided = MagicMock()
        return m

    def test_arriving_far_too_close_is_a_FAILURE_not_a_success(self):
        """⚠️ HỒI QUY (húc kệ 03/08): dừng ở 3.3cm khi mục tiêu 11.9 KHÔNG phải ✅.

        Log hôm đó đã in đúng con số — "bù THIẾU, nâng APPROACH_STOP_MARGIN 8.6 cm"
        — rồi vẫn trả True. Bước luồn càng sau đó tiến MÙ theo niềm tin "còn cách
        11.9cm" và húc thẳng vào kệ. Đứng gần hơn mục tiêu nhiều nghĩa là có gì đó
        TRƯỚC ĐÓ đã sai (pose lệch một giao lộ), và đây là lưới an toàn ĐỘC LẬP với
        toàn bộ phần điều hướng.
        """
        m = self._motion([3.3])
        with self.assertLogs("control.motion", level="ERROR") as nk:
            self.assertFalse(m.approach_shelf(config.APPROACH_DISTANCE))
        self.assertIn("Tiếp cận THẤT BẠI", "\n".join(nk.output))

    def test_normal_arrival_is_still_a_success(self):
        """Sai số tiếp cận bình thường vẫn phải ĐẠT — lưới trên không được quá chặt."""
        gan = config.APPROACH_DISTANCE - config.APPROACH_ARRIVAL_TOLERANCE + 0.5
        m = self._motion([gan])
        self.assertTrue(m.approach_shelf(config.APPROACH_DISTANCE))

    def test_near_zone_stops_between_steps_so_it_measures_standing_still(self):
        """⚠️ Đoạn cuối phải ĐI TỪNG NHỊP — DỪNG — ĐO, không đo trong lúc chạy.

        Vệt thật 03/08: cảm biến mất mục tiêu 0.2s giữa đoạn quyết định (báo 23cm
        khi kệ ở 15cm), rồi nhảy 16.6 → 8.8, bỏ qua hẳn mốc dừng 14.4cm. Biên từ
        16.5cm tới điểm dừng chỉ 2.1cm, bằng ĐÚNG MỘT nhịp cập nhật siêu âm.
        Cảm biến đứng yên thì σ = 0.20cm (997 mẫu) — nên dừng lại mà đo.
        """
        moc = config.APPROACH_DISTANCE
        m = self._motion([18.0, 16.0, moc + config.APPROACH_STOP_MARGIN])
        self.assertTrue(m.approach_shelf(moc))
        self.assertGreaterEqual(
            m.stop_gently.call_count, 2,
            "phải dừng GIỮA các nhịp, không chỉ dừng một lần lúc tới nơi")

    def test_a_single_noise_spike_must_not_send_it_back_to_FAST(self):
        """⚠️ HỒI QUY: chuyển pha phải CHỐT MỘT CHIỀU.

        Đo trên robot 03/08 (option 5, tầng 2) — vệt siêu âm thật:
            0.28s:16.9 → chậm | 0.41s:22.0 → NHANH lại | 0.47s:16.6 | 0.60s:9.5 lố
        Robot chỉ TIẾN nên số đo "xa hơn" sau khi đã vào vùng gần chỉ có thể là
        nhiễu. Một mẫu như thế ở đúng 2cm cuối là hỏng cả lần tiếp cận.
        """
        gan = config.APPROACH_SLOW_DISTANCE
        moc = config.APPROACH_DISTANCE
        m = self._motion([gan - 3, config.APPROACH_SLOW_DISTANCE + 2,
                          gan - 4, moc + config.APPROACH_STOP_MARGIN])
        toc = []
        m._forward_guided = lambda sp: toc.append(sp)
        self.assertTrue(m.approach_shelf(moc))
        self.assertTrue(all(v == config.APPROACH_SLOW_SPEED for v in toc),
                        f"đã quay lại pha NHANH sau một mẫu nhiễu: {toc}")

    def test_stops_early_by_the_lag_margin(self):
        """Dừng ở mốc + bù, không phải ở đúng mốc — bù độ trễ siêu âm."""
        moc = config.APPROACH_DISTANCE
        bu = config.APPROACH_STOP_MARGIN
        # đọc được đúng "mốc + bù" → phải dừng NGAY, chưa được tiến thêm
        m = self._motion([moc + bu])
        self.assertTrue(m.approach_shelf(moc))
        m.stop_gently.assert_called_once()

    def test_keeps_going_while_still_beyond_margin(self):
        """Còn xa hơn mốc + bù thì phải tiến tiếp, không dừng non."""
        moc = config.APPROACH_DISTANCE
        bu = config.APPROACH_STOP_MARGIN
        # Số đo GIẢM DẦN — robot đang thật sự tiến. Dãy hằng số sẽ bị cơ chế
        # "KHÔNG TIẾN THÊM ĐƯỢC" bắt (đúng), nhất là ở chế độ đi từng nhịp vốn
        # tốn ~0.4s mỗi vòng thay vì 0.02s.
        m = self._motion([moc + bu + 3.0, moc + bu + 2.2, moc + bu + 1.4,
                          moc + bu + 0.7, moc + bu])
        self.assertTrue(m.approach_shelf(moc))
        self.assertGreater(m._forward_guided.call_count, 0,
                           "phải tiến ít nhất một nhịp trước khi dừng")

    def test_margin_is_biased_early_never_late(self):
        """Bù phải DƯƠNG. Bù âm là dừng MUỘN — càng chui vào gầm kệ."""
        self.assertGreater(config.APPROACH_STOP_MARGIN, 0,
                           "bù âm = dừng muộn = càng chui vào gầm kệ")

    def test_does_not_drive_on_a_stale_sonar_reading(self):
        """⚠️ HỒI QUY: siêu âm ĐỨNG SỐ thì phải DỪNG, không chạy mù.

        Đo trên robot 03/08, vệt đo trong một pha tiếp cận:
            0.00s:15.9  0.02s:16.2  0.09s:16.3  0.79s:5.9
        Số đo kẹt ở 16.3 suốt 0.7 giây rồi nhảy thẳng xuống 5.9 — robot chạy MÙ hết
        0.7s đó và vượt điểm dừng ~10cm, lao vào kệ. APPROACH_NO_PROGRESS_TIME =
        1.2s không bắt được vì đóng băng ngắn hơn thế.
        """
        moc = config.APPROACH_DISTANCE + config.APPROACH_STOP_MARGIN + 5.0
        m = self._motion([moc])          # số đo KHÔNG BAO GIỜ đổi
        m.stop = MagicMock()
        m.advance_to_end = None
        t0 = time.time()
        m.approach_shelf(config.APPROACH_DISTANCE)
        self.assertGreater(m.stop.call_count, 0,
                           "số đo đứng yên mà vẫn chạy tiếp = chạy mù")
        # phải dừng lái ngay sau ULTRASONIC_STALE_TIME, không đợi hết 1.2s no-progress
        self.assertLess(config.ULTRASONIC_STALE_TIME, config.APPROACH_NO_PROGRESS_TIME)

    def test_stop_trigger_stays_inside_the_slow_phase(self):
        """Điểm dừng phải nằm DƯỚI mốc chuyển tốc, không thì dừng lúc còn chạy nhanh.

        approach_shelf chạy 60% khi xa, 32% khi dưới APPROACH_SLOW_DISTANCE. Nếu
        APPROACH_DISTANCE + APPROACH_STOP_MARGIN vượt mốc đó thì robot dừng khi VẪN
        đang ở pha nhanh — quãng trôi lớn hơn hẳn, và cả phép bù mất ý nghĩa vì nó
        được đo ở tốc độ chậm.
        """
        kich_hoat = config.APPROACH_DISTANCE + config.APPROACH_STOP_MARGIN
        self.assertLess(
            kich_hoat, config.APPROACH_SLOW_DISTANCE,
            f"dừng ở {kich_hoat:.1f}cm nhưng chỉ chậm lại dưới "
            f"{config.APPROACH_SLOW_DISTANCE}cm — nới APPROACH_SLOW_DISTANCE")

    def test_retreat_speed_clears_the_dead_zone(self):
        """Lùi ra phải đủ nhanh để thắng ma sát khi robot đang CÕNG 2 KIỆN.

        Đo trên robot 02/08: APPROACH_SPEED = 30 (chỉ hơn vùng chết 5) làm
        retreat_from_shelf TIMEOUT sau 5s. Trong trận mọi tuyến giao đều mở đầu bằng
        lùi, nên chặng này hỏng là hỏng cả lượt.
        """
        self.assertGreaterEqual(
            config.APPROACH_SPEED, config.MOTOR_MIN_DUTY + 10,
            "lùi ra quá sát vùng chết — cõng hàng là không thắng nổi ma sát")

    def test_fails_without_distance_sensor(self):
        m = object.__new__(Motion)
        m._distance_sensor = None
        self.assertFalse(m.approach_shelf())


class TestRetreatFromShelf(unittest.TestCase):
    """Lùi ra khỏi kệ phải xong được KỂ CẢ khi siêu âm bị kiện hàng che.

    Sau khi nhấc, pallet nằm ngay trước cảm biến và đi CÙNG robot → số đo đứng yên,
    điều kiện `dist >= RETREAT_DISTANCE` không bao giờ đạt. Đo trên robot 02/08:
        bốc THÀNH CÔNG (có pallet)  → lùi TIMEOUT 5s
        bốc THẤT BẠI (không pallet) → lùi OK, báo 13.3cm
    Trong trận thì lượt nào cũng lùi lúc đang cõng kiện — 6 lần × 5s = 30s.
    """

    def _motion(self, distances):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m._distance_sensor = MagicMock()
        seq = list(distances)
        m.get_distance = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
        m.backward = MagicMock()
        m.stop = MagicMock()
        return m

    def test_normal_case_stops_at_target(self):
        """Không cõng kiện: siêu âm dùng được, dừng đúng mốc."""
        m = self._motion([3.0, 6.0, 10.0, config.RETREAT_DISTANCE + 0.5])
        self.assertTrue(m.retreat_from_shelf())
        m.stop.assert_called_once()

    def test_blocked_sensor_falls_back_to_timed_retreat(self):
        """Số đo ĐỨNG YÊN (kiện che) → lùi theo giờ rồi dừng, KHÔNG chạy hết timeout."""
        m = self._motion([4.0])           # luôn 4.0cm, không bao giờ tăng
        t0 = time.time()
        self.assertTrue(m.retreat_from_shelf())
        troi = time.time() - t0
        self.assertLess(troi, config.APPROACH_TIMEOUT,
                        "phải dừng theo RETREAT_BLIND_TIME, không chạy hết timeout")
        self.assertGreaterEqual(troi, config.RETREAT_BLIND_TIME - 0.1)
        m.stop.assert_called_once()

    def test_blind_time_is_shorter_than_the_timeout_it_replaces(self):
        """Nếu lùi mù còn lâu hơn timeout thì chẳng sửa được gì."""
        self.assertLess(config.RETREAT_BLIND_TIME, config.APPROACH_TIMEOUT)
        self.assertLess(config.RETREAT_STUCK_TIME, config.RETREAT_BLIND_TIME)


class TestEscapeIntersection(unittest.TestCase):
    """Rời giao lộ phải bám theo CẢM BIẾN, không theo đồng hồ.

    C0R0 là ngã BA: vạch dọc kéo lên bắc 324mm, phía nam không có gì — nên thanh cảm
    biến đọc ra kiểu LỆCH (đo thật trên robot: 0 0 1 1 1 1). Vạch dọc chỉ rộng 20mm
    theo hướng robot đi. Bản cũ chạy mù 0.3s ở ADVANCE_SPEED=40, không đủ thoát, và
    advance_to_end đọc lại chính giao lộ đó → "gặp giao lộ".
    """

    def _motion(self, frames):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m.forward = MagicMock()
        m.backward = MagicMock()
        m.stop = MagicMock()
        seq = list(frames)
        m.read_line_sensor = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
        return m

    GIAO_LO = [1, 1, 1, 1, 0, 0]     # 4/6 — kiểu ngã ba đọc được trên robot
    LINE = [0, 0, 1, 1, 0, 0]        # 2/6 — vạch thẳng bình thường

    def test_keeps_going_until_sensor_is_clear(self):
        """Còn báo giao lộ thì còn chạy, dù đã quá 0.3s của bản cũ."""
        m = self._motion([self.GIAO_LO] * 60 + [self.LINE])
        t0 = time.time()
        with patch.object(config, "ESCAPE_MIN_TIME", 0.0), \
             patch.object(config, "ESCAPE_CLEAR_TIME", 0.05):
            self.assertTrue(m._escape_intersection(40))
        self.assertGreater(time.time() - t0, 0.3,
                           "bản cũ dừng ở 0.3s và đó chính là lỗi")
        m.stop.assert_called_once()

    def test_gives_up_at_cap_when_never_clear(self):
        """Mảng đen lớn (không phải giao lộ) → bỏ cuộc, KHÔNG chạy mãi."""
        m = self._motion([self.GIAO_LO])
        with patch.object(config, "ESCAPE_MAX_TIME", 0.3):
            self.assertFalse(m._escape_intersection(40))
        m.stop.assert_called_once()

    def test_honours_min_time_even_if_clear_immediately(self):
        """Sạch ngay từ đầu cũng phải chạy đủ sàn, không thì gần như không nhúc nhích."""
        m = self._motion([self.LINE])
        t0 = time.time()
        with patch.object(config, "ESCAPE_MIN_TIME", 0.2), \
             patch.object(config, "ESCAPE_CLEAR_TIME", 0.0):
            m._escape_intersection(40)
        self.assertGreaterEqual(time.time() - t0, 0.2)

    def test_requires_sustained_clear_not_a_few_samples(self):
        """Sạch chớp nhoáng rồi đen lại thì KHÔNG được coi là đã ra khỏi giao lộ."""
        chop = [self.GIAO_LO] * 5 + [self.LINE] * 2 + [self.GIAO_LO] * 200
        m = self._motion(chop)
        with patch.object(config, "ESCAPE_MIN_TIME", 0.0), \
             patch.object(config, "ESCAPE_CLEAR_TIME", 0.25), \
             patch.object(config, "ESCAPE_MAX_TIME", 0.5):
            self.assertFalse(m._escape_intersection(40),
                             "2 nhịp sạch giữa chừng không đủ để tuyên bố đã thoát")

    def test_reverse_uses_backward(self):
        m = self._motion([self.LINE])
        with patch.object(config, "ESCAPE_MIN_TIME", 0.0), \
             patch.object(config, "ESCAPE_CLEAR_TIME", 0.0):
            m._escape_intersection(40, reverse=True)
        m.backward.assert_called_once_with(40)
        m.forward.assert_not_called()


class TestSmokePickupKhongHaCang(unittest.TestCase):
    """Option 5 gọi lại option 2 — KHÔNG được hạ càng ở giữa chừng.

    Option 2 chạy riêng thì hỏi "Hạ càng về sàn? (Y/n)" mặc định CÓ, để lượt sau bắt
    đầu từ trạng thái đúng. Nhưng option 5 còn phải CHỞ KIỆN ĐI GIAO — hạ ở đó là
    thả cả 2 kiện xuống sàn rồi robot đi giao tay không, mà người test rất dễ bấm
    Enter theo quán tính vì mặc định là CÓ.
    """

    def test_full_lap_passes_ha_cang_cuoi_false(self):
        import inspect
        from tests import test_smoke
        src = inspect.getsource(test_smoke.smoke_full_lap)
        self.assertIn("doc_lap=False", src,
                      "option 5 phải yêu cầu GIỮ càng, không thì thả kiện giữa chừng")

    def test_standalone_default_is_to_lower(self):
        import inspect
        from tests import test_smoke
        sig = inspect.signature(test_smoke.smoke_pickup_cycle)
        self.assertTrue(sig.parameters["doc_lap"].default,
                        "chạy riêng option 2 thì mặc định PHẢI hạ càng")


class TestStopGently(unittest.TestCase):
    """Dừng có giảm tốc ở những chỗ TƯ THẾ robot quyết định bước sau.

    stop() là PHANH ĐỘNG (cả 4 chân về 0, EN nối cứng mức cao → 2 đầu motor cùng
    xuống đất). Phanh gấp ngay trước kệ làm robot lệch vài độ tại chỗ, và bước luồn
    càng kế tiếp không còn line để tự sửa.
    """

    def _motion(self):
        m = object.__new__(Motion)
        m.forward = MagicMock()
        m.backward = MagicMock()
        m.stop = MagicMock()
        return m

    def test_ramps_down_before_cutting(self):
        m = self._motion()
        with patch.object(config, "STOP_RAMP_TIME", 0.04), \
             patch.object(config, "STOP_RAMP_STEPS", 4), \
             patch.object(config, "STOP_SETTLE_TIME", 0):
            m.stop_gently(40)
        speeds = [c.args[0] for c in m.forward.call_args_list]
        self.assertEqual(speeds, [30.0, 20.0, 10.0], "phải giảm dần đều rồi mới cắt")
        m.stop.assert_called_once()

    def test_uses_backward_when_reversing(self):
        m = self._motion()
        with patch.object(config, "STOP_RAMP_TIME", 0.04), \
             patch.object(config, "STOP_SETTLE_TIME", 0):
            m.stop_gently(40, reverse=True)
        m.backward.assert_called()
        m.forward.assert_not_called()

    def test_zero_ramp_is_plain_stop(self):
        """Đặt 0 thì giữ ĐÚNG hành vi cũ — cắt phụt, không trôi thêm."""
        m = self._motion()
        with patch.object(config, "STOP_RAMP_TIME", 0), \
             patch.object(config, "STOP_SETTLE_TIME", 0):
            m.stop_gently(40)
        m.forward.assert_not_called()
        m.stop.assert_called_once()

    def test_settle_pause_is_honoured(self):
        m = self._motion()
        t0 = time.time()
        with patch.object(config, "STOP_RAMP_TIME", 0), \
             patch.object(config, "STOP_SETTLE_TIME", 0.2):
            m.stop_gently(40)
        self.assertGreaterEqual(time.time() - t0, 0.2)


class TestExitStartZone(unittest.TestCase):
    """Cửa sổ mù đầu ô xuất phát: bỏ qua hình MASCOT in ngay dưới robot.

    Ô xuất phát nằm trong khoảng đứt của R0 và chỗ đó in mascot, mặt đen tuyền —
    đo trên bản in thì thanh cảm biến thấy tới 14/23 px đen ngay tại chỗ đặt. Không
    có cửa sổ mù thì exit_start_zone() "chạm line" ở mẫu đầu tiên rồi căn giữa 1
    giây trên mặt con mascot.
    """

    def _motion(self, values):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m.forward = MagicMock()
        m.stop = MagicMock()
        m.read_line_sensor = lambda: values
        m.follow_line = MagicMock(return_value=(False, values))
        return m

    def _motion_seq(self, frames):
        """frames: đọc lần lượt; hết thì lặp giá trị cuối."""
        m = self._motion([0] * 6)
        seq = list(frames)

        def read():
            return seq.pop(0) if len(seq) > 1 else seq[0]

        m.read_line_sensor = read
        m.follow_line = MagicMock(return_value=(False, [0] * 6))
        return m

    def test_ignores_line_during_blind_window(self):
        """Thấy 'line' suốt (mascot) thì KHÔNG được dừng trong cửa sổ mù."""
        m = self._motion([1, 1, 1, 0, 0, 0])
        t0 = time.time()
        with patch.object(config, "EXIT_START_BLIND_TIME", 0.4):
            self.assertTrue(m.exit_start_zone(timeout=3.0))
        self.assertGreaterEqual(time.time() - t0, 0.4)

    def test_blind_window_ends_early_once_art_is_cleared(self):
        """Thấy đen (mascot) rồi thấy SẠCH = đã ra khỏi hình in → tìm line ngay.

        Đây mới là đường chạy BÌNH THƯỜNG. Nhờ nó, điểm kết thúc cửa sổ mù bám
        theo HÌNH IN chứ không theo đồng hồ, nên không phụ thuộc cm/s (chưa đo)
        lẫn chỗ đặt robot trong ô 400x400mm.
        """
        # mascot (đen) → sạch → line thật
        m = self._motion_seq([[1, 1, 0, 0, 0, 0]] * 3 + [[0] * 6] * 2
                             + [[0, 0, 1, 1, 0, 0]])
        t0 = time.time()
        with patch.object(config, "EXIT_START_BLIND_TIME", 5.0):
            with patch.object(config, "EXIT_START_ALIGN_TIME", 0.0):
                self.assertTrue(m.exit_start_zone(timeout=3.0))
        self.assertLess(time.time() - t0, 5.0,
                        "phải thoát sớm khi qua hết vùng in, không chờ hết chặn trên")

    def test_finds_line_immediately_when_no_blind_window(self):
        """Đặt 0 thì giữ ĐÚNG hành vi cũ — dừng ngay khi thấy line."""
        m = self._motion([1, 1, 1, 0, 0, 0])
        t0 = time.time()
        with patch.object(config, "EXIT_START_BLIND_TIME", 0.0):
            with patch.object(config, "EXIT_START_ALIGN_TIME", 0.0):
                self.assertTrue(m.exit_start_zone(timeout=3.0))
        self.assertLess(time.time() - t0, 0.3)

    def test_flag_is_set_when_alignment_runs_onto_the_intersection(self):
        """Căn giữa chạm giao lộ → phải BÁO RA, vì lúc đó robot đứng trên C0R0.

        ⚠️ HỒI QUY (đâm kệ 03/08): trước đây chỉ ghi log "ROUTE_START sẽ đếm" rồi
        thôi. Route KHÔNG đếm được giao lộ đang đứng lên — navigate_intersections()
        mở đầu bằng _escape_intersection(). Xem navigation.pose_sau_xuat_phat.
        """
        m = self._motion([1, 1, 1, 0, 0, 0])
        m.follow_line = MagicMock(return_value=(True, [0, 0, 1, 1, 1, 1]))
        # Chữ ký C0R0 THẬT đo trên robot 03/08 — 4 mắt ADC bão hoà 0.
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (921, 921, 0, 0, 0, 0)]
        with patch.object(config, "EXIT_START_BLIND_TIME", 0.0):
            with patch.object(config, "EXIT_START_ALIGN_TIME", 1.0):
                self.assertTrue(m.exit_start_zone(timeout=3.0))
        self.assertTrue(m.tren_giao_lo_dau)
        self.assertEqual(navigation.pose_sau_xuat_phat(m.tren_giao_lo_dau),
                         (navigation.NODE_DAU_TU_START, navigation.TOWARD_SHELVES))

    def test_faint_intersection_during_alignment_does_not_set_the_flag(self):
        """⚠️ HỒI QUY: mép vạch mờ lúc robot XIÊN không được tính là C0R0.

        Đo trên robot 03/08 — bước căn giữa báo "chạm giao lộ" với ADC
        [224, 232, 0, 0, 263, 826]. 224/232 chỉ lọt dưới ngưỡng THÍCH NGHI (248),
        không phải đen. Tin nó → pose = C0R0 trong khi robot còn cách 20cm → route
        bỏ mất lệnh forward → advance đâm ngay vào C0R0 thật và báo "Bản đồ hoặc vị
        trí không khớp", robot dừng hẳn giữa đường.
        """
        m = self._motion([1, 1, 1, 0, 0, 0])
        m.follow_line = MagicMock(return_value=(True, [1, 1, 0, 0, 1, 0]))
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (21, 515, 0, 0, 5, 917)]
        with patch.object(config, "EXIT_START_BLIND_TIME", 0.0):
            with patch.object(config, "EXIT_START_ALIGN_TIME", 0.1):
                self.assertTrue(m.exit_start_zone(timeout=3.0))
        self.assertFalse(m.tren_giao_lo_dau)
        self.assertEqual(navigation.pose_sau_xuat_phat(m.tren_giao_lo_dau),
                         navigation.START_POSE)

    def test_flag_stays_down_when_alignment_does_not_reach_it(self):
        """Không chạm giao lộ → pose vẫn là START, route giữ nguyên lệnh forward."""
        m = self._motion([1, 1, 1, 0, 0, 0])
        with patch.object(config, "EXIT_START_BLIND_TIME", 0.0):
            with patch.object(config, "EXIT_START_ALIGN_TIME", 0.05):
                self.assertTrue(m.exit_start_zone(timeout=3.0))
        self.assertFalse(m.tren_giao_lo_dau)
        self.assertEqual(navigation.pose_sau_xuat_phat(m.tren_giao_lo_dau),
                         navigation.START_POSE)

    def test_fails_when_line_never_found(self):
        """Hết timeout mà không thấy line → False, không báo thành công."""
        m = self._motion([0, 0, 0, 0, 0, 0])
        with patch.object(config, "EXIT_START_BLIND_TIME", 0.1):
            self.assertFalse(m.exit_start_zone(timeout=0.5))
        m.stop.assert_called()

    def test_blind_window_must_not_exceed_distance_to_intersection(self):
        """Chốt bằng số: cửa sổ mù dài quá thì vượt giao lộ C0R0 mà không đếm.

        Đo trên bản in: mascot hết ở 10.2cm, line R0 thật bắt đầu 21.9cm, giao lộ
        C0R0 ở 51.2cm. Test này không đo được cm/s trên PC, nên nó chỉ chặn việc ai
        đó đặt một con số lớn tới mức KHÔNG có tốc độ hợp lý nào còn an toàn:
        ở 20cm/s (chậm nhất còn tin được) thì 2.5s đã là 50cm, sát C0R0.
        """
        self.assertLessEqual(config.EXIT_START_BLIND_TIME, 1.5,
                             "chặn trên: 1.5s an toàn tới 34cm/s (1.5×34=51cm, sát C0R0)")
        self.assertGreater(config.EXIT_START_BLIND_TIME, 0.0,
                           "0 = quay lại lỗi bắt nhầm mascot làm line")


class TestAdvanceToEnd(unittest.TestCase):
    """advance_to_end phải phân biệt "hết line" với "chưa từng thấy line".

    Gộp hai cái lại thì robot đứng ngoài vạch cũng được báo là ĐÃ TỚI ĐIỂM CUỐI —
    gặp thật ở smoke option 1 sau bước dò nửa sân (probe_side_branch chạy hở, robot
    quay về lệch khỏi vạch), advance báo thành công sau 0.55s.
    """

    def _motion(self, frames, dist=999.0):
        """frames: list giá trị cảm biến trả lần lượt; hết thì lặp lại giá trị cuối."""
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m.get_distance = lambda *a, **k: dist
        m.stop = MagicMock()
        # advance_to_end dừng bằng stop_gently() → cần forward/backward để giảm tốc
        m.forward = MagicMock()
        m.backward = MagicMock()
        m._escape_intersection = MagicMock()
        seq = list(frames)

        def follow(_speed):
            v = seq.pop(0) if len(seq) > 1 else seq[0]
            return False, v

        m.follow_line = follow
        # Chữ ký giao lộ THẬT cho advance: cần ADVANCE_INTERSECTION_DAM = 5 mắt đen
        # ĐẬM (cao hơn INTERSECTION_THRESHOLD có chủ ý — xem config). Ngã tư thật
        # cho 6 mắt nên thừa sức đạt.
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (917, 0, 0, 0, 0, 0)]
        return m

    def test_end_of_line_after_seeing_it_is_success(self):
        """Thấy line rồi mới mất = đã tới điểm cuối thật."""
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 5 + [[0] * 6])
        self.assertTrue(m.advance_to_end(timeout=3.0))

    def test_never_seeing_line_is_failure(self):
        """Không nằm trên line từ đầu -> THẤT BẠI, không phải 'đã tới điểm cuối'."""
        m = self._motion([[0] * 6])
        self.assertFalse(m.advance_to_end(timeout=3.0))
        m.stop.assert_called()

    def test_never_seeing_line_stops_within_acquire_window(self):
        """Không được chạy mù hết ADVANCE_TIMEOUT ở ADVANCE_SPEED."""
        import time as _t
        m = self._motion([[0] * 6])
        t0 = _t.time()
        m.advance_to_end(timeout=6.0)
        self.assertLess(_t.time() - t0, config.ADVANCE_ACQUIRE_TIME + 0.5)

    def test_ultrasonic_near_target_is_success(self):
        """Siêu âm thấy mục tiêu LẠI GẦN DẦN -> bàn giao cho approach_shelf."""
        m = self._motion([[0] * 6])
        xa = config.APPROACH_SLOW_DISTANCE + 10
        seq = [xa, xa - 3, config.APPROACH_SLOW_DISTANCE - 1]
        m.get_distance = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
        self.assertTrue(m.advance_to_end(timeout=3.0))

    def test_hard_stop_fires_even_when_line_never_ends(self):
        """⛔ CHẶN CỨNG: số đo dưới mốc là dừng, dù logic nào phía trên nghĩ gì.

        Nhánh "đi tới khi hết line" VỀ BẢN CHẤT là đâm vào kệ — line kéo tới cách
        chân kệ 1mm. Đây là lưới an toàn cuối cùng cho mọi đường dẫn tới đó.

        ⚠️ Bản trước của test này chỉ kiểm "trả True và có gọi stop" — mà nhánh "tới
        gần mục tiêu" cũng làm đúng vậy, nên nó KHÔNG phân biệt được hai nhánh. Nhờ
        thế đoạn chặn cứng bị xoá nhầm ở 4fe93e7 mà test vẫn xanh, và robot lao vào
        kệ thêm nhiều lần. Giờ bắt ĐÚNG dòng log của nhánh chặn cứng.
        """
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 400)   # line KHÔNG bao giờ hết
        m.get_distance = lambda: config.ADVANCE_HARD_STOP_CM - 1.0
        with self.assertLogs("control.motion", level="WARNING") as ghi:
            self.assertTrue(m.advance_to_end(timeout=3.0))
        self.assertTrue(any("CHẶN CỨNG" in d for d in ghi.output),
                        f"phải đi qua nhánh CHẶN CỨNG, log thực tế: {ghi.output}")

    def test_advance_does_not_drive_on_a_stale_reading(self):
        """Số đo ĐỨNG YÊN thì advance cũng phải dừng chờ, y như approach_shelf.

        Đo trên robot 03/08: advance dừng ở 4.3cm thay vì 20cm rồi approach_shelf
        tiếp tục từ đó — robot đã ở sát kệ trước khi pha tiếp cận bắt đầu. Trước đây
        tôi chỉ vá chống-số-đo-cũ ở approach_shelf mà quên chỗ này, mà đây mới là
        chỗ chạy TRƯỚC.
        """
        gan = config.APPROACH_SLOW_DISTANCE + 2.0     # TRONG tầm nguy hiểm
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 400)
        m.get_distance = lambda: gan                  # không bao giờ đổi
        m.advance_to_end(timeout=0.6)
        self.assertGreater(m.stop.call_count, 0,
                           "số đo đứng yên trong tầm gần mà vẫn chạy = chạy mù")

    def test_glitch_while_moving_is_rejected_by_the_stationary_re_measure(self):
        """Gai nhiễu 4.6cm giữa lúc chạy KHÔNG được coi là "đã tới kệ".

        Đo trên robot 03/08: đứng yên 30s cho 997 mẫu, độ lệch chuẩn 0.20cm,
        0 mẫu lệch quá 2cm. Cùng cảm biến đó lúc ĐANG CHẠY báo 4.6cm khi kệ ở
        ~35cm. Robot dừng lại ngay tại GIAO LỘ, tưởng đã tới kệ, rồi bước luồn
        càng tiến lên mù 35cm và HÚC THẲNG VÀO KỆ.
        Nhịp 1 báo 4.6 (gai); đo lại lúc đứng yên ra 35.0 → phải chạy tiếp.
        """
        doc = iter([4.6, 35.0, 25.0, 19.0, 19.0] + [19.0] * 200)
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 400)
        m.get_distance = lambda *a, **k: next(doc)
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertTrue(m.advance_to_end(timeout=3.0))
        ghi = "\n".join(nk.output)
        self.assertIn("BỎ QUA GAI NHIỄU", ghi)
        self.assertNotIn("CHẶN CỨNG", ghi)
        self.assertIn("đã tới gần mục tiêu", ghi)

    def test_glitch_quota_is_finite_so_it_cannot_loop_forever(self):
        """Hết quota bỏ qua thì phải TIN số đo và dừng — thà dừng sớm còn hơn kẹt."""
        doc = iter([4.6, 35.0] * 40 + [4.6] * 200)
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 900)
        m.get_distance = lambda *a, **k: next(doc)
        with self.assertLogs("control.motion", level="WARNING") as nk:
            self.assertTrue(m.advance_to_end(timeout=6.0))
        ghi = "\n".join(nk.output)
        self.assertEqual(ghi.count("BỎ QUA GAI NHIỄU"), config.ULTRASONIC_MAX_GLITCH)
        self.assertIn("CHẶN CỨNG", ghi)

    def test_factory_print_is_ARRIVAL_not_a_map_error_when_carrying(self):
        """⚠️ Mảng in khu nhà máy = ĐÃ TỚI, không phải "bản đồ không khớp".

        Đo trên robot 03/08, chặng tới khu Samsung — CẢ THANH tối dần đều trong
        0.14s, không phải một vạch cắt ngang:
            mắt 6:  913 → 878 → 820 → 749 → 666 → 499
            mắt 1:  633 → 434 → 358 → 311 → 138
        Robot đi vào mảng in của khu nhà máy (ảnh nền tối). Nó ĐÃ TỚI NƠI, nhưng
        advance đọc ra giao lộ và báo lỗi — robot đứng chết trước khu Samsung,
        không thả hàng. Ở khu nhà máy KHÔNG có giao lộ nào để gặp.
        """
        m = self._motion([[1] * 6] * 400)
        m.dang_cong_hang = True
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (138, 0, 0, 0, 0, 100)]
        m.follow_line = lambda speed: (True, [1, 1, 1, 1, 1, 1])
        m.get_distance = lambda *a, **k: 100.0
        m._encoder_left = _EncoderGia(500)
        m._encoder_right = _EncoderGia(500)
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertTrue(m.advance_to_end(timeout=3.0))
        ghi = "\n".join(nk.output)
        self.assertIn("ĐÃ VÀO KHU NHÀ MÁY", ghi)
        self.assertNotIn("Bản đồ hoặc vị trí không khớp", ghi)

    def test_factory_print_is_told_apart_by_the_BRIGHTEST_eye(self):
        """⚠️ HỒI QUY: 4 mắt đen là chưa đủ để phân biệt tấm in với vạch line.

        Đo trên robot 03/08 — cả bốn ca đều có 4 mắt đen ĐẬM, chỉ khác ở mắt SÁNG
        NHẤT. Trên TẤM IN thì cả vùng đều tối, không mắt nào thấy nền trắng sạch:
            tấm in Hana      4 đen, sáng nhất 509   ← đây là điểm thả
            vạch line thường 4 đen, sáng nhất 926
            giao lộ thật     4 đen, sáng nhất 911
        Đòi 5 mắt (như trước) thì bỏ sót tấm in Hana → robot đi quá khỏi ô nhà máy.
        Hạ xuống 4 mà không xét độ sáng thì vạch thường cũng bị nhận nhầm.
        """
        gia = {"tấm in Hana": ([0, 0, 15, 123, 509, 446], True),
               "tấm in đậm":  ([138, 0, 0, 0, 0, 100], True),
               "vạch thường": ([0, 703, 0, 0, 0, 926], False),
               "giao lộ":     ([0, 0, 0, 0, 577, 911], False)}
        for ten, (adc, mong_doi) in gia.items():
            raw = [v / 1023 for v in adc]
            la_nha_may = (LineSensor.dem_den_dam(raw) >= config.ADVANCE_FACTORY_DARK_EYES
                          and max(raw) <= config.ADVANCE_FACTORY_MAX_BRIGHT)
            self.assertEqual(la_nha_may, mong_doi, f"{ten}: ADC {adc}")

    def test_dark_patch_too_early_is_still_not_the_factory(self):
        """Chưa đi đủ xa thì mảng tối là giao lộ vừa thoát, không phải nhà máy."""
        m = self._motion([[1] * 6] * 400)
        m.dang_cong_hang = True
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (138, 0, 0, 0, 0, 100)]
        m.follow_line = lambda speed: (True, [1, 1, 1, 1, 1, 1])
        m.get_distance = lambda *a, **k: 100.0
        m._encoder_left = _EncoderGia(0)      # không nhúc nhích
        m._encoder_right = _EncoderGia(0)
        m.read_line_sensor_adc = lambda: [138, 0, 0, 0, 0, 100]
        with self.assertLogs("control.motion", level="WARNING") as nk:
            m.advance_to_end(timeout=2.0)
        self.assertNotIn("ĐÃ VÀO KHU NHÀ MÁY", "\n".join(nk.output))

    def test_plain_line_inflated_by_adaptive_threshold_is_not_an_intersection(self):
        """⚠️ HỒI QUY: advance cũng phải đếm mắt đen ĐẬM, không tin ngưỡng thích nghi.

        Đo trên robot 03/08, chặng tới khu Samsung:
            ADC [834, 270, 0, 0, 0, 930]  ngưỡng 279  → chỉ 3 mắt đen ĐẬM
        Vạch line thường (mắt 3,4,5) bị thổi thành giao lộ vì mắt 2 đọc 270, lọt
        dưới ngưỡng 279. Advance thoát giao lộ OAN hai lần rồi lạc và báo "bản đồ
        không khớp" — robot đứng chết ở giao lộ trước khu Samsung.
        """
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 30 + [[0] * 6])
        # Mắt 2 nằm ĐÚNG MÉP vạch: cùng vạch đó nó đọc 270 rồi 98 rồi 169... Ở đây
        # lấy ca 98 — ĐEN ĐẬM thật, tức đủ 4 mắt và lọt qua ngưỡng cũ. Chỉ mức 5
        # mới bác được.
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (502, 98, 0, 0, 0, 916)]
        m.follow_line = lambda speed: (True, [0, 1, 1, 1, 1, 0])
        m.get_distance = lambda *a, **k: 100.0
        m.dang_cong_hang = True          # bỏ siêu âm, chỉ còn line quyết định
        with self.assertLogs("control.motion", level="INFO") as nk:
            m.advance_to_end(timeout=1.0)
        ghi = "\n".join(nk.output)
        self.assertIn("mắt đen ĐẬM", ghi)
        self.assertNotIn("Bản đồ hoặc vị trí không khớp", ghi)
        self.assertGreater(m.forward.call_count, 1,
                           "bác tín hiệu mà không chạy lại = khoá chết, vì "
                           "follow_line() tự stop() khi thấy giao lộ")

    def test_intersection_right_after_escape_is_forgiven_once(self):
        """⚠️ HỒI QUY: escape chạm trần rồi bỏ cuộc → advance đọc lại chính nó.

        Đo trên robot 03/08, chạy option 5 năm lượt: 3 đúng 2 sai. Lượt THÀNH CÔNG
        vẫn ghi "Rời giao lộ: hết 1.21s mà cảm biến vẫn báo giao lộ" và vệt siêu âm
        bắt đầu ở 30.1cm — tức mới đi ~5cm khỏi C0R0 (kệ cách 35.4cm). Nó chỉ may
        là nhịp đọc kế không ra giao lộ. Đây là ranh giới, không phải lỗi logic.
        """
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 400)
        m.tren_giao_lo_dau = False           # KHÔNG dựa vào cờ
        m._escape_intersection = MagicMock(return_value=True)
        lan = {"n": 0}

        def fl(speed):
            lan["n"] += 1
            return (lan["n"] == 1, [0, 0, 1, 1, 1, 1])

        m.follow_line = fl
        m.get_distance = lambda *a, **k: 19.0
        with self.assertLogs("control.motion", level="WARNING") as nk:
            self.assertTrue(m.advance_to_end(timeout=3.0))
        self.assertIn("cửa sổ ân hạn", "\n".join(nk.output))

    def test_only_the_FIRST_intersection_is_forgiven(self):
        """Ân hạn dùng ĐÚNG MỘT lần — cái thứ hai vẫn là lỗi bản đồ."""
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 900)
        m.tren_giao_lo_dau = False
        m._escape_intersection = MagicMock(return_value=True)
        m.follow_line = lambda speed: (True, [0, 0, 1, 1, 1, 1])
        m.read_line_sensor_adc = lambda: [917, 914, 0, 0, 0, 0]
        m.get_distance = lambda *a, **k: 30.0
        self.assertFalse(m.advance_to_end(timeout=3.0))

    def test_self_corrects_when_the_C0R0_flag_was_wrong_by_one_intersection(self):
        """Cờ bật nhầm → gặp giao lộ → TỰ SỬA và đi tiếp, không dừng hẳn.

        ⚠️ HỒI QUY (option 8, 03/08): cờ bật nhầm vì hình in mascot cho 4 mắt đen
        ĐỨT QUÃNG. Route bỏ mất lệnh forward, advance gặp ngay C0R0 thật và báo
        "Bản đồ hoặc vị trí không khớp" — robot dừng hẳn giữa đường.
        Cờ đó dựa trên MỘT lần đọc giữa lúc robot còn xiên nên không thể chắc 100%;
        nhưng gặp giao lộ TRONG LÚC cờ đang bật thì suy ra được ngay là niềm tin
        sai đúng một giao lộ.
        """
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 900)
        m.tren_giao_lo_dau = True
        m._escape_intersection = MagicMock(return_value=True)
        # SAU cửa sổ ân hạn — để bài này kiểm ĐÚNG cơ chế của cờ, không phải ân hạn.
        t0, xong = time.time(), {"v": False}

        def fl(speed):
            if not xong["v"] and time.time() - t0 > config.ADVANCE_START_GRACE + 0.1:
                xong["v"] = True
                return (True, [0, 0, 1, 1, 1, 1])
            return (False, [0, 0, 1, 1, 1, 1])

        m.follow_line = fl
        # Chỉ cho "tới gần mục tiêu" SAU khi đã gặp giao lộ, không thì advance về
        # đích trước cả lúc cơ chế cần kiểm được kích hoạt.
        # 42cm: đã thấy mục tiêu (≤45) nhưng NGOÀI tầm của chặn-số-đo-cũ (≤40), nên
        # số không đổi vẫn chạy tiếp. Xem test_stale_guard_does_not_stall_on_a_far_reading.
        m.get_distance = lambda *a, **k: 19.0 if xong["v"] else 42.0
        with self.assertLogs("control.motion", level="WARNING") as nk:
            self.assertTrue(m.advance_to_end(timeout=3.0),
                            "cờ sai một giao lộ thì phải tự sửa, không dừng hẳn")
        self.assertIn("Tự sửa", "\n".join(nk.output))
        self.assertFalse(m.tren_giao_lo_dau, "cờ phải bị tiêu thụ")

    def test_meeting_an_intersection_without_the_flag_is_still_a_failure(self):
        """Không có cờ thì gặp giao lộ vẫn là LỖI — không được nới lỏng kiểm tra."""
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 400)
        m.tren_giao_lo_dau = False
        m.follow_line = lambda speed: (True, [0, 0, 1, 1, 1, 1])
        m.read_line_sensor_adc = lambda: [917, 914, 0, 0, 0, 0]
        m.get_distance = lambda *a, **k: 100.0
        self.assertFalse(m.advance_to_end(timeout=3.0))

    def test_lost_echo_after_seeing_target_stops_instead_of_ramming(self):
        """Thấy mục tiêu rồi số đo nhảy KỊCH TRẦN = mất tiếng vọng, không phải "xa ra".

        Đây là ca giết robot: 30→25→22 rồi 100,100,100 mà vẫn chạy tiếp. Nhánh
        "hết line" ở kệ CHÍNH LÀ đâm vào kệ — vạch kéo tới cách chân kệ 1mm.
        """
        doc = iter([30.0, 25.0, 22.0] + [100.0] * 40)
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 400)
        m.get_distance = lambda *a, **k: next(doc)
        with self.assertLogs("control.motion", level="WARNING") as nk:
            self.assertTrue(m.advance_to_end(timeout=3.0))
        self.assertIn("MẤT TIẾNG VỌNG", "\n".join(nk.output))

    def test_never_seeing_anything_stops_instead_of_driving_to_end_of_line(self):
        """Siêu âm mù suốt = KHÔNG được đi tới hết line (ở kệ thì đó là chân kệ)."""
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 900)
        m.get_distance = lambda *a, **k: 100.0
        t0 = time.time()
        self.assertFalse(m.advance_to_end(timeout=6.0))
        self.assertLess(time.time() - t0, config.ADVANCE_BLIND_TIMEOUT + 0.7)

    def test_stale_guard_does_not_stall_on_a_far_reading(self):
        """Số đo KỊCH TRẦN (không có tiếng vọng) cũng "không đổi" — không được chặn.

        Chặn cả ca đó thì robot đứng im vĩnh viễn. Ở xa thì số đo cũ vô hại vì còn
        lâu mới tới điểm dừng. Hai test cũ của lớp này bắt được đúng lỗi đó.
        """
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 20 + [[0] * 6])
        # 42cm: ĐÃ thấy mục tiêu (≤ APPROACH_DETECT_DISTANCE = 45) nhưng vẫn NGOÀI
        # tầm nguy hiểm của chặn-số-đo-cũ (2 × APPROACH_SLOW_DISTANCE = 40).
        m.get_distance = lambda: 42.0                 # không đổi, và không kịch trần
        self.assertTrue(m.advance_to_end(timeout=3.0),
                        "phải đi tới khi hết line, không đứng im chờ số mới")

    def test_near_target_still_works_when_reading_actually_changes(self):
        """⚠️ HỒI QUY: cơ chế chống-kiện-che KHÔNG được phá đường vào kệ.

        Bản trước đòi khoảng cách phải GIẢM ≥5cm mới tin siêu âm. Khi điều kiện đó
        không đạt, advance chạy tới HẾT LINE — mà line kéo tới tận chân kệ, tức ĐÂM
        THẲNG VÀO KỆ. Đã gặp thật ở option 8.
        Ở đây số đo GIẢM DẦN bình thường: phải dừng bằng siêu âm, KHÔNG chạy tới
        hết line.
        """
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 200)   # line KHÔNG bao giờ hết
        seq = [30.0, 26.0, 22.0, config.APPROACH_SLOW_DISTANCE - 1]
        m.get_distance = lambda: seq.pop(0) if len(seq) > 1 else seq[0]
        self.assertTrue(m.advance_to_end(timeout=3.0),
                        "phải dừng bằng siêu âm chứ không chạy tới hết line")


class TestNgUongDenDam(unittest.TestCase):
    """Phân biệt giao lộ THẬT với mép vạch mờ / hình in — bằng số đo trên robot."""

    def test_reverse_false_positive_is_rejected_by_contiguity(self):
        """⚠️ HỒI QUY: chặng LÙI cũng phải đòi dãy đen LIỀN NHAU.

        Đo trên robot 03/08, chặng lùi khỏi kệ:
            cảm biến [0,1,1,0,1,1]   ADC [504, 0, 106, 454, 0, 0]   ngưỡng 151
        Bốn mắt "đen" nhưng ĐỨT QUÃNG. back_to_intersection() nhận nhầm, dừng khi
        còn cách C0R0 khá xa và vẫn gần kệ, rồi tiến bù 12cm VỀ PHÍA KỆ và xoay →
        chạm kệ. Bộ lọc liền-nhau đã có ở exit_start_zone nhưng quên áp cho đây.
        """
        raw = [v / 1023 for v in (504, 0, 106, 454, 0, 0)]
        self.assertGreaterEqual(sum(LineSensor.digital_from_raw(raw)),
                                config.INTERSECTION_THRESHOLD,
                                "tiền đề: ngưỡng thích nghi ĐANG gọi đây là giao lộ")
        self.assertLess(LineSensor.day_den_dam_dai_nhat(raw),
                        config.INTERSECTION_THRESHOLD,
                        "dãy liền nhau phải bác bỏ nó")

    """Phân biệt giao lộ THẬT với mép vạch mờ — bằng đúng 2 số đo trên robot."""

    def test_real_C0R0_signature_counts_as_strong_evidence(self):
        raw = [v / 1023 for v in (921, 921, 0, 0, 0, 0)]
        self.assertGreaterEqual(LineSensor.dem_den_dam(raw),
                                config.INTERSECTION_THRESHOLD)

    def test_mascot_print_has_enough_black_eyes_but_they_are_NOT_CONTIGUOUS(self):
        """⚠️ HỒI QUY: đếm TỔNG số mắt đen là chưa đủ.

        Đo trên robot 03/08, hai lần đọc cùng cho 4 mắt đen đậm — bộ lọc chỉ đếm
        tổng cho cả hai lọt qua, robot chốt nhầm pose = C0R0 khi còn cách ~20cm,
        route bỏ mất lệnh forward, advance đâm ngay vào C0R0 thật và dừng hẳn.
        """
        in_hinh = [v / 1023 for v in (21, 515, 0, 0, 5, 917)]
        that = [v / 1023 for v in (917, 914, 0, 0, 0, 0)]
        self.assertEqual(LineSensor.dem_den_dam(in_hinh),
                         LineSensor.dem_den_dam(that),
                         "tiền đề: đếm TỔNG không phân biệt được hai cái")
        self.assertLess(LineSensor.day_den_dam_dai_nhat(in_hinh),
                        config.INTERSECTION_THRESHOLD,
                        "mắt sáng kẹp giữa = hình in, vạch line là dải LIỀN")
        self.assertGreaterEqual(LineSensor.day_den_dam_dai_nhat(that),
                                config.INTERSECTION_THRESHOLD)

    def test_alignment_false_positive_does_not(self):
        """ADC 224/232 lọt dưới ngưỡng THÍCH NGHI (248) nhưng KHÔNG phải đen."""
        raw = [v / 1023 for v in (224, 232, 0, 0, 263, 826)]
        self.assertEqual(sum(LineSensor.digital_from_raw(raw)),
                         config.INTERSECTION_THRESHOLD,
                         "tiền đề: ngưỡng thích nghi ĐANG gọi đây là giao lộ")
        self.assertLess(LineSensor.dem_den_dam(raw), config.INTERSECTION_THRESHOLD,
                        "ngưỡng đen ĐẬM phải bác bỏ nó")


class TestAdvanceKhiCongHang(unittest.TestCase):
    """Cõng hàng thì advance phải BỎ QUA siêu âm và đi tới hết line.

    ⚠️ HỒI QUY: đo trên robot 03/08, chặng giao hàng — vừa rời giao lộ đã đọc
    9.4cm rồi 10.2cm, lùi 0.8s mà số chỉ đổi 1.6cm. Thả xong hàng và gập càng thì
    CÙNG cảm biến đó đọc 100.0cm. Kiện trên càng chắn chùm sóng, nên chặn cứng
    kích hoạt ngay khi robot vừa rời giao lộ và nó THẢ HÀNG GIỮA ĐƯỜNG.
    (check_load_blocks_sonar trước đây kết luận "không chắn" vì chỉ đặt PALLET
    TRẦN — thiếu 4 khối mút cao 40mm, chính chúng mới chắn.)
    """

    def _motion(self, frames):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m.stop = MagicMock()
        m.stop_gently = MagicMock()
        m.forward = MagicMock()
        m._escape_intersection = MagicMock(return_value=True)
        m.read_line_sensor_adc = lambda: [0] * 6
        seq = list(frames)
        m.follow_line = lambda speed: (False, seq.pop(0) if len(seq) > 1 else seq[0])
        return m

    def test_carrying_ignores_the_blocked_reading_and_runs_to_end_of_line(self):
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 20 + [[0] * 6])
        m.dang_cong_hang = True
        m.get_distance = lambda *a, **k: 9.4        # bị kiện chắn, đứng yên
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertTrue(m.advance_to_end(timeout=3.0))
        ghi = "\n".join(nk.output)
        self.assertIn("ĐANG CÕNG HÀNG", ghi)
        self.assertIn("đã hết line", ghi)
        self.assertNotIn("CHẶN CỨNG", ghi)

    def test_not_carrying_still_uses_the_sonar(self):
        """Không cõng hàng thì mọi chặn siêu âm giữ nguyên — không nới lỏng gì."""
        m = self._motion([[0, 0, 1, 1, 0, 0]] * 400)
        m.dang_cong_hang = False
        m.get_distance = lambda *a, **k: 9.4
        with self.assertLogs("control.motion", level="WARNING") as nk:
            self.assertTrue(m.advance_to_end(timeout=3.0))
        self.assertIn("CHẶN CỨNG", "\n".join(nk.output))


class TestNguongThichNghiDoiCoDenThat(unittest.TestCase):
    """Ngưỡng thích nghi chỉ có nghĩa khi trên thanh CÓ CÁI GÌ ĐÓ ĐEN THẬT.

    ⚠️ HỒI QUY (robot 03/08): robot đứng trên TẤM IN khu nhà máy —
        ADC [626, 750, 642, 863, 624, 555]   ngưỡng thích nghi 667   → [1,0,1,0,1,1]
    Không mắt nào đen (tối nhất 555/1023) nhưng 4 mắt bị gọi là "thấy line", vì
    công thức chia tỉ lệ trên dải sáng-tối của CHÍNH lần đọc đó. Hậu quả: advance
    tưởng vẫn đang bám line, không bao giờ thấy "hết line", robot chạy đè qua khu
    nhà máy rồi thò càng ra ngoài mép sa bàn. Thể lệ: rời sa bàn = bị reset.
    """

    def test_all_grey_print_reads_as_NO_line(self):
        raw = [v / 1023 for v in (626, 750, 642, 863, 624, 555)]
        self.assertEqual(sum(LineSensor.digital_from_raw(raw)), 0,
                         "tấm in xám phải đọc ra KHÔNG có line")

    def test_a_real_line_still_uses_the_adaptive_threshold(self):
        """Có đen thật thì giữ nguyên ngưỡng thích nghi — đừng phá cái đang chạy."""
        raw = [v / 1023 for v in (917, 914, 0, 0, 0, 0)]
        self.assertGreater(LineSensor.nguong_cho(raw),
                           config.LINE_THRESHOLD / 1023.0,
                           "ngưỡng thích nghi phải CAO hơn ngưỡng tuyệt đối ở đây")
        self.assertEqual(sum(LineSensor.digital_from_raw(raw)), 4)

    def test_dim_light_still_works(self):
        """Ánh sáng tối đi (mọi giá trị tụt) vẫn phải bắt được vạch — lý do có
        ngưỡng thích nghi ngay từ đầu."""
        raw = [v / 1023 for v in (600, 590, 20, 15, 580, 610)]
        self.assertEqual(sum(LineSensor.digital_from_raw(raw)), 2)


class TestThuTuThaVaNangCang(unittest.TestCase):
    """THẢ → LÙI → NÂNG. Nâng càng khi còn đứng trên kiện là XÚC NÓ LÊN LẠI.

    ⚠️ HỒI QUY (robot 03/08): thả xong ở Samsung, robot nâng càng NGAY TẠI CHỖ nên
    xúc lại chính kiện vừa đặt, rồi mang sang thả ở Hana. HAI kiện sai nhà máy mà
    log vẫn báo thả OK và packages_delivered vẫn cộng — lỗi KHÔNG có tín hiệu báo.
    """

    def _lift(self):
        lift = MagicMock()
        lift.dropoff_left.return_value = True
        lift.dropoff_right.return_value = True
        return lift

    def test_retreat_happens_between_drop_and_raise(self):
        from control.handling import drop_side
        thu_tu = []
        lift = self._lift()
        lift.dropoff_right.side_effect = lambda: thu_tu.append("tha") or True
        lift.raise_after_drop.side_effect = lambda s: thu_tu.append("nang")
        drop_side(lift, "right", last=False, lui=lambda: thu_tu.append("lui"))
        self.assertEqual(thu_tu, ["tha", "lui", "nang"])

    def test_stow_also_waits_for_the_retreat(self):
        from control.handling import drop_side
        thu_tu = []
        lift = self._lift()
        lift.dropoff_left.side_effect = lambda: thu_tu.append("tha") or True
        lift.stow_forks.side_effect = lambda s: thu_tu.append("gap")
        drop_side(lift, "left", last=True, lui=lambda: thu_tu.append("lui"))
        self.assertEqual(thu_tu, ["tha", "lui", "gap"])

    def test_raise_still_happens_when_IR_says_the_drop_failed(self):
        """BẤT BIẾN cũ phải giữ: càng nằm thấp mà chạy tiếp là cạ sàn/vướng kệ."""
        from control.handling import drop_side
        lift = self._lift()
        lift.dropoff_right.return_value = False
        self.assertFalse(drop_side(lift, "right", last=False, lui=lambda: None))
        lift.raise_after_drop.assert_called_once_with("right")

    def test_missing_retreat_callback_warns_loudly(self):
        """Quên truyền bước lùi = quay lại đúng lỗi cũ → phải kêu, đừng im lặng."""
        from control.handling import drop_side
        lift = self._lift()
        with self.assertLogs("control.handling", level="WARNING") as nk:
            drop_side(lift, "right", last=False)
        self.assertIn("xúc nó lên lại", "\n".join(nk.output))


class TestNangThemKhiLuonCang(unittest.TestCase):
    """raise_to_insert() nâng THÊM LIFT_INSERT_EXTRA để mũi càng nhỉnh hơn đáy khe.

    ⚠️ Bài này tồn tại vì một lỗi thật: bản đầu gọi self._stop_motors() — một hàm
    KHÔNG TỒN TẠI — mà cả 4 bộ test vẫn xanh, vì không bài nào chạy qua đường đó.
    Trên robot thì nó nổ AttributeError giữa lúc càng đang đi lên.
    """

    def _lift(self):
        lift = object.__new__(Lift)
        for ten in ("_left_en", "_left_up", "_left_down", "_right_up", "_right_down"):
            setattr(lift, ten, MagicMock())
        lift.go_to_level = MagicMock()
        lift._stop_all = MagicMock()
        return lift

    def test_extra_raise_runs_and_stops_the_motors(self):
        lift = self._lift()
        with patch.object(config, "LIFT_INSERT_EXTRA", 0.05):
            lift.raise_to_insert(1)
        lift.go_to_level.assert_called_once_with(1)
        lift._left_up.on.assert_called()
        lift._right_up.on.assert_called()
        lift._stop_all.assert_called_once()

    def test_zero_extra_keeps_the_old_behaviour(self):
        lift = self._lift()
        with patch.object(config, "LIFT_INSERT_EXTRA", 0.0):
            lift.raise_to_insert(2)
        lift.go_to_level.assert_called_once_with(2)
        lift._stop_all.assert_not_called()

    def test_no_extra_raise_at_floor_level(self):
        """Tầng 0 = sàn; nâng thêm ở đó là đội càng lên khỏi sàn vô cớ."""
        lift = self._lift()
        with patch.object(config, "LIFT_INSERT_EXTRA", 0.05):
            lift.raise_to_insert(0)
        lift._stop_all.assert_not_called()


class TestBuLechTheoTang(unittest.TestCase):
    """Bù lệch 2 càng phải khai báo được RIÊNG cho từng tầng.

    ⚠️ Đo trên robot 03/08: tầng 1 hai càng khớp, tầng 2 CÀNG PHẢI NÂNG THIẾU nên
    luồn vào không tới khe pallet — lùi ra chỉ càng trái bốc được kiện. Một hằng số
    LIFT_*_EXTRA cho MỌI tầng không tả được chuyện đó: dây curoa mỗi bên căng khác
    nhau và độ trượt tăng theo quãng chạy, nên sai lệch ở tầng 2 (3.9s) lớn hơn hẳn
    tầng 1 (0.8s).
    """

    def _lift(self):
        return object.__new__(Lift)

    def test_per_level_override_beats_the_shared_constant(self):
        lift = self._lift()
        with patch.object(config, "LIFT_RIGHT_EXTRA", 0.050):
            with patch.object(config, "LIFT_RIGHT_EXTRA_BY_LEVEL", {2: 0.300}):
                t1 = lift._level_time(1, "right", raising=True)
                t2 = lift._level_time(2, "right", raising=True)
        self.assertAlmostEqual(t1, config.LIFT_TIME_SHELF_1 + 0.050, places=3,
                               msg="tầng KHÔNG khai báo phải dùng hằng số chung")
        self.assertAlmostEqual(t2, config.LIFT_TIME_SHELF_2 + 0.300, places=3,
                               msg="tầng có khai báo phải dùng số riêng")

    def test_empty_dict_keeps_the_old_behaviour(self):
        lift = self._lift()
        with patch.object(config, "LIFT_LEFT_EXTRA", -0.040):
            with patch.object(config, "LIFT_LEFT_EXTRA_BY_LEVEL", {}):
                t = lift._level_time(2, "left", raising=True)
        self.assertAlmostEqual(t, config.LIFT_TIME_SHELF_2 - 0.040, places=3)

    def test_lowering_is_untouched(self):
        """Bù khi HẠ vẫn dùng hằng số riêng của nó — đừng đụng vào."""
        lift = self._lift()
        with patch.object(config, "LIFT_RIGHT_EXTRA_BY_LEVEL", {2: 9.9}):
            t = lift._level_time(2, "right", raising=False)
        self.assertAlmostEqual(t, config.LIFT_TIME_SHELF_2
                               + config.LIFT_RIGHT_LOWER_EXTRA, places=3)


class TestPoseSauXuatPhat(unittest.TestCase):
    """Căn giữa chạy tới C0R0 thì pose PHẢI là C0R0, không phải START.

    ⚠️ HỒI QUY — đây là lỗi đâm kệ ngày 03/08, và nó KHÔNG nằm ở siêu âm.
    exit_start_zone() căn giữa line R0, và bước căn đó có lúc chạy tới tận giao lộ
    đầu tiên, có lúc không (tuỳ robot đặt lệch bao nhiêu trong ô 400x400mm). Khi
    nó tới nơi mà pose vẫn báo START, route "tiến 1 giao lộ" sẽ rời C0R0 rồi đi
    tiếp 35cm và bắt MẢNG ĐEN CHÂN KỆ làm giao lộ. advance khởi hành khi robot đã
    cách kệ 3.3cm; log ghi "✅ tới Kệ 3"; bước luồn càng húc thẳng vào kệ.
    Tính bất định của bước căn giữa chính là "lúc dừng đúng, lúc lao vào kệ".
    """

    def test_standing_on_the_first_intersection_gives_the_C0R0_pose(self):
        self.assertEqual(navigation.pose_sau_xuat_phat(True),
                         (navigation.NODE_DAU_TU_START, navigation.TOWARD_SHELVES))

    def test_not_standing_on_it_gives_START_POSE(self):
        self.assertEqual(navigation.pose_sau_xuat_phat(False), navigation.START_POSE)

    def test_route_from_C0R0_to_shelf3_no_longer_counts_an_intersection(self):
        """Đứng trên C0R0 rồi thì chỉ còn ADVANCE — không được tiến giao lộ nào nữa."""
        route, _ = navigation.plan(navigation.pose_sau_xuat_phat(True), "SHELF0")
        self.assertEqual(route, [("advance",)],
                         "còn lệnh forward = robot sẽ đi lố qua kệ")

    def test_route_from_START_still_has_the_one_forward(self):
        route, _ = navigation.plan(navigation.pose_sau_xuat_phat(False), "SHELF0")
        self.assertEqual(route, [("forward", 1), ("advance",)])


class TestTurnRecenterAfterForward(unittest.TestCase):
    """Xoay sau khi TIẾN tới giao lộ phải có bước tiến bù, như chiều lùi đã có.

    Thanh cảm biến ở đầu xe, trục bánh cách nó 12cm về sau. Tiến tới giao lộ thì cảm
    biến TRÊN vạch còn trục còn cách vạch 12cm — xoay lúc đó là quay quanh điểm nằm
    TRƯỚC giao lộ, xoay xong cảm biến văng ra vùng trắng.
    Đo trên robot (smoke option 8):
        xoay sau khi LÙI  → [0,0,0,1,1,0]  còn thấy line
        xoay sau khi TIẾN → [0,0,0,0,0,0]  TRẮNG HẾT → route gãy
    """

    def _motion(self):
        m = object.__new__(Motion)
        m.last_route_progress = []
        m.forward = MagicMock()
        m.stop = MagicMock()
        m.turn_left_90 = MagicMock()
        m.turn_right_90 = MagicMock()
        m.navigate_intersections = MagicMock(return_value=True)
        m.back_to_intersection = MagicMock(return_value=True)
        m.advance_to_end = MagicMock(return_value=True)
        return m

    def test_nudges_forward_before_turning_after_a_forward_leg(self):
        m = self._motion()
        with patch.object(config, "TURN_RECENTER_TIME", 0.02):
            self.assertTrue(m.execute_route([("forward", 2), ("right",)]))
        m.forward.assert_called_once_with(config.REVERSE_RECENTER_SPEED)
        m.turn_right_90.assert_called_once()

    def test_no_nudge_after_a_reverse_leg(self):
        """back_to_intersection đã tự tiến bù rồi — bù thêm lần nữa là đi lố."""
        m = self._motion()
        with patch.object(config, "TURN_RECENTER_TIME", 0.02):
            self.assertTrue(m.execute_route([("back", 1), ("right",)]))
        m.forward.assert_not_called()

    def test_no_nudge_when_turn_is_the_first_command(self):
        """Xoay ngay đầu route: robot đang đứng sẵn ở đâu đó, không tự ý tiến."""
        m = self._motion()
        with patch.object(config, "TURN_RECENTER_TIME", 0.02):
            self.assertTrue(m.execute_route([("right",), ("forward", 1)]))
        m.forward.assert_not_called()

    def test_two_turns_in_a_row_nudge_only_once(self):
        """Xoay 180° = 2 lệnh xoay liền nhau; chỉ bù trước cái ĐẦU."""
        m = self._motion()
        with patch.object(config, "TURN_RECENTER_TIME", 0.02):
            self.assertTrue(m.execute_route([("forward", 1), ("right",), ("right",)]))
        self.assertEqual(m.forward.call_count, 1)


class TestBackMinTravel(unittest.TestCase):
    """Lùi ra khỏi kệ không được nhận giao lộ trong những giây đầu.

    Từ điểm cuối tới giao lộ là 35.4cm, robot đứng cách kệ ~12.9cm → cảm biến phải
    lùi HƠN 20cm mới tới giao lộ thật. Nhận nhầm sớm thì bước TIẾN BÙ ngay sau đó
    (1.3s về phía kệ) đẩy robot trở lại CHẠM KỆ — đã gặp thật ở option 8.
    """

    def _motion(self, luon_bao_giao_lo=True):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m._last_error = 0.0
        m.forward = MagicMock()
        m.backward = MagicMock()
        m.stop = MagicMock()
        m._escape_intersection = MagicMock()
        m.follow_line = MagicMock(return_value=(luon_bao_giao_lo, [1, 1, 1, 1, 0, 0]))
        # Chữ ký giao lộ THẬT: 4 mắt đen đậm LIỀN NHAU (đo trên robot 03/08).
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (917, 914, 0, 0, 0, 0)]
        return m

    def _motion_seq(self, frames):
        m = self._motion()
        seq = list(frames)

        def follow(_speed, reverse=False):
            v = seq.pop(0) if len(seq) > 1 else seq[0]
            return sum(v) >= config.INTERSECTION_THRESHOLD, v

        m.follow_line = follow
        return m

    def test_ignores_intersection_before_seeing_a_plain_line(self):
        """Báo giao lộ ngay từ đầu (còn trên mảng đen của điểm cuối) → bỏ qua."""
        giao_lo = [1, 1, 1, 1, 0, 0]
        vach = [0, 0, 1, 1, 0, 0]
        m = self._motion_seq([giao_lo] * 5 + [vach] * 3 + [giao_lo] * 50)
        with patch.object(config, "REVERSE_RECENTER_TIME", 0.0):
            self.assertTrue(m.back_to_intersection(1))

    def test_accepts_intersection_after_a_plain_line(self):
        """Đã thấy vạch thường rồi thì giao lộ kế tiếp phải được chấp nhận."""
        m = self._motion_seq([[0, 0, 1, 1, 0, 0]] * 3 + [[1, 1, 1, 1, 0, 0]] * 50)
        with patch.object(config, "REVERSE_RECENTER_TIME", 0.0):
            self.assertTrue(m.back_to_intersection(1))

    def test_no_time_based_gate_left(self):
        """Không còn cổng chặn theo THỜI GIAN — nó phụ thuộc cm/s chưa ai đo."""
        self.assertFalse(hasattr(config, "BACK_MIN_TRAVEL_TIME"),
                         "mốc thời gian đã bị thay bằng bằng chứng 'đã thấy vạch'")


class TestBackMinTravelCm(unittest.TestCase):
    """Chặng lùi bỏ qua giao lộ cho tới khi ĐÃ LÙI ĐỦ XA (đo bằng encoder).

    ⚠️ Vì sao không lọc bằng HÌNH DẠNG tín hiệu: đo trên robot 03/08, chữ ký GIẢ ở
    chân kệ và chữ ký THẬT ở giao lộ CÙNG MỘT DẠNG —
        giả  ADC [504,   0, 106, 454,   0,   0]   đen ở 2,3,5,6
        thật ADC [  0, 703,   0,   0,   0, 926]   đen ở 1,3,4,5
    cả hai đều 4 mắt đen với đúng một mắt hở. Bộ lọc "dãy liền nhau" (đúng cho
    exit_start_zone) bác luôn cả cái thật: robot bỏ qua giao lộ rồi lùi tới 3.2s,
    vượt xa C0R0. Quãng đường thì phân biệt được — mảng đen chân kệ nằm NGAY ĐẦU
    chặng lùi, giao lộ thì cách một đoạn.
    """

    def _motion(self, xung_moi_lan: int, co_encoder: bool = True):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m._last_error = 0.0
        m.forward = MagicMock()
        m.backward = MagicMock()
        m.stop = MagicMock()
        m._escape_intersection = MagicMock()
        m.tien_bu_cm = MagicMock(return_value=True)
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (0, 703, 0, 0, 0, 926)]
        n = config.LINE_SENSOR_COUNT
        vach = [0] * n
        vach[n // 2 - 1] = vach[n // 2] = 1
        dem = {"n": 0}

        def fl(speed, reverse=False):
            dem["n"] += 1
            return (dem["n"] > 2, [1] * n if dem["n"] > 2 else vach)

        m.follow_line = fl
        m._encoder_left = _EncoderGia(xung_moi_lan, co_encoder)
        m._encoder_right = _EncoderGia(0, co_encoder)
        return m

    def test_plain_line_inflated_by_the_adaptive_threshold_is_rejected(self):
        """⚠️ HỒI QUY: vạch THƯỜNG bị ngưỡng thích nghi thổi thành "giao lộ".

        Đo trên robot 03/08, chặng lùi: ADC [228, 481, 0, 0, 0, 925] ngưỡng 277.
        Line thật chỉ ở mắt 3,4,5 (ADC 0); mắt 1 đọc 228 — KHÔNG đen, chỉ lọt dưới
        ngưỡng thích nghi. back_to_intersection nhận nhầm, dừng khi mới lùi 5cm,
        rồi tiến bù 12cm VỀ PHÍA KỆ và xoay → va vào kệ.
        """
        raw = [v / 1023 for v in (228, 481, 0, 0, 0, 925)]
        self.assertGreaterEqual(sum(LineSensor.digital_from_raw(raw)),
                                config.INTERSECTION_THRESHOLD,
                                "tiền đề: ngưỡng thích nghi ĐANG gọi đây là giao lộ")
        self.assertLess(LineSensor.dem_den_dam(raw), config.INTERSECTION_THRESHOLD,
                        "đếm mắt đen ĐẬM phải bác nó")

    def test_real_junction_survives_the_strict_count(self):
        """Giao lộ thật (4 mắt đen đậm, một mắt hở) vẫn phải được nhận."""
        raw = [v / 1023 for v in (0, 703, 0, 0, 0, 926)]
        self.assertGreaterEqual(LineSensor.dem_den_dam(raw),
                                config.INTERSECTION_THRESHOLD)
        self.assertLess(LineSensor.day_den_dam_dai_nhat(raw),
                        config.INTERSECTION_THRESHOLD,
                        "đòi LIỀN NHAU sẽ bác nhầm nó — đã thử, robot lùi mất 3.2s")

    def test_intersection_within_the_first_few_cm_is_ignored(self):
        """Chưa lùi đủ xa thì tín hiệu giao lộ là mảng đen chân kệ, không phải C0R0."""
        m = self._motion(xung_moi_lan=0)          # không nhúc nhích
        with self.assertLogs("control.motion", level="INFO") as nk:
            self.assertFalse(m.back_to_intersection(1, timeout=0.6))
        self.assertIn("mới lùi", "\n".join(nk.output))
        self.assertGreater(m.backward.call_count, 1,
                           "⚠️ HỒI QUY: follow_line() tự stop() khi thấy giao lộ. Bác "
                           "tín hiệu mà không ra lệnh chạy lại thì vòng sau nó lại "
                           "thấy, lại phanh — robot đứng im vĩnh viễn. Đo trên robot "
                           "03/08: kẹt ở 4.7cm suốt 8 giây rồi timeout.")

    def test_intersection_after_enough_travel_is_accepted(self):
        can = int(config.BACK_MIN_TRAVEL_CM * config.ENCODER_PULSES_PER_CM) + 10
        m = self._motion(xung_moi_lan=can)        # đủ ngay nhịp đầu
        self.assertTrue(m.back_to_intersection(1, timeout=2.0))

    def test_no_encoder_falls_back_instead_of_reversing_forever(self):
        """⚠️ HỒI QUY: thiếu encoder mà vẫn áp cổng thì lui_cm luôn = 0 → lùi vô hạn."""
        m = self._motion(xung_moi_lan=0, co_encoder=False)
        with self.assertLogs("control.motion", level="WARNING") as nk:
            self.assertTrue(m.back_to_intersection(1, timeout=2.0))
        self.assertIn("KHÔNG đo được quãng", "\n".join(nk.output))


class TestReverseRecenter(unittest.TestCase):
    """Đoạn tiến bù sau khi lùi phải dùng ĐÚNG tốc độ mà thời gian được đo ra.

    Nó chạy MÙ theo thời gian nên quãng đường tỉ lệ thẳng với tốc độ. Buộc nó vào
    REVERSE_SPEED là mỗi lần chỉnh tốc độ lùi lại âm thầm phá hằng số đã calibrate —
    đã gặp thật: nâng REVERSE_SPEED 35 → 40 làm robot tiến bù quá vạch, xoay xong
    mất line (option 8).
    """

    def test_recenter_uses_its_own_calibrated_speed(self):
        m = object.__new__(Motion)
        m._aborted = lambda: False
        m._last_error = 0.0
        m.forward = MagicMock()
        m.backward = MagicMock()
        # Chữ ký giao lộ THẬT: 4 mắt đen đậm LIỀN NHAU (đo trên robot 03/08).
        m.read_line_sensor_raw = lambda: [v / 1023 for v in (917, 914, 0, 0, 0, 0)]
        m.stop = MagicMock()
        m._escape_intersection = MagicMock()
        m.follow_line = MagicMock(return_value=(True, [0, 0, 1, 1, 0, 0]))
        with patch.object(config, "REVERSE_RECENTER_TIME", 0.02):
            m.back_to_intersection(1, base_speed=99)
        self.assertTrue(m.forward.called, "phải có đoạn tiến bù")
        self.assertEqual(m.forward.call_args.args[0], config.REVERSE_RECENTER_SPEED,
                         "tiến bù phải dùng REVERSE_RECENTER_SPEED, không phải base_speed")

    def test_recenter_speed_is_above_the_dead_zone(self):
        self.assertGreater(config.REVERSE_RECENTER_SPEED, config.MOTOR_MIN_DUTY)


class TestNguongTuongDoi(unittest.TestCase):
    """Ngưỡng đen/trắng phải trôi theo ánh sáng, không cố định.

    QTR-8A đo PHẢN XẠ: tối đi thì nền trắng phản xạ ít hơn, mắt ở RÌA vạch tụt xuống
    dưới ngưỡng cố định và bị đếm là đen → đủ 4 mắt là GIAO LỘ GIẢ giữa đoạn thẳng.
    Đo trên robot buổi tối 02/08. Thể lệ ghi ánh sáng sân thi KHÔNG đảm bảo ổn định.

    KHÔNG chữa được bằng cách nâng INTERSECTION_THRESHOLD lên 5 — C0R0 là NGÃ BA,
    chỉ cho 4/6 mắt.
    """

    def _dig(self, adc):
        return LineSensor.digital_from_raw([v / 1023 for v in adc])

    def test_dim_light_edge_pixels_are_not_counted_as_line(self):
        """Ca đã gặp: buổi tối, 2 mắt rìa đọc ~190 — dưới LINE_THRESHOLD = 200."""
        toi = [600, 190, 10, 15, 185, 610]
        with patch.object(config, "LINE_ADAPTIVE", False):
            cu = self._dig(toi)
        moi = self._dig(toi)
        self.assertGreaterEqual(sum(cu), config.INTERSECTION_THRESHOLD,
                                "tiền đề: ngưỡng cố định PHẢI nhận nhầm ca này")
        self.assertLess(sum(moi), config.INTERSECTION_THRESHOLD,
                        "ngưỡng tương đối phải KHÔNG nhận nhầm là giao lộ")

    def test_t_junction_still_detected_in_dim_light(self):
        """Ngã ba C0R0 cho đúng 4/6 — phải VẪN nhận ra, không thì mất giao lộ thật."""
        self.assertGreaterEqual(sum(self._dig([610, 600, 5, 5, 5, 5])),
                                config.INTERSECTION_THRESHOLD)

    def test_all_white_stays_all_white(self):
        """Mất line: dải quá hẹp → rơi về ngưỡng tuyệt đối, không bịa ra mắt đen."""
        self.assertEqual(sum(self._dig([600, 610, 595, 605, 600, 608])), 0)

    def test_all_black_stays_all_black(self):
        """Giữa ngã tư: dải hẹp → tuyệt đối, phải ra đủ 6 mắt đen."""
        self.assertEqual(sum(self._dig([10, 8, 5, 5, 6, 9])), 6)

    def test_bright_light_unchanged(self):
        """Ban ngày vẫn cho đúng kết quả cũ — không phá thứ đang chạy được."""
        self.assertEqual(self._dig([925, 900, 10, 15, 910, 920]), [0, 0, 1, 1, 0, 0])

    def test_threshold_follows_the_light_level(self):
        sang = LineSensor.nguong_cho([v / 1023 for v in [925, 900, 10, 15, 910, 920]])
        toi = LineSensor.nguong_cho([v / 1023 for v in [600, 590, 10, 15, 585, 610]])
        self.assertGreater(sang, toi, "trời sáng hơn thì ngưỡng phải cao hơn")


class TestLineCenterOffset(unittest.TestCase):
    """Điểm đặt bám line phải là "càng thẳng khe pallet", không phải "giữa thanh".

    Số ADC dưới đây ĐO THẬT trên robot 02/08 bằng test_motion option 5, ở hai tư thế
    do người vận hành xác định bằng mắt. Giữ nguyên số gốc để test này vừa là kiểm
    thử vừa là BẢN GHI phép đo.
    """

    # đo thật: thanh 6 mắt, ngưỡng LINE_THRESHOLD, giá trị nhỏ = đen
    LECH = [908, 19, 0, 0, 926, 926]     # người vận hành: robot LỆCH
    CHUAN = [891, 925, 0, 0, 0, 911]     # người vận hành: robot CHUẨN

    def _err(self, adc):
        m = object.__new__(Motion)
        m._last_error = 0.0
        return m.compute_line_error_analog([v / 1023 for v in adc])

    def test_offset_equals_the_raw_error_at_the_aligned_pose(self):
        """Phép ĐO ở tư thế đúng cho +0.50 — và đó chính là giá trị của điểm đặt."""
        self.assertAlmostEqual(self._err(self.CHUAN),
                               config.LINE_CENTER_OFFSET, delta=0.1)

    def test_steering_sees_zero_error_at_the_aligned_pose(self):
        """Ở tư thế ĐÚNG, luật lái phải KHÔNG sinh hiệu chỉnh — 2 bánh bằng nhau.

        Đây mới là điều thật sự quan trọng: không có điểm đặt thì follow_line lái để
        đưa sai số THÔ về 0, tức chủ động kéo robot RA KHỎI tư thế đúng. Mọi lần
        tiếp cận kệ chệch ~5mm, càng vướng mép pallet, IR không xác nhận.
        """
        m = object.__new__(Motion)
        m._last_error = 0.0
        m._drive = MagicMock()
        m._steer([v / 1023 for v in self.CHUAN], 40)
        trai, phai = m._drive.call_args.args[0], m._drive.call_args.args[1]
        self.assertAlmostEqual(trai, phai, delta=2.0,
                               msg="tư thế đúng mà vẫn lái = kéo robot đi khỏi nó")

    def test_without_offset_the_aligned_pose_would_be_steered_away(self):
        """Chứng minh ngược lại: bỏ điểm đặt thì đúng tư thế vẫn bị lái."""
        m = object.__new__(Motion)
        m._last_error = 0.0
        m._drive = MagicMock()
        with patch.object(config, "LINE_CENTER_OFFSET", 0.0):
            m._steer([v / 1023 for v in self.CHUAN], 40)
        trai, phai = m._drive.call_args.args[0], m._drive.call_args.args[1]
        self.assertGreater(abs(trai - phai), 2.0)


class TestClampCorrection(unittest.TestCase):
    """Hiệu chỉnh bám line không được đẩy bánh chậm xuống dưới vùng chết.

    LINE_KP = 16 chỉnh cho SPEED_DEFAULT = 50, nhưng bám line còn chạy ở 32%
    (APPROACH_SLOW_SPEED, INSERT_SPEED) mà vùng chết là ~25%. Không kẹp thì chỉ cần
    sai số 0.44 là bánh trong ĐỨNG HẲN và robot xoay quanh nó thay vì lượn — đo thật
    trên robot ở smoke option 2: đi chệch hướng, một càng thọc sâu hơn càng kia.
    """

    def _banh(self, err, base):
        c = Motion._clamp_correction(config.LINE_KP * err, base)
        return base + c, base - c

    def test_slow_wheel_never_enters_dead_zone(self):
        for base in (32, 40, 50, 60):
            for err in (0.2, 0.5, 1.0, 1.5, 2.5, -2.5):
                l, r = self._banh(err, base)
                self.assertGreaterEqual(
                    min(l, r), config.MOTOR_MIN_DUTY,
                    f"base={base} sai số={err}: bánh chậm {min(l, r):.1f} "
                    f"dưới vùng chết {config.MOTOR_MIN_DUTY}")

    def test_small_errors_pass_through_untouched(self):
        """Sai số nhỏ KHÔNG bị đụng tới — kẹp chỉ chặn phần vượt.

        Suy từ hằng số, KHÔNG viết cứng: bản trước ghi thẳng (3.2, base 32) và tự
        gãy khi MOTOR_MIN_DUTY lên 30 (lúc đó base 32 chỉ còn ±2). Cùng loại mong
        manh với test ngưỡng ORB/HSV đã sửa sáng nay.
        """
        base = config.SPEED_DEFAULT
        nho = (base - config.MOTOR_MIN_DUTY) / 2      # chắc chắn dưới hạn mức
        self.assertGreater(nho, 0, "SPEED_DEFAULT phải cao hơn vùng chết")
        self.assertAlmostEqual(Motion._clamp_correction(nho, base), nho)
        self.assertAlmostEqual(Motion._clamp_correction(-nho, base), -nho)

    def test_higher_base_speed_buys_more_steering(self):
        """Muốn lái mạnh hơn thì NÂNG tốc độ nền, không phải bỏ kẹp."""
        lon = config.LINE_KP * 2.5      # sai số cực đại
        thap = Motion._clamp_correction(lon, config.MOTOR_MIN_DUTY + 5)
        cao = Motion._clamp_correction(lon, config.MOTOR_MIN_DUTY + 20)
        self.assertGreater(cao, thap)

    def test_every_line_following_speed_has_steering_headroom(self):
        """QUÉT MỌI tốc độ dùng với follow_line — lực lái = base − MOTOR_MIN_DUTY.

        Nâng MOTOR_MIN_DUTY mà quên nâng một tốc độ nào đó là chỗ ấy MẤT LÁI âm
        thầm: robot vẫn chạy, vẫn tới nơi, chỉ là tới trong tư thế lệch. Đã sót
        đúng như vậy: sửa INSERT_SPEED mà bỏ quên APPROACH_SLOW_SPEED (còn ±2) và
        REVERSE_SPEED (còn ±5) — hai chỗ tư thế quan trọng nhất.
        """
        thieu = []
        for ten in ("SPEED_DEFAULT", "ADVANCE_SPEED", "APPROACH_SLOW_SPEED",
                    "APPROACH_FAST_SPEED", "INSERT_SPEED", "REVERSE_SPEED"):
            base = getattr(config, ten)
            luc = base - config.MOTOR_MIN_DUTY
            if luc < 8:
                thieu.append(f"{ten}={base} → ±{luc}")
        self.assertEqual(
            thieu, [],
            "tốc độ không đủ lực lái (cần ≥ MOTOR_MIN_DUTY + 8): " + ", ".join(thieu))

    def test_insert_speed_leaves_usable_steering(self):
        """Bước LUỒN CÀNG phải còn lái được, không thì _forward_guided vô nghĩa.

        Ở INSERT_SPEED = 32 với MOTOR_MIN_DUTY = 30 thì lực lái chỉ còn ±2 — bám
        line lúc đó chỉ là hình thức. Đo trên robot: bò ~5.7cm/s rồi timeout.
        """
        luc_lai = config.INSERT_SPEED - config.MOTOR_MIN_DUTY
        self.assertGreaterEqual(
            luc_lai, 8,
            f"INSERT_SPEED={config.INSERT_SPEED} chỉ hơn vùng chết "
            f"{config.MOTOR_MIN_DUTY} là {luc_lai} — không đủ để lái")

    def test_disabled_when_min_duty_is_zero(self):
        with patch.object(config, "MOTOR_MIN_DUTY", 0):
            self.assertAlmostEqual(Motion._clamp_correction(40, 32), 40)

    def test_no_clamp_when_base_already_below_dead_zone(self):
        """base dưới vùng chết thì kẹp vô nghĩa — đừng đảo dấu hiệu chỉnh."""
        self.assertAlmostEqual(Motion._clamp_correction(40, 20), 40)


class TestForwardGuided(unittest.TestCase):
    """Tiến sát kệ phải CÓ LÁI khi còn thấy line, và chỉ chạy thẳng khi mất line.

    approach_shelf() và creep_until() trước đây chạy forward() MÙ suốt ~10cm cuối.
    Robot không đi thẳng tuyệt đối nên nó lệch dần, càng không luồn hết vào khe
    pallet, IR không báo có hàng → bốc hàng hỏng. Đây là mắt xích ĐẦU của chuỗi đó.
    """

    def _motion(self, adc):
        m = object.__new__(Motion)
        m._line_sensor = MagicMock()
        m._line_sensor.available = True
        m._last_error = 0.0
        m.read_line_sensor_raw = lambda: [v / 1023 for v in adc]
        m.forward = MagicMock()
        m._steer = MagicMock()
        m._drive_straight = MagicMock()
        m.follow_line = MagicMock()
        m.stop = MagicMock()
        return m

    def test_steers_while_line_is_visible(self):
        m = self._motion([900, 900, 10, 15, 900, 900])
        m._forward_guided(30)
        m._steer.assert_called_once()
        m.forward.assert_not_called()
        m._drive_straight.assert_not_called()

    def test_falls_back_to_straight_when_line_is_gone(self):
        """Line không kéo tới tận kệ thì phải giữ ĐÚNG hành vi cũ, không đứng im."""
        m = self._motion([900, 910, 905, 900, 908, 900])
        m._forward_guided(30)
        m.forward.assert_called_once_with(30)
        m._steer.assert_not_called()

    def test_falls_back_when_sensor_unavailable(self):
        m = self._motion([900, 900, 10, 15, 900, 900])
        m._line_sensor.available = False
        m._forward_guided(30)
        m.forward.assert_called_once_with(30)
        m._steer.assert_not_called()

    def test_all_black_goes_straight_and_NEVER_stops(self):
        """⚠️ HỒI QUY: sát kệ, viền đen của ô kệ làm MỌI mắt đen.

        Bản trước gọi follow_line(), mà follow_line() thấy giao lộ là gọi self.stop()
        rồi trả về — tức DỪNG MOTOR ngay giữa pha tiếp cận kệ. Đo trên robot: 6 dòng
        "Phát hiện giao lộ (active=6)" liên tiếp trong một pha tiếp cận.
        Ở đây chỉ cần phần LÁI. Mọi mắt đen thì sai số line là số rác → đi THẲNG.
        """
        m = self._motion([0, 0, 0, 0, 0, 0])
        m._forward_guided(30)
        m._drive_straight.assert_called_once_with(30)
        m.stop.assert_not_called()
        m.follow_line.assert_not_called()
        m._steer.assert_not_called()


class TestBackToIntersection(unittest.TestCase):
    """back_to_intersection — vòng lặp lùi tới giao lộ."""

    @classmethod
    def setUpClass(cls):
        cls.m = Motion()

    @classmethod
    def tearDownClass(cls):
        cls.m.cleanup()

    def setUp(self):
        # Lớp này dùng Motion() thật với chân GPIO GIẢ, nên encoder "khả dụng"
        # nhưng KHÔNG BAO GIỜ sinh xung — robot mô phỏng không hề nhúc nhích. Cổng
        # quãng-đường-tối-thiểu vì thế chặn mọi giao lộ, mà đó không phải thứ mấy
        # bài này kiểm. Tắt cổng ở đây; nó có bài riêng bên dưới.
        gate = patch.object(config, "BACK_MIN_TRAVEL_CM", 0.0)
        gate.start()
        self.addCleanup(gate.stop)
        n = config.LINE_SENSOR_COUNT
        # Vài nhịp đầu đọc VẠCH THƯỜNG (2 mắt giữa), rồi mới tới giao lộ (mọi mắt).
        # Không có mấy nhịp vạch thường đó thì back_to_intersection bỏ qua tín hiệu
        # giao lộ — nó đòi bằng chứng "robot đã rời khỏi mảng đen của điểm cuối"
        # trước khi tin. Xem TestBackMinTravel.
        vach = [1.0] * n
        for i in (n // 2 - 1, n // 2):
            vach[i] = 0.0
        # Lặp TUẦN HOÀN: vài nhịp vạch thường rồi tới giao lộ, rồi lại vạch...
        # Chặng thứ 2 của back_to_intersection(2) cũng cần thấy vạch thường trước,
        # nên không dùng danh sách cạn được.
        import itertools
        vong = itertools.cycle([vach] * 3 + [[0.0] * n] * 3)
        self.m.read_line_sensor_raw = lambda: next(vong)

    def test_stale_pd_error_is_cleared_before_and_after(self):
        """`_last_error` mang từ pha TIẾN sang sẽ tạo đạo hàm giả → giật một cái
        ngay lúc bắt đầu lùi (LINE_KD × chênh lệch). Và ngược lại khi quay về tiến."""
        seen = []
        real_follow = self.m.follow_line
        self.m.follow_line = lambda *a, **k: (seen.append(self.m._last_error),
                                              real_follow(*a, **k))[1]
        try:
            self.m._last_error = 2.5              # sai số còn lại của pha tiến
            self.assertTrue(self.m.back_to_intersection(1))
        finally:
            self.m.follow_line = real_follow

        self.assertEqual(seen[0], 0.0, "phải xoá sai số cũ TRƯỚC nhịp lùi đầu tiên")
        self.assertEqual(self.m._last_error, 0.0,
                         "phải trả về 0 để pha TIẾN kế tiếp không thừa hưởng dấu ngược")

    def test_multi_hop_escapes_intersection_between_hops(self):
        """Đứng ngay trên giao lộ vừa tới mà bám line tiếp thì nhận lại chính nó,
        chặng thứ 2 'xong' tức thì mà robot chưa đi đâu cả."""
        calls = []
        real_escape = self.m._escape_intersection
        self.m._escape_intersection = lambda speed=None, reverse=False: calls.append(reverse)
        try:
            self.assertTrue(self.m.back_to_intersection(2))
        finally:
            self.m._escape_intersection = real_escape
        self.assertEqual(calls, [True],
                         "chặng 2 phải LÙI khỏi giao lộ trước, chặng 1 thì không")

    def test_zero_count_is_a_noop(self):
        self.assertTrue(self.m.back_to_intersection(0))

    def test_abort_stops_immediately(self):
        self.m.abort_check = lambda: True
        try:
            self.assertFalse(self.m.back_to_intersection(1))
        finally:
            self.m.abort_check = None


class TestFitToRange(unittest.TestCase):
    """Kẹp tốc độ 2 bánh vào 0-100 phải GIỮ ĐỘ CHÊNH — độ chênh mới tạo ra góc lái."""

    def _diff(self, l, r):
        a, b = Motion._fit_to_range(l, r)
        return a - b, (a, b)

    def test_no_change_inside_range(self):
        self.assertEqual(Motion._fit_to_range(90.0, 10.0), (90.0, 10.0))

    def test_keeps_differential_when_over_100(self):
        """SPEED_DEFAULT=80 + correction 40 → (120, 40): phải ra (100, 20) chênh 80."""
        diff, pair = self._diff(120.0, 40.0)
        self.assertEqual(pair, (100.0, 20.0))
        self.assertEqual(diff, 80.0, "kẹp riêng từng bánh sẽ ăn mất 25% lực lái")

    def test_keeps_differential_when_below_zero(self):
        diff, pair = self._diff(30.0, -10.0)
        self.assertEqual(pair, (40.0, 0.0))
        self.assertEqual(diff, 40.0)

    def test_clamps_when_differential_wider_than_range(self):
        """Chênh > 100 thì phải đảo chiều một bánh mới đạt — đành kẹp, nhưng hợp lệ."""
        a, b = Motion._fit_to_range(150.0, -30.0)
        self.assertEqual((a, b), (100.0, 0.0))

    def test_always_in_range_and_diff_preserved_up_to_100(self):
        for l, r in ((120.0, 40.0), (40.0, 120.0), (-10.0, 30.0), (105.0, 25.0),
                     (150.0, -30.0), (50.0, 50.0)):
            with self.subTest(pair=(l, r)):
                a, b = Motion._fit_to_range(l, r)
                self.assertTrue(0.0 <= a <= 100.0 and 0.0 <= b <= 100.0)
                want = l - r
                # Giữ nguyên độ chênh nếu nó nằm trong dải; ngoài dải thì kẹp ±100
                expect = max(-100.0, min(100.0, want))
                self.assertAlmostEqual(a - b, expect)

    def test_current_speed_never_saturates_but_80_does(self):
        """Chốt lại con số: ở 50 chưa vượt dải, ở 80 thì vượt → lỗi này ngủ tới khi tăng tốc."""
        corr = config.LINE_KP * max(abs(w) for w in config.LINE_WEIGHTS)
        self.assertLessEqual(50 + corr, 100.0, "ở tốc độ 50 không được vượt dải")
        self.assertGreater(80 + corr, 100.0, "ở tốc độ 80 phải vượt dải (nếu không, test này lạc hậu)")


class TestContinuousIntersections(unittest.TestCase):
    """Chế độ đếm giao lộ KHÔNG dừng (config.CONTINUOUS_INTERSECTIONS)."""

    @classmethod
    def setUpClass(cls):
        cls.m = Motion()

    @classmethod
    def tearDownClass(cls):
        cls.m.cleanup()

    def setUp(self):
        self._saved = getattr(config, "CONTINUOUS_INTERSECTIONS", False)
        config.CONTINUOUS_INTERSECTIONS = True
        self.m.abort_check = None
        self.m._last_error = 0.0

    def tearDown(self):
        config.CONTINUOUS_INTERSECTIONS = self._saved
        self.m.abort_check = None

    def _feed(self, pattern):
        """pattern: list số mắt thấy line cho từng nhịp đọc."""
        n = config.LINE_SENSOR_COUNT
        thr = config.LINE_THRESHOLD / 1023.0
        seq = iter(pattern)

        def fake_raw():
            active = next(seq, 0)
            return [thr * 0.5] * active + [1.0] * (n - active)
        self.m.read_line_sensor_raw = fake_raw

    def test_counts_each_mark_once_with_hysteresis(self):
        """Vạch cắt kéo dài nhiều nhịp đọc → vẫn chỉ đếm MỘT giao lộ."""
        on, off = config.INTERSECTION_THRESHOLD, 1
        self._feed([off] * 3 + [on] * 5 + [off] * 3 + [on] * 5 + [off] * 20)
        reached = []
        self.assertTrue(self.m._navigate_continuous(2, 50, lambda: reached.append(1)))
        self.assertEqual(len(reached), 2, "vạch dài bị đếm thành nhiều giao lộ")

    def test_does_not_count_before_clearing(self):
        """Chưa tụt xuống dưới ngưỡng CLEAR thì không được đếm cái kế."""
        on, off = config.INTERSECTION_THRESHOLD, 1
        mid = config.INTERSECTION_CLEAR_THRESHOLD + 1   # vẫn còn trên vạch
        self._feed([off] * 2 + [on] * 3 + [mid] * 3 + [on] * 3 + [off] * 30)
        reached = []
        # chỉ có 1 giao lộ THẬT → yêu cầu 2 phải timeout, không được tự đếm đủ
        self.assertFalse(self.m._navigate_continuous(2, 50, lambda: reached.append(1)))
        self.assertEqual(len(reached), 1)

    def test_does_not_count_the_mark_it_starts_on(self):
        """KHỞI HÀNH khi đang đứng trên giao lộ → không được đếm chính cái đó.

        Lệnh ("forward", N) luôn bắt đầu tại một giao lộ (vừa dừng ở giao lộ trước
        hoặc vừa xoay tại đó). Đếm cả cái đang đứng là mọi chặng dừng SỚM một giao
        lộ — sai vị trí toàn bộ phần route còn lại mà không có dấu hiệu gì.
        """
        on, off = config.INTERSECTION_THRESHOLD, 1
        # đang trên vạch (3 nhịp) → ra khỏi → 1 giao lộ THẬT → hết
        self._feed([on] * 3 + [off] * 3 + [on] * 3 + [off] * 30)
        reached = []
        self.assertTrue(self.m._navigate_continuous(1, 50, lambda: reached.append(1)),
                        "đòi 1 giao lộ mà không tới được → cờ on_mark ban đầu bị sai")
        self.assertEqual(len(reached), 1, "đã đếm cả giao lộ đang đứng trên")

    def test_still_works_when_not_starting_on_a_mark(self):
        """Chặng đầu sau exit_start_zone KHÔNG đứng trên giao lộ — cờ phải tự hạ."""
        on, off = config.INTERSECTION_THRESHOLD, 1
        self._feed([off] * 5 + [on] * 2 + [off] * 30)
        self.assertTrue(self.m._navigate_continuous(1, 50))

    def test_stops_only_at_last_intersection(self):
        on, off = config.INTERSECTION_THRESHOLD, 1
        self._feed([off] * 2 + [on] * 2 + [off] * 2 + [on] * 2 + [off] * 20)
        stops = []
        real_stop = self.m.stop
        self.m.stop = lambda: (stops.append(1), real_stop())[1]
        try:
            self.assertTrue(self.m._navigate_continuous(2, 50))
        finally:
            self.m.stop = real_stop
        self.assertEqual(len(stops), 1, "chỉ được dừng ở giao lộ CUỐI")

    def test_abort_stops_immediately(self):
        self._feed([1] * 50)
        self.m.abort_check = lambda: True
        self.assertFalse(self.m._navigate_continuous(3, 50))

    def test_flag_off_uses_stop_at_each_mode(self):
        """Cờ TẮT → vẫn đi qua nhánh cũ (dừng từng giao lộ)."""
        config.CONTINUOUS_INTERSECTIONS = False
        called = []
        real = self.m._navigate_continuous
        self.m._navigate_continuous = lambda *a, **k: called.append(1) or True
        try:
            self.m.navigate_intersections(0)      # count<=0 → về ngay
        finally:
            self.m._navigate_continuous = real
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
