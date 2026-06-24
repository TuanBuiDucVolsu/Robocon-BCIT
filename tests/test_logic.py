#!/usr/bin/env python3
"""
Unit test logic — chạy trên PC hoặc Pi, không cần GPIO/camera.
  python3 -m unittest tests.test_logic -v
  python3 tests/test_logic.py
"""

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control.motion import LineSensor, Motion
from main import Robot


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


class TestPlanDelivery(unittest.TestCase):
    def test_same_label_single_stop(self):
        robot = _robot_stub()
        robot._plan_delivery("samsung", "samsung")
        self.assertEqual(robot.delivery_queue, ["samsung"])

    def test_different_labels_picks_shorter_route(self):
        robot = _robot_stub()
        robot._plan_delivery("samsung", "foxconn")
        self.assertEqual(len(robot.delivery_queue), 2)
        self.assertSetEqual(set(robot.delivery_queue), {"samsung", "foxconn"})

        cost_a = (
            Robot._route_cost(config.ROUTE_SHELF_TO_FACTORY["samsung"])
            + Robot._route_cost(Robot._between_route("samsung", "foxconn"))
        )
        cost_b = (
            Robot._route_cost(config.ROUTE_SHELF_TO_FACTORY["foxconn"])
            + Robot._route_cost(Robot._between_route("foxconn", "samsung"))
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


class TestMotionRoute(unittest.TestCase):
    def setUp(self):
        self.motion = Motion()

    def test_execute_route_empty_returns_false(self):
        self.assertFalse(self.motion.execute_route([]))

    def test_navigate_zero_returns_true(self):
        self.assertTrue(self.motion.navigate_intersections(0))

    @patch.object(Motion, "follow_line_until_intersection", return_value=False)
    def test_execute_route_fails_on_lost_line(self, _mock_follow):
        self.assertFalse(self.motion.execute_route([("forward", 1)]))

    @patch.object(Motion, "follow_line_until_intersection", return_value=True)
    def test_execute_route_succeeds(self, _mock_follow):
        self.assertTrue(self.motion.execute_route([("forward", 2)]))

    @patch.object(Motion, "turn_left_90")
    @patch.object(Motion, "follow_line_until_intersection", return_value=True)
    def test_execute_route_with_turn(self, _mock_follow, mock_turn):
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


class TestRouteConfigIntegrity(unittest.TestCase):
    """Route trong config phải có cặp BETWEEN_FACTORIES đầy đủ khi cần."""

    def test_all_shelf_to_factory_labels_exist(self):
        for label in config.COLOR_RANGES:
            self.assertIn(label, config.ROUTE_SHELF_TO_FACTORY)

    def test_start_route_not_empty(self):
        self.assertTrue(len(config.ROUTE_START_TO_SHELF_0) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
