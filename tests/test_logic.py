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
import navigation as nav
from control.motion import LineSensor, Motion
from main import Robot, State


def _robot_stub() -> Robot:
    """Robot không khởi tạo phần cứng — chỉ test logic state."""
    robot = object.__new__(Robot)
    robot.delivery_queue = []
    robot.pose = nav.START_POSE
    robot.current_shelf = 0
    robot.current_tier = 1
    robot._tier_retries = 0
    robot._side_detected = False
    return robot


def _simulate(pose, route):
    """Chạy route trên lưới → (vị trí mới, hướng mới).

    ĐÂY là thứ bộ test cũ thiếu: test cũ chỉ so route với chính config nên không
    bao giờ phát hiện được route đi sai chỗ. Hàm này mô phỏng vật lý: robot đi đâu,
    quay hướng nào — độc lập với code sinh route.
    """
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
                    assert heading == nav.opposite(term_heading), (
                        f"Ra khỏi điểm cuối {place} sai hướng")
                    place = node
                    continue
                step = nav.ADJACENCY[place].get(heading)
                assert step is not None, (
                    f"Không có line từ {place} theo hướng {nav.HEADING_NAMES[heading]}")
                place = step[0]
        elif cmd[0] == "back":
            # Lùi CHỈ dùng để rút khỏi điểm cuối, và vẫn phải quay mặt vào nó
            for _ in range(cmd[1]):
                assert place in nav.TERMINALS, (
                    f"Lệnh lùi ở {place} — chỉ được lùi ra khỏi điểm cuối")
                node, term_heading, _ = nav.TERMINALS[place]
                assert heading == term_heading, (
                    f"Lùi khỏi {place} mà không quay mặt vào nó")
                place = node
        elif cmd[0] == "advance":
            terms = [t for t, (n, h, _) in nav.TERMINALS.items()
                     if n == place and h == heading]
            assert terms, f"Không có điểm cuối ở {place} theo hướng {heading}"
            place = terms[0]
        else:
            raise AssertionError(f"Lệnh lạ: {cmd}")
    return place, heading


class TestBoardMap(unittest.TestCase):
    """Bản đồ phải khớp sa bàn in thật (xem docs/SA_BAN.md)."""

    def test_shelf_column_has_only_three_nodes(self):
        col0 = [n for n, (c, _r) in nav.NODES.items() if c == 0]
        self.assertEqual(len(col0), 3, "Cột kệ chỉ có giao lộ ở R4/R2/R0")

    def test_r2_horizontal_is_blocked(self):
        """Hàng R2 đứt bởi vòng tròn ROBOCON → không được có cạnh C0R2↔C1R2."""
        self.assertNotIn(nav.EAST, nav.ADJACENCY["C0R2"])
        self.assertNotIn(nav.WEST, nav.ADJACENCY["C1R2"])

    def test_no_direct_line_between_factories(self):
        """Các khu nhà máy không nối nhau bằng line — phải vòng về cột giữa."""
        for term, (node, _h, _d) in nav.TERMINALS.items():
            if term.startswith("F_"):
                self.assertTrue(node.startswith("C1"))

    def test_every_terminal_reachable_from_start(self):
        for term in nav.TERMINALS:
            if term == "START":
                continue
            route, _ = nav.plan(nav.START_POSE, term)
            self.assertIsNotNone(route, f"Không tới được {term}")


