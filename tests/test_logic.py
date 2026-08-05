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

# ⚠️ PHẢI đặt TRƯỚC khi import control.* — chạy file này TRÊN PI mà không có dòng này
# thì Motion() gắn vào chân GPIO thật. Xem giải thích đầy đủ ở tests/test_units.py.
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
os.environ.setdefault("GPIOZERO_MOCK_PIN_CLASS", "mockpwmpin")

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

    def test_uturn_is_two_turns_in_the_SAME_direction(self):
        """Quay đầu 180° = hai lần xoay CÙNG CHIỀU, không phải trái rồi phải.

        ⚠️ Bài này TRƯỚC ĐÂY dùng tuyến Kệ 3 → Foxconn làm ví dụ, vì hồi đó tuyến
        rẻ nhất tới Foxconn là quay đầu rồi đi thẳng qua ô xuất phát. Đo trên robot
        03/08: tuyến đó KHÔNG CHẠY ĐƯỢC — vạch line đứt 245mm ở ô xuất phát, robot
        ra ngoài line và đi lung tung. EDGE_COST_START_GAP đã nâng 3 → 20 để tránh
        hẳn, nên Kệ 3 → Foxconn giờ mở đầu bằng LÙI.
        Tính chất "quay đầu = 2 lần xoay cùng chiều" thì vẫn đúng, nên bài kiểm
        thẳng vào apply() thay vì mượn một tuyến cụ thể — tuyến thì đổi theo chi
        phí, tính chất thì không.
        """
        pose = nav.pose_at("SHELF0")
        for chieu in ("left", "right"):
            sau = nav.apply(pose, [(chieu,), (chieu,)])
            self.assertEqual(sau[0], pose[0], "quay đầu tại chỗ, KHÔNG đổi vị trí")
            self.assertNotEqual(sau[1], pose[1], "hướng phải đổi")
            self.assertEqual(nav.apply(sau, [(chieu,), (chieu,)])[1], pose[1],
                             "quay đầu hai lần thì về hướng cũ")


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
        robot.motion.tren_giao_lo_dau = False
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


class TestNoDropOutsideFactory(unittest.TestCase):
    """Hết giờ ở DELIVER thì DỪNG, không được thả kiện giữa sân.

    Bản trước rẽ sang DROP_FIRST/DROP_SECOND. Thả ngoài khu nhà máy = 0 điểm theo
    thể lệ, NHƯNG cảm biến IR vẫn xác nhận pallet đã rời càng nên packages_delivered
    vẫn +1/+2. Con số đó dùng để: in điểm ra log, quyết định chuyển sang NV2
    (>= TOTAL_PACKAGES_TASK1), và làm đầu vào cho tools.measure_phases — sai một chỗ
    là sai cả chuỗi, mà không có dấu hiệu lỗi nào.
    """

    def _robot(self, queue, carried):
        robot = _robot_stub()
        robot.motion = MagicMock()
        robot.lift = MagicMock()
        robot.lift.dropoff.return_value = True
        robot.lift.dropoff_left.return_value = True
        robot.lift.dropoff_right.return_value = True
        robot.vision = MagicMock()
        robot.vision.get_factory_name.side_effect = lambda lb: lb
        robot.packages_delivered = 0
        robot._last_delivered_label = None
        robot.delivery_queue = list(queue)
        robot.carried_labels = list(carried)
        robot.match_start_time = time.time() - (config.MATCH_DURATION - 1)  # còn 1s
        return robot

    def test_deliver_first_stops_instead_of_dropping(self):
        robot = self._robot(["samsung", "amkor"], ["samsung", "amkor"])
        self.assertEqual(robot._handle_deliver_first(), State.DONE)
        self.assertEqual(robot.packages_delivered, 0)
        robot.lift.dropoff.assert_not_called()
        robot.lift.dropoff_left.assert_not_called()

    def test_deliver_second_stops_instead_of_dropping(self):
        robot = self._robot(["amkor"], ["samsung", "amkor"])
        self.assertEqual(robot._handle_deliver_second(), State.DONE)
        self.assertEqual(robot.packages_delivered, 0)
        robot.lift.dropoff_right.assert_not_called()

    def test_still_delivers_when_time_is_fine(self):
        robot = self._robot(["samsung", "amkor"], ["samsung", "amkor"])
        robot.match_start_time = time.time()
        self.assertEqual(robot._handle_deliver_first(), State.DROP_FIRST)
        robot.motion.execute_route.assert_called()

    def test_queue_untouched_so_nothing_is_marked_delivered(self):
        """delivery_queue KHÔNG được pop: pop là hành vi của DROP, nghĩa là 'đã giao'."""
        robot = self._robot(["samsung", "amkor"], ["samsung", "amkor"])
        robot._handle_deliver_first()
        self.assertEqual(robot.delivery_queue, ["samsung", "amkor"])


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


