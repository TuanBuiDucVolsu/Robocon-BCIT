#!/usr/bin/env python3
"""
Robot tự động Bảng O2 — Robocon Bắc Ninh mở rộng 2026.
State machine điều phối toàn bộ nhiệm vụ.
Nâng 2 kiện hàng/lượt (2 pallet cạnh nhau trên cùng tầng kệ).
"""

import os
import time
import enum
import logging
import signal
import sys

try:
    from gpiozero import Button, Device
    Device.ensure_pin_factory()
except Exception:
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory, MockPWMPin
        Device.pin_factory = MockFactory(pin_class=MockPWMPin)
        from gpiozero import Button
    except ImportError:
        from unittest.mock import MagicMock

        # Không gán thẳng MagicMock: tham số vị trí đầu của nó là `spec`, nên
        # Button(16, ...) sẽ sinh mock bị spec theo int (xem control/motion.py).
        def Button(*_args, **_kwargs):
            return MagicMock()

import config
import navigation
from control import Motion, Lift
from control.board_switch import BoardSideSwitch
from control.mcp3008_bus import get_mcp3008_bus, reset_mcp3008_bus
from control.handling import drop_both, drop_side, insert_and_lift_once
from vision import Vision

# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG_MODE else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("main")


# ============================================================
# Các trạng thái (States)
# ============================================================

class State(enum.Enum):
    INIT = "INIT"
    START = "START"
    DETECT_SIDE = "DETECT_SIDE"
    NAVIGATE_TO_SHELF = "NAVIGATE_TO_SHELF"
    PICKUP_PAIR = "PICKUP_PAIR"
    DELIVER_FIRST = "DELIVER_FIRST"
    DROP_FIRST = "DROP_FIRST"
    DELIVER_SECOND = "DELIVER_SECOND"
    DROP_SECOND = "DROP_SECOND"
    RETURN_TO_WAREHOUSE = "RETURN_TO_WAREHOUSE"
    TASK2_NAVIGATE_TO_LOOSE = "TASK2_NAVIGATE_TO_LOOSE"
    TASK2_PICKUP = "TASK2_PICKUP"
    TASK2_NAVIGATE_TO_JOINT = "TASK2_NAVIGATE_TO_JOINT"
    TASK2_DROP = "TASK2_DROP"
    DONE = "DONE"
    EMERGENCY_STOP = "EMERGENCY_STOP"


# ============================================================
# Bộ điều khiển Robot
# ============================================================

