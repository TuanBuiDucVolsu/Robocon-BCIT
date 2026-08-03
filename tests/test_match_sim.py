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
import time
import sys
import unittest
from unittest.mock import MagicMock, patch

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
        elif cmd[0] == "back":
            for _ in range(cmd[1]):
                assert place in nav.TERMINALS, \
                    f"lệnh lùi ở {place} — chỉ lùi ra khỏi điểm cuối"
                node, term_heading, _ = nav.TERMINALS[place]
                assert heading == term_heading, \
                    f"lùi khỏi {place} mà không quay mặt vào nó"
                place = node
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
        out.extend([(cmd[0], 1)] * cmd[1] if cmd[0] in ("forward", "back") else [cmd])
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
    # Reset giữa trận chờ đội viên đặt robot xong rồi bấm nút xác nhận
    # (main._wait_for_placement) — mock trả về ngay, không chặn mô phỏng.
    robot._start_button = MagicMock()

    # Dùng CHÍNH hàm reset của Robot thay vì chép tay danh sách field: thêm field
    # mới vào state machine mà quên thêm ở đây thì test sẽ nổ AttributeError giữa
    # chừng (đã xảy ra với task2_done — kiện thứ 13 không được khởi tạo).
    robot._reset_for_new_run()
    robot.match_start_time = 1e18      # thời gian coi như vô hạn để chạy hết kịch bản
    robot.state = main_mod.State.START

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
    robot.motion.tren_giao_lo_dau = False
    # Dò nhánh line tại giao lộ Kệ 3: THẤY line ⟺ đang ở nửa chuẩn
    if probe_result == "auto":
        robot.motion.probe_side_branch.side_effect = lambda *a, **k: not nav.MIRRORED
    else:
        robot.motion.probe_side_branch.side_effect = lambda *a, **k: probe_result
    robot.motion.approach_shelf.side_effect = lambda *a, **k: maybe_fail()
    robot.motion.retreat_from_shelf.return_value = True
    # Luồng bốc hàng mới: raise_to_insert → creep_until (luồn, IR dẫn) →
    # lift_off → confirm_pickup. Cho cả 2 bước có thể hỏng như phần cứng thật.
    robot.motion.creep_until.side_effect = lambda *a, **k: maybe_fail()
    robot.lift.confirm_pickup.side_effect = lambda *a, **k: maybe_fail()
    robot.lift.pickup.side_effect = lambda *a, **k: maybe_fail()
    robot.lift.dropoff.return_value = True
    robot.lift.dropoff_left.return_value = True
    robot.lift.dropoff_right.return_value = True
    robot.vision.get_factory_name.side_effect = lambda label: label
    # `*a` là BẮT BUỘC: main.py gọi classify_pair(self.current_tier) — vùng quét
    # dịch theo tầng. Lambda 0 tham số làm cả 14 test chết bằng TypeError, và vì
    # test_match_sim không nằm trong lệnh test hay chạy nên nó chết âm thầm.
    robot.vision.classify_pair.side_effect = lambda *a, **k: (
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
        """Phần cứng hoàn hảo → phải giao đủ 13/13 kiện, mọi route hợp lệ.

        13 = 12 kiện NV1 + 1 kiện hàng rời NV2. Chỉ kiểm 12 thì luồng NV2 (30 điểm)
        có hỏng cũng không test nào báo.
        """
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                robot, errors = run_match(seed)
                self.assertEqual(errors, [])
                self.assertEqual(robot.packages_delivered, 12)
                self.assertTrue(robot.task2_done, "không giao được kiện thứ 13 (NV2)")
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


class TestTask2(unittest.TestCase):
    """Kiện thứ 13 — hàng rời NV2, 30 điểm, chỉ được làm sau 100% NV1."""

    def test_not_attempted_before_task1_complete(self):
        """Luật: NV2 chỉ sau khi xong 100% NV1. Bỏ dở NV1 thì không được rẽ sang NV2."""
        robot, errors = run_match(0, hw_fail_rate=0.35)
        self.assertEqual(errors, [])
        if robot.packages_delivered < 12:
            self.assertFalse(robot.task2_done,
                             "làm NV2 khi NV1 chưa xong 100% — sai luật")

    def test_skipped_when_out_of_time(self):
        """Còn ít giờ hơn TASK2_MIN_TIME → đứng yên, không chạy một chuyến vô ích."""
        robot, _ = run_match(0)
        robot.match_start_time = time.time() - (config.MATCH_DURATION
                                                - config.TASK2_MIN_TIME + 5)
        self.assertEqual(robot._handle_task2_navigate_to_loose(),
                         main_mod.State.DONE)

    def test_pickup_retries_before_giving_up(self):
        """NV1 được retry còn NV2 thì không là bất đối xứng — 30 điểm mà bỏ ngay
        lần hỏng đầu tiên."""
        robot, _ = run_match(0)
        robot.match_start_time = time.time()          # còn đủ giờ
        robot.motion.creep_until.side_effect = None
        robot.motion.creep_until.return_value = False   # luôn không luồn được càng
        robot.motion.approach_shelf.side_effect = None
        robot.motion.approach_shelf.return_value = True
        robot.motion.creep_until.reset_mock()

        self.assertEqual(robot._handle_task2_pickup(), main_mod.State.DONE)
        self.assertGreaterEqual(robot.motion.creep_until.call_count, 2,
                                "phải thử lại ít nhất 1 lần trước khi bỏ 30 điểm")

    def test_reset_during_task2_retries_it(self):
        """Reset lúc đang mang kiện hàng rời → về ô xuất phát rồi LÀM LẠI NV2,
        vì NV1 đã xong nên không có gì khác để làm."""
        robot, _ = run_match(0)
        robot.task2_done = False
        robot._reset_requested = True
        state = robot._handle_reset()
        self.assertEqual(state, main_mod.State.START)
        self.assertEqual(robot.packages_delivered, 12)
        # NV1 đã xong → state machine phải quay lại nhánh NV2
        self.assertEqual(robot._finish_task1_or_done(),
                         main_mod.State.TASK2_NAVIGATE_TO_LOOSE)


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


class TestGioiHanLuotBoc(unittest.TestCase):
    """ROBOT_MAX_PICKUPS — diễn tập giới hạn, dừng sau n lượt bốc.

    Lấp khoảng trống giữa test_smoke option 5 (đúng các bước nhưng KHÔNG chạy state
    machine của main.py) và practice.sh (trọn trận, quá dài để lặp). Bài diễn tập
    này chạy THẬT state machine nên phủ được nút bấm, công tắc nửa sân, đồng hồ
    240s, retry/bỏ tầng và luồng reset.
    """

    def test_stops_after_the_configured_number_of_pickups(self):
        import os
        with patch.dict(os.environ, {"ROBOT_MAX_PICKUPS": "1"}):
            robot, errors = run_match(0)
        self.assertEqual(errors, [])
        self.assertEqual(robot.pickup_count, 1,
                         "phải dừng đúng sau 1 lượt bốc, không chạy tiếp")
        self.assertLess(robot.packages_delivered, config.TOTAL_PACKAGES_TASK1)

    def test_no_limit_runs_the_whole_match(self):
        import os
        moi_truong = {k: v for k, v in os.environ.items() if k != "ROBOT_MAX_PICKUPS"}
        with patch.dict(os.environ, moi_truong, clear=True):
            robot, errors = run_match(0)
        self.assertEqual(errors, [])
        self.assertEqual(robot.packages_delivered, config.TOTAL_PACKAGES_TASK1,
                         "không đặt giới hạn thì phải chạy trọn trận như cũ")

    def test_limit_comes_from_env_not_config(self):
        """Đặt trong config thì có ngày lỡ commit rồi mang vào trận thật."""
        self.assertFalse(hasattr(config, "ROBOT_MAX_PICKUPS"))
        self.assertFalse(hasattr(config, "MAX_PICKUPS"))


class TestAutoDetectSide(unittest.TestCase):
    """Robot tự dò nửa sân đầu trận: cấu hình sai vẫn phải chạy đúng.

    ⚠️ `config.BOARD_AUTO_DETECT` hiện là **False** (xem lý do trong config.py).
    Lớp này BẬT LẠI cờ đó trong phạm vi từng test, vì nó kiểm CƠ CHẾ dò chứ không
    kiểm cấu hình mặc định — cơ chế vẫn còn trong code và bật lại được. Không ép
    cờ thì cả 2 test xanh một cách vô nghĩa: state DETECT_SIDE thoát ngay ở dòng
    đầu, không lần nào gọi tới probe.
    """

    def setUp(self):
        self._saved = nav.MIRRORED
        self._auto = patch.object(config, "BOARD_AUTO_DETECT", True)
        self._auto.start()

    def tearDown(self):
        self._auto.stop()
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