class TestSoGiaoTheoNhaMay(unittest.TestCase):
    """Robot nhớ mỗi nhà máy đã nhận mấy kiện — nền cho việc tránh kiện đã thả.

    12 kiện chia 4 nhà máy = MỖI NHÀ MÁY 3 KIỆN. Khu nhà máy sâu 25cm, kiện sâu
    9cm → 3 kiện nối đuôi là 27cm, KHÔNG LỌT. Kiện thứ 2 và 3 phải tránh kiện đã
    nằm sẵn, mà muốn tránh thì trước hết phải BIẾT có bao nhiêu kiện ở đó.
    """

    def _robot(self):
        from unittest.mock import MagicMock
        import main
        r = object.__new__(main.Robot)
        r._retreat_from_shelf = MagicMock()
        return r

    def test_counts_per_factory_not_just_a_total(self):
        r = self._robot()
        r._ghi_nhan_giao("samsung")
        r._ghi_nhan_giao("hana_micron")
        r._ghi_nhan_giao("samsung")
        self.assertEqual(r._so_kien_da_giao("samsung"), 2)
        self.assertEqual(r._so_kien_da_giao("hana_micron"), 1)
        self.assertEqual(r._so_kien_da_giao("amkor"), 0)

    def test_drop_both_counts_two(self):
        r = self._robot()
        r._ghi_nhan_giao("amkor", 2)
        self.assertEqual(r._so_kien_da_giao("amkor"), 2)

    def test_ledger_is_lazily_created(self):
        """Test và dry_run dựng Robot bằng object.__new__ — không được nổ."""
        r = self._robot()
        self.assertEqual(r._so_kien_da_giao("foxconn"), 0)

    def test_backoff_is_ON_because_the_sonar_cannot_help_while_carrying(self):
        """⚠️ Phải ĐẾM kiện, không trông vào siêu âm.

        Đo 04/08 (tools.check_sees_dropped_package): siêu âm nhìn kiện dưới sàn RẤT
        tốt — có kiện 24.9cm (tản 0.1), bỏ ra 73.6cm, chênh +48.7cm.
        NHƯNG phép đo đó làm với càng Ở SÀN, KHÔNG mang gì. Lúc giao hàng robot
        đang CÕNG KIỆN và chính kiện đó chắn chùm sóng (đo 03/08: cõng hàng đọc
        8-10cm suốt, thả xong cùng cảm biến đọc 100cm). Siêu âm "thấy" được kiện cũ
        nhưng KHÔNG thấy vào đúng lúc cần → bắt buộc đếm.
        """
        self.assertGreater(config.FACTORY_STACK_BACKOFF_CM, 0.0,
                           "tắt thì kiện thứ 2 chồng lên kiện thứ 1")

    def test_first_package_at_a_factory_is_NOT_backed_off(self):
        """Nhà máy còn trống thì thả đúng chỗ, không lùi vô cớ."""
        r = self._robot()
        r._lui_tranh_kien_cu("samsung")
        r._retreat_from_shelf.assert_not_called()

    def test_backoff_scales_with_how_many_are_already_there(self):
        """Bù tăng theo số kiện đã có — bài này kiểm ĐƯỜNG LÙI (chốt quãng TẮT).

        Từ 04/08, mặc định là TRỪ NGAY vào quãng đi vào nhà máy
        (ADVANCE_FACTORY_STOP_CM > 0) và khi đó bước lùi này bị tắt để không bù
        HAI LẦN — xem TestTranhKienCuKhongBuHaiLan trong test_units. Bài này ép
        chốt quãng về 0 để vẫn kiểm được đường lùi cũ.
        """
        from unittest.mock import patch
        r = self._robot()
        with patch.object(config, "FACTORY_STACK_BACKOFF_CM", 9.0), \
             patch.object(config, "ADVANCE_FACTORY_STOP_CM", 0.0):
            r._lui_tranh_kien_cu("samsung")          # chưa có kiện nào
            r._retreat_from_shelf.assert_not_called()
            r._ghi_nhan_giao("samsung")
            r._lui_tranh_kien_cu("samsung")          # đã có 1 kiện → lùi 9cm
            self.assertAlmostEqual(
                r._retreat_from_shelf.call_args.kwargs["quang_cm"], 9.0)
            r._ghi_nhan_giao("samsung")
            r._lui_tranh_kien_cu("samsung")          # đã có 2 kiện → lùi 18cm
            self.assertAlmostEqual(
                r._retreat_from_shelf.call_args.kwargs["quang_cm"], 18.0)