class TestRouteReachesDestination(unittest.TestCase):
    """Mô phỏng lại route sinh ra: phải tới ĐÚNG chỗ, đúng hướng."""

    def _check(self, src_pose, goal):
        route, new_pose = nav.plan(src_pose, goal)
        self.assertIsNotNone(route, f"{src_pose} → {goal}: không có đường")
        end = _simulate(src_pose, route)
        self.assertEqual(end[0], goal,
                         f"{src_pose} → {goal}: dừng ở {end[0]} ({nav.route_to_text(route)})")
        self.assertEqual(end, new_pose, "pose dự đoán khác pose mô phỏng")

    def test_start_to_every_shelf(self):
        for shelf in nav.SHELF_TERMINAL.values():
            self._check(nav.START_POSE, shelf)

    def test_every_shelf_to_every_factory(self):
        """12 tổ hợp — đây chính là nhóm mà bảng route tĩnh cũ sai 9/12."""
        for shelf in nav.SHELF_TERMINAL.values():
            for factory in nav.FACTORY_TERMINAL.values():
                self._check(nav.pose_at(shelf), factory)

    def test_every_factory_to_every_shelf(self):
        for factory in nav.FACTORY_TERMINAL.values():
            for shelf in nav.SHELF_TERMINAL.values():
                self._check(nav.pose_at(factory), shelf)

    def test_between_all_factory_pairs(self):
        terms = list(nav.FACTORY_TERMINAL.values())
        for a in terms:
            for b in terms:
                if a != b:
                    self._check(nav.pose_at(a), b)

    def test_task2_chain(self):
        for factory in nav.FACTORY_TERMINAL.values():
            self._check(nav.pose_at(factory), nav.LOOSE_TERMINAL)
        self._check(nav.pose_at(nav.LOOSE_TERMINAL), nav.JOINT_TERMINAL)

    def test_same_place_gives_empty_route(self):
        """Lấy tầng 2 cùng kệ → không phải di chuyển."""
        route, pose = nav.plan(nav.pose_at("SHELF0"), "SHELF0")
        self.assertEqual(route, [])
        self.assertEqual(pose, nav.pose_at("SHELF0"))

    def test_same_place_wrong_heading_still_turns(self):
        """Regression: đã ở kệ nhưng đang quay MẶT RA NGOÀI (route trước hỏng ngay
        sau lúc quay đầu) → phải quay lại vào kệ, không được trả route rỗng rồi
        tưởng mình đang quay mặt vào kệ."""
        route, pose = nav.plan(("SHELF0", nav.EAST), "SHELF0")
        self.assertNotEqual(route, [])
        self.assertEqual(pose, nav.pose_at("SHELF0"))
        self.assertEqual(_simulate(("SHELF0", nav.EAST), route), nav.pose_at("SHELF0"))

    def test_apply_partial_route(self):
        """navigation.apply: vị trí sau khi chạy DỞ một route."""
        start = nav.pose_at("SHELF0")
        self.assertEqual(nav.apply(start, []), start)
        self.assertEqual(nav.apply(start, [("right",), ("right",), ("forward", 1)]),
                         ("C0R0", nav.EAST))

    def test_apply_stops_at_invalid_step(self):
        """Bước không có line → dừng lại ở trạng thái hợp lệ cuối, không nổ."""
        # C0R2 không có line sang phải (hàng R2 đứt ở vòng tròn ROBOCON)
        self.assertEqual(nav.apply(("C0R2", nav.EAST), [("forward", 3)]),
                         ("C0R2", nav.EAST))

    def test_shelf_to_shelf_is_one_intersection(self):
        """Kệ↔kệ = 1 giao lộ (R1/R3 không cắt cột kệ), không phải 2."""
        route, _ = nav.plan(nav.pose_at("SHELF0"), "SHELF1")
        # Đếm cả "back": rút khỏi điểm cuối bằng cách LÙI cũng là đi hết 1 khoảng
        # line như tiến, chỉ khác là không phải quay đầu trước.
        hops = [c[1] for c in route if c[0] in ("forward", "back")]
        # ra khỏi điểm cuối (1) + đi 1 giao lộ dọc cột kệ (1)
        self.assertEqual(sum(hops), 2, nav.route_to_text(route))

    def test_route_leaving_terminal_starts_with_uturn(self):
        """Rời kệ để đi TIẾP THEO HƯỚNG CŨ thì vẫn phải quay đầu 180°.

        (Đi vuông góc thì rẻ hơn nếu LÙI ra — xem TestReverseExit.)
        """
        route, _ = nav.plan(nav.pose_at("SHELF0"), "F_foxconn")
        self.assertEqual(route[0][0], route[1][0])
        self.assertIn(route[0][0], ("left", "right"))


class TestMirroredHalf(unittest.TestCase):
    """Sa bàn chia đôi bởi tường giữa sân. Nếu nửa của đội là ẢNH GƯƠNG của nửa
    trong docs/sa_ban.png thì `config.BOARD_MIRRORED=True` phải đảo đúng chiều xoay
    mà giữ nguyên số giao lộ."""

    def setUp(self):
        self._saved = nav.MIRRORED

    def tearDown(self):
        nav.set_mirrored(self._saved)

    @staticmethod
    def _swap(route):
        flip = {"left": ("right",), "right": ("left",)}
        return [flip.get(c[0], c) for c in route]

    def _all_routes(self):
        out = {}
        places = list(nav.SHELF_TERMINAL.values()) + list(nav.FACTORY_TERMINAL.values())
        for src in places:
            for dst in places:
                if src != dst:
                    out[(src, dst)] = nav.plan(nav.pose_at(src), dst)[0]
        return out

    def test_mirrored_routes_are_turn_swapped(self):
        nav.set_mirrored(False)
        normal = self._all_routes()
        nav.set_mirrored(True)
        mirrored = self._all_routes()

        self.assertEqual(len(normal), len(mirrored))
        for key, route in normal.items():
            self.assertEqual(self._swap(route), mirrored[key],
                             f"{key}: nửa gương phải là ảnh gương của nửa chuẩn")

    def test_mirrored_start_heading_flips(self):
        nav.set_mirrored(True)
        self.assertEqual(nav.START_POSE[1], nav.EAST)
        self.assertEqual(nav.TOWARD_SHELVES, nav.EAST)
        for term in nav.TERMINALS:
            if term != "START":
                self.assertIsNotNone(nav.plan(nav.START_POSE, term)[0])

    def test_set_mirrored_is_reversible(self):
        nav.set_mirrored(False)
        before = nav.plan(nav.pose_at("SHELF0"), "F_samsung")[0]
        nav.set_mirrored(True)
        nav.set_mirrored(False)
        self.assertEqual(nav.plan(nav.pose_at("SHELF0"), "F_samsung")[0], before)


