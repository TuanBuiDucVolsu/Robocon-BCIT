#!/usr/bin/env python3
"""
Mô phỏng TRỌN VẸN một trận đấu với phần cứng giả lập — chạy trên PC, không cần Pi.

    python3 -m unittest tests.test_match_sim -v

Khác `test_logic.py` (kiểm từng hàm), file này chạy THẬT state machine của main.py
từ START đến DONE, đồng thời mô phỏng vật lý robot đi trên bản đồ:

  - Mỗi route được "chạy" trên lưới line thật (navigation.NODES/EDGES). Bước nào
    không có line → hỏng ngay, báo lỗi.
  - Sau MỖI state, so vị trí mà main.py TIN TƯỞNG với vị trí MÔ PHỎNG. Lệch một
    lần là fail — đây chính là loại lỗi mà bộ test cũ (so route với config) không
    bao giờ bắt được, và là loại lỗi làm robot giao hàng nhầm nhà máy.

3 kịch bản: chạy sạch, phần cứng lỗi ngẫu nhiên, và mất line giữa route.
"""

import os
import random
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import navigation as nav
import main as main_mod

LABELS = ["samsung", "foxconn", "amkor", "hana_micron"]
MAX_STEPS = 400          # chặn vòng lặp vô hạn


def _simulate(pose, route):
    """Chạy route trên bản đồ, raise nếu bước đó không có line thật."""
    place, heading = pose
    for cmd in route:
        if cmd[0] == "left":
            heading = nav.turn_left(heading)
        elif cmd[0] == "right":
            heading = nav.turn_right(heading)
        elif cmd[0] == "forward":
            for _ in range(cmd[1]):
                if place in nav.TERMINALS:
                    node, term_heading, _ = nav.TERMINALS[place]
                    assert heading == nav.opposite(term_heading), \
                        f"rời điểm cuối {place} sai hướng"
                    place = node
                    continue
                step = nav.ADJACENCY[place].get(heading)
                assert step is not None, \
                    f"KHÔNG có line từ {place} theo hướng {nav.HEADING_NAMES[heading]}"
                place = step[0]
        elif cmd[0] == "advance":
            terms = [t for t, (n, h, _) in nav.TERMINALS.items()
                     if n == place and h == heading]
            assert terms, f"không có điểm cuối tại {place} theo hướng {heading}"
            place = terms[0]
        else:
            raise AssertionError(f"lệnh lạ: {cmd}")
    return place, heading


def _atomic(route):
    out = []
    for cmd in route:
        out.extend([("forward", 1)] * cmd[1] if cmd[0] == "forward" else [cmd])
    return out