class TestKiemDaToiKeTruocKhiBoc(unittest.TestCase):
    """⚠️ Trước khi bốc phải KIỂM đã tới kệ thật chưa — chặng về là chặng dễ lệch nhất.

    Chặng quay về kệ sau khi giao xong dài nhất trận (tới 4 lần xoay, 6-7 giao lộ)
    nên sai một chỗ là cộng dồn. Mà bước bốc KHÔNG tự phát hiện được: bước tiếp cận
    đã bỏ, nên robot nâng càng rồi luồn vào chỗ trống suốt INSERT_TIMEOUT = 8s mới
    báo lỗi — mất cả lượt.
    Lúc này siêu âm DÙNG ĐƯỢC (đã thả hết hàng, không còn kiện chắn) và ở ~20cm nó
    đọc mặt kệ rất chuẩn — advance vừa dừng bằng chính số đo đó.
    """

    def _robot(self, dist):
        from unittest.mock import MagicMock
        import main
        r = object.__new__(main.Robot)
        r.motion = MagicMock()
        r.motion.get_distance.return_value = dist
        r.current_shelf, r.current_tier = 0, 1
        r.is_time_safe = lambda: True
        r._retry_or_skip_tier = MagicMock(return_value="RETRY")
        r.vision = MagicMock()
        r.vision.classify_pair.return_value = ("samsung", "amkor")
        # Chỉ kiểm CỬA CHẶN đầu hàm; phần sau giả lập cho qua.
        r.carried_labels = [None, None]
        r._dat_co_cong_hang = MagicMock()
        r._plan_delivery = MagicMock()
        r._insert_and_lift = MagicMock(return_value=True)
        r._retreat_from_shelf = MagicMock()
        r._clear_carry_state = MagicMock()
        r._tier_retries = 0
        r.pickup_count = 0
        return r

    def test_far_from_any_shelf_retries_navigation(self):
        r = self._robot(dist=100.0)          # không thấy gì trước mặt
        r._handle_pickup_pair()
        r._retry_or_skip_tier.assert_called_once_with("navigate")

    def test_in_front_of_the_shelf_proceeds(self):
        r = self._robot(dist=19.5)
        r._handle_pickup_pair()
        r._retry_or_skip_tier.assert_not_called()
        r.vision.classify_pair.assert_called()

    def test_read_error_does_NOT_block(self):
        """Cảm biến lỗi thì thà THỬ BỐC còn hơn bỏ tầng."""
        r = self._robot(dist=-1.0)
        r._handle_pickup_pair()
        r._retry_or_skip_tier.assert_not_called()

    def test_non_numeric_reading_does_NOT_crash(self):
        from unittest.mock import MagicMock
        r = self._robot(dist=MagicMock())    # mock trả về vật lạ
        r._handle_pickup_pair()
        r._retry_or_skip_tier.assert_not_called()


