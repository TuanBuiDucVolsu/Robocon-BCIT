#!/usr/bin/env python3
"""
Chạy KHÔ một trận: in ra từng bước robot sẽ đi, từ ô xuất phát đến hết nhiệm vụ.

    python3 -m tools.dry_run                       # kịch bản mặc định
    python3 -m tools.dry_run --scenario "samsung,foxconn amkor,amkor ..."
    python3 -m tools.dry_run --forward 1.7 --turn 0.9      # số đo thật từ measure_phases

VÌ SAO CÓ FILE NÀY: bản đồ line trong navigation.py đo từ file in, nhưng vẫn phải
ĐỐI CHIẾU TAY trên sa bàn thật trước khi chạy. `show_routes` in từng tuyến rời rạc,
còn file này in TRỌN kịch bản theo đúng thứ tự robot sẽ làm — cầm tờ này đi bộ trên
sa bàn là kiểm được từng bước một.

Các bước KHÔNG phải tôi viết tay: script gọi thẳng state machine trong main.py với
phần cứng giả lập, nên những gì in ra đúng là những gì robot sẽ làm. Sửa navigation
hay main mà lệch đi thì bản in này đổi theo.

Mốc thời gian chỉ là ƯỚC TÍNH từ 6 tham số bên dưới — lấy số thật bằng:
    bash scripts/practice.sh && python3 -m tools.measure_phases
"""

import argparse
import logging
import sys
import time
from unittest.mock import MagicMock

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

# TẮT log TRƯỚC khi import main: main.py cấu hình logging ghi vào robot_log.txt ngay
# lúc import. Chạy khô mà để nó ghi thì `tools.measure_phases` sẽ đọc phải một "lượt
# chạy" hoàn toàn giả với thời gian ~0s và bịa ra số đo vô nghĩa.
logging.disable(logging.CRITICAL)

import config
import navigation as nav
import main as main_mod

# Kệ3 T1 → Kệ3 T2 → Kệ2 T1 → Kệ2 T2 → Kệ1 T1 → Kệ1 T2 (thứ tự robot lấy hàng).
# Mặc định: mỗi loại đúng 3 kiện, trộn đều — không phải kịch bản dễ nhất cũng không
# phải khó nhất.
DEFAULT_SCENARIO = [
    ("samsung", "foxconn"),
    ("amkor", "amkor"),
    ("hana_micron", "samsung"),
    ("foxconn", "hana_micron"),
    ("amkor", "foxconn"),
    ("samsung", "hana_micron"),
]

SHELF_NAMES = {0: "Kệ 3 (hàng R0)", 1: "Kệ 2 (hàng R2)", 2: "Kệ 1 (hàng R4)"}
MAX_STEPS = 400


class Recorder:
    """Ghi lại từng hành động vật lý + cộng dồn thời gian ước tính."""

    def __init__(self, a):
        self.a = a
        self.rows = []      # (loại, mô tả, giây, mốc tích luỹ, kiện NV1, có phải NV2)
        self.clock = 0.0

    def add(self, kind, text, secs, packages=0, nv2=False):
        self.clock += secs
        self.rows.append((kind, text, secs, self.clock, packages, nv2))

    def route(self, pose, route):
        """Tách route thành từng lệnh rời để in cho dễ đối chiếu trên sa bàn."""
        place, heading = pose
        for cmd in route:
            if cmd[0] in ("forward", "back"):
                lui = cmd[0] == "back"
                for _ in range(cmd[1]):
                    nxt = self._step(place, heading)
                    self.add("đi", f"{'LÙI' if lui else 'tiến'} 1 giao lộ "
                                   f"({place} → {nxt}){' — không xoay đầu' if lui else ''}",
                             self.a.reverse if lui else self.a.forward)
                    place = nxt
            elif cmd[0] in ("left", "right"):
                heading = (nav.turn_left(heading) if cmd[0] == "left"
                           else nav.turn_right(heading))
                self.add("xoay", f"xoay 90° {'TRÁI' if cmd[0] == 'left' else 'PHẢI'}"
                                 f"  (giờ quay {nav.HEADING_NAMES.get(heading, '?')})",
                         self.a.turn)
            elif cmd[0] == "advance":
                term = next((t for t, (n, h, _) in nav.TERMINALS.items()
                             if n == place and h == heading), "?")
                self.add("đi", f"bám line tới HẾT line  ({place} → {term})", self.a.advance)
                place = term

    @staticmethod
    def _step(place, heading):
        if place in nav.TERMINALS:
            return nav.TERMINALS[place][0]
        got = nav.ADJACENCY.get(place, {}).get(heading)
        return got[0] if got else "?"