class Robot:
    def __init__(self):
        logger.info("========== KHỞI TẠO ROBOT ==========")
        self._mcp_bus = get_mcp3008_bus()
        self.motion = Motion(mcp_bus=self._mcp_bus)
        self.lift = Lift(mcp_bus=self._mcp_bus)
        self.vision = Vision()

        self.state = State.INIT
        self.packages_delivered = 0
        self.pickup_count = 0             # Số lần đã nâng (0-6)
        self.current_shelf = 0            # Giá kệ hiện tại (0 đến SHELVES_TASK1 - 1)
        self.current_tier = 1             # Tầng kệ hiện tại (1 = dưới, 2 = trên)
        self.match_start_time = 0.0
        self._tier_retries = 0            # Số lần đã thử lại tầng kệ hiện tại
        self.task2_done = False           # Kiện hàng rời NV2 đã giao chưa (kiện thứ 13)
        self._side_detected = False       # Đã dò xong chiều trái/phải chưa (1 lần/trận)

        # Đo thời gian từng chặng — để biết 240s đang tiêu vào đâu
        self._phase_times: dict[str, float] = {}
        self._phase_counts: dict[str, int] = {}

        # Vị trí + hướng hiện tại trên bản đồ (navigation.py). Mọi route được TÍNH
        # từ trạng thái này, không còn tra bảng route tĩnh.
        self.pose = navigation.START_POSE

        # 2 kiện đang mang trên càng
        self.carried_labels: list[str | None] = [None, None]
        # Đã giao mấy kiện cho TỪNG nhà máy. Mỗi nhà máy nhận 3 kiện trong trận,
        # nên kiện thứ 2 và 3 phải tránh kiện đã nằm sẵn ở đó.
        # Xem config.FACTORY_STACK_BACKOFF_CM.
        self.da_giao_theo_nha_may: dict[str, int] = {}
        # Thứ tự giao: [label_giao_trước, label_giao_sau] (tối ưu theo khoảng cách)
        self.delivery_queue: list[str] = []
        # Label cuối cùng đã giao thực tế (dùng để chọn route quay về)
        self._last_delivered_label: str | None = None
        # Bước DELIVER vừa rồi có tới được nhà máy không — DROP dùng để quyết định
        # có TÍNH ĐIỂM hay không (xem _delivery_is_trustworthy). Mặc định True để
        # đường nào chưa đi qua DELIVER cũng không bị coi là đáng ngờ.
        self._deliver_nav_ok = True

        # Khôi phục sau lỗi (chế độ thi đấu)
        self._resume_epoch: float | None = None   # mốc trận dở để chạy nốt thời gian
        self._enable_match_persist = False         # chỉ True ở run() thi đấu
        self._exit_code = 0                        # main() dùng để systemd restart khi ≠ 0

        # Nút khởi động
        self._start_button = Button(config.START_BUTTON_PIN, pull_up=True, bounce_time=0.1)

        # Công tắc gạt chọn nửa sân (quyết định thứ tự nhà máy trên tường)
        self._side_switch = BoardSideSwitch()
        self._apply_board_side()

        # Reset giữa trận (luật cho 5 lần, mỗi lần −10 điểm): đội viên đặt tay robot
        # về ô xuất phát rồi BẤM NÚT. Motion poll cờ này để bỏ dở việc đang làm ngay,
        # không phải chờ hết timeout.
        self._reset_requested = False
        self._reset_count = 0
        self.motion.abort_check = lambda: self._reset_requested

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info(navigation.board_summary())
        logger.info("Robot đã sẵn sàng. Nhấn nút khởi động để bắt đầu.")
        logger.info("Chế độ: nâng 2 kiện/lượt — %d lượt cho %d kiện",
                     config.PICKUPS_TASK1, config.TOTAL_PACKAGES_TASK1)

    # ----------------------------------------------------------
    # Nửa sân
    # ----------------------------------------------------------

    def _apply_board_side(self) -> str:
        """Đọc công tắc gạt → nạp đúng thứ tự nhà máy cho nửa sân đang thi đấu.

        Công tắc THẮNG config: ở sân chỉ cần gạt, không phải sửa file. Không đọc được
        công tắc (chưa lắp / đứt dây) → rơi về config.FACTORY_AT_START_ROW và ghi log
        rõ, vì đây là thứ đặt sai thì KHÔNG có tín hiệu báo lỗi nào khác.
        """
        side = self._side_switch.read()
        source = "CÔNG TẮC GẠT (GPIO %s)" % self._side_switch.pin
        if side is None:
            side = getattr(config, "FACTORY_AT_START_ROW", "foxconn")
            source = ("config.FACTORY_AT_START_ROW — KHÔNG đọc được công tắc"
                      if self._side_switch.pin is not None
                      else "config.FACTORY_AT_START_ROW (chưa lắp công tắc)")

        if side != navigation.FACTORY_AT_START_ROW:
            navigation.set_factory_order(side)

        logger.warning("=" * 60)
        logger.warning("  NỬA SÂN: nhà máy CÙNG HÀNG ô xuất phát = %s", side.upper())
        logger.warning("  Nguồn: %s", source)
        logger.warning("  KIỂM LẠI BẰNG MẮT: đứng ở ô xuất phát nhìn sang tường")
        logger.warning("  giữa sân — cụm nhà máy cùng hàng phải đúng là %s.", side.upper())
        logger.warning("  Sai = giao nhầm nhà máy, log vẫn báo thành công.")
        logger.warning("=" * 60)
        return side

    # ----------------------------------------------------------
    # Reset giữa trận
    # ----------------------------------------------------------

    def _on_reset_button(self):
        """Nút được bấm TRONG lúc đang chạy → trọng tài cho reset."""
        self._reset_requested = True
        self.motion.stop()
        logger.warning("NÚT ĐƯỢC BẤM GIỮA TRẬN → yêu cầu RESET")

    def _handle_reset(self) -> State:
        """Robot vừa được đặt tay về ô xuất phát — chạy tiếp từ đó.

        GIỮ NGUYÊN tiến độ (packages_delivered, current_shelf, current_tier) vì kiện
        đã giao vẫn được tính điểm và kiện đã lấy khỏi kệ thì không còn ở đó nữa.
        CHỈ đặt lại VỊ TRÍ. Đồng hồ trận vẫn chạy tiếp — reset không được cộng giờ.
        """
        self._reset_requested = False
        self._reset_count += 1
        self.motion.stop()

        logger.warning("=" * 60)
        logger.warning("  RESET lần %d — robot đã được đặt về ô xuất phát", self._reset_count)
        logger.warning("  Tiến độ giữ nguyên: %d/%d kiện, tiếp theo kệ %d tầng %d",
                       self.packages_delivered, config.TOTAL_PACKAGES_TASK1,
                       self.current_shelf, self.current_tier)
        logger.warning("  Còn %.0fs. Luật: tối đa 5 lần reset, mỗi lần −10 điểm.",
                       self.time_remaining())
        logger.warning("=" * 60)

        # Càng có thể đang mang kiện dở — hạ hết về sàn cho an toàn khi xuất phát lại
        self.lift.reset()
        self._clear_carry_state()
        self.pose = navigation.START_POSE
        # Tầng đang dở đã bị bỏ giữa chừng — trả bộ đếm retry về 0 để tầng mới
        # được thử đủ số lần như bình thường.
        self._tier_retries = 0
        self._wait_for_placement()
        return State.START

    def _wait_for_placement(self):
        """Chờ đội viên đặt XONG robot vào ô xuất phát rồi bấm nút lần nữa.

        BẮT BUỘC phải chờ: luật quy định đội viên TAY đặt robot về ô xuất phát. Nếu
        chạy tiếp ngay sau cú bấm gây reset thì robot bắt đầu tiến trong lúc người
        còn đang bê nó — vừa nguy hiểm vừa chắc chắn hỏng lượt vì xuất phát sai chỗ.
        """
        logger.warning("  → ĐẶT robot vào ô xuất phát (quay mặt về phía kệ), "
                       "rồi BẤM NÚT lần nữa để chạy tiếp")

        # Gỡ callback trước khi chờ: để nguyên thì chính cú bấm xác nhận này lại
        # được hiểu là một yêu cầu reset mới → reset lặp vô hạn.
        self._start_button.when_pressed = None
        # Không chờ lâu hơn thời gian trận còn lại: hết 240s thì có chờ tiếp cũng
        # không ghi thêm điểm, mà treo ở đây thì không bao giờ in được bảng kết quả.
        remaining = max(self.time_remaining(), 0.0) if self.match_start_time > 0 else None
        try:
            # Nút có thể VẪN đang được giữ từ cú bấm gây reset. wait_for_press()
            # trả về ngay khi nút đang ở trạng thái nhấn, nên phải chờ nhả trước —
            # không thì "xác nhận" tự xảy ra mà không ai bấm.
            self._start_button.wait_for_release(timeout=5)
            if self._start_button.wait_for_press(timeout=remaining) is False:
                logger.error("Hết giờ trận mà chưa có nút xác nhận — kết thúc")
            else:
                logger.warning("Đã bấm nút — chạy tiếp, còn %.0fs", self.time_remaining())
        except Exception as e:
            logger.error("Không chờ được nút (%s) — chạy tiếp ngay", e)

        # Cú bấm vừa rồi là XÁC NHẬN, không phải yêu cầu reset mới.
        self._reset_requested = False
        self._start_button.when_pressed = self._on_reset_button

    def _signal_handler(self, sig, frame):
        logger.warning("Nhận tín hiệu dừng (signal %s)", sig)
        self.state = State.EMERGENCY_STOP
        self._emergency_stop()
        # Dừng chủ động (Ctrl+C / systemctl stop) → xoá trận dở để không tự resume lần sau
        self._clear_match_state()
        sys.exit(0)

    # ----------------------------------------------------------
    # Timer
    # ----------------------------------------------------------

    def elapsed(self) -> float:
        return time.time() - self.match_start_time

    def time_remaining(self) -> float:
        return config.MATCH_DURATION - self.elapsed()

    def is_time_safe(self) -> bool:
        return self.time_remaining() > config.SAFETY_MARGIN

    def _goto(self, goal: str, context: str) -> bool:
        """Tính route từ trạng thái hiện tại đến `goal` rồi chạy. Cập nhật self.pose.

        Route chạy DỞ (mất line / timeout giao lộ) → vị trí mới tính từ các bước đã
        thật sự hoàn thành (`motion.last_route_progress`), KHÔNG đoán bừa là đã tới
        đích. Nhờ vậy lần thử lại của `_retry_or_skip_tier("navigate")` mới có ý
        nghĩa: robot chạy lại đúng phần đường còn thiếu thay vì tưởng đã tới nơi.
        """
        route, new_pose = navigation.plan(self.pose, goal)
        if route is None:
            logger.error("Không có đường từ %s tới %s — %s",
                         navigation.describe(self.pose), goal, context)
            return False

        if not route:
            logger.info("Đã ở %s rồi — không cần di chuyển (%s)", goal, context)
            self.pose = new_pose
            return True

        logger.info("Đi %s → %s: %s",
                    navigation.describe(self.pose), goal, navigation.route_to_text(route))
        ok = self.motion.execute_route(route)
        if ok:
            self.pose = new_pose
        else:
            done = list(getattr(self.motion, "last_route_progress", None) or [])
            total = sum(c[1] if c[0] == "forward" else 1 for c in route)
            self.pose = navigation.apply(self.pose, done)
            logger.error("Navigation thất bại — %s. Chạy được %d/%d bước, "
                         "vị trí ước tính: %s",
                         context, len(done), total, navigation.describe(self.pose))
        return ok

    def _approach_shelf(self, context: str) -> bool:
        if not self.motion.approach_shelf():
            logger.warning("Tiếp cận thất bại — %s", context)
            return False
        return True

    def _dat_co_cong_hang(self) -> None:
        """Đồng bộ cờ "đang cõng hàng" của Motion theo carried_labels.

        Cõng hàng thì siêu âm VÔ DỤNG: kiện trên càng chắn chùm sóng. Đo trên robot
        03/08 — vừa rời giao lộ đã đọc 9.4cm, thả xong hàng thì cùng cảm biến đó đọc
        100.0cm. Robot vì thế "tới nơi" ngay giữa đường và thả hàng trên line.
        Gọi ở MỌI chỗ carried_labels đổi, không rải cờ lung tung.
        """
        motion = getattr(self, "motion", None)
        if motion is None:
            return          # _reset_for_new_run() chạy được cả trước khi dựng Motion
        cong = any(x is not None for x in self.carried_labels)
        if getattr(motion, "dang_cong_hang", False) != cong:
            logger.info("Cờ cõng hàng → %s (kiện đang giữ: %s)",
                        "CÓ" if cong else "KHÔNG", self.carried_labels)
        motion.dang_cong_hang = cong

    def _approach_for_drop(self, context: str) -> bool:
        """Tiếp cận điểm thả hàng, thử lại 1 lần trước khi đành thả tại chỗ."""
        if getattr(self.motion, "dang_cong_hang", False):
            # Không tiếp cận được bằng siêu âm khi đang cõng hàng (kiện chắn chùm
            # sóng — xem _dat_co_cong_hang). Ở khu nhà máy cũng chẳng có mặt phẳng
            # nào để canh: advance_to_end() đã đưa robot tới HẾT LINE, tức mép ô
            # nhà máy, và đó chính là điểm thả.
            logger.info("Bỏ bước tiếp cận điểm thả (%s) — đang cõng hàng nên siêu âm "
                        "không dùng được; advance đã dừng ở cuối line = mép ô nhà máy.",
                        context)
            return True
        if self._approach_shelf(context):
            return True
        logger.warning("Thử tiếp cận lại điểm thả — %s", context)
        if self._approach_shelf(context + " (lần 2)"):
            return True
        logger.error("KHÔNG tiếp cận được điểm thả — %s. Vẫn thả tại chỗ "
                     "(mang đi tiếp thì mất luôn cả lượt), kiểm tra lại siêu âm/bản đồ.",
                     context)
        return False

    def _insert_and_lift(self, tier: int, require_both: bool = True) -> bool:
        """NÂNG ngang tầng → LUỒN càng vào pallet → NHẤC bổng → xác nhận IR.

        Cơ cấu là xe nâng thật: càng phải luồn vào pallet rồi mới nhấc được. Bản
        trước gọi thẳng `lift.pickup()` — hàm đó nâng càng TỪ SÀN tại chỗ, không hề
        tiến vào, nên càng chỉ đi lên trong không khí trước mặt kệ và không bao giờ
        móc được pallet. Với tầng 2 còn tệ hơn: càng đội thẳng vào mặt tầng 1.

        Điểm dừng khi luồn dùng IR trên mặt càng chứ không dùng siêu âm — xem
        Motion.creep_until.
        """
        for attempt in range(1, config.PICKUP_MAX_RETRIES + 1):
            logger.info("Bốc hàng tầng %d — lần %d/%d",
                        tier, attempt, config.PICKUP_MAX_RETRIES)

            # Chuỗi thao tác nằm ở control/pickup.py — MỘT cài đặt duy nhất dùng
            # chung với test_smoke, để test và trận không bao giờ lệch nhau nữa.
            if insert_and_lift_once(self.motion, self.lift, tier, require_both):
                return True
            logger.warning("Lần %d: bốc hàng chưa thành công", attempt)

            # Rút ra rồi hạ càng về sàn trước khi thử lại — thử lại tại chỗ với
            # càng đang lơ lửng trong kệ thì chỉ càng cào vào pallet.
            if attempt < config.PICKUP_MAX_RETRIES:
                self._retreat_from_shelf(f"bốc hàng lần {attempt}")
                self.lift.go_to_level(0)
                if not self._approach_shelf(f"bốc hàng lần {attempt + 1}"):
                    break

        logger.error("Bốc hàng THẤT BẠI sau %d lần", config.PICKUP_MAX_RETRIES)
        self.lift.go_to_level(0)
        return False

    def _retreat_from_shelf(self, context: str, quang_cm: float | None = None):
        """Lùi khỏi kệ / khu nhà máy.

        `quang_cm` — lùi ĐÚNG bấy nhiêu cm. Truyền khi rút khỏi NHÀ MÁY sau khi
        thả: ở đó robot không hề luồn càng nên quãng luồn của lần bốc trước không
        liên quan, mà dùng nó là lùi quá xa và vượt qua giao lộ.
        Xem config.RETREAT_AFTER_DROP_CM.
        """
        if not self.motion.retreat_from_shelf(quang_cm=quang_cm):
            logger.warning("Lùi khỏi kệ thất bại (timeout) — %s", context)

    # ----------------------------------------------------------
    # Tính toán route tối ưu
    # ----------------------------------------------------------

    def _delivery_cost(self, first: str, second: str) -> int:
        """Tổng chi phí: vị trí hiện tại → NM1 → NM2 → quay về kệ pickup tiếp theo."""
        term1 = navigation.FACTORY_TERMINAL.get(first)
        term2 = navigation.FACTORY_TERMINAL.get(second)
        if term1 is None or term2 is None:
            return 10 ** 6
        cost = navigation.route_cost(self.pose, term1)
        cost += navigation.route_cost(navigation.pose_at(term1), term2)
        shelf_terminal = navigation.SHELF_TERMINAL.get(self._next_pickup_shelf())
        if shelf_terminal is not None:
            cost += navigation.route_cost(navigation.pose_at(term2), shelf_terminal)
        return cost

    def _plan_delivery(self, label_left: str, label_right: str):
        """
        Lên kế hoạch giao 2 kiện theo thứ tự tối ưu.
        So sánh tổng chi phí: kho → NM1 → NM2 → return về kệ (gồm cả lần xoay).
        Nếu cùng nhà máy → giao 1 lần duy nhất.
        """
        if label_left == label_right:
            self.delivery_queue = [label_left]
            logger.info("2 kiện cùng loại (%s) — giao 1 điểm duy nhất", label_left)
            return

        cost_left_first = self._delivery_cost(label_left, label_right)
        cost_right_first = self._delivery_cost(label_right, label_left)

        if cost_left_first <= cost_right_first:
            self.delivery_queue = [label_left, label_right]
            logger.info("Giao: %s → %s (tổng cost=%d vs %d, gồm return)",
                        label_left, label_right, cost_left_first, cost_right_first)
        else:
            self.delivery_queue = [label_right, label_left]
            logger.info("Giao: %s → %s (tổng cost=%d vs %d, gồm return)",
                        label_right, label_left, cost_right_first, cost_left_first)

    # ----------------------------------------------------------
    # State handlers
    # ----------------------------------------------------------

    def _handle_init(self) -> State:
        logger.info("Trạng thái: INIT — chờ nút khởi động...")
        # Home càng TRƯỚC khi chờ nút: thao tác này mất LIFT_HOME_DURATION giây, làm
        # sau khi bấm nút là ăn thẳng vào 240s của trận.
        if getattr(config, "HOME_AT_INIT", True):
            logger.info("Hạ càng về sàn (%.1fs) trước khi chờ nút...",
                        config.LIFT_HOME_DURATION)
            self.lift.reset()
        else:
            # Khối cảnh báo nhiều dòng, cùng kiểu với _apply_board_side: đây là điều
            # kiện KHÔNG kiểm chứng được (không có limit switch), quên là hỏng cả
            # trận mà không có tín hiệu lỗi nào.
            logger.warning("=" * 60)
            logger.warning("HOME_AT_INIT = False — ROBOT KHÔNG TỰ HẠ CÀNG")
            logger.warning("  ⚠ ĐỘI PHẢI TỰ HẠ CÀNG VỀ SÀN TRƯỚC KHI BẤM NÚT.")
            logger.warning("  Robot mặc định coi càng đang ở SÀN (_current_level = 0)")
            logger.warning("  và KHÔNG có cách nào kiểm chứng — không có limit switch.")
            logger.warning("  Càng chưa ở sàn = mọi phép tính tầng sau đó lệch, im lặng.")
            logger.warning("=" * 60)
        # Đọc công tắc nửa sân LÚC NÀY để đội còn nhìn log mà gạt lại nếu sai
        self._apply_board_side()

        # Gỡ callback reset khi đang chờ nút, nếu không lần bấm để KHỞI ĐỘNG sẽ bị
        # hiểu thành yêu cầu reset.
        self._start_button.when_pressed = None
        self._reset_requested = False

        self._start_button.wait_for_press()
        logger.info("Nút khởi động đã được nhấn!")
        # Đọc lại NGAY SAU khi bấm — giá trị chốt cuối cùng, phòng trường hợp vừa
        # gạt lại công tắc trong lúc chờ.
        self._apply_board_side()

        # Từ đây, bấm nút = yêu cầu RESET giữa trận
        self._reset_requested = False
        self._start_button.when_pressed = self._on_reset_button
        if self._resume_epoch is not None:
            # Khôi phục sau lỗi: dùng lại đồng hồ gốc → chạy nốt thời gian còn lại
            self.match_start_time = self._resume_epoch
            logger.warning("KHÔI PHỤC sau lỗi — đồng hồ gốc, còn ~%.0fs", self.time_remaining())
        else:
            self.match_start_time = time.time()
            if self._enable_match_persist:
                self._persist_match_start()
        return State.START

    # ---- Khôi phục sau lỗi (chỉ chế độ thi đấu, qua systemd Restart=on-failure) ----

    def _state_file(self) -> str:
        return getattr(config, "MATCH_STATE_FILE", "/tmp/robot_match_state")

    def _persist_match_start(self):
        """Lưu mốc bắt đầu trận để restart sau lỗi còn biết thời gian đã trôi."""
        try:
            with open(self._state_file(), "w") as f:
                f.write(str(self.match_start_time))
        except OSError as e:
            logger.warning("Không ghi được file trạng thái trận: %s", e)

    def _load_match_resume(self) -> float | None:
        """Trả mốc bắt đầu nếu đang có trận dở (còn trong 240s); quá hạn → None + xoá file."""
        try:
            with open(self._state_file()) as f:
                epoch = float(f.read().strip())
        except (OSError, ValueError):
            return None
        if time.time() - epoch >= config.MATCH_DURATION:
            self._clear_match_state()
            return None
        return epoch

    def _clear_match_state(self):
        try:
            os.remove(self._state_file())
        except OSError:
            pass

    def _handle_start(self) -> State:
        logger.info("Trạng thái: START — bắt đầu trận đấu (240s)")

        # Hết giờ thì KHÔNG được xuất phát nữa. Đường vào đây sau RESET bỏ qua lần
        # kiểm giờ của _run_state_machine (nó `continue` ngay sau _handle_reset), nên
        # reset lúc 239s mà không ai bấm xác nhận thì robot sẽ lao ra khỏi ô xuất
        # phát đúng lúc trọng tài đã tính giờ xong.
        if self.match_start_time > 0 and not self.is_time_safe():
            logger.warning("Hết giờ — không xuất phát lại (còn %.0fs)", self.time_remaining())
            return State.DONE

        # Thoát ô start → tìm line R0 → căn giữa (KHÔNG đếm giao lộ; bộ tìm đường lo)
        # Thử lại như các lỗi navigation khác — 1 lần glitch cảm biến ngay lúc
        # xuất phát không nên khiến cả trận kết thúc ngay lập tức.
        max_attempts = config.MAX_TIER_RETRIES + 1
        for attempt in range(1, max_attempts + 1):
            if self.motion.exit_start_zone():
                # Bước căn giữa CÓ THỂ đã chạy tới tận C0R0 — khi đó pose là C0R0
                # chứ không phải START, nếu không route đi lố một giao lộ và
                # advance khởi hành khi đã sát kệ. Xem navigation.pose_sau_xuat_phat.
                self.pose = navigation.pose_sau_xuat_phat(
                    getattr(self.motion, "tren_giao_lo_dau", False) is True)
                return State.DETECT_SIDE
            logger.warning("Thoát ô start thất bại — thử lại (lần %d/%d)",
                           attempt, max_attempts)

        logger.error("Không thoát được ô start sau %d lần thử — dừng!", max_attempts)
        return State.DONE

    def _handle_detect_side(self) -> State:
        """
        Xác định robot đang ở NỬA SÂN nào, rồi nạp đúng bản đồ.

        Sa bàn chia đôi bởi tường giữa sân; nửa của đội có thể là ảnh gương của nửa
        kia — khi đó mọi lệnh xoay phải đảo chiều. Thay vì bắt người nhớ đặt cờ
        config.BOARD_MIRRORED trước mỗi trận (quên là hỏng cả trận), robot tự dò:

        Đi tới giao lộ Kệ 3 rồi xoay thử sang PHẢI — đường line dọc cột kệ chỉ chạy
        về MỘT phía (lên Kệ 2/Kệ 1), phía kia là mép sa bàn:
            thấy line  → cột kệ ở bên phải  → nửa CHUẨN
            không thấy → cột kệ ở bên trái  → nửa GƯƠNG
        """
        if not getattr(config, "BOARD_AUTO_DETECT", False):
            logger.info("Tự dò nửa sân đang TẮT — dùng config.BOARD_MIRRORED=%s",
                        navigation.MIRRORED)
            return State.NAVIGATE_TO_SHELF

        # Sau RESET, state machine quay lại START → DETECT_SIDE. Nhưng sa bàn không
        # đổi giữa trận: dò lại là mất thêm ~2-4s mỗi lần (5 lần reset = tới 20s)
        # để ra đúng kết quả cũ. Dò một lần duy nhất đầu trận là đủ.
        if getattr(self, "_side_detected", False):
            logger.info("Đã dò nửa sân từ đầu trận (%s) — bỏ qua, đi thẳng vào kệ",
                        "GƯƠNG" if navigation.MIRRORED else "CHUẨN")
            return State.NAVIGATE_TO_SHELF

        if not self._goto(navigation.PROBE_NODE, "tới giao lộ Kệ 3 để dò nửa sân"):
            logger.error("Không tới được giao lộ dò — giữ nguyên bản đồ theo "
                         "config.BOARD_MIRRORED=%s", navigation.MIRRORED)
            return State.NAVIGATE_TO_SHELF

        found = self.motion.probe_side_branch("right")
        if found is None:
            logger.error("Dò nửa sân THẤT BẠI (cảm biến line) — giữ nguyên bản đồ "
                         "theo config.BOARD_MIRRORED=%s", navigation.MIRRORED)
        else:
            # Chỉ chốt "đã dò xong" khi có kết luận rõ ràng — dò lỗi cảm biến thì để
            # lần sau (nếu có reset) thử lại, chứ không khoá luôn kết quả không chắc.
            self._side_detected = True
            mirrored = not found
            if mirrored != navigation.MIRRORED:
                navigation.set_mirrored(mirrored)
                logger.warning("TỰ DÒ: đang ở nửa %s — ĐÃ NẠP LẠI bản đồ",
                               "GƯƠNG" if mirrored else "CHUẨN")
            else:
                logger.info("TỰ DÒ: đang ở nửa %s — khớp cấu hình sẵn có",
                            "GƯƠNG" if mirrored else "CHUẨN")
            logger.info(navigation.board_summary())

        # Robot đang đứng tại giao lộ dò, quay mặt về phía kệ. Đặt lại pose theo bản
        # đồ MỚI (nhãn hướng đổi khi lật gương, dù tư thế vật lý không đổi).
        self.pose = (navigation.PROBE_NODE, navigation.TOWARD_SHELVES)
        return State.NAVIGATE_TO_SHELF

    def _handle_navigate_to_shelf(self) -> State:
        """Di chuyển đến giá kệ hiện tại."""
        if self._shelves_exhausted():
            logger.warning("Đã hết kệ NV1 (kệ %d)", self.current_shelf)
            return self._finish_task1_or_done()

        logger.info("Di chuyển đến kệ %d, tầng %d...",
                     self.current_shelf, self.current_tier)

        # Bộ tìm đường tự lo mọi trường hợp: từ ô xuất phát, từ kệ khác, hoặc đã
        # đứng sẵn tại kệ (lấy tầng 2 → route rỗng, không di chuyển).
        goal = navigation.SHELF_TERMINAL[self.current_shelf]
        if not self._goto(goal, f"đến kệ {self.current_shelf} tầng {self.current_tier}"):
            return self._retry_or_skip_tier("navigate")

        return State.PICKUP_PAIR

    def _handle_pickup_pair(self) -> State:
        """Tiếp cận kệ, quét nhận diện 2 kiện, rồi nâng pallet."""
        logger.info("Trạng thái: PICKUP_PAIR — kệ %d, tầng %d",
                     self.current_shelf, self.current_tier)

        if not self.is_time_safe():
            logger.warning("Sắp hết giờ! Dừng lại.")
            return State.DONE

        # KHÔNG tiếp cận thêm nữa. advance_to_end() đã dừng robot ở ~20cm bằng số
        # đo mà siêu âm CÒN đọc được; dưới mức đó nó không nhìn thấy kệ (đo 03/08:
        # thước 12cm, cảm biến 35.7cm — mặt trước giá kệ hở, sóng lọt qua). Đoạn
        # còn lại do IR trên mặt càng dẫn trong creep_until, đúng cảm biến cho việc
        # đó. Bỏ luôn một bước là bớt một chỗ hỏng và bớt ~2-3 giây mỗi lượt.

        # ...NHƯNG phải kiểm ĐÃ TỚI KỆ THẬT chưa. Chặng quay về sau khi giao là
        # chặng dài nhất trận (tới 4 lần xoay, 6-7 giao lộ) nên dễ lệch nhất, mà
        # bước bốc thì không tự phát hiện được: nó luồn vào chỗ trống suốt 8 giây
        # rồi mới báo lỗi. Lúc này siêu âm DÙNG ĐƯỢC vì đã thả hết hàng.
        # Xem config.PICKUP_MAX_SHELF_DISTANCE.
        try:
            cach_ke = float(self.motion.get_distance())
        except (TypeError, ValueError):
            cach_ke = -1.0          # đọc lỗi → KHÔNG chặn, thà thử bốc
        if 0 <= cach_ke > config.PICKUP_MAX_SHELF_DISTANCE:
            logger.error(
                "KHÔNG THẤY KỆ trước mặt — siêu âm đọc %.1fcm (tối đa %.1f). Chặng "
                "quay về kệ đã đi lạc; bốc hàng lúc này là luồn càng vào chỗ trống "
                "suốt %.1fs rồi mới hỏng. Thử lại điều hướng.",
                cach_ke, config.PICKUP_MAX_SHELF_DISTANCE, config.INSERT_TIMEOUT)
            return self._retry_or_skip_tier("navigate")
        logger.info("Đã ở trước kệ — siêu âm %.1fcm", cach_ke)

        label_left, label_right = None, None
        for attempt in range(1, config.MAX_PAIR_SCAN_ATTEMPTS + 1):
            # Truyền TẦNG: camera cố định vào thân nên vùng quét phải dịch theo tầng,
            # không thì ROI vắt ngang 2 tầng và ôm 2 loại kiện cùng lúc (config.ROI_Y_CENTER).
            label_left, label_right = self.vision.classify_pair(self.current_tier)
            if label_left is not None and label_right is not None:
                logger.info("Nhận diện OK (lần %d): trái=%s, phải=%s",
                            attempt, label_left, label_right)
                break
            logger.warning("Lần %d: không nhận diện đủ 2 kiện — thử lại", attempt)
            if attempt < config.MAX_PAIR_SCAN_ATTEMPTS:
                time.sleep(config.SCAN_RETRY_DELAY)
        else:
            logger.error("Không nhận diện được sau %d lần quét", config.MAX_PAIR_SCAN_ATTEMPTS)
            self._retreat_from_shelf("PICKUP_PAIR scan fail")
            return self._retry_or_skip_tier("scan")

        self.carried_labels = [label_left, label_right]
        self._dat_co_cong_hang()
        self._plan_delivery(label_left, label_right)

        success = self._insert_and_lift(self.current_tier)

        # Lùi ra khỏi kệ — dừng khi đã lùi đủ xa
        self._retreat_from_shelf("PICKUP_PAIR")

        if not success:
            logger.error("NÂNG THẤT BẠI")
            self._clear_carry_state()
            return self._retry_or_skip_tier("pickup")

        self._tier_retries = 0
        self.pickup_count += 1
        logger.info("Đã nâng lượt %d/%d (cảm biến xác nhận OK)",
                     self.pickup_count, config.PICKUPS_TASK1)

        return State.DELIVER_FIRST

    def _handle_deliver_first(self) -> State:
        """Di chuyển đến nhà máy đầu tiên trong delivery_queue."""
        if not self.delivery_queue:
            return State.RETURN_TO_WAREHOUSE

        label = self.delivery_queue[0]
        factory = self.vision.get_factory_name(label)
        goal = navigation.FACTORY_TERMINAL.get(label)

        logger.info("Giao kiện 1: %s → %s", label, factory)

        if goal is None:
            logger.error("Nhãn %s không có trên bản đồ — bỏ qua lượt giao này", label)
            self.delivery_queue.clear()
            return State.RETURN_TO_WAREHOUSE

        if not self.is_time_safe():
            # KHÔNG rẽ sang DROP_FIRST: chưa đi tới nhà máy nào cả, thả ở đây là thả
            # giữa sân — 0 điểm theo thể lệ, nhưng IR VẪN báo pallet đã rời càng nên
            # packages_delivered +1/+2 và log báo điểm không hề có. Số đó còn dùng để
            # quyết định chuyển sang NV2 và để tools.measure_phases dự báo, nên sai ở
            # đây là sai cả chuỗi. Hạ càng lúc này cũng tốn thêm vài giây vô ích.
            logger.warning("Sắp hết giờ (còn %.0fs) — KHÔNG thả giữa sân, giữ kiện "
                           "trên càng và dừng (thả ngoài khu nhà máy không có điểm)",
                           self.time_remaining())
            return State.DONE

        # Trừ NGAY vào quãng đi tới, đừng đi vào rồi lùi ra: kiện đã thả ở nhà máy
        # này nằm đúng trên đường robot sắp đi vào. Xem config.ADVANCE_FACTORY_STOP_CM.
        self._dat_bot_quang_nha_may(label)
        self._deliver_nav_ok = self._goto(goal, f"DELIVER → {label}")
        return State.DROP_FIRST

    def _get_drop_side(self, label: str) -> str | None:
        """Xác định càng nào (left/right) đang giữ kiện có label này."""
        if self.carried_labels[0] == label:
            return "left"
        if self.carried_labels[1] == label:
            return "right"
        logger.error("Label %s không khớp càng %s", label, self.carried_labels)
        return None

    def _so_kien_da_giao(self, label: str) -> int:
        """Nhà máy `label` đã nhận mấy kiện. Tự khởi tạo sổ nếu chưa có.

        Khởi tạo lười vì test và tools/dry_run dựng Robot bằng object.__new__()
        (không chạy __init__) — bắt chúng nhớ đặt tay từng thuộc tính mới là sớm
        muộn sót một cái rồi nổ AttributeError giữa trận.
        """
        if getattr(self, "da_giao_theo_nha_may", None) is None:
            self.da_giao_theo_nha_may = {}
        return self.da_giao_theo_nha_may.get(label, 0)

    def _ghi_nhan_giao(self, label: str, so_kien: int = 1) -> None:
        """Ghi nhớ nhà máy `label` vừa nhận thêm `so_kien` kiện."""
        truoc = self._so_kien_da_giao(label)
        self.da_giao_theo_nha_may[label] = truoc + so_kien
        logger.info("Nhà máy %s: đã nhận %d kiện (tổng đã giao: %s)",
                    label.upper(), truoc + so_kien,
                    ", ".join(f"{k}={v}" for k, v in
                              sorted(self.da_giao_theo_nha_may.items())))

    def _dat_bot_quang_nha_may(self, label: str) -> None:
        """Báo cho Motion phải dừng SỚM bao nhiêu cm vì nhà máy đó đã có kiện.

        Mỗi nhà máy nhận 3 kiện và chúng nằm ĐÚNG trên đường robot đi vào, nên
        chốt quãng đường cố định sẽ húc vào kiện cũ. `_lui_tranh_kien_cu()` lùi
        SAU KHI ĐÃ TỚI — tức đã va rồi mới lùi. Trừ trước thì không bao giờ chạm.
        """
        bu = getattr(config, "FACTORY_STACK_BACKOFF_CM", 0.0)
        da_co = self._so_kien_da_giao(label)
        bot = bu * da_co if bu > 0 else 0.0
        self.motion.bot_quang_nha_may = bot
        if bot > 0:
            logger.info("Nhà máy %s đã có %d kiện — dừng SỚM hơn %.1fcm để không "
                        "húc vào chúng", label.upper(), da_co, bot)

    def _lui_tranh_kien_cu(self, label: str) -> None:
        """Lùi bớt trước khi thả, để kiện mới không chồng lên kiện đã có.

        TẮT khi FACTORY_STACK_BACKOFF_CM = 0 (mặc định) — xem chú thích ở config:
        chưa ai chạy tools.check_sees_dropped_package nên chưa biết siêu âm có tự
        thấy kiện cũ hay không.
        """
        bu = getattr(config, "FACTORY_STACK_BACKOFF_CM", 0.0)
        da_co = self._so_kien_da_giao(label)
        if bu <= 0 or da_co <= 0:
            return
        # ⛔ ĐỪNG BÙ HAI LẦN. Khi ADVANCE_FACTORY_STOP_CM > 0 thì chặng đi vào khu
        # nhà máy đã TRỪ SẴN phần này khỏi quãng đi tới (_dat_bot_quang_nha_may),
        # nên robot dừng sớm và KHÔNG hề chạm kiện cũ. Lùi thêm ở đây là lùi đúp:
        # kiện thứ 2 rơi cách kiện thứ 1 tận 18cm thay vì 9cm, tràn khỏi ô 25cm.
        if getattr(config, "ADVANCE_FACTORY_STOP_CM", 0.0) > 0:
            logger.info("Nhà máy %s: KHÔNG lùi thêm — quãng đi vào đã trừ sẵn "
                        "%.1fcm tránh kiện cũ", label.upper(), bu * da_co)
            return
        lui = bu * da_co
        logger.info("Nhà máy %s đã có %d kiện — lùi thêm %.1fcm trước khi thả để "
                    "không chồng lên chúng", label.upper(), da_co, lui)
        self._retreat_from_shelf(f"tránh kiện cũ ở {label}", quang_cm=lui)

    def _da_tha_xong(self, side: str | None = None) -> None:
        """Xoá nhãn kiện ĐÃ RỜI CÀNG, rồi đồng bộ lại cờ cõng hàng.

        ⚠️ Trước đây carried_labels CHỈ được xoá khi bốc hàng THẤT BẠI hoặc reset —
        không bao giờ xoá sau khi giao xong. Nên cờ "đang cõng hàng" bật suốt phần
        còn lại của trận, và trên đường VỀ KỆ robot bỏ qua siêu âm rồi coi mảng tối
        đầu tiên là "đã vào khu nhà máy" → dừng bừa giữa đường.
        Đo trên robot 03/08: thả tầng 1 kệ đầu OK, nhưng quay lại kệ lấy tầng 2 thì
        "chạy rất lung tung".

        side=None → xoá cả hai (thả cùng lúc bằng drop_both).
        """
        for i, ben in enumerate(("left", "right")):
            if side is None or side == ben:
                self.carried_labels[i] = None
        self._dat_co_cong_hang()

    def _drop_single_side(self, side: str) -> bool:
        """Thả 1 kiện rồi nâng lại càng — chuỗi ở control/handling.py."""
        # LÙI nằm GIỮA thả và nâng càng — xem control/handling.drop_side.
        ok = drop_side(self.lift, side, last=False,
                       lui=lambda: self._retreat_from_shelf("sau khi thả",
                                        quang_cm=config.RETREAT_AFTER_DROP_CM))
        # Xoá nhãn DÙ IR BÁO HỎNG: nếu kiện thật sự còn trên càng thì bước sau đã
        # hỏng rồi, còn giữ nhãn thì cờ cõng hàng kẹt bật và phá NỐT chặng về.
        self._da_tha_xong(side)
        return ok

    def _delivery_is_trustworthy(self, approach_ok: bool, context: str) -> bool:
        """Có đủ căn cứ để TIN rằng đang đứng trong khu nhà máy không?

        Hai tín hiệu độc lập: tìm đường có tới nơi không, và siêu âm có thấy tường
        khu nhà máy trước mặt không. Chỉ cần MỘT cái đúng là tin — tìm đường tới nơi
        nhưng siêu âm chớp nhoáng lỗi, hay ngược lại, đều còn khả năng đang đúng chỗ.

        CẢ HAI cùng hỏng thì nghĩa là "không biết đang ở đâu, mà trước mặt cũng trống
        trơn". Vẫn PHẢI thả để giải phóng càng — giữ kiện lại thì lượt bốc sau không
        luồn được vào pallet và robot đứng chết với hàng trên càng suốt phần trận còn
        lại, tệ hơn hẳn. Nhưng KHÔNG được cộng điểm:

        thả ngoài khu nhà máy = 0 điểm theo thể lệ, trong khi IR vẫn xác nhận pallet
        đã rời càng nên `packages_delivered` vẫn tăng nếu không chặn ở đây. Con số đó
        còn quyết định lúc nào chuyển sang NV2 và là đầu vào của tools.measure_phases
        — sai một chỗ là sai cả chuỗi, mà log thì vẫn báo thành công.
        """
        if self._deliver_nav_ok or approach_ok:
            return True
        logger.warning("=" * 60)
        logger.warning("  %s — KHÔNG TÍNH ĐIỂM kiện này", context)
        logger.warning("  Tìm đường tới nhà máy THẤT BẠI và siêu âm KHÔNG thấy gì")
        logger.warning("  trước mặt → nhiều khả năng đang thả ngoài khu nhà máy.")
        logger.warning("  Vẫn thả để giải phóng càng, nhưng packages_delivered")
        logger.warning("  giữ nguyên: đếm cả kiện thả sai chỗ là sai luôn mốc")
        logger.warning("  chuyển NV2 và mọi số liệu của measure_phases.")
        logger.warning("=" * 60)
        return False

    def _handle_drop_first(self) -> State:
        """Hạ kiện hàng đầu tiên."""
        label = self.delivery_queue.pop(0)
        self._last_delivered_label = label
        same_factory = self.carried_labels[0] == self.carried_labels[1]

        logger.info("Trạng thái: DROP_FIRST — %s (%s)",
                     label, "cả 2 càng" if same_factory else self._get_drop_side(label))

        approach_ok = self._approach_for_drop(f"DROP_FIRST {label}")
        self._lui_tranh_kien_cu(label)
        trusted = self._delivery_is_trustworthy(approach_ok, f"DROP_FIRST {label}")

        if same_factory:
            if drop_both(self.lift):
                self._ghi_nhan_giao(label, 2)
                if trusted:
                    self.packages_delivered += 2
            else:
                logger.error("DROP_FIRST thất bại — IR vẫn thấy pallet hoặc lỗi cảm biến")
            self._da_tha_xong()          # cả 2 càng
        else:
            side = self._get_drop_side(label)
            if side is None:
                logger.error("DROP_FIRST — bỏ qua drop, không xác định được càng")
            elif self._drop_single_side(side):
                self._ghi_nhan_giao(label)
                if trusted:
                    self.packages_delivered += 1
            else:
                logger.error("DROP_FIRST thất bại — càng %s chưa thả được pallet", side)

        # KHÔNG lùi ở đây nữa: drop_side() đã lùi GIỮA thả và nâng càng. Còn nhánh
        # same_factory dùng drop_both() thì hạ đồng bộ, không nâng lại, nên lùi sau
        # vẫn đúng — gọi riêng cho nhánh đó.
        if same_factory:
            self._retreat_from_shelf(f"DROP_FIRST {label}")

        logger.info("Đã giao %d/%d kiện",
                     self.packages_delivered, config.TOTAL_PACKAGES_TASK1)

        if self.delivery_queue:
            return State.DELIVER_SECOND

        if self.packages_delivered >= config.TOTAL_PACKAGES_TASK1:
            logger.info("NHIỆM VỤ 1 HOÀN THÀNH!")
            return State.TASK2_NAVIGATE_TO_LOOSE

        if not self.is_time_safe():
            return State.DONE

        return State.RETURN_TO_WAREHOUSE

    def _handle_deliver_second(self) -> State:
        """Di chuyển đến nhà máy thứ 2."""
        if not self.delivery_queue:
            return State.RETURN_TO_WAREHOUSE

        label = self.delivery_queue[0]
        factory = self.vision.get_factory_name(label)
        goal = navigation.FACTORY_TERMINAL.get(label)

        logger.info("Giao kiện 2: %s → %s (từ %s)",
                    label, factory, navigation.describe(self.pose))

        if goal is None:
            logger.error("Nhãn %s không có trên bản đồ — bỏ qua kiện 2", label)
            self.delivery_queue.clear()
            return State.RETURN_TO_WAREHOUSE

        if not self.is_time_safe():
            # Xem lý do ở _handle_deliver_first: kiện 1 đã giao xong và đã được đếm,
            # kiện 2 thả tại nhà máy 1 (hoặc giữa đường) thì không có điểm.
            logger.warning("Sắp hết giờ (còn %.0fs) — KHÔNG thả kiện 2 ngoài khu nhà "
                           "máy của nó, dừng tại đây", self.time_remaining())
            return State.DONE

        # Bộ tìm đường tự lo đoạn nhà máy → nhà máy (phải vòng về cột giữa vì giữa
        # các khu nhà máy không có line nối dọc).
        self._dat_bot_quang_nha_may(label)
        self._deliver_nav_ok = self._goto(goal, f"DELIVER kiện 2 → {label}")
        return State.DROP_SECOND

    def _handle_drop_second(self) -> State:
        """Hạ kiện hàng thứ 2 (càng còn lại)."""
        label = self.delivery_queue.pop(0)
        self._last_delivered_label = label
        side = self._get_drop_side(label)

        logger.info("Trạng thái: DROP_SECOND — %s (càng %s)", label, side or "?")

        if side is None:
            logger.error("DROP_SECOND — bỏ qua drop, không xác định được càng")
        else:
            approach_ok = self._approach_for_drop(f"DROP_SECOND {label}")
            self._lui_tranh_kien_cu(label)
            trusted = self._delivery_is_trustworthy(approach_ok, f"DROP_SECOND {label}")

            # Chuỗi thả ở control/handling.py — gập càng chạy LUÔN, kể cả khi IR
            # không xác nhận (càng nằm thấp mà robot chạy tiếp là cạ sàn/vướng kệ).
            dropped = drop_side(
                self.lift, side, last=True,
                lui=lambda: self._retreat_from_shelf(f"sau khi thả {label}",
                                        quang_cm=config.RETREAT_AFTER_DROP_CM))
            self._da_tha_xong(side)
            if dropped:
                self._ghi_nhan_giao(label)
            if dropped and trusted:
                self.packages_delivered += 1
            else:
                logger.error("DROP_SECOND thất bại — càng %s chưa thả được pallet", side)

            # drop_side() đã lùi rồi (giữa thả và gập càng).
        logger.info("Đã giao %d/%d kiện",
                     self.packages_delivered, config.TOTAL_PACKAGES_TASK1)

        if self.packages_delivered >= config.TOTAL_PACKAGES_TASK1:
            logger.info("NHIỆM VỤ 1 HOÀN THÀNH!")
            return State.TASK2_NAVIGATE_TO_LOOSE

        if not self.is_time_safe():
            return State.DONE

        return State.RETURN_TO_WAREHOUSE

    def _next_pickup_shelf(self) -> int:
        """Kệ sẽ pickup sau _advance_position() (trước khi gọi advance)."""
        if self.current_tier == 1:
            return self.current_shelf
        return self.current_shelf + 1

    def _handle_return_to_warehouse(self) -> State:
        """Quay về kho đúng kệ pickup tiếp theo, rồi chuyển tầng/kệ."""
        # ROBOT_MAX_PICKUPS=n — DIỄN TẬP GIỚI HẠN: chạy ĐÚNG state machine thi đấu
        # (nút bấm, công tắc nửa sân, đồng hồ 240s, retry/bỏ tầng, reset) nhưng dừng
        # sau n lượt bốc thay vì cả 6. Lấp khoảng trống giữa test_smoke option 5
        # (đúng các bước nhưng KHÔNG chạy state machine) và practice.sh (trọn trận,
        # quá dài để lặp). Chỉ đọc từ biến môi trường, không phải hằng số config —
        # để không ai lỡ commit rồi mang vào trận thật.
        gioi_han = os.environ.get("ROBOT_MAX_PICKUPS")
        if gioi_han and gioi_han.isdigit() and self.pickup_count >= int(gioi_han):
            logger.warning("=" * 60)
            logger.warning("  DIỄN TẬP GIỚI HẠN: đã xong %d/%s lượt bốc — DỪNG.",
                           self.pickup_count, gioi_han)
            logger.warning("  Đã giao %d kiện. Bỏ ROBOT_MAX_PICKUPS để chạy trọn trận.",
                           self.packages_delivered)
            logger.warning("=" * 60)
            return State.DONE

        target_shelf = self._next_pickup_shelf()
        goal = navigation.SHELF_TERMINAL.get(target_shelf)
        if goal is None:
            logger.info("Không còn kệ NV1 để quay về (kệ %d) — chuyển tiếp", target_shelf)
        else:
            logger.info("Quay về kho từ %s → kệ %d...",
                        navigation.describe(self.pose), target_shelf)
            self._goto(goal, f"RETURN → kệ {target_shelf}")

        self._advance_position()
        logger.info("Tiếp theo: kệ %d, tầng %d",
                     self.current_shelf, self.current_tier)
        return State.NAVIGATE_TO_SHELF

    # ----------------------------------------------------------
    # Nhiệm vụ 2
    # ----------------------------------------------------------

    def _handle_task2_navigate_to_loose(self) -> State:
        """Đi từ nhà máy cuối cùng đã giao → kho hàng rời (kệ 4, dưới trái)."""
        logger.info("Nhiệm vụ 2: đi đến kho hàng rời (kệ 4) từ %s...",
                    navigation.describe(self.pose))
        # Ngưỡng RIÊNG, không dùng chung SAFETY_MARGIN: cả chuyến NV2 tốn ~20-25s,
        # khởi hành khi còn 15s là chắc chắn không kịp mà vẫn kết thúc trận giữa sân.
        remaining = self.time_remaining()
        if remaining < config.TASK2_MIN_TIME:
            logger.warning("Bỏ NV2: còn %.0fs, cần tối thiểu %ds — đứng yên an toàn "
                           "hơn chạy một chuyến chắc chắn không kịp",
                           remaining, config.TASK2_MIN_TIME)
            return State.DONE

        if not self._goto(navigation.LOOSE_TERMINAL, "NV2 → kho hàng rời"):
            logger.error("Navigation NV2 thất bại — dừng")
            return State.DONE
        return State.TASK2_PICKUP

    def _handle_task2_pickup(self) -> State:
        """Nhấc kiện hàng rời (kiện thứ 13, +30 điểm).

        CÓ thử lại — khác bản trước bỏ cuộc ngay lần đầu hỏng. NV1 được retry
        MAX_TIER_RETRIES lần mà NV2 thì không, trong khi một lần thử lại chỉ tốn vài
        giây và đây là 30 trong 270 điểm. Vẫn kiểm giờ trước mỗi lần để không thử
        lại vô ích ở phút chót.
        """
        for attempt in range(1, config.MAX_TIER_RETRIES + 2):
            logger.info("Nhiệm vụ 2: nhấc hàng từ kho hàng rời (lần %d)...", attempt)
            if self.time_remaining() < config.TASK2_MIN_TIME / 2:
                logger.warning("Bỏ NV2: còn %.0fs, không đủ để nhấc và giao",
                               self.time_remaining())
                return State.DONE

            approached = self._approach_shelf("TASK2_PICKUP")
            # NV2 chỉ cần 1 IR — nhưng vẫn phải NÂNG-LUỒN-NHẤC như NV1, cơ cấu
            # càng là một, không có đường tắt nào cho hàng rời.
            # NV2 không dùng carried_labels (không có nhãn để giao — hàng rời luôn
            # về nhà máy liên hợp), nên cờ cõng hàng phải đặt TAY ở đây. Thiếu nó
            # thì bước lùi và các chặng advance sau vẫn tin siêu âm trong khi kiện
            # đang chắn chùm sóng — đúng lỗi vừa sửa cho NV1.
            self.motion.dang_cong_hang = True
            success = (self._insert_and_lift(tier=1, require_both=False)
                       if approached else False)
            self._retreat_from_shelf("TASK2_PICKUP")
            if success:
                return State.TASK2_NAVIGATE_TO_JOINT
            self.motion.dang_cong_hang = False
            logger.warning("Nhiệm vụ 2: lần %d thất bại (%s)", attempt,
                           "không tiếp cận được" if not approached else "IR không thấy pallet")

        logger.error("Nhiệm vụ 2: nhấc hàng rời thất bại — bỏ kiện thứ 13")
        return State.DONE

    def _handle_task2_navigate_to_joint(self) -> State:
        logger.info("Nhiệm vụ 2: đi đến nhà máy liên hợp...")
        if not self.is_time_safe():
            return State.DONE
        if not self._goto(navigation.JOINT_TERMINAL, "NV2 → nhà máy liên hợp"):
            logger.error("Navigation NV2 thất bại — dừng")
            return State.DONE
        return State.TASK2_DROP

    def _handle_task2_drop(self) -> State:
        logger.info("Nhiệm vụ 2: đặt hàng tại nhà máy liên hợp...")
        self._approach_for_drop("TASK2_DROP")
        if drop_both(self.lift):
            self.task2_done = True
            logger.info("NHIỆM VỤ 2 HOÀN THÀNH!")
        else:
            logger.error("NHIỆM VỤ 2: drop thất bại — IR vẫn thấy pallet hoặc lỗi cảm biến")
        # Thả xong (hoặc thả hỏng) thì chặng lùi vẫn nên bỏ siêu âm nếu kiện còn
        # trên càng; hạ cờ SAU khi lùi để không rơi vào ca "IR báo hỏng nhưng kiện
        # vẫn nằm đó và tiếp tục chắn chùm sóng".
        self._retreat_from_shelf("TASK2_DROP")
        self.motion.dang_cong_hang = False
        return State.DONE

    # ----------------------------------------------------------
    # Tiện ích
    # ----------------------------------------------------------

    def _advance_position(self):
        """Chuyển sang tầng/kệ tiếp theo sau mỗi lượt nâng."""
        if self.current_tier == 1:
            # Xong tầng 1 → lên tầng 2 (cùng kệ)
            self.current_tier = 2
        else:
            # Xong tầng 2 → sang kệ tiếp, tầng 1
            self.current_tier = 1
            self.current_shelf += 1

    def _shelves_exhausted(self) -> bool:
        return self.current_shelf >= config.SHELVES_TASK1

    def _clear_carry_state(self):
        """Xóa trạng thái kiện hàng đang mang (sau nâng thất bại)."""
        self.carried_labels = [None, None]
        self._dat_co_cong_hang()
        self.delivery_queue = []

    def _finish_task1_or_done(self) -> State:
        """Chuyển sang NV2 nếu đủ 12 kiện, không thì dừng."""
        if self.packages_delivered >= config.TOTAL_PACKAGES_TASK1:
            logger.info("NHIỆM VỤ 1 HOÀN THÀNH!")
            return State.TASK2_NAVIGATE_TO_LOOSE
        logger.warning("Hết kệ nhưng mới giao %d/%d kiện",
                       self.packages_delivered, config.TOTAL_PACKAGES_TASK1)
        return State.DONE

    def _retry_or_skip_tier(self, reason: str) -> State:
        """Thử lại tầng hiện tại hoặc bỏ qua sang tầng/kệ tiếp."""
        if self._tier_retries < config.MAX_TIER_RETRIES:
            self._tier_retries += 1
            logger.warning("%s thất bại — thử lại tầng (lần %d/%d)",
                           reason.capitalize(), self._tier_retries, config.MAX_TIER_RETRIES)
            if reason == "navigate":
                return State.NAVIGATE_TO_SHELF
            return State.PICKUP_PAIR

        logger.error("%s thất bại — bỏ qua tầng kệ %d tầng %d",
                     reason.capitalize(), self.current_shelf, self.current_tier)
        self._clear_carry_state()
        self._tier_retries = 0
        self._advance_position()
        if self._shelves_exhausted():
            return self._finish_task1_or_done()
        return State.NAVIGATE_TO_SHELF

    def _emergency_stop(self):
        logger.critical("DỪNG KHẨN CẤP!")
        self.motion.stop()
        self.lift.cleanup()

    # ----------------------------------------------------------
    # Vòng lặp chính
    # ----------------------------------------------------------

    STATE_HANDLERS = {
        State.INIT: "_handle_init",
        State.START: "_handle_start",
        State.DETECT_SIDE: "_handle_detect_side",
        State.NAVIGATE_TO_SHELF: "_handle_navigate_to_shelf",
        State.PICKUP_PAIR: "_handle_pickup_pair",
        State.DELIVER_FIRST: "_handle_deliver_first",
        State.DROP_FIRST: "_handle_drop_first",
        State.DELIVER_SECOND: "_handle_deliver_second",
        State.DROP_SECOND: "_handle_drop_second",
        State.RETURN_TO_WAREHOUSE: "_handle_return_to_warehouse",
        State.TASK2_NAVIGATE_TO_LOOSE: "_handle_task2_navigate_to_loose",
        State.TASK2_PICKUP: "_handle_task2_pickup",
        State.TASK2_NAVIGATE_TO_JOINT: "_handle_task2_navigate_to_joint",
        State.TASK2_DROP: "_handle_task2_drop",
    }

    def _run_state_machine(self):
        """Chạy state machine MỘT lượt đến DONE/EMERGENCY_STOP. KHÔNG dọn phần cứng."""
        logger.info("========== BẮT ĐẦU STATE MACHINE ==========")
        while self.state not in (State.DONE, State.EMERGENCY_STOP):
            handler_name = self.STATE_HANDLERS.get(self.state)
            if handler_name is None:
                logger.error("Không có handler cho state: %s", self.state)
                break

            handler = getattr(self, handler_name)
            phase = self.state.value
            t0 = time.time()
            next_state = handler()
            elapsed = time.time() - t0
            # INIT gồm cả thời gian chờ nhấn nút (ngoài đồng hồ trận) → không tính
            if self.state is not State.INIT:
                self._phase_times[phase] = self._phase_times.get(phase, 0.0) + elapsed
                self._phase_counts[phase] = self._phase_counts.get(phase, 0) + 1

            # Trọng tài cho reset giữa trận → bỏ mọi thứ đang dở, về ô xuất phát.
            # Kiểm TRƯỚC khi nhận next_state vì handler vừa rồi có thể đã fail do bị
            # bỏ dở giữa chừng — kết quả của nó không còn ý nghĩa.
            if self._reset_requested:
                self.state = self._handle_reset()
                continue

            logger.info("Chuyển trạng thái: %s -> %s", self.state.value, next_state.value)
            self.state = next_state

            if self.match_start_time > 0 and not self.is_time_safe():
                logger.warning("Hết thời gian an toàn! Dừng lại.")
                self.state = State.DONE

    def run(self):
        """
        Chế độ THI ĐẤU: chạy MỘT trận rồi dọn dẹp và thoát.
        Nếu gặp exception → dừng an toàn rồi thoát **mã 1** để systemd (Restart=on-failure)
        khởi động lại; lần chạy mới đọc lại đồng hồ trận → chạy NỐT thời gian còn lại
        (về INIT chờ nhấn nút). Xong sạch → xoá file trận → thoát mã 0 (không restart).
        """
        self._enable_match_persist = True
        self._resume_epoch = self._load_match_resume()
        if self._resume_epoch is not None:
            logger.warning("Phát hiện trận đang dở — sẽ KHÔI PHỤC khi nhấn nút (còn ~%.0fs)",
                           config.MATCH_DURATION - (time.time() - self._resume_epoch))

        crashed = False
        try:
            self._run_state_machine()
        except Exception as e:
            logger.exception("LỖI NGHIÊM TRỌNG: %s", e)
            self._emergency_stop()
            crashed = True
        finally:
            self._log_result()
            if crashed:
                self._exit_code = 1   # giữ file trận → systemd restart sẽ chạy nốt
                logger.error("Thoát mã 1 — systemd sẽ khởi động lại để chạy nốt trận")
            else:
                self._clear_match_state()
            self._shutdown()

    def run_practice_loop(self):
        """
        Chế độ LUYỆN TẬP: chạy 1 lượt → log kết quả → reset → CHỜ NHẤN NÚT → lặp lại.
        KHÔNG dọn phần cứng giữa các lượt (giữ nút + motor sẵn sàng). Ctrl+C để thoát.
        Lỗi 1 lượt không làm sập chương trình — dừng motor rồi về chờ nút lượt sau.
        """
        run_no = 0
        try:
            while True:
                run_no += 1
                logger.info("=" * 52)
                logger.info("LƯỢT LUYỆN TẬP #%d — đặt robot về ô xuất phát (hướng 9h) "
                            "rồi NHẤN NÚT để bắt đầu", run_no)
                logger.info("=" * 52)
                self._reset_for_new_run()
                try:
                    self._run_state_machine()
                except Exception as e:
                    logger.exception("Lỗi lượt #%d: %s — dừng motor, về chờ nút", run_no, e)
                self.motion.stop()
                self._log_result()
        finally:
            self._shutdown()

    def _reset_for_new_run(self):
        """Đặt lại toàn bộ trạng thái cho 1 lượt mới (dùng trong luyện tập)."""
        self.state = State.INIT
        self.packages_delivered = 0
        self.pickup_count = 0
        self.current_shelf = 0
        self.current_tier = 1
        self.match_start_time = 0.0
        self._tier_retries = 0
        self._side_detected = False
        self._phase_times = {}
        self._phase_counts = {}
        self._reset_requested = False
        self._reset_count = 0
        self.task2_done = False
        self.pose = navigation.START_POSE
        self.carried_labels = [None, None]
        self._dat_co_cong_hang()
        self.delivery_queue = []
        self._last_delivered_label = None

    def _log_result(self):
        self.motion.stop()
        elapsed = self.elapsed() if self.match_start_time > 0 else 0
        logger.info("========== KẾT THÚC LƯỢT ==========")
        logger.info("Thời gian: %.1f/%ds  (còn %.1fs)",
                    elapsed, config.MATCH_DURATION, config.MATCH_DURATION - elapsed)
        logger.info("Kiện hàng đã giao: %d/%d (trong %d lượt nâng)",
                     self.packages_delivered, config.TOTAL_PACKAGES_TASK1,
                     self.pickup_count)
        logger.info("Nhiệm vụ 2: %s",
                    "HOÀN THÀNH (+30 điểm)" if self.task2_done else "chưa xong")
        if self._reset_count:
            logger.warning("Số lần RESET: %d (−%d điểm theo luật)",
                           self._reset_count, self._reset_count * 10)
        # Tổng kết theo ĐIỂM, gồm cả kiện hàng rời NV2 (kiện thứ 13) và trừ reset —
        # không có dòng này thì log báo "12/12" kể cả khi đã ăn thêm 30 điểm NV2,
        # và tools.measure_phases đọc log sẽ tính thiếu đúng 30 điểm đó.
        total_pkg = self.packages_delivered + (1 if self.task2_done else 0)
        points = (self.packages_delivered * 20
                  + (30 if self.task2_done else 0)
                  - self._reset_count * 10)
        logger.info("TỔNG: %d/%d kiện — %d điểm",
                    total_pkg, config.TOTAL_PACKAGES_TASK1 + 1, points)
        self._log_phase_breakdown(elapsed)

    def _log_phase_breakdown(self, total: float):
        """240s tiêu vào đâu — chặng nào ăn nhiều giây nhất thì tối ưu chặng đó.

        Không có bảng này thì chỉ biết 'chạy không kịp' chứ không biết vì sao.
        """
        if not self._phase_times:
            return
        logger.info("--- Thời gian từng chặng ---")
        for phase, secs in sorted(self._phase_times.items(), key=lambda kv: -kv[1]):
            count = self._phase_counts.get(phase, 0)
            pct = (secs / total * 100) if total > 0 else 0
            logger.info("  %-24s %6.1fs  %4.1f%%  (%d lần, TB %.1fs)",
                        phase, secs, pct, count, secs / max(count, 1))
        measured = sum(self._phase_times.values())
        logger.info("  %-24s %6.1fs", "TỔNG đo được", measured)
        if self.packages_delivered:
            logger.info("  Trung bình %.1fs/kiện — nhịp này giao đủ 12 kiện mất %.0fs",
                        measured / self.packages_delivered,
                        measured / self.packages_delivered * config.TOTAL_PACKAGES_TASK1)

    def _shutdown(self):
        """Dọn dẹp phần cứng MỘT lần khi thoát hẳn (thi đấu xong hoặc Ctrl+C)."""
        self.motion.stop()
        self.motion.cleanup()
        self.lift.cleanup()
        self.vision.cleanup()
        reset_mcp3008_bus()
        self._start_button.close()
        self._side_switch.close()


# ============================================================
# Entry point
# ============================================================

def main():
    # Chế độ LUYỆN TẬP (ROBOT_LOOP=1): chạy state machine lặp, nhấn nút mỗi lượt.
    # Ưu tiên trước cả DEBUG_MODE để dùng được nút thật trên sa bàn.
    if os.environ.get("ROBOT_LOOP") == "1":
        logger.warning("*** CHẾ ĐỘ LUYỆN TẬP — nhấn nút để chạy lại mỗi lượt, Ctrl+C để thoát ***")
        Robot().run_practice_loop()
        return

    if config.DEBUG_MODE:
        logger.warning("*** CHẾ ĐỘ DEBUG — KHÔNG DÙNG KHI THI ĐẤU ***")
        from debug import run_debug_server
        run_debug_server()
        return

    robot = Robot()
    robot.run()
    sys.exit(robot._exit_code)   # ≠ 0 khi lỗi → systemd restart để chạy nốt trận


if __name__ == "__main__":
    main()
