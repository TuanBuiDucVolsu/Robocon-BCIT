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
    SCAN_PAIR = "SCAN_PAIR"
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
        self.motion = Motion()
        self.lift = Lift()
        self.vision = Vision()

        self.state = State.INIT
        self.packages_delivered = 0
        self.pickup_count = 0             # Số lần đã nâng (0-6)
        self.current_shelf = 0            # Giá kệ hiện tại (0-2)
        self.current_tier = 1             # Tầng kệ hiện tại (1 = dưới, 2 = trên)
        self.match_start_time = 0.0

        # 2 kiện đang mang trên càng
        self.carried_labels: list[str | None] = [None, None]
        # Thứ tự giao: [label_giao_trước, label_giao_sau] (tối ưu theo khoảng cách)
        self.delivery_queue: list[str] = []

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

    # ----------------------------------------------------------
    # Tính toán route tối ưu
    # ----------------------------------------------------------

    def _get_factory_distance(self, label_a: str, label_b: str) -> int:
        """Lấy khoảng cách giữa 2 nhà máy (số giao lộ)."""
        if label_a == label_b:
            return 0
        key = (label_a, label_b)
        rev_key = (label_b, label_a)
        return config.FACTORY_DISTANCE.get(key,
               config.FACTORY_DISTANCE.get(rev_key, 2))

    def _plan_delivery(self, label_left: str, label_right: str):
        """
        Lên kế hoạch giao 2 kiện theo thứ tự tối ưu.
        Ưu tiên: giao nhà máy gần kho trước → giảm tổng quãng đường.
        Nếu cùng nhà máy → giao 1 lần duy nhất.
        """
        dist_left = config.FACTORY_NAV_MAP.get(label_left, 99)
        dist_right = config.FACTORY_NAV_MAP.get(label_right, 99)

        if label_left == label_right:
            # Cùng nhà máy → giao 1 lần, đếm 2 kiện
            self.delivery_queue = [label_left]
            logger.info("2 kiện cùng loại (%s) — giao 1 điểm duy nhất", label_left)
        elif dist_left <= dist_right:
            self.delivery_queue = [label_left, label_right]
            logger.info("Giao: %s (gần, %d giao lộ) → %s (xa, %d giao lộ)",
                        label_left, dist_left, label_right, dist_right)
        else:
            self.delivery_queue = [label_right, label_left]
            logger.info("Giao: %s (gần, %d giao lộ) → %s (xa, %d giao lộ)",
                        label_right, dist_right, label_left, dist_left)

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
        return State.NAVIGATE_TO_SHELF

    def _handle_navigate_to_shelf(self) -> State:
        """Di chuyển đến giá kệ hiện tại."""
        logger.info("Di chuyển đến kệ %d, tầng %d...",
                     self.current_shelf, self.current_tier)

        if self.pickup_count == 0:
            intersections = config.NAV_START_TO_SHELF_0
        elif self.current_tier == 1:
            # Vừa quay về từ nhà máy → đi đến kệ
            intersections = config.NAV_FACTORY_TO_WAREHOUSE
            if self.current_shelf > 0:
                intersections += self.current_shelf * config.NAV_BETWEEN_SHELVES
        else:
            # Tầng 2 cùng kệ → không cần di chuyển xa, chỉ căn chỉnh lại
            intersections = 0

        if intersections > 0:
            self.motion.navigate_intersections(intersections)

        return State.SCAN_PAIR

    def _handle_scan_pair(self) -> State:
        """Quét nhận diện 2 kiện hàng trên cùng tầng kệ."""
        logger.info("Trạng thái: SCAN_PAIR — kệ %d, tầng %d",
                     self.current_shelf, self.current_tier)

        if not self.is_time_safe():
            logger.warning("Sắp hết giờ! Dừng lại.")
            return State.DONE

        label_left, label_right = self.vision.classify_pair()

        # Fallback nếu không nhận diện được
        all_labels = list(config.LABEL_TO_FACTORY.keys())
        if label_left is None:
            label_left = all_labels[0]
            logger.warning("Không nhận diện được kiện trái, fallback: %s", label_left)
        if label_right is None:
            label_right = all_labels[1]
            logger.warning("Không nhận diện được kiện phải, fallback: %s", label_right)

        self.carried_labels = [label_left, label_right]
        self._plan_delivery(label_left, label_right)

        return State.PICKUP_PAIR

    def _handle_pickup_pair(self) -> State:
        """Nâng 2 pallet cùng lúc từ tầng kệ hiện tại."""
        logger.info("Trạng thái: PICKUP_PAIR — nâng 2 kiện")

        # Tiến chậm vào kệ
        self.motion.forward(config.SPEED_SLOW)
        time.sleep(0.5)
        self.motion.stop()

        self.lift.pickup(self.current_tier)

        # Lùi ra
        self.motion.backward(config.SPEED_SLOW)
        time.sleep(0.5)
        self.motion.stop()

        self.pickup_count += 1
        logger.info("Đã nâng lượt %d/%d", self.pickup_count, config.PICKUPS_TASK1)

        return State.DELIVER_FIRST

    def _handle_deliver_first(self) -> State:
        """Di chuyển đến nhà máy đầu tiên trong delivery_queue."""
        if not self.delivery_queue:
            return State.RETURN_TO_WAREHOUSE

        label = self.delivery_queue[0]
        factory = self.vision.get_factory_name(label)
        intersections = config.FACTORY_NAV_MAP.get(label, 3)

        logger.info("Giao kiện 1: %s → %s (%d giao lộ)", label, factory, intersections)

        if not self.is_time_safe():
            logger.warning("Sắp hết giờ!")
            return State.DROP_FIRST

        self.motion.navigate_intersections(intersections)
        return State.DROP_FIRST

    def _handle_drop_first(self) -> State:
        """Hạ kiện hàng đầu tiên."""
        logger.info("Trạng thái: DROP_FIRST")

        self.motion.forward(config.SPEED_SLOW)
        time.sleep(0.3)
        self.motion.stop()

        self.lift.dropoff()

        self.motion.backward(config.SPEED_SLOW)
        time.sleep(0.5)
        self.motion.stop()

        label = self.delivery_queue.pop(0)
        # Nếu 2 kiện cùng nhà máy → đếm 2
        if not self.delivery_queue or self.delivery_queue[0] != label:
            self.packages_delivered += 1
        else:
            self.packages_delivered += 2
            self.delivery_queue.pop(0)

        # Cùng nhà máy đã giao hết → không cần giao tiếp
        if label == self.carried_labels[0] == self.carried_labels[1]:
            self.packages_delivered = min(self.packages_delivered,
                                          self.packages_delivered)

        logger.info("Đã giao %d/%d kiện",
                     self.packages_delivered, config.TOTAL_PACKAGES_TASK1)

        if self.delivery_queue:
            return State.DELIVER_SECOND

        # Hết queue → kiểm tra hoàn thành
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
        prev_label = self.carried_labels[0] if self.carried_labels[0] != label else self.carried_labels[1]
        factory = self.vision.get_factory_name(label)

        # Tính khoảng cách từ nhà máy vừa giao đến nhà máy tiếp
        intersections = self._get_factory_distance(prev_label, label)
        if intersections == 0:
            intersections = config.FACTORY_NAV_MAP.get(label, 3)

        logger.info("Giao kiện 2: %s → %s (%d giao lộ)", label, factory, intersections)

        if not self.is_time_safe():
            logger.warning("Sắp hết giờ!")
            return State.DROP_SECOND

        # Nâng lại càng để giữ kiện thứ 2 (nếu đã hạ kiện 1)
        self.lift.go_to_level(1)

        self.motion.navigate_intersections(intersections)
        return State.DROP_SECOND

    def _handle_drop_second(self) -> State:
        """Hạ kiện hàng thứ 2."""
        logger.info("Trạng thái: DROP_SECOND")

        self.motion.forward(config.SPEED_SLOW)
        time.sleep(0.3)
        self.motion.stop()

        self.lift.dropoff()

        self.motion.backward(config.SPEED_SLOW)
        time.sleep(0.5)
        self.motion.stop()

        self.delivery_queue.pop(0)
        self.packages_delivered += 1
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
        self._advance_position()
        logger.info("Quay về kho — tiếp theo: kệ %d, tầng %d",
                     self.current_shelf, self.current_tier)
        return State.NAVIGATE_TO_SHELF

    # ----------------------------------------------------------
    # Nhiệm vụ 2
    # ----------------------------------------------------------

    def _handle_task2_navigate_to_loose(self) -> State:
        logger.info("Nhiệm vụ 2: đi đến kho hàng rời...")
        if not self.is_time_safe():
            return State.DONE
        self.motion.navigate_intersections(config.NAV_WAREHOUSE_TO_LOOSE)
        return State.TASK2_PICKUP

    def _handle_task2_pickup(self) -> State:
        logger.info("Nhiệm vụ 2: nhấc hàng từ kho hàng rời...")
        self.motion.forward(config.SPEED_SLOW)
        time.sleep(0.5)
        self.motion.stop()
        self.lift.pickup(shelf_level=1)
        self.motion.backward(config.SPEED_SLOW)
        time.sleep(0.5)
        self.motion.stop()
        return State.TASK2_NAVIGATE_TO_JOINT

    def _handle_task2_navigate_to_joint(self) -> State:
        logger.info("Nhiệm vụ 2: đi đến nhà máy liên hợp...")
        if not self.is_time_safe():
            return State.DONE
        self.motion.navigate_intersections(config.NAV_LOOSE_TO_JOINT_FACTORY)
        return State.TASK2_DROP

    def _handle_task2_drop(self) -> State:
        logger.info("Nhiệm vụ 2: đặt hàng tại nhà máy liên hợp...")
        self.motion.forward(config.SPEED_SLOW)
        time.sleep(0.3)
        self.motion.stop()
        self.lift.dropoff()
        self.motion.backward(config.SPEED_SLOW)
        time.sleep(0.5)
        self.motion.stop()
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
        State.SCAN_PAIR: "_handle_scan_pair",
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