def build_robot(scenario, rec):
    """Robot thật của main.py, phần cứng thay bằng mock có ghi lại hành động."""
    r = object.__new__(main_mod.Robot)
    r.motion, r.lift, r.vision = MagicMock(), MagicMock(), MagicMock()
    r._start_button = MagicMock()
    r.packages_delivered = r.pickup_count = 0
    r.current_shelf, r.current_tier = 0, 1
    r._tier_retries = 0
    r._side_detected = False
    r.pose = nav.START_POSE
    r.carried_labels = [None, None]
    r.delivery_queue = []
    r._last_delivered_label = None
    r._reset_requested = False
    r._reset_count = 0
    r._phase_times, r._phase_counts = {}, {}
    r.match_start_time = time.time()      # mô phỏng chạy tức thì → luôn còn giờ
    r.state = main_mod.State.START

    a = rec.a

    def exit_start():
        rec.add("đi", "tiến thẳng khỏi ô xuất phát tới khi chạm line hàng R0, "
                      "rồi bám line ngắn để căn giữa", a.exit)
        return True

    def execute_route(route):
        rec.route(r.pose, route)          # r.pose vẫn là vị trí CŨ lúc này
        return True

    def probe(direction="right"):
        rec.add("dò", f"dò nhánh line phía {direction.upper()}: xoay ra, tiến "
                      f"{config.PROBE_TRAVEL_TIME}s, đọc cảm biến, lùi về, xoay lại", a.probe)
        return True                        # thấy line → nửa CHUẨN

    def approach():
        rec.add("căn", f"tiến chậm bằng siêu âm, dừng cách {config.APPROACH_DISTANCE}cm",
                a.approach)
        return True

    def retreat():
        rec.add("căn", f"lùi ra {config.RETREAT_DISTANCE}cm", a.retreat)
        return True

    def classify():
        pair = scenario[min(r.pickup_count, len(scenario) - 1)]
        rec.add("quét", f"chụp ảnh, chia đôi khung → TRÁI={pair[0]}  PHẢI={pair[1]}", a.scan)
        return pair

    # Chữ ký phải khớp Lift.pickup(shelf_level, require_both) — main gọi cả kiểu vị
    # trí (NV1) lẫn kiểu từ khoá shelf_level= (NV2).
    def pickup(shelf_level=1, require_both=True):
        rec.add("nâng", f"nâng 2 càng lên tầng {shelf_level}, IR xác nhận "
                        f"{'CẢ 2' if require_both else '≥1'} pallet", a.lift)
        return True

    r.motion.exit_start_zone.side_effect = exit_start
    r.motion.execute_route.side_effect = execute_route
    r.motion.probe_side_branch.side_effect = probe
    r.motion.approach_shelf.side_effect = approach
    r.motion.retreat_from_shelf.side_effect = retreat
    r.motion.last_route_progress = []
    r.vision.classify_pair.side_effect = classify
    r.vision.get_factory_name.side_effect = config.LABEL_TO_FACTORY.get
    r.lift.pickup.side_effect = pickup
    def dropoff_both():
        # Cùng một lệnh dùng cho 2 kiện NV1 cùng nhà máy (2×20đ) và cho NV2 (30đ)
        nv2 = r.state is main_mod.State.TASK2_DROP
        rec.add("hạ", "hạ CẢ 2 càng, IR xác nhận cả 2 pallet đã rời"
                      + (" — NV2 XONG (+30đ)" if nv2 else ""),
                a.lift, packages=0 if nv2 else 2, nv2=nv2)
        return True

    r.lift.dropoff.side_effect = dropoff_both
    r.lift.dropoff_left.side_effect = lambda: (
        rec.add("hạ", "hạ càng TRÁI, IR xác nhận pallet trái đã rời", a.lift, 1), True)[1]
    r.lift.dropoff_right.side_effect = lambda: (
        rec.add("hạ", "hạ càng PHẢI, IR xác nhận pallet phải đã rời", a.lift, 1), True)[1]
    r.lift.raise_after_drop.side_effect = lambda side: rec.add(
        "nâng", f"nâng lại càng {side} cho ngang càng kia", 0.0)
    r.lift.stow_forks.side_effect = lambda side: rec.add(
        "nâng", "gập càng còn lại về sàn", 0.0)
    return r


def run(robot, rec):
    """Chạy state machine THẬT, gom hành động theo từng state."""
    blocks, steps = [], 0
    while robot.state not in (main_mod.State.DONE, main_mod.State.EMERGENCY_STOP):
        if steps >= MAX_STEPS:
            blocks.append(("!! VÒNG LẶP", [], robot.current_shelf, robot.current_tier))
            break
        steps += 1
        name = robot.STATE_HANDLERS.get(robot.state)
        if name is None:
            break
        label, shelf, tier = robot.state.value, robot.current_shelf, robot.current_tier
        mark = len(rec.rows)
        robot.state = getattr(robot, name)()
        blocks.append((label, rec.rows[mark:], shelf, tier))
    return blocks


BULLET = {"đi": "→", "xoay": "↻", "căn": "⇥", "quét": "◉", "nâng": "▲",
          "hạ": "▼", "dò": "?"}