def run_match(seed: int, hw_fail_rate: float = 0.0, line_loss_rate: float = 0.0,
              probe_result: object = "auto", physical_mirrored: bool | None = None,
              reset_after_states: int | None = None):
    """Chạy 1 trận giả lập. Trả về (robot, danh sách lỗi).

    probe_result: kết quả robot ĐỌC ĐƯỢC khi dò nhánh line ở giao lộ Kệ 3.
        "auto" = đọc đúng sự thật (thấy line ⟺ nửa chuẩn); True/False = ép giá trị;
        None = cảm biến hỏng.
    physical_mirrored: nửa sân THẬT ngoài đời (chỉ để đọc cho rõ ý ở test; trước lúc
        dò robot chưa xoay lần nào nên đường đi giống hệt ở cả 2 nửa).
    reset_after_states: bấm nút RESET sau bấy nhiêu lần chuyển state (mô phỏng trọng
        tài cho reset giữa trận + đội viên đặt tay robot về ô xuất phát).
    """
    random.seed(seed)
    robot = object.__new__(main_mod.Robot)
    robot.motion = MagicMock()
    robot.lift = MagicMock()
    robot.vision = MagicMock()
    robot.packages_delivered = 0
    robot.pickup_count = 0
    robot.current_shelf = 0
    robot.current_tier = 1
    robot._tier_retries = 0
    robot.pose = nav.START_POSE
    robot.carried_labels = [None, None]
    robot.delivery_queue = []
    robot._last_delivered_label = None
    robot.match_start_time = 1e18      # thời gian coi như vô hạn để chạy hết kịch bản
    robot.state = main_mod.State.START
    robot._reset_requested = False
    robot._reset_count = 0
    robot._phase_times = {}
    robot._phase_counts = {}

    physical = {"pose": nav.START_POSE}
    errors: list[str] = []

    def execute_route(route):
        before = physical["pose"]
        steps = _atomic(route)
        if line_loss_rate and steps and random.random() < line_loss_rate:
            steps = steps[:random.randrange(len(steps))]     # mất line giữa chừng
            ok = False
        else:
            ok = True
        robot.motion.last_route_progress = steps
        try:
            physical["pose"] = _simulate(before, steps)
        except AssertionError as e:
            errors.append(f"{before} + {route}: {e}")
            return False
        return ok

    def maybe_fail():
        return random.random() >= hw_fail_rate

    robot.motion.execute_route.side_effect = execute_route
    robot.motion.exit_start_zone.return_value = True
    # Dò nhánh line tại giao lộ Kệ 3: THẤY line ⟺ đang ở nửa chuẩn
    if probe_result == "auto":
        robot.motion.probe_side_branch.side_effect = lambda *a, **k: not nav.MIRRORED
    else:
        robot.motion.probe_side_branch.side_effect = lambda *a, **k: probe_result
    robot.motion.approach_shelf.side_effect = lambda *a, **k: maybe_fail()
    robot.motion.retreat_from_shelf.return_value = True
    robot.lift.pickup.side_effect = lambda *a, **k: maybe_fail()
    robot.lift.dropoff.return_value = True
    robot.lift.dropoff_left.return_value = True
    robot.lift.dropoff_right.return_value = True
    robot.vision.get_factory_name.side_effect = lambda label: label
    robot.vision.classify_pair.side_effect = lambda: (
        (random.choice(LABELS), random.choice(LABELS)) if maybe_fail() else (None, None))

    steps_run = 0
    while robot.state not in (main_mod.State.DONE, main_mod.State.EMERGENCY_STOP):
        steps_run += 1
        if steps_run > MAX_STEPS:
            errors.append("state machine không kết thúc (vòng lặp vô hạn?)")
            break
        state_before = robot.state
        handler = getattr(robot, main_mod.Robot.STATE_HANDLERS[robot.state])
        next_state = handler()

        # Mô phỏng trọng tài cho reset: bấm nút + đặt tay robot về ô xuất phát
        if reset_after_states is not None and steps_run == reset_after_states:
            robot._reset_requested = True
        if robot._reset_requested:
            robot.state = robot._handle_reset()
            physical["pose"] = nav.START_POSE      # đội viên đặt tay robot về start
            continue
        robot.state = next_state
        if state_before is main_mod.State.DETECT_SIDE:
            # Dò xong có thể lật bản đồ: robot KHÔNG di chuyển, chỉ đổi hệ nhãn
            # hướng → đồng bộ lại vị trí mô phỏng sang hệ mới.
            physical["pose"] = robot.pose
        elif robot.pose != physical["pose"]:
            errors.append(
                f"LỆCH VỊ TRÍ sau {robot.state.value}: "
                f"main tin là {robot.pose}, thực tế {physical['pose']}")
            physical["pose"] = robot.pose      # đồng bộ lại để soi tiếp lỗi sau
    return robot, errors


class TestFullMatch(unittest.TestCase):
    SEEDS = range(20)

    def test_clean_run_delivers_all_packages(self):
        """Phần cứng hoàn hảo → phải giao đủ 12/12 kiện, mọi route hợp lệ."""
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                robot, errors = run_match(seed)
                self.assertEqual(errors, [])
                self.assertEqual(robot.packages_delivered, 12)
                self.assertEqual(robot.state, main_mod.State.DONE)

    def test_hardware_failures_terminate_cleanly(self):
        """15% thao tác phần cứng lỗi → vẫn kết thúc, không kẹt, không đi lung tung."""
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                robot, errors = run_match(seed, hw_fail_rate=0.15)
                self.assertEqual(errors, [])
                self.assertEqual(robot.state, main_mod.State.DONE)

    def test_line_loss_keeps_position_consistent(self):
        """20% route mất line giữa chừng → main.py vẫn biết đúng robot đang ở đâu."""
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                _robot, errors = run_match(seed, line_loss_rate=0.2)
                self.assertEqual(errors, [])