class TestCoCongHangDuocHaSauKhiGiao(unittest.TestCase):
    """⚠️ Cờ "đang cõng hàng" phải HẠ sau khi giao xong, không kẹt cả trận.

    Đo trên robot 03/08: thả tầng 1 kệ đầu OK, nhưng quay lại kệ lấy tầng 2 thì
    "chạy rất lung tung". Nguyên nhân: carried_labels CHỈ được xoá khi bốc hàng
    THẤT BẠI hoặc reset — không bao giờ xoá sau khi GIAO XONG. Cờ vì thế bật suốt
    phần còn lại của trận, và advance_to_end khi cõng hàng thì BỎ QUA SIÊU ÂM rồi
    coi mảng tối đầu tiên là "đã vào khu nhà máy" → dừng bừa giữa đường về.
    """

    def _robot(self):
        from unittest.mock import MagicMock
        import main
        r = object.__new__(main.Robot)
        r.motion = MagicMock()
        r.motion.dang_cong_hang = False
        r.lift = MagicMock()
        r.lift.dropoff_left.return_value = True
        r.lift.dropoff_right.return_value = True
        r.carried_labels = ["samsung", "hana_micron"]
        r._retreat_from_shelf = MagicMock()
        r._dat_co_cong_hang()
        return r

    def test_flag_is_on_while_carrying(self):
        r = self._robot()
        self.assertTrue(r.motion.dang_cong_hang)

    def test_dropping_one_side_clears_only_that_label(self):
        r = self._robot()
        r._drop_single_side("left")
        self.assertEqual(r.carried_labels, [None, "hana_micron"])
        self.assertTrue(r.motion.dang_cong_hang, "còn 1 kiện thì cờ phải GIỮ")

    def test_flag_goes_down_once_both_are_delivered(self):
        r = self._robot()
        r._drop_single_side("left")
        r._da_tha_xong("right")
        self.assertEqual(r.carried_labels, [None, None])
        self.assertFalse(r.motion.dang_cong_hang,
                         "cờ kẹt bật → chặng VỀ KỆ bỏ qua siêu âm và dừng bừa")

    def test_label_is_cleared_even_when_IR_says_the_drop_failed(self):
        """Giữ nhãn khi IR báo hỏng là để cờ kẹt bật và phá NỐT chặng về."""
        r = self._robot()
        r.lift.dropoff_left.return_value = False
        r._drop_single_side("left")
        self.assertEqual(r.carried_labels[0], None)


class TestKhongQuayDauTaiDiemCuoi(unittest.TestCase):
    """⚠️ KHÔNG route nào được QUAY ĐẦU 180° ngay tại điểm cuối.

    Quay đầu tại điểm cuối = hai lần xoay CÙNG CHIỀU ở lệnh đầu route. Hai thứ hỏng
    theo, đo trên robot 03/08:
      • execute_route chỉ chèn TIẾN BÙ khi lệnh trước là `forward`; route mở đầu
        bằng xoay thì không có gì, robot quay quanh chỗ retreat bỏ nó lại nên tâm
        xoay sai và xoay xong cảm biến văng khỏi vạch — "bám line một lúc rồi đi
        lung tung, không về được kệ".
      • cổng quãng đường nhận "vừa rời điểm cuối" qua route[0] == "back", nên route
        quay đầu lọt lưới và robot đếm TẤM IN dưới chân thành giao lộ.
    EDGE_COST_REVERSE = 0 khiến bộ tìm đường luôn chọn LÙI để rút khỏi điểm cuối.
    """

    def _quay_dau(self, route):
        return (len(route) > 1 and route[0][0] in ("left", "right")
                and route[0][0] == route[1][0])

    def test_no_return_route_starts_with_a_uturn(self):
        for nm, t in nav.FACTORY_TERMINAL.items():
            route, _ = nav.plan(nav.pose_at(t), "SHELF0")
            self.assertFalse(self._quay_dau(route),
                             f"{nm} → Kệ 3 quay đầu tại nhà máy: "
                             f"{nav.route_to_text(route)}")

    def test_no_delivery_route_starts_with_a_uturn(self):
        for ke in ("SHELF0", "SHELF1", "SHELF2"):
            for nm, t in nav.FACTORY_TERMINAL.items():
                route, _ = nav.plan(nav.pose_at(ke), t)
                self.assertFalse(self._quay_dau(route),
                                 f"{ke} → {nm} quay đầu tại kệ: "
                                 f"{nav.route_to_text(route)}")