class TestFactoryOrderPerHalf(unittest.TestCase):
    """Hai nửa sân là bản quay 180° của nhau NÊN chiều trái/phải giống nhau, nhưng
    cụm nhà máy in trên tường không quay theo → thứ tự nhà máy theo hàng bị ĐẢO.
    Đây mới là khác biệt thật giữa 2 nửa (xem docs/Sa bàn đầy đủ.png)."""

    def setUp(self):
        self._saved = nav.FACTORY_AT_START_ROW

    def tearDown(self):
        nav.set_factory_order(self._saved)

    def _rows(self):
        return {label: nav.TERMINALS[term][0]
                for label, term in nav.FACTORY_TERMINAL.items()}

    def test_order_is_reversed_between_halves(self):
        nav.set_factory_order("foxconn")
        blue = self._rows()
        nav.set_factory_order("samsung")
        red = self._rows()

        self.assertEqual(blue["foxconn"], red["samsung"])
        self.assertEqual(blue["samsung"], red["foxconn"])
        self.assertEqual(blue["amkor"], red["hana_micron"])
        self.assertEqual(blue["hana_micron"], red["amkor"])

    def test_start_row_factory_matches_flag(self):
        for side in nav.FACTORY_AT_START_ROW_CHOICES:
            nav.set_factory_order(side)
            # nhà máy cùng hàng ô xuất phát phải nằm ở node của hàng R0
            start_node = nav.TERMINALS["START"][0]          # C0R0
            row = start_node[-1]
            self.assertEqual(nav.TERMINALS[nav.FACTORY_TERMINAL[side]][0], f"C1R{row}")

    def test_joint_factory_stays_in_middle(self):
        for side in nav.FACTORY_AT_START_ROW_CHOICES:
            nav.set_factory_order(side)
            self.assertEqual(nav.TERMINALS[nav.JOINT_TERMINAL][0], "C1R2",
                             "nhà máy liên hợp ở giữa nên không đổi khi lật nửa sân")

    def test_all_routes_valid_on_both_halves(self):
        for side in nav.FACTORY_AT_START_ROW_CHOICES:
            nav.set_factory_order(side)
            for shelf in nav.SHELF_TERMINAL.values():
                for factory in nav.FACTORY_TERMINAL.values():
                    src = nav.pose_at(shelf)
                    route, pose = nav.plan(src, factory)
                    self.assertIsNotNone(route, f"{side}: {shelf}→{factory}")
                    self.assertEqual(_simulate(src, route), pose,
                                     f"{side}: {shelf}→{factory}")

    def test_invalid_value_rejected(self):
        with self.assertRaises(ValueError):
            nav.set_factory_order("hana_micron")


class TestBoardSideSwitch(unittest.TestCase):
    """Công tắc gạt chọn nửa sân (control/board_switch.py)."""

    def setUp(self):
        from control.board_switch import BoardSideSwitch
        self._cls = BoardSideSwitch
        self._saved = getattr(config, "BOARD_SIDE_SWITCH_CLOSED", "samsung")

    def tearDown(self):
        config.BOARD_SIDE_SWITCH_CLOSED = self._saved

    def _switch(self, pressed: bool):
        sw = self._cls.__new__(self._cls)
        closed = getattr(config, "BOARD_SIDE_SWITCH_CLOSED", "samsung")
        sw.closed_side = closed
        sw.open_side = "foxconn" if closed == "samsung" else "samsung"
        sw.pin = 12
        sw._button = MagicMock(is_pressed=pressed)
        return sw

    def test_no_pin_returns_none(self):
        sw = self._cls(pin=None)
        self.assertIsNone(sw.read())
        self.assertFalse(sw.available)

    def test_closed_is_gnd_side(self):
        config.BOARD_SIDE_SWITCH_CLOSED = "samsung"
        self.assertEqual(self._switch(pressed=True).read(), "samsung")
        self.assertEqual(self._switch(pressed=False).read(), "foxconn")

    def test_mapping_can_be_swapped_in_config(self):
        """Đấu dây ngược thì đổi 1 hằng số, không phải đảo lại dây."""
        config.BOARD_SIDE_SWITCH_CLOSED = "foxconn"
        self.assertEqual(self._switch(pressed=True).read(), "foxconn")
        self.assertEqual(self._switch(pressed=False).read(), "samsung")

    def test_read_error_returns_none_not_a_guess(self):
        sw = self._switch(pressed=False)
        type(sw._button).is_pressed = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("GPIO lỗi")))
        self.assertIsNone(sw.read(), "đọc lỗi phải trả None để caller rơi về config")