class TestMirroredHalfMatch(unittest.TestCase):
    """Chạy trọn trận ở NỬA SÂN GƯƠNG (config.BOARD_MIRRORED=True).

    Sa bàn chia đôi bởi tường giữa sân; nửa của đội có thể là ảnh gương của nửa
    trong docs/sa_ban.png. Khi đó chiều xoay trái/phải đảo hết — phải chắc chắn
    robot vẫn giao đủ 12 kiện chứ không rẽ ngược mọi ngã.
    """

    def setUp(self):
        self._saved = nav.MIRRORED
        nav.set_mirrored(True)

    def tearDown(self):
        nav.set_mirrored(self._saved)

    def test_mirrored_half_delivers_all_packages(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                robot, errors = run_match(seed)
                self.assertEqual(errors, [])
                self.assertEqual(robot.packages_delivered, 12)


class TestOtherHalfFactoryOrder(unittest.TestCase):
    """Chạy trọn trận ở nửa sân có SAMSUNG cùng hàng ô xuất phát (đội góc trên-phải).

    Hai nửa quay 180° nên chiều trái/phải giống nhau, nhưng thứ tự nhà máy trên
    tường bị đảo — phải chắc chắn robot vẫn giao đủ 12 kiện với bản đồ đảo đó.
    """

    def setUp(self):
        self._saved = nav.FACTORY_AT_START_ROW
        nav.set_factory_order("samsung")

    def tearDown(self):
        nav.set_factory_order(self._saved)

    def test_delivers_all_packages(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                robot, errors = run_match(seed)
                self.assertEqual(errors, [])
                self.assertEqual(robot.packages_delivered, 12)

    def test_survives_hardware_failures(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                _robot, errors = run_match(seed, hw_fail_rate=0.15, line_loss_rate=0.2)
                self.assertEqual(errors, [])


class TestMidMatchReset(unittest.TestCase):
    """Reset giữa trận trong một trận ĐẦY ĐỦ — kịch bản sát thi đấu nhất.

    Luật cho 5 lần reset. Sau reset robot bị đặt tay về ô xuất phát: nếu code không
    xử lý thì nó vẫn tưởng mình đang ở nhà máy và lái đi lung tung. Test này bấm nút
    reset ở giữa trận rồi kiểm robot có về đúng ô xuất phát và chạy tiếp không.
    """

    def test_reset_midway_still_finishes(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                robot, errors = run_match(seed, reset_after_states=12)
                self.assertEqual(errors, [])
                self.assertGreaterEqual(robot._reset_count, 1, "reset chưa được xử lý")
                self.assertEqual(robot.state, main_mod.State.DONE)

    def test_progress_kept_across_reset(self):
        """Kiện đã giao vẫn tính điểm, không bị lấy lại từ đầu."""
        robot, errors = run_match(0, reset_after_states=20)
        self.assertEqual(errors, [])
        # Không được lấy lại kiện đã lấy → tổng số lần nâng không vượt số lượt cần
        self.assertLessEqual(robot.pickup_count, config.PICKUPS_TASK1 + 2)


class TestAutoDetectSide(unittest.TestCase):
    """Robot tự dò nửa sân đầu trận: cấu hình sai vẫn phải chạy đúng."""

    def setUp(self):
        self._saved = nav.MIRRORED

    def tearDown(self):
        nav.set_mirrored(self._saved)

    def test_wrong_config_is_corrected_by_probe(self):
        """Cấu hình để nhầm là nửa CHUẨN nhưng thực tế đang ở nửa GƯƠNG.

        Cảm biến (probe) nói sự thật → robot phải tự nạp lại bản đồ gương và vẫn
        giao đủ 12 kiện. Đây chính là tình huống quên đặt cờ trước trận.
        """
        nav.set_mirrored(False)                      # cấu hình SAI

        real_half_mirrored = True                    # sự thật ngoài sân
        robot, errors = run_match(
            0, probe_result=not real_half_mirrored,  # probe: không thấy line
            physical_mirrored=real_half_mirrored)

        self.assertEqual(errors, [])
        self.assertTrue(nav.MIRRORED, "phải tự chuyển sang bản đồ gương")
        self.assertEqual(robot.packages_delivered, 12)

    def test_probe_failure_falls_back_to_config(self):
        """Cảm biến hỏng (probe trả None) → giữ nguyên cấu hình, vẫn chạy tiếp."""
        nav.set_mirrored(False)
        robot, errors = run_match(0, probe_result=None, physical_mirrored=False)
        self.assertEqual(errors, [])
        self.assertFalse(nav.MIRRORED)
        self.assertEqual(robot.packages_delivered, 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