class TestReverseExit(unittest.TestCase):
    """Lệnh ("back", N) — rút khỏi kệ/nhà máy mà không xoay 180°.

    Xoay là chi phí cố định LỚN NHẤT của trận (~70 lần). Mỗi lần rút bằng cách lùi
    bỏ được 2 lần xoay khi chặng kế tiếp đi vuông góc.
    """

    def test_perpendicular_leg_uses_reverse(self):
        """Kệ 2 → Samsung: rời kệ rồi đi LÊN — lùi ra rẻ hơn quay đầu."""
        route, _ = nav.plan(nav.pose_at("SHELF1"), "F_samsung")
        self.assertEqual(route[0], ("back", 1), nav.route_to_text(route))

    def test_start_gap_is_avoided_even_when_it_is_the_short_way(self):
        """⚠️ Kệ 3 → Foxconn KHÔNG được đi xuyên ô xuất phát, dù đó là đường ngắn nhất.

        Foxconn cùng hàng R0 với ô xuất phát nên cạnh C0R0↔C1R0 là đường ngắn nhất
        tới nó. Nhưng vạch line ở đó ĐỨT 245mm và còn in hình mascot đen. Đo trên
        robot 03/08: robot quay 180° tại kệ, đi thẳng qua ô xuất phát, cảm biến ra
        ngoài line và đi lung tung — lạc ở đó thì rủi ro ra khỏi sa bàn (reset −10đ).
        EDGE_COST_START_GAP = 20 (mức 10 vẫn còn chọn cạnh này).
        Giá: route_cost tổng cho 4 nhà máy đi+về tăng 107 → 131, tức +22%.
        """
        route, _ = nav.plan(nav.pose_at("SHELF0"), "F_foxconn")
        nut = [nav.TERMINALS["SHELF0"][0]]
        pose = nav.pose_at("SHELF0")
        for lenh in route:
            pose = nav.apply(pose, [lenh])
            nut.append(pose[0])
        cap = set(zip(nut, nut[1:])) | set(zip(nut[1:], nut))
        self.assertNotIn(("C0R0", "C1R0"), cap,
                         f"tuyến đi xuyên khoảng đứt ô xuất phát: "
                         f"{nav.route_to_text(route)}")

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
        """Ngưỡng TUYỆT ĐỐI — ép tắt ngưỡng tương đối để kiểm riêng nhánh này.

        Không ép thì test đo lẫn hai cơ chế: ngưỡng tương đối tính lại theo dải
        sáng-tối của chính mẫu, nên giá trị sát ngưỡng tuyệt đối rơi về phía khác.
        Nhánh tương đối có test riêng ở TestNguongTuongDoi (test_units).
        """
        with patch.object(config, "LINE_ADAPTIVE", False):
            threshold = config.LINE_THRESHOLD / 1023.0
            raw = [0.0, threshold - 0.01, threshold + 0.01, 1.0]
            self.assertEqual(LineSensor.digital_from_raw(raw), [1, 1, 0, 0])

    def test_absolute_threshold_still_reachable(self):
        """Dải sáng-tối hẹp thì PHẢI rơi về ngưỡng tuyệt đối, kể cả khi bật tương đối."""
        gan_nhau = [0.60, 0.61, 0.60, 0.62]      # dải ~20/1023, hẹp hơn MIN_RANGE
        self.assertEqual(LineSensor.digital_from_raw(gan_nhau), [0, 0, 0, 0])


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

    def tearDown(self):
        # Phải đóng tường minh: không đóng thì chân GPIO còn bị giữ và test sau
        # báo GPIOPinInUse — trước đây chỉ chạy được nhờ GC dọn kịp, không tất định.
        self.motion.cleanup()

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