class TestApplyBoardSide(unittest.TestCase):
    """Robot._apply_board_side(): công tắc THẮNG config, và phải nạp lại bản đồ."""

    def setUp(self):
        self._saved_order = nav.FACTORY_AT_START_ROW
        self._saved_cfg = getattr(config, "FACTORY_AT_START_ROW", "foxconn")
        self.robot = _robot_stub()
        self.robot._side_switch = MagicMock(pin=12)

    def tearDown(self):
        config.FACTORY_AT_START_ROW = self._saved_cfg
        nav.set_factory_order(self._saved_order)

    def test_switch_beats_config(self):
        nav.set_factory_order("foxconn")
        config.FACTORY_AT_START_ROW = "foxconn"
        self.robot._side_switch.read.return_value = "samsung"

        self.assertEqual(self.robot._apply_board_side(), "samsung")
        self.assertEqual(nav.FACTORY_AT_START_ROW, "samsung")
        # bản đồ phải đổi theo: Samsung về hàng ô xuất phát
        self.assertEqual(nav.TERMINALS[nav.FACTORY_TERMINAL["samsung"]][0], "C1R0")

    def test_falls_back_to_config_when_switch_unreadable(self):
        nav.set_factory_order("foxconn")
        config.FACTORY_AT_START_ROW = "samsung"
        self.robot._side_switch.read.return_value = None

        self.assertEqual(self.robot._apply_board_side(), "samsung")
        self.assertEqual(nav.FACTORY_AT_START_ROW, "samsung")

    def test_no_change_when_already_correct(self):
        nav.set_factory_order("samsung")
        self.robot._side_switch.read.return_value = "samsung"
        self.assertEqual(self.robot._apply_board_side(), "samsung")
        self.assertEqual(nav.FACTORY_AT_START_ROW, "samsung")


class TestMidMatchReset(unittest.TestCase):
    """Reset giữa trận — luật cho 5 lần, mỗi lần −10 điểm.

    Đội viên đặt TAY robot về ô xuất phát rồi bấm nút. Robot phải chạy tiếp từ ô
    xuất phát nhưng GIỮ NGUYÊN tiến độ: kiện đã giao vẫn được tính điểm, và kiện đã
    lấy khỏi kệ thì không còn ở đó để lấy lại.
    """

    def setUp(self):
        self.robot = _robot_stub()
        self.robot.motion = MagicMock()
        self.robot.lift = MagicMock()
        self.robot._start_button = MagicMock()
        self.robot.packages_delivered = 5
        self.robot.pickup_count = 3
        self.robot.current_shelf = 1
        self.robot.current_tier = 2
        self.robot._tier_retries = 1
        self.robot.pose = nav.pose_at("F_samsung")
        self.robot.carried_labels = ["samsung", "foxconn"]
        self.robot.delivery_queue = ["foxconn"]
        self.robot._reset_requested = True
        self.robot._reset_count = 0
        self.robot.match_start_time = time.time()

    def test_reset_returns_to_start_and_keeps_progress(self):
        state = self.robot._handle_reset()

        self.assertEqual(state, State.START)
        self.assertEqual(self.robot.pose, nav.START_POSE)
        # tiến độ PHẢI giữ nguyên
        self.assertEqual(self.robot.packages_delivered, 5)
        self.assertEqual(self.robot.current_shelf, 1)
        self.assertEqual(self.robot.current_tier, 2)
        # càng phải được hạ về sàn và xoá kiện đang mang
        self.robot.lift.reset.assert_called_once()
        self.assertEqual(self.robot.carried_labels, [None, None])
        self.assertEqual(self.robot.delivery_queue, [])

    def test_reset_counted_and_flag_cleared(self):
        self.robot._handle_reset()
        self.assertEqual(self.robot._reset_count, 1)
        self.assertFalse(self.robot._reset_requested,
                         "không xoá cờ thì sẽ reset lặp vô hạn")

    def test_reset_does_not_extend_match_clock(self):
        before = self.robot.match_start_time
        self.robot._handle_reset()
        self.assertEqual(self.robot.match_start_time, before,
                         "reset KHÔNG được cộng thêm giờ")

    def test_button_during_match_requests_reset_and_stops(self):
        self.robot._reset_requested = False
        self.robot._on_reset_button()
        self.assertTrue(self.robot._reset_requested)
        self.robot.motion.stop.assert_called()

    def test_reset_waits_for_second_press_before_running_again(self):
        """Luật: đội viên TAY đặt robot về ô xuất phát. Chạy tiếp ngay sau cú bấm
        gây reset = robot tiến trong lúc người còn đang bê nó."""
        self.robot._handle_reset()
        self.robot._start_button.wait_for_press.assert_called_once()

    def test_reset_waits_for_release_before_press(self):
        """Nút có thể vẫn đang được giữ từ cú bấm gây reset — wait_for_press() sẽ
        trả về ngay nếu không chờ nhả trước, tức là tự xác nhận mà không ai bấm."""
        calls = []
        self.robot._start_button.wait_for_release.side_effect = \
            lambda *a, **k: calls.append("release")
        self.robot._start_button.wait_for_press.side_effect = \
            lambda *a, **k: calls.append("press")
        self.robot._handle_reset()
        self.assertEqual(calls, ["release", "press"])

    def test_confirm_press_is_not_taken_as_a_new_reset(self):
        """Callback phải được gỡ trong lúc chờ, nếu không cú bấm xác nhận lại bị
        hiểu là yêu cầu reset mới → reset lặp vô hạn."""
        self.robot._handle_reset()
        self.assertFalse(self.robot._reset_requested)
        # ...và phải được gắn lại để lần reset sau vẫn bấm được
        self.assertEqual(self.robot._start_button.when_pressed,
                         self.robot._on_reset_button)

    def test_reset_clears_tier_retries(self):
        """Tầng đang dở bị bỏ giữa chừng — bộ đếm retry phải về 0."""
        self.robot._handle_reset()
        self.assertEqual(self.robot._tier_retries, 0)

    def test_button_failure_does_not_hang_the_match(self):
        """Nút hỏng/đứt dây → log lỗi rồi chạy tiếp, không đứng im hết 240s."""
        self.robot._start_button.wait_for_press.side_effect = RuntimeError("nút hỏng")
        self.assertEqual(self.robot._handle_reset(), State.START)

    def test_wait_is_bounded_by_remaining_match_time(self):
        """Không ai bấm xác nhận → không được treo quá 240s, còn phải in kết quả."""
        self.robot.match_start_time = time.time() - 200      # còn ~40s
        self.robot._handle_reset()
        timeout = self.robot._start_button.wait_for_press.call_args.kwargs["timeout"]
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, config.MATCH_DURATION - 200 + 1)