def report(blocks, rec, scenario, args):
    print("=" * 78)
    print(" CHẠY KHÔ — CÁC BƯỚC ROBOT SẼ ĐI")
    print("=" * 78)
    print(f" {nav.board_summary()}")
    print("\n Kịch bản kiện hàng giả định (BTC xếp ngẫu nhiên — đây chỉ là 1 khả năng):")
    for i, (l, r) in enumerate(scenario):
        print(f"   {SHELF_NAMES[i // 2]:<16} tầng {i % 2 + 1}:  trái={l:<12} phải={r}")
    print(f"\n Thời gian ước tính: giao lộ {args.forward}s | LÙI 1 giao lộ "
          f"{args.reverse}s | xoay {args.turn}s | advance {args.advance}s"
          f"\n {'':19} tiếp cận {args.approach}s | lùi khỏi kệ {args.retreat}s | "
          f"nâng-hạ {args.lift}s | quét {args.scan}s")

    n, cut_shown = 0, False
    for label, rows, shelf, tier in blocks:
        if not rows:
            continue
        head = label
        if label in ("NAVIGATE_TO_SHELF", "PICKUP_PAIR"):
            head = f"{label}  —  {SHELF_NAMES.get(shelf, '?')}, tầng {tier}"
        print(f"\n  {head}")
        for kind, text, secs, clock, _pkg, _nv2 in rows:
            n += 1
            if clock > config.MATCH_DURATION and not cut_shown:
                cut_shown = True
                print(f"       {'─' * 68}")
                print(f"       ↑ HẾT 240 GIÂY — mọi bước dưới đây KHÔNG kịp làm")
                print(f"       {'─' * 68}")
            print(f"    {n:>3}. {BULLET.get(kind, '·')} {text:<58} "
                  f"{secs:>4.1f}s  ({clock:5.1f}s)")

    in_time = [(pkg, nv2) for _l, rows, _s, _t in blocks
               for _k, _x, _sec, clock, pkg, nv2 in rows
               if clock <= config.MATCH_DURATION]
    scored = sum(pkg for pkg, _ in in_time)
    nv2_ok = any(nv2 for _, nv2 in in_time)
    points = scored * 20 + (30 if nv2_ok else 0)

    print("\n" + "=" * 78)
    print(f" TỔNG: {n} bước, ước tính {rec.clock:.0f}s / {config.MATCH_DURATION}s")
    print(f" Trong 240s: {scored}/{config.TOTAL_PACKAGES_TASK1} kiện NV1"
          f"{' + NV2' if nv2_ok else ''}  →  {points} điểm")
    if rec.clock > config.MATCH_DURATION:
        print(f" → KHÔNG kịp hết kịch bản (thiếu {rec.clock - config.MATCH_DURATION:.0f}s)")
    else:
        print(f" → Kịp, dư {config.MATCH_DURATION - rec.clock:.0f}s")
    print(" Mốc thời gian là ƯỚC TÍNH. Số thật: practice.sh → tools.measure_phases")
    print("=" * 78)


def parse_scenario(text):
    pairs = []
    for chunk in text.split():
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) != 2 or any(p not in config.LABEL_TO_FACTORY for p in parts):
            raise SystemExit(f"Cặp không hợp lệ: {chunk!r} "
                             f"(dùng: {','.join(config.LABEL_TO_FACTORY)})")
        pairs.append(tuple(parts))
    if len(pairs) != config.PICKUPS_TASK1:
        raise SystemExit(f"Cần đúng {config.PICKUPS_TASK1} cặp, nhận {len(pairs)}")
    return pairs


def main():
    p = argparse.ArgumentParser(description="In từng bước robot sẽ đi trong 1 trận")
    p.add_argument("--scenario", help="6 cặp 'trái,phải' cách nhau bởi dấu cách")
    p.add_argument("--forward", type=float, default=2.5)
    p.add_argument("--reverse", type=float, default=3.0,
                   help="giây LÙI 1 giao lộ (chậm hơn tiến — config.REVERSE_SPEED)")
    p.add_argument("--turn", type=float, default=1.2)
    p.add_argument("--advance", type=float, default=2.0)
    p.add_argument("--approach", type=float, default=1.8)
    p.add_argument("--retreat", type=float, default=1.2)
    p.add_argument("--lift", type=float, default=5.1)
    p.add_argument("--scan", type=float, default=1.0)
    p.add_argument("--exit", type=float, default=2.0, help="giây thoát ô xuất phát")
    p.add_argument("--probe", type=float, default=3.0, help="giây dò nửa sân")
    args = p.parse_args()

    scenario = parse_scenario(args.scenario) if args.scenario else DEFAULT_SCENARIO
    rec = Recorder(args)
    robot = build_robot(scenario, rec)
    blocks = run(robot, rec)
    report(blocks, rec, scenario, args)


if __name__ == "__main__":
    main()
