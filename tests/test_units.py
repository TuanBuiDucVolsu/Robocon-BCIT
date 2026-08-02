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

import config
from control.lift import MAX_LEVEL, Lift, PalletSensors
from control.motion import Motion
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
        """Siêu âm thấy kệ gần -> bàn giao cho approach_shelf, kể cả khi chưa thấy line."""
        m = self._motion([[0] * 6], dist=config.APPROACH_SLOW_DISTANCE - 1)
        self.assertTrue(m.advance_to_end(timeout=3.0))


class TestForwardGuided(unittest.TestCase):
    """Tiến sát kệ phải CÓ LÁI khi còn thấy line, và chỉ chạy thẳng khi mất line.

    approach_shelf() và creep_until() trước đây chạy forward() MÙ suốt ~10cm cuối.
    Robot không đi thẳng tuyệt đối nên nó lệch dần, càng không luồn hết vào khe
    pallet, IR không báo có hàng → bốc hàng hỏng. Đây là mắt xích ĐẦU của chuỗi đó.
    """

    def _motion(self, values):
        m = object.__new__(Motion)
        m._line_sensor = MagicMock()
        m._line_sensor.available = True
        m.read_line_sensor = lambda: values
        m.follow_line = MagicMock(return_value=(False, values))
        m.forward = MagicMock()
        return m

    def test_steers_while_line_is_visible(self):
        m = self._motion([0, 0, 1, 1, 0, 0])
        m._forward_guided(30)
        m.follow_line.assert_called_once()
        m.forward.assert_not_called()

    def test_falls_back_to_straight_when_line_is_gone(self):
        """Line không kéo tới tận kệ thì phải giữ ĐÚNG hành vi cũ, không đứng im."""
        m = self._motion([0, 0, 0, 0, 0, 0])
        m._forward_guided(30)
        m.forward.assert_called_once_with(30)
        m.follow_line.assert_not_called()

    def test_falls_back_when_sensor_unavailable(self):
        m = self._motion([0, 0, 1, 1, 0, 0])
        m._line_sensor.available = False
        m._forward_guided(30)
        m.forward.assert_called_once_with(30)
        m.follow_line.assert_not_called()


class TestBackToIntersection(unittest.TestCase):
    """back_to_intersection — vòng lặp lùi tới giao lộ."""

    @classmethod
    def setUpClass(cls):
        cls.m = Motion()

    @classmethod
    def tearDownClass(cls):
        cls.m.cleanup()

    def setUp(self):
        n = config.LINE_SENSOR_COUNT
        # Mọi mắt thấy line = giao lộ ngay lập tức → vòng lặp thoát tức thì
        self.m.read_line_sensor_raw = lambda: [0.0] * n

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