class TestMotionAbort(unittest.TestCase):
    """Motion phải bỏ dở NGAY khi có yêu cầu reset, không chờ hết timeout."""

    def setUp(self):
        self.motion = Motion()

    def tearDown(self):
        self.motion.abort_check = None

    def test_no_abort_check_is_noop(self):
        self.motion.abort_check = None
        self.assertFalse(self.motion._aborted())

    def test_abort_stops_motors(self):
        self.motion.abort_check = lambda: True
        self.assertTrue(self.motion._aborted())

    def test_abort_check_exception_does_not_crash(self):
        self.motion.abort_check = lambda: 1 / 0
        self.assertFalse(self.motion._aborted())

    def test_long_loops_return_false_when_aborted(self):
        self.motion.abort_check = lambda: True
        self.assertFalse(self.motion.follow_line_until_intersection(timeout=5))
        self.assertFalse(self.motion.navigate_intersections(3))
        self.assertFalse(self.motion.advance_to_end(timeout=5))
        self.assertFalse(self.motion.exit_start_zone(timeout=5))


class TestStartTimeGuard(unittest.TestCase):
    """START phải từ chối xuất phát khi trận đã hết giờ.

    Đường vào START sau RESET bỏ qua lần kiểm giờ của _run_state_machine (nó
    `continue` ngay sau _handle_reset). Không chặn ở đây thì reset lúc 239s mà không
    ai bấm xác nhận sẽ làm robot lao ra khỏi ô xuất phát sau khi đã hết giờ.
    """

    def _robot(self):
        robot = _robot_stub()
        robot.motion = MagicMock()
        robot.motion.exit_start_zone.return_value = True
        return robot

    def test_refuses_to_start_when_time_is_up(self):
        robot = self._robot()
        robot.match_start_time = time.time() - config.MATCH_DURATION
        self.assertEqual(robot._handle_start(), State.DONE)
        robot.motion.exit_start_zone.assert_not_called()

    def test_starts_normally_at_the_beginning_of_a_match(self):
        robot = self._robot()
        robot.match_start_time = time.time()
        self.assertEqual(robot._handle_start(), State.DETECT_SIDE)
        robot.motion.exit_start_zone.assert_called()

    def test_clock_not_started_yet_does_not_block(self):
        """Luyện tập/khởi động: match_start_time = 0 thì không được coi là hết giờ."""
        robot = self._robot()
        robot.match_start_time = 0.0
        self.assertEqual(robot._handle_start(), State.DETECT_SIDE)


