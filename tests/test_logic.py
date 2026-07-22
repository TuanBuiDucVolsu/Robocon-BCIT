#!/usr/bin/env python3
"""
Unit test logic — chạy trên PC hoặc Pi, không cần GPIO/camera.
  python3 -m unittest tests.test_logic -v
  python3 tests/test_logic.py
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control.motion import LineSensor, Motion
from main import Robot, State


def _robot_stub() -> Robot:
    """Robot không khởi tạo phần cứng — chỉ test logic state."""
    robot = object.__new__(Robot)
    robot.delivery_queue = []
    return robot


class TestRouteCost(unittest.TestCase):
    def test_forward_steps(self):
        self.assertEqual(Robot._route_cost([("forward", 3)]), 3)
        self.assertEqual(Robot._route_cost([("forward", 1), ("forward", 2)]), 3)

    def test_turn_steps(self):
        cost = Robot._route_cost([("right",), ("forward", 2), ("left",)])
        self.assertEqual(cost, 2 * config.ROUTE_TURN_COST + 2)

    def test_empty_route(self):
        self.assertEqual(Robot._route_cost([]), 0)


class TestBetweenRoute(unittest.TestCase):
    def test_direct_key(self):
        route = Robot._between_route("samsung", "foxconn")
        self.assertEqual(route, config.ROUTE_BETWEEN_FACTORIES[("samsung", "foxconn")])

    def test_both_directions_resolve(self):
        """Mỗi chiều có route riêng trong config (không đối xứng)."""
        fwd = Robot._between_route("samsung", "foxconn")
        rev = Robot._between_route("foxconn", "samsung")
        self.assertEqual(fwd, config.ROUTE_BETWEEN_FACTORIES[("samsung", "foxconn")])
        self.assertEqual(rev, config.ROUTE_BETWEEN_FACTORIES[("foxconn", "samsung")])
        self.assertTrue(len(fwd) > 0 and len(rev) > 0)

    def test_unknown_pair_returns_empty(self):
        self.assertEqual(Robot._between_route("unknown_a", "unknown_b"), [])

    def test_reverse_fallback_when_direct_missing(self):
        """Chiều ngược được dùng nếu thiếu key trực tiếp."""
        saved = config.ROUTE_BETWEEN_FACTORIES.pop(("samsung", "foxconn"), None)
        try:
            route = Robot._between_route("samsung", "foxconn")
            self.assertEqual(route, config.ROUTE_BETWEEN_FACTORIES[("foxconn", "samsung")])
        finally:
            if saved is not None:
                config.ROUTE_BETWEEN_FACTORIES[("samsung", "foxconn")] = saved


class TestReturnCost(unittest.TestCase):
    def test_tier1_targets_same_shelf(self):
        robot = _robot_stub()
        robot.current_shelf = 0
        robot.current_tier = 1
        cost = robot._return_cost("foxconn")
        route = config.get_return_route("foxconn", 0)
        self.assertEqual(cost, Robot._route_cost(route))

    def test_tier2_targets_next_shelf(self):
        robot = _robot_stub()
        robot.current_shelf = 0
        robot.current_tier = 2
        cost = robot._return_cost("foxconn")
        route = config.get_return_route("foxconn", 1)
        self.assertEqual(cost, Robot._route_cost(route))


class TestPlanDelivery(unittest.TestCase):
    def test_same_label_single_stop(self):
        robot = _robot_stub()
        robot._plan_delivery("samsung", "samsung")
        self.assertEqual(robot.delivery_queue, ["samsung"])

    def test_different_labels_picks_shorter_route(self):
        robot = _robot_stub()
        robot.current_shelf = 0
        robot.current_tier = 1
        robot._plan_delivery("samsung", "foxconn")
        self.assertEqual(len(robot.delivery_queue), 2)
        self.assertSetEqual(set(robot.delivery_queue), {"samsung", "foxconn"})

        cost_a = (
            Robot._route_cost(config.ROUTE_SHELF_TO_FACTORY["samsung"])
            + Robot._route_cost(Robot._between_route("samsung", "foxconn"))
            + robot._return_cost("foxconn")
        )
        cost_b = (
            Robot._route_cost(config.ROUTE_SHELF_TO_FACTORY["foxconn"])
            + Robot._route_cost(Robot._between_route("foxconn", "samsung"))
            + robot._return_cost("samsung")
        )
        if cost_a <= cost_b:
            self.assertEqual(robot.delivery_queue[0], "samsung")
        else:
            self.assertEqual(robot.delivery_queue[0], "foxconn")


class TestLineSensorDigital(unittest.TestCase):
    def test_threshold_mapping(self):
        threshold = config.LINE_THRESHOLD / 1023.0
        raw = [0.0, threshold - 0.01, threshold + 0.01, 1.0]
        digital = LineSensor.digital_from_raw(raw)
        self.assertEqual(digital, [1, 1, 0, 0])


class TestLineSensorPolarity(unittest.TestCase):
    """LINE_BLACK_IS_HIGH đảo tín hiệu ngay tại nguồn để giữ 0.0=line."""

    def setUp(self):
        self._bus = MagicMock()
        self._bus.available = True
        self._bus.last_read_ok = True
        self._bus.read_many.return_value = [0.1, 0.2, 0.8, 0.9, 0.5, 0.6]
        self._saved = config.LINE_BLACK_IS_HIGH

    def tearDown(self):
        config.LINE_BLACK_IS_HIGH = self._saved

    def test_normal_polarity_passthrough(self):
        config.LINE_BLACK_IS_HIGH = False
        sensor = LineSensor(self._bus)
        self.assertEqual(sensor.read_raw(), [0.1, 0.2, 0.8, 0.9, 0.5, 0.6])

    def test_inverted_polarity(self):
        config.LINE_BLACK_IS_HIGH = True
        sensor = LineSensor(self._bus)
        got = [round(v, 2) for v in sensor.read_raw()]
        self.assertEqual(got, [0.9, 0.8, 0.2, 0.1, 0.5, 0.4])

    def test_inverted_keeps_line_low_for_digital(self):
        # Mắt trên line đen (đọc CAO 0.95) → sau đảo phải thành "trên line" (digital 1)
        config.LINE_BLACK_IS_HIGH = True
        self._bus.read_many.return_value = [0.95, 0.95, 0.05, 0.05, 0.05, 0.05]
        sensor = LineSensor(self._bus)
        digital = LineSensor.digital_from_raw(sensor.read_raw())
        self.assertEqual(digital, [1, 1, 0, 0, 0, 0])

    def test_read_error_returns_neutral_not_inverted(self):
        # SPI/ADC lỗi (last_read_ok=False): dù LINE_BLACK_IS_HIGH=True, KHÔNG được
        # đảo fallback thô 1.0 thành 0.0 ("trên line" giả) — phải trả trung tính
        # "không thấy line" để tránh giao lộ giả khi bus glitch giữa trận.
        config.LINE_BLACK_IS_HIGH = True
        self._bus.last_read_ok = False
        self._bus.read_many.return_value = [1.0] * 6
        sensor = LineSensor(self._bus)
        self.assertEqual(sensor.read_raw(), [1.0] * config.LINE_SENSOR_COUNT)


class TestMotionRoute(unittest.TestCase):
    def setUp(self):
        self.motion = Motion()

    def test_execute_route_empty_returns_false(self):
        self.assertFalse(self.motion.execute_route([]))

    def test_navigate_zero_returns_true(self):
        self.assertTrue(self.motion.navigate_intersections(0))

    @patch.object(Motion, "navigate_intersections", return_value=False)
    def test_execute_route_fails_on_lost_line(self, _mock_nav):
        self.assertFalse(self.motion.execute_route([("forward", 1)]))

    @patch.object(Motion, "navigate_intersections", return_value=True)
    def test_execute_route_succeeds(self, _mock_nav):
        self.assertTrue(self.motion.execute_route([("forward", 2)]))

    @patch.object(Motion, "navigate_intersections", return_value=True)
    @patch.object(Motion, "turn_left_90")
    def test_execute_route_with_turn(self, mock_turn, _mock_nav):
        route = [("forward", 1), ("left",), ("forward", 1)]
        self.assertTrue(self.motion.execute_route(route))
        mock_turn.assert_called_once()


class TestRunRouteHelper(unittest.TestCase):
    def test_empty_route_returns_false(self):
        robot = _robot_stub()
        robot.motion = MagicMock()
        self.assertFalse(robot._run_route([], "test"))
        robot.motion.execute_route.assert_not_called()

    def test_motion_fail_propagates(self):
        robot = _robot_stub()
        robot.motion = MagicMock()
        robot.motion.execute_route.return_value = False
        self.assertFalse(robot._run_route([("forward", 1)], "test"))


class TestMcp3008ReadOk(unittest.TestCase):
    def test_unavailable_bus_marks_read_not_ok(self):
        from control.mcp3008_bus import Mcp3008Bus

        bus = Mcp3008Bus()
        bus.available = False
        bus.read(0)
        self.assertFalse(bus.last_read_ok)
        bus.read_many([0, 1])
        self.assertFalse(bus.last_read_ok)


class TestConfigCompeteMode(unittest.TestCase):
    def test_robot_compete_forces_debug_off(self):
        env = os.environ.copy()
        env["ROBOT_COMPETE"] = "1"
        code = (
            "import os, importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location('cfg', 'config.py')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "print(mod.DEBUG_MODE)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "False")


class TestVerticalOnShelfColumn(unittest.TestCase):
    def test_same_row_empty(self):
        self.assertEqual(config._vertical_on_shelf_column(0, 0), [])

    def test_down_and_up_differ(self):
        down = config._vertical_on_shelf_column(4, 0)
        up = config._vertical_on_shelf_column(0, 4)
        self.assertNotEqual(down, up)
        self.assertEqual(down[0], ("right",))
        self.assertEqual(up[0], ("left",))
        self.assertEqual(down[1], ("forward", 4))
        self.assertEqual(up[1], ("forward", 4))


class TestReturnRoute(unittest.TestCase):
    def test_samsung_to_kesh3_adds_vertical(self):
        """Samsung (R4) → Kệ 3 (R0) phải có thêm đoạn dọc so với base."""
        base = config.ROUTE_FACTORY_TO_SHELF["samsung"]
        route = config.get_return_route("samsung", 0)
        self.assertGreater(len(route), len(base))
        self.assertEqual(route[:len(base)], base)

    def test_foxconn_to_kesh3_same_row(self):
        """Foxconn (R0) → Kệ 3 (R0) — không cần đoạn dọc thêm."""
        route = config.get_return_route("foxconn", 0)
        self.assertEqual(route, config.ROUTE_FACTORY_TO_SHELF["foxconn"])

    def test_foxconn_to_kesh2_goes_up(self):
        route = config.get_return_route("foxconn", 1)
        self.assertIn(("forward", 2), route)

    def test_unknown_factory_returns_base_only(self):
        route = config.get_return_route("unknown", 0)
        self.assertEqual(route, [])


class TestNextPickupShelf(unittest.TestCase):
    def test_tier1_advances_to_same_shelf(self):
        robot = _robot_stub()
        robot.current_shelf = 0
        robot.current_tier = 1
        self.assertEqual(robot._next_pickup_shelf(), 0)

    def test_tier2_advances_to_next_shelf(self):
        robot = _robot_stub()
        robot.current_shelf = 0
        robot.current_tier = 2
        self.assertEqual(robot._next_pickup_shelf(), 1)


class TestRouteConfigIntegrity(unittest.TestCase):
    """Route trong config phải có cặp BETWEEN_FACTORIES đầy đủ khi cần."""

    def test_all_shelf_to_factory_labels_exist(self):
        for label in config.COLOR_RANGES:
            self.assertIn(label, config.ROUTE_SHELF_TO_FACTORY)

    def test_start_route_not_empty(self):
        self.assertTrue(len(config.ROUTE_START_TO_SHELF_0) > 0)


class TestResetForNewRun(unittest.TestCase):
    """_reset_for_new_run() xoá sạch trạng thái 1 lượt cho chế độ luyện tập."""

    def test_reset_clears_all_run_state(self):
        robot = object.__new__(Robot)
        # Giả lập trạng thái "bẩn" sau 1 lượt
        robot.state = State.DONE
        robot.packages_delivered = 12
        robot.pickup_count = 6
        robot.current_shelf = 3
        robot.current_tier = 2
        robot.match_start_time = 123.0
        robot._tier_retries = 1
        robot.carried_labels = ["samsung", "foxconn"]
        robot.delivery_queue = ["amkor"]
        robot._last_delivered_label = "amkor"

        robot._reset_for_new_run()

        self.assertEqual(robot.state, State.INIT)
        self.assertEqual(robot.packages_delivered, 0)
        self.assertEqual(robot.pickup_count, 0)
        self.assertEqual(robot.current_shelf, 0)
        self.assertEqual(robot.current_tier, 1)
        self.assertEqual(robot.match_start_time, 0.0)
        self.assertEqual(robot._tier_retries, 0)
        self.assertEqual(robot.carried_labels, [None, None])
        self.assertEqual(robot.delivery_queue, [])
        self.assertIsNone(robot._last_delivered_label)


class TestMatchResume(unittest.TestCase):
    """Khôi phục trận sau lỗi: lưu/đọc/xoá mốc bắt đầu để chạy nốt thời gian còn lại."""

    def setUp(self):
        self.robot = object.__new__(Robot)
        self.robot.match_start_time = 0.0
        fd, self.tmp = tempfile.mkstemp(prefix="match_state_")
        os.close(fd)
        os.remove(self.tmp)  # để trống — test tự kiểm soát
        self._saved = config.MATCH_STATE_FILE
        config.MATCH_STATE_FILE = self.tmp

    def tearDown(self):
        if os.path.exists(self.tmp):
            os.remove(self.tmp)
        config.MATCH_STATE_FILE = self._saved

    def test_no_file_returns_none(self):
        self.assertIsNone(self.robot._load_match_resume())

    def test_persist_then_load_within_window(self):
        self.robot.match_start_time = time.time()
        self.robot._persist_match_start()
        epoch = self.robot._load_match_resume()
        self.assertIsNotNone(epoch)
        self.assertAlmostEqual(epoch, self.robot.match_start_time, places=1)

    def test_stale_match_returns_none_and_clears(self):
        self.robot.match_start_time = time.time() - config.MATCH_DURATION - 5
        self.robot._persist_match_start()
        self.assertIsNone(self.robot._load_match_resume())
        self.assertFalse(os.path.exists(self.tmp))  # tự xoá file quá hạn

    def test_clear_removes_file(self):
        self.robot.match_start_time = time.time()
        self.robot._persist_match_start()
        self.robot._clear_match_state()
        self.assertFalse(os.path.exists(self.tmp))


try:
    import cv2 as _cv2
    import numpy as _np
except ImportError:
    _cv2 = _np = None


@unittest.skipIf(_cv2 is None or _np is None, "cần cv2 + numpy")
class TestVisionColorClassify(unittest.TestCase):
    """_classify_by_color: ưu tiên màu sắc nét hơn Amkor (xám)."""

    @classmethod
    def setUpClass(cls):
        from vision.vision import Vision
        cls.vision = object.__new__(Vision)  # bỏ qua __init__ (không cần camera)

    def _frame(self, fill_rgb, center_rgb=None, center_side=0):
        """Ảnh BGR 100x100 (khớp format camera thật) nền fill_rgb, ô vuông giữa
        center_rgb cạnh center_side. Tham số vẫn nhận màu theo thứ tự RGB cho dễ đọc,
        tự đảo sang BGR trước khi build mảng."""
        fill_bgr = tuple(reversed(fill_rgb))
        f = _np.full((100, 100, 3), fill_bgr, dtype=_np.uint8)
        if center_rgb is not None and center_side > 0:
            s = (100 - center_side) // 2
            f[s:s + center_side, s:s + center_side] = tuple(reversed(center_rgb))
        return f

    def _label(self, frame):
        return self.vision._classify_by_color(frame)[0]

    # Màu test = điểm GIỮA dải COLOR_RANGES đã calibrate thật từ camera (không phải
    # màu tổng hợp cực đại RGB 0/255 — camera thật dưới ánh sáng thường không bao giờ
    # cho ra S=255,V=255 tuyệt đối, nên test kiểu đó không còn khớp sau khi calibrate
    # thật thu hẹp COLOR_RANGES). Xem tools/calibrate_vision.py để tái tạo các dải này.

    def test_solid_blue_is_samsung(self):
        self.assertEqual(self._label(self._frame((45, 86, 110))), "samsung")

    def test_solid_yellow_is_foxconn(self):
        self.assertEqual(self._label(self._frame((112, 120, 61))), "foxconn")

    def test_solid_red_is_hana(self):
        self.assertEqual(self._label(self._frame((120, 80, 68))), "hana_micron")

    def test_solid_gray_is_amkor(self):
        self.assertEqual(self._label(self._frame((180, 162, 162))), "amkor")

    def test_blue_chip_on_gray_bg_is_samsung_not_amkor(self):
        # Regression: nền xám 56% > chip xanh 44% pixel. Logic cũ -> amkor (sai).
        # Logic mới ưu tiên màu chromatic đạt ngưỡng -> samsung (đúng).
        # Màu = điểm giữa dải calibrate thật (xem comment ở test_solid_* phía trên).
        frame = self._frame((180, 162, 162), center_rgb=(45, 86, 110), center_side=40)
        self.assertEqual(self._label(frame), "samsung")


if __name__ == "__main__":
    unittest.main(verbosity=2)