class TestConfigInvariants(unittest.TestCase):
    """Các quan hệ giữa hằng số config PHẢI đúng, không thì phần cứng hỏng/logic sai.

    Calibrate là sửa trực tiếp config.py (menu d của test_motion/test_lift, tools.
    calibrate_line, calibrate_vision). Mỗi hằng số nhìn riêng thì hợp lý, nhưng vài
    cặp có ràng buộc mà không chỗ nào kiểm — sửa một cái là ngầm phá cái kia.
    """

    def test_no_duplicate_gpio_pins(self):
        """2 thiết bị dùng chung 1 chân → gpiozero ném GPIOPinInUse lúc khởi tạo."""
        pins = {k: v for k, v in vars(config).items()
                if k.isupper() and isinstance(v, int) and not isinstance(v, bool)
                and ("PIN" in k or k.startswith(("IN1", "IN2", "IN3", "IN4", "ENA", "ENB")))}
        seen = {}
        for name, pin in sorted(pins.items()):
            with self.subTest(pin=name):
                self.assertNotIn(pin, seen,
                                 f"GPIO {pin} dùng cho cả {seen.get(pin)} và {name}")
            seen[pin] = name

    def test_does_not_use_hardware_spi_pins(self):
        """MCP3008 chiếm cứng GPIO 8/9/10/11 — không thiết bị nào được lấn vào."""
        spi = {8: "CE0", 9: "MISO", 10: "MOSI", 11: "SCLK"}
        for name, value in vars(config).items():
            if (name.isupper() and isinstance(value, int) and not isinstance(value, bool)
                    and ("PIN" in name or name.startswith(("IN", "ENA", "ENB")))):
                with self.subTest(const=name):
                    self.assertNotIn(value, spi,
                                     f"{name}={value} đụng chân SPI {spi.get(value)}")

    def test_distance_thresholds_ordered(self):
        self.assertLess(config.APPROACH_DISTANCE, config.APPROACH_SLOW_DISTANCE,
                        "điểm dừng phải gần hơn ngưỡng chuyển sang pha chậm")
        self.assertLessEqual(config.APPROACH_SLOW_DISTANCE, config.APPROACH_DETECT_DISTANCE,
                             "vào pha chậm mà chưa tính là 'đã thấy mục tiêu' thì "
                             "APPROACH_BLIND_TIMEOUT có thể cắt ngang lúc đang tới gần")
        self.assertGreater(config.RETREAT_DISTANCE, config.APPROACH_DISTANCE,
                           "lùi ra phải xa hơn lúc tiếp cận, không thì retreat về ngay")

    def test_blind_timeout_shorter_than_total(self):
        """Chặn chạy mù phải cắt TRƯỚC timeout tổng, không thì nó vô nghĩa."""
        self.assertLess(config.APPROACH_BLIND_TIMEOUT, config.APPROACH_TIMEOUT)

    def test_intersection_hysteresis_valid(self):
        """Ngưỡng CLEAR phải THẤP HƠN ngưỡng đếm, nếu không trễ 2 ngưỡng vô hiệu và
        một vạch cắt bị đếm thành nhiều giao lộ."""
        self.assertLess(config.INTERSECTION_CLEAR_THRESHOLD, config.INTERSECTION_THRESHOLD)
        self.assertLessEqual(config.INTERSECTION_THRESHOLD, config.LINE_SENSOR_COUNT,
                             "không bao giờ đủ mắt → không bao giờ nhận ra giao lộ")

    def test_task2_threshold_above_safety_margin(self):
        """Cả chuyến NV2 tốn ~20-25s: ngưỡng riêng phải lớn hơn SAFETY_MARGIN chung."""
        self.assertGreater(config.TASK2_MIN_TIME, config.SAFETY_MARGIN)

    def test_speeds_ordered(self):
        self.assertLessEqual(config.SPEED_SLOW, config.SPEED_DEFAULT)
        self.assertLess(config.APPROACH_SLOW_SPEED, config.APPROACH_FAST_SPEED)
        for name in ("SPEED_DEFAULT", "SPEED_SLOW", "SPEED_TURN", "APPROACH_FAST_SPEED",
                     "APPROACH_SLOW_SPEED", "ADVANCE_SPEED", "REVERSE_SPEED",
                     "EXIT_START_SPEED", "PROBE_SPEED"):
            with self.subTest(const=name):
                self.assertTrue(0 < getattr(config, name) <= 100,
                                f"{name} phải trong (0, 100]")

    def test_package_counts_consistent(self):
        """3 kệ × 2 tầng × 2 kiện = 12 kiện NV1. Sửa lệch là state machine dừng sai chỗ."""
        self.assertEqual(config.SHELVES_TASK1 * 2, config.PICKUPS_TASK1)
        self.assertEqual(config.PICKUPS_TASK1 * 2, config.TOTAL_PACKAGES_TASK1)
        self.assertEqual(len(nav.SHELF_TERMINAL), config.SHELVES_TASK1)

    def test_every_label_has_a_factory_and_a_terminal(self):
        for label in config.LABEL_TO_FACTORY:
            with self.subTest(label=label):
                self.assertIn(label, nav.FACTORY_TERMINAL,
                              "nhãn nhận diện được nhưng không có nhà máy trên bản đồ "
                              "→ main.py bỏ cả lượt giao")
                self.assertIn(nav.FACTORY_TERMINAL[label], nav.TERMINALS)

    def test_lift_home_covers_worst_case(self):
        """Nhắc lại ở đây vì calibrate LIFT_*_LOWER_EXTRA rất dễ phá ngưỡng home."""
        from control.lift import Lift, MAX_LEVEL
        lift = object.__new__(Lift)
        lift._current_level = 0
        self.assertGreaterEqual(config.LIFT_HOME_DURATION, lift.min_home_duration())


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