class TestDetectSide(unittest.TestCase):
    """State DETECT_SIDE: robot tự dò nửa sân bằng nhánh line ở giao lộ Kệ 3."""

    def setUp(self):
        self._saved_map = nav.MIRRORED
        self._saved_flag = getattr(config, "BOARD_AUTO_DETECT", True)
        nav.set_mirrored(False)
        self.robot = _robot_stub()
        self.robot.motion = MagicMock()
        self.robot.motion.execute_route.return_value = True
        self.robot.pose = nav.START_POSE

    def tearDown(self):
        config.BOARD_AUTO_DETECT = self._saved_flag
        nav.set_mirrored(self._saved_map)

    def test_line_found_keeps_standard_map(self):
        config.BOARD_AUTO_DETECT = True
        self.robot.motion.probe_side_branch.return_value = True
        self.assertEqual(self.robot._handle_detect_side(), State.NAVIGATE_TO_SHELF)
        self.assertFalse(nav.MIRRORED)
        self.assertEqual(self.robot.pose, (nav.PROBE_NODE, nav.TOWARD_SHELVES))

    def test_no_line_switches_to_mirrored_map(self):
        """Không thấy nhánh line bên phải → đang ở nửa gương → nạp lại bản đồ."""
        config.BOARD_AUTO_DETECT = True
        self.robot.motion.probe_side_branch.return_value = False
        self.assertEqual(self.robot._handle_detect_side(), State.NAVIGATE_TO_SHELF)
        self.assertTrue(nav.MIRRORED)
        self.assertEqual(self.robot.pose, (nav.PROBE_NODE, nav.TOWARD_SHELVES))
        # bản đồ mới phải dùng được ngay
        self.assertIsNotNone(nav.plan(self.robot.pose, "SHELF0")[0])

    def test_sensor_error_keeps_configured_map(self):
        config.BOARD_AUTO_DETECT = True
        self.robot.motion.probe_side_branch.return_value = None
        self.robot._handle_detect_side()
        self.assertFalse(nav.MIRRORED, "dò lỗi thì giữ nguyên cấu hình, không đoán")

    def test_disabled_skips_probe(self):
        config.BOARD_AUTO_DETECT = False
        self.robot._handle_detect_side()
        self.robot.motion.probe_side_branch.assert_not_called()

    def test_navigation_failure_does_not_flip_map(self):
        """Không tới được giao lộ dò → không được dò bừa rồi lật bản đồ."""
        config.BOARD_AUTO_DETECT = True
        self.robot.motion.execute_route.return_value = False
        self.robot.motion.last_route_progress = []
        self.robot._handle_detect_side()
        self.robot.motion.probe_side_branch.assert_not_called()
        self.assertFalse(nav.MIRRORED)

    def test_probe_runs_only_once_per_match(self):
        """Sau RESET, state machine quay lại START → DETECT_SIDE. Sa bàn không đổi
        giữa trận nên dò lại chỉ tốn ~2-4s để ra đúng kết quả cũ."""
        config.BOARD_AUTO_DETECT = True
        self.robot.motion.probe_side_branch.return_value = True
        self.robot._handle_detect_side()
        self.assertTrue(self.robot._side_detected)

        self.robot.motion.probe_side_branch.reset_mock()
        self.assertEqual(self.robot._handle_detect_side(), State.NAVIGATE_TO_SHELF)
        self.robot.motion.probe_side_branch.assert_not_called()

    def test_sensor_error_leaves_probe_open_for_retry(self):
        """Dò lỗi cảm biến = chưa có kết luận → lần reset sau vẫn được thử lại."""
        config.BOARD_AUTO_DETECT = True
        self.robot.motion.probe_side_branch.return_value = None
        self.robot._handle_detect_side()
        self.assertFalse(self.robot._side_detected)


