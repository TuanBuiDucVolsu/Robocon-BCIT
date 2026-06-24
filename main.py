#!/usr/bin/env python3
"""
Robot tự động Bảng O2 — Robocon Bắc Ninh mở rộng 2026.
State machine điều phối toàn bộ nhiệm vụ.
Nâng 2 kiện hàng/lượt (2 pallet cạnh nhau trên cùng tầng kệ).
"""

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
        Button = MagicMock

import config
from control import Motion, Lift
from control.mcp3008_bus import get_mcp3008_bus, reset_mcp3008_bus
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

        # 2 kiện đang mang trên càng
        self.carried_labels: list[str | None] = [None, None]
        # Thứ tự giao: [label_giao_trước, label_giao_sau] (tối ưu theo khoảng cách)
        self.delivery_queue: list[str] = []
        # Label cuối cùng đã giao thực tế (dùng để chọn route quay về)
        self._last_delivered_label: str | None = None

        # Nút khởi động
        self._start_button = Button(config.START_BUTTON_PIN, pull_up=True, bounce_time=0.1)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Robot đã sẵn sàng. Nhấn nút khởi động để bắt đầu.")
        logger.info("Chế độ: nâng 2 kiện/lượt — %d lượt cho %d kiện",
                     config.PICKUPS_TASK1, config.TOTAL_PACKAGES_TASK1)

    def _signal_handler(self, sig, frame):
        logger.warning("Nhận tín hiệu dừng (signal %s)", sig)
        self.state = State.EMERGENCY_STOP
        self._emergency_stop()
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

    def _run_route(self, route: list, context: str) -> bool:
        if not route:
            logger.warning("Route rỗng — %s", context)
            return False
        if not self.motion.execute_route(route):
            logger.error("Navigation thất bại — %s", context)
            return False
        return True

    def _approach_shelf(self, context: str) -> bool:
        if not self.motion.approach_shelf():
            logger.warning("Tiếp cận kệ thất bại (timeout) — %s", context)
            return False
        return True

    def _retreat_from_shelf(self, context: str):
        if not self.motion.retreat_from_shelf():
            logger.warning("Lùi khỏi kệ thất bại (timeout) — %s", context)

    # ----------------------------------------------------------
    # Tính toán route tối ưu
    # ----------------------------------------------------------

    @staticmethod
    def _route_cost(route: list) -> int:
        """Chi phí route: forward = số giao lộ, turn = ROUTE_TURN_COST."""
        cost = 0
        for step in route:
            if step[0] == "forward":
                cost += step[1]
            elif step[0] in ("left", "right"):
                cost += config.ROUTE_TURN_COST
        return cost

    @staticmethod
    def _between_route(from_label: str, to_label: str) -> list:
        return config.ROUTE_BETWEEN_FACTORIES.get(
            (from_label, to_label),
            config.ROUTE_BETWEEN_FACTORIES.get((to_label, from_label), []),
        )

    def _plan_delivery(self, label_left: str, label_right: str):
        """
        Lên kế hoạch giao 2 kiện theo thứ tự tối ưu.
        So sánh tổng chi phí: kho → NM1 → NM2 (gồm cả lần xoay).
        Nếu cùng nhà máy → giao 1 lần duy nhất.
        """
        if label_left == label_right:
            self.delivery_queue = [label_left]
            logger.info("2 kiện cùng loại (%s) — giao 1 điểm duy nhất", label_left)
            return

        route_left = config.ROUTE_SHELF_TO_FACTORY.get(label_left, [])
        route_right = config.ROUTE_SHELF_TO_FACTORY.get(label_right, [])
        cost_left_first = (
            self._route_cost(route_left)
            + self._route_cost(self._between_route(label_left, label_right))
        )
        cost_right_first = (
            self._route_cost(route_right)
            + self._route_cost(self._between_route(label_right, label_left))
        )

        if cost_left_first <= cost_right_first:
            self.delivery_queue = [label_left, label_right]
            logger.info("Giao: %s → %s (tổng cost=%d vs %d)",
                        label_left, label_right, cost_left_first, cost_right_first)
        else:
            self.delivery_queue = [label_right, label_left]
            logger.info("Giao: %s → %s (tổng cost=%d vs %d)",
                        label_right, label_left, cost_right_first, cost_left_first)

    # ----------------------------------------------------------
    # State handlers
    # ----------------------------------------------------------

    def _handle_init(self) -> State:
        logger.info("Trạng thái: INIT — chờ nút khởi động...")
        self._start_button.wait_for_press()
        logger.info("Nút khởi động đã được nhấn!")
        self.match_start_time = time.time()
        return State.START

    def _handle_start(self) -> State:
        logger.info("Trạng thái: START — bắt đầu trận đấu (240s)")
        self.lift.reset()

        # Thoát ô start → tìm line R0 → căn giữa (giao lộ do ROUTE_START đếm)
        if not self.motion.exit_start_zone():
            logger.error("Không thoát được ô start — dừng!")
            return State.DONE

        return State.NAVIGATE_TO_SHELF

    def _handle_navigate_to_shelf(self) -> State:
        """Di chuyển đến giá kệ hiện tại."""
        if self._shelves_exhausted():
            logger.warning("Đã hết kệ NV1 (kệ %d)", self.current_shelf)
            return self._finish_task1_or_done()

        logger.info("Di chuyển đến kệ %d, tầng %d...",
                     self.current_shelf, self.current_tier)

        if self.pickup_count == 0:
            # Lần đầu: exit_start_zone() đã chạm line R0 → forward 1 giao lộ đến Kệ 3
            if not self._run_route(config.ROUTE_START_TO_SHELF_0, "START → Kệ 3"):
                return self._retry_or_skip_tier("navigate")
        elif self.current_tier == 2:
            # Tầng 2 cùng kệ → không cần di chuyển, chỉ quay lại tiếp cận
            pass
        else:
            # Sang kệ tiếp → di chuyển giữa các kệ
            if not self._run_route(config.ROUTE_BETWEEN_SHELVES, "giữa các kệ"):
                return self._retry_or_skip_tier("navigate")

        return State.PICKUP_PAIR

    def _handle_pickup_pair(self) -> State:
        """Tiếp cận kệ, quét nhận diện 2 kiện, rồi nâng pallet."""
        logger.info("Trạng thái: PICKUP_PAIR — kệ %d, tầng %d",
                     self.current_shelf, self.current_tier)

        if not self.is_time_safe():
            logger.warning("Sắp hết giờ! Dừng lại.")
            return State.DONE

        if not self._approach_shelf("PICKUP_PAIR"):
            return self._retry_or_skip_tier("approach")

        label_left, label_right = None, None
        for attempt in range(1, config.MAX_PAIR_SCAN_ATTEMPTS + 1):
            label_left, label_right = self.vision.classify_pair()
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
        self._plan_delivery(label_left, label_right)

        success = self.lift.pickup(self.current_tier)

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
        route = config.ROUTE_SHELF_TO_FACTORY.get(label, [])

        logger.info("Giao kiện 1: %s → %s", label, factory)

        if not self.is_time_safe():
            logger.warning("Sắp hết giờ!")
            return State.DROP_FIRST

        if not self._run_route(route, f"DELIVER → {label}"):
            logger.warning("Navigation lệch — vẫn thử hạ hàng tại %s", factory)
        return State.DROP_FIRST

    def _get_drop_side(self, label: str) -> str:
        """Xác định càng nào (left/right) đang giữ kiện có label này."""
        if self.carried_labels[0] == label:
            return "left"
        return "right"

    def _drop_single_side(self, side: str) -> bool:
        """Thả 1 kiện và nâng lại càng vừa thả. Trả về True nếu IR xác nhận."""
        if side == "left":
            dropped = self.lift.dropoff_left()
        else:
            dropped = self.lift.dropoff_right()
        if dropped:
            self.lift.raise_after_drop(side)
        return dropped

    def _handle_drop_first(self) -> State:
        """Hạ kiện hàng đầu tiên."""
        label = self.delivery_queue.pop(0)
        self._last_delivered_label = label
        same_factory = self.carried_labels[0] == self.carried_labels[1]

        logger.info("Trạng thái: DROP_FIRST — %s (%s)",
                     label, "cả 2 càng" if same_factory else self._get_drop_side(label))

        self._approach_shelf(f"DROP_FIRST {label}")

        if same_factory:
            if self.lift.dropoff():
                self.packages_delivered += 2
            else:
                logger.error("DROP_FIRST thất bại — IR vẫn thấy pallet hoặc lỗi cảm biến")
        else:
            side = self._get_drop_side(label)
            if self._drop_single_side(side):
                self.packages_delivered += 1
            else:
                logger.error("DROP_FIRST thất bại — càng %s chưa thả được pallet", side)

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
        prev_label = self._last_delivered_label
        if prev_label is None:
            logger.error("Không có nhà máy trước đó — dùng carried_labels fallback")
            prev_label = (
                self.carried_labels[0]
                if self.carried_labels[0] != label
                else self.carried_labels[1]
            )
        factory = self.vision.get_factory_name(label)

        route_key = (prev_label, label)
        rev_key = (label, prev_label)
        route = config.ROUTE_BETWEEN_FACTORIES.get(
            route_key, config.ROUTE_BETWEEN_FACTORIES.get(rev_key, [])
        )

        logger.info("Giao kiện 2: %s → %s (từ %s)", label, factory, prev_label)

        if not self.is_time_safe():
            logger.warning("Sắp hết giờ!")
            return State.DROP_SECOND

        if not self._run_route(route, f"DELIVER → {label} (từ {prev_label})"):
            logger.warning("Navigation lệch — vẫn thử hạ hàng tại %s", factory)
        return State.DROP_SECOND

    def _handle_drop_second(self) -> State:
        """Hạ kiện hàng thứ 2 (càng còn lại)."""
        label = self.delivery_queue.pop(0)
        self._last_delivered_label = label
        side = self._get_drop_side(label)

        logger.info("Trạng thái: DROP_SECOND — %s (càng %s)", label, side)

        self._approach_shelf(f"DROP_SECOND {label}")

        dropped = False
        if side == "left":
            dropped = self.lift.dropoff_left()
        else:
            dropped = self.lift.dropoff_right()

        if dropped:
            self.lift.stow_forks(side)
            self.packages_delivered += 1
        else:
            logger.error("DROP_SECOND thất bại — càng %s chưa thả được pallet", side)

        self._retreat_from_shelf(f"DROP_SECOND {label}")
        logger.info("Đã giao %d/%d kiện",
                     self.packages_delivered, config.TOTAL_PACKAGES_TASK1)

        if self.packages_delivered >= config.TOTAL_PACKAGES_TASK1:
            logger.info("NHIỆM VỤ 1 HOÀN THÀNH!")
            return State.TASK2_NAVIGATE_TO_LOOSE

        if not self.is_time_safe():
            return State.DONE

        return State.RETURN_TO_WAREHOUSE

    def _handle_return_to_warehouse(self) -> State:
        """Quay về kho, chuyển sang tầng/kệ tiếp theo."""
        route = config.ROUTE_FACTORY_TO_SHELF.get(self._last_delivered_label, [])
        logger.info("Quay về kho từ %s...", self._last_delivered_label)
        if not self._run_route(route, f"RETURN từ {self._last_delivered_label}"):
            logger.warning("Quay về kho có thể lệch vị trí")

        self._advance_position()
        logger.info("Tiếp theo: kệ %d, tầng %d",
                     self.current_shelf, self.current_tier)
        return State.NAVIGATE_TO_SHELF

    # ----------------------------------------------------------
    # Nhiệm vụ 2
    # ----------------------------------------------------------

    def _handle_task2_navigate_to_loose(self) -> State:
        """Đi từ nhà máy cuối cùng đã giao → kho hàng rời (kệ 4, dưới trái)."""
        logger.info("Nhiệm vụ 2: đi đến kho hàng rời (kệ 4)...")
        if not self.is_time_safe():
            return State.DONE

        route = config.ROUTE_FACTORY_TO_LOOSE.get(self._last_delivered_label, [])
        logger.info("Đi từ %s đến kệ 4...", self._last_delivered_label)
        if not self._run_route(route, f"NV2 → kho rời từ {self._last_delivered_label}"):
            logger.error("Navigation NV2 thất bại — dừng")
            return State.DONE
        return State.TASK2_PICKUP

    def _handle_task2_pickup(self) -> State:
        logger.info("Nhiệm vụ 2: nhấc hàng từ kho hàng rời...")
        if not self._approach_shelf("TASK2_PICKUP"):
            logger.error("Nhiệm vụ 2: không tiếp cận được kho rời — dừng")
            return State.DONE
        success = self.lift.pickup(shelf_level=1, require_both=False)
        self._retreat_from_shelf("TASK2_PICKUP")
        if not success:
            logger.error("Nhiệm vụ 2: nâng thất bại — bỏ qua")
            return State.DONE
        return State.TASK2_NAVIGATE_TO_JOINT

    def _handle_task2_navigate_to_joint(self) -> State:
        logger.info("Nhiệm vụ 2: đi đến nhà máy liên hợp...")
        if not self.is_time_safe():
            return State.DONE
        if not self._run_route(config.ROUTE_LOOSE_TO_JOINT, "NV2 → nhà máy liên hợp"):
            logger.error("Navigation NV2 thất bại — dừng")
            return State.DONE
        return State.TASK2_DROP

    def _handle_task2_drop(self) -> State:
        logger.info("Nhiệm vụ 2: đặt hàng tại nhà máy liên hợp...")
        self._approach_shelf("TASK2_DROP")
        if not self.lift.dropoff():
            logger.error("TASK2_DROP thất bại — IR vẫn thấy pallet hoặc lỗi cảm biến")
        self._retreat_from_shelf("TASK2_DROP")
        logger.info("NHIỆM VỤ 2 HOÀN THÀNH!")
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

    def run(self):
        """Chạy state machine cho đến khi DONE hoặc hết giờ."""
        logger.info("========== BẮT ĐẦU STATE MACHINE ==========")

        try:
            while self.state not in (State.DONE, State.EMERGENCY_STOP):
                handler_name = self.STATE_HANDLERS.get(self.state)
                if handler_name is None:
                    logger.error("Không có handler cho state: %s", self.state)
                    break

                handler = getattr(self, handler_name)
                next_state = handler()

                logger.info("Chuyển trạng thái: %s -> %s", self.state.value, next_state.value)
                self.state = next_state

                if self.match_start_time > 0 and not self.is_time_safe():
                    logger.warning("Hết thời gian an toàn! Dừng lại.")
                    self.state = State.DONE

        except Exception as e:
            logger.exception("LỖI NGHIÊM TRỌNG: %s", e)
            self._emergency_stop()

        finally:
            self._finish()

    def _finish(self):
        self.motion.stop()
        elapsed = self.elapsed() if self.match_start_time > 0 else 0
        logger.info("========== KẾT THÚC ==========")
        logger.info("Thời gian: %.1f giây", elapsed)
        logger.info("Kiện hàng đã giao: %d/%d (trong %d lượt nâng)",
                     self.packages_delivered, config.TOTAL_PACKAGES_TASK1,
                     self.pickup_count)
        self.motion.cleanup()
        self.lift.cleanup()
        self.vision.cleanup()
        reset_mcp3008_bus()
        self._start_button.close()


# ============================================================
# Entry point
# ============================================================

def main():
    if config.DEBUG_MODE:
        logger.warning("*** CHẾ ĐỘ DEBUG — KHÔNG DÙNG KHI THI ĐẤU ***")
        from debug import run_debug_server
        run_debug_server()
        return

    robot = Robot()
    robot.run()


if __name__ == "__main__":
    main()