class TestDeliveryTrust(unittest.TestCase):
    """Chỉ TÍNH ĐIỂM khi có căn cứ tin là đang đứng trong khu nhà máy.

    Thả ngoài khu nhà máy = 0 điểm theo thể lệ, nhưng IR vẫn xác nhận pallet đã rời
    càng nên packages_delivered vẫn tăng nếu không chặn. Con số đó còn quyết định mốc
    chuyển sang NV2 và là đầu vào của tools.measure_phases — đếm sai một kiện là sai
    cả chuỗi, mà log thì vẫn báo thành công.
    """

    def _robot(self, nav_ok: bool) -> Robot:
        robot = object.__new__(Robot)
        robot._deliver_nav_ok = nav_ok
        return robot

    def test_navigate_ok_is_enough(self):
        """Tới được nhà máy thì siêu âm chớp lỗi một nhịp cũng vẫn tin."""
        self.assertTrue(self._robot(True)._delivery_is_trustworthy(False, "test"))

    def test_approach_ok_is_enough(self):
        """Siêu âm thấy tường khu nhà máy thì tìm đường trục trặc cũng vẫn tin."""
        self.assertTrue(self._robot(False)._delivery_is_trustworthy(True, "test"))

    def test_both_failing_is_not_trusted(self):
        """CẢ HAI hỏng = không biết đang ở đâu, trước mặt cũng trống trơn."""
        self.assertFalse(self._robot(False)._delivery_is_trustworthy(False, "test"))

    def test_only_both_failing_blocks_the_count(self):
        """Chốt lại bảng chân trị — chỉ đúng MỘT ô chặn đếm điểm."""
        for nav_ok in (True, False):
            for approach_ok in (True, False):
                with self.subTest(nav=nav_ok, approach=approach_ok):
                    got = self._robot(nav_ok)._delivery_is_trustworthy(approach_ok, "t")
                    self.assertEqual(got, nav_ok or approach_ok)


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