class TestReverseExit(unittest.TestCase):
    """Lệnh ("back", N) — rút khỏi kệ/nhà máy mà không xoay 180°.

    Xoay là chi phí cố định LỚN NHẤT của trận (~70 lần). Mỗi lần rút bằng cách lùi
    bỏ được 2 lần xoay khi chặng kế tiếp đi vuông góc.
    """

    def test_perpendicular_leg_uses_reverse(self):
        """Kệ 2 → Samsung: rời kệ rồi đi LÊN — lùi ra rẻ hơn quay đầu."""
        route, _ = nav.plan(nav.pose_at("SHELF1"), "F_samsung")
        self.assertEqual(route[0], ("back", 1), nav.route_to_text(route))

    def test_straight_leg_still_turns_around(self):
        """Kệ 3 → Foxconn: rời kệ rồi đi THẲNG tiếp — quay đầu vẫn rẻ hơn."""
        route, _ = nav.plan(nav.pose_at("SHELF0"), "F_foxconn")
        self.assertNotIn("back", [c[0] for c in route], nav.route_to_text(route))

    def test_reverse_keeps_heading_and_reaches_the_node(self):
        pose = nav.pose_at("SHELF1")                    # (SHELF1, hướng vào kệ)
        self.assertEqual(nav.apply(pose, [("back", 1)]),
                         (nav.TERMINALS["SHELF1"][0], pose[1]))

    def test_reverse_from_wrong_heading_is_rejected(self):
        """Đã quay đầu rồi mà còn lùi = lùi vào kệ. apply() phải dừng tại chỗ."""
        node, term_heading, _ = nav.TERMINALS["SHELF1"]
        pose = ("SHELF1", nav.opposite(term_heading))
        self.assertEqual(nav.apply(pose, [("back", 1)]), pose)

    def test_reverse_only_from_terminals(self):
        """Giữa 2 giao lộ không được lùi — chỉ dùng để rút khỏi điểm cuối."""
        self.assertEqual(nav.apply(("C1R2", nav.NORTH), [("back", 1)]),
                         ("C1R2", nav.NORTH))

    def test_never_reverses_out_of_the_start_box(self):
        """Ô xuất phát nằm giữa khoảng ĐỨT 245mm của hàng R0 — không có line để bám
        khi lùi. Ra khỏi đó phải bằng exit_start_zone() (tiến thẳng qua chỗ hở)."""
        for dst in list(nav.TERMINALS) + list(nav.NODES):
            if dst == "START":
                continue
            route, _ = nav.plan(nav.pose_at("START"), dst)
            if not route:
                continue
            with self.subTest(dst=dst):
                self.assertNotIn("back", [c[0] for c in route],
                                 nav.route_to_text(route))

    def test_no_route_reverses_into_a_shelf(self):
        """Quét MỌI tuyến (điểm cuối + giao lộ): lệnh lùi chỉ được ở ĐẦU route, và
        không bao giờ được nối tiếp bằng forward/advance — lùi ra rồi tiến lại vào
        chính chỗ vừa rời là đi thừa, mà tệ hơn là đi ngược vào kệ."""
        targets = list(nav.TERMINALS) + list(nav.NODES)
        for src in nav.TERMINALS:
            for dst in targets:
                if src == dst:
                    continue
                route, _ = nav.plan(nav.pose_at(src), dst)
                if not route:
                    continue
                for i, cmd in enumerate(route):
                    if cmd[0] != "back":
                        continue
                    with self.subTest(src=src, dst=dst):
                        self.assertEqual(i, 0, nav.route_to_text(route))
                        nxt = route[i + 1][0] if i + 1 < len(route) else None
                        self.assertNotIn(nxt, ("forward", "advance"),
                                         nav.route_to_text(route))

    def test_apply_matches_plan_for_every_route(self):
        """Mô phỏng độc lập phải ra đúng vị trí mà plan() hứa — gồm cả lệnh lùi."""
        for src in nav.TERMINALS:
            for dst in nav.TERMINALS:
                if src == dst:
                    continue
                route, promised = nav.plan(nav.pose_at(src), dst)
                if route is None:
                    continue
                with self.subTest(src=src, dst=dst):
                    self.assertEqual(nav.apply(nav.pose_at(src), route), promised,
                                     nav.route_to_text(route))

    def test_reverse_cuts_total_turns_across_the_match(self):
        """Đo trên toàn bộ tuyến kệ→nhà máy: phải bớt được nhiều lần xoay."""
        def turns(pose, goal):
            route, _ = nav.plan(pose, goal)
            return sum(1 for c in route if c[0] in ("left", "right"))

        pairs = [(nav.pose_at(s), f) for s in ("SHELF0", "SHELF1", "SHELF2")
                 for f in nav.FACTORY_TERMINAL.values()]
        with_reverse = sum(turns(p, g) for p, g in pairs)

        saved = config.EDGE_COST_REVERSE
        try:
            config.EDGE_COST_REVERSE = 10 ** 6      # cấm lùi → về hành vi cũ
            without = sum(turns(p, g) for p, g in pairs)
        finally:
            config.EDGE_COST_REVERSE = saved

        self.assertLess(with_reverse, without,
                        f"lùi phải bớt xoay ({with_reverse} vs {without})")


class TestRouteCost(unittest.TestCase):
    def test_cost_is_positive_and_symmetric_ish(self):
        # Đo từ Kệ 1 (R4), KHÔNG phải Kệ 3: tuyến Kệ3→Foxconn đi qua cạnh R0 bị phạt
        # EDGE_COST_START_GAP nên chi phí không còn phản ánh khoảng cách nữa.
        c1 = nav.route_cost(nav.pose_at("SHELF2"), "F_samsung")      # cùng hàng R4
        c2 = nav.route_cost(nav.pose_at("SHELF2"), "F_foxconn")      # tận hàng R0
        self.assertGreater(c1, 0)
        self.assertGreater(c2, c1, "Kệ1 (R4) tới Foxconn (R0) phải xa hơn tới Samsung (R4)")

    def test_unreachable_goal_is_expensive(self):
        with self.assertRaises(KeyError):
            nav.route_cost(nav.START_POSE, "KHONG_TON_TAI")


class TestPlanDelivery(unittest.TestCase):
    def test_same_label_single_stop(self):
        robot = _robot_stub()
        robot._plan_delivery("samsung", "samsung")
        self.assertEqual(robot.delivery_queue, ["samsung"])

    def test_different_labels_picks_cheaper_order(self):
        robot = _robot_stub()
        robot.pose = nav.pose_at("SHELF0")     # đang ở Kệ 3 (R0)
        robot._plan_delivery("samsung", "foxconn")
        self.assertEqual(len(robot.delivery_queue), 2)
        self.assertSetEqual(set(robot.delivery_queue), {"samsung", "foxconn"})

        cost_a = robot._delivery_cost("samsung", "foxconn")
        cost_b = robot._delivery_cost("foxconn", "samsung")
        expected = "samsung" if cost_a <= cost_b else "foxconn"
        self.assertEqual(robot.delivery_queue[0], expected)

    def test_unknown_label_not_crash(self):
        robot = _robot_stub()
        self.assertEqual(robot._delivery_cost("khong_ton_tai", "samsung"), 10 ** 6)


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

    def test_execute_route_empty_is_success(self):
        """Route rỗng = đã ở đích (vd lấy tầng 2 cùng kệ), không phải lỗi."""
        self.assertTrue(self.motion.execute_route([]))

    def test_execute_route_rejects_unknown_command(self):
        self.assertFalse(self.motion.execute_route([("bay_len",)]))

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


class TestGotoHelper(unittest.TestCase):
    def test_already_at_goal_skips_motion(self):
        robot = _robot_stub()
        robot.motion = MagicMock()
        robot.pose = nav.pose_at("SHELF0")
        self.assertTrue(robot._goto("SHELF0", "test"))
        robot.motion.execute_route.assert_not_called()

    def test_fail_at_first_step_keeps_pose(self):
        """Route hỏng ngay bước đầu → vẫn ở chỗ cũ, để lần retry chạy lại cả route."""
        robot = _robot_stub()
        robot.pose = nav.pose_at("SHELF0")
        robot.motion = MagicMock()
        robot.motion.execute_route.return_value = False
        robot.motion.last_route_progress = []
        self.assertFalse(robot._goto("F_foxconn", "test"))
        self.assertEqual(robot.pose, nav.pose_at("SHELF0"))

    def test_partial_progress_updates_pose(self):
        """Chạy dở → vị trí tính theo các bước ĐÃ hoàn thành, không đoán là đã tới."""
        robot = _robot_stub()
        robot.pose = nav.pose_at("SHELF0")
        robot.motion = MagicMock()
        robot.motion.execute_route.return_value = False
        # xoay 180° rồi đi được 1 giao lộ (ra tới node cột kệ) thì mất line
        robot.motion.last_route_progress = [("right",), ("right",), ("forward", 1)]
        self.assertFalse(robot._goto("F_foxconn", "test"))
        self.assertEqual(robot.pose, ("C0R0", nav.EAST))

    def test_success_updates_pose(self):
        robot = _robot_stub()
        robot.motion = MagicMock()
        robot.motion.execute_route.return_value = True
        self.assertTrue(robot._goto("SHELF2", "test"))
        self.assertEqual(robot.pose, nav.pose_at("SHELF2"))


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
    """Mọi nhãn nhận diện được đều phải có điểm giao trên bản đồ."""

    def test_all_labels_have_factory_terminal(self):
        for label in config.COLOR_RANGES:
            self.assertIn(label, nav.FACTORY_TERMINAL)
            self.assertIn(nav.FACTORY_TERMINAL[label], nav.TERMINALS)

    def test_all_shelves_have_terminal(self):
        for shelf in range(config.SHELVES_TASK1):
            self.assertIn(shelf, nav.SHELF_TERMINAL)

    def test_every_terminal_attaches_to_real_node(self):
        for term, (node, _h, _d) in nav.TERMINALS.items():
            self.assertIn(node, nav.NODES, f"{term} gắn vào node không tồn tại")


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
        robot.pose = nav.pose_at("F_amkor")
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
        self.assertEqual(robot.pose, nav.START_POSE)
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
