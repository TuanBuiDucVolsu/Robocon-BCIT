#!/usr/bin/env python3
"""
Ước tính THỜI GIAN TRẬN từ số đo thật — trả lời câu "có kịp 240 giây không?".

    python3 -m tools.estimate_time                  # dùng số đo mặc định bên dưới
    python3 -m tools.estimate_time --forward 2.4 --turn 1.1 --lift 3.0

Vì sao cần: chi phí giữa các kịch bản xếp kiện chênh nhau tới HƠN 2 LẦN (BTC xếp kiện
ngẫu nhiên mỗi trận). Chạy thử trúng kịch bản nhẹ rồi kết luận "kịp giờ" là tự lừa
mình. Tool này đếm ĐÚNG số lệnh trong route thật của cả 6 lượt, cho 2 kịch bản biên:

    - TỆ NHẤT : mỗi lượt 2 kiện đi 2 nhà máy xa nhau nhất
    - NHẸ NHẤT: mỗi lượt 2 kiện cùng 1 nhà máy gần nhất

Số đo đầu vào (đo trên sa bàn, KHÔNG phải đoán):
    --forward  giây đi hết 1 khoảng giữa 2 giao lộ (test_motion #7, bấm đồng hồ)
    --turn     giây xoay 90° (= TURN_TIME + thời gian dừng/ổn định)
    --advance  giây bám line đoạn cuối vào kệ/nhà máy
    --approach giây tiếp cận siêu âm + lùi ra
    --lift     giây nâng + hạ 1 lượt (dùng LIFT_TIME_* nếu không truyền)
    --scan     giây quét nhận diện classify_pair
"""

import argparse
import itertools
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

import config
import navigation as nav

SHELF_NAMES = {0: "Kệ3", 1: "Kệ2", 2: "Kệ1"}


def count_route(pose, goal):
    """(số giao lộ, số lần xoay, số lệnh advance) của route pose→goal."""
    route, new_pose = nav.plan(pose, goal)
    if route is None:
        return None, pose
    fwd = sum(c[1] for c in route if c[0] == "forward")
    turns = sum(1 for c in route if c[0] in ("left", "right"))
    adv = sum(1 for c in route if c[0] == "advance")
    return (fwd, turns, adv), new_pose


def lap_ops(shelf, tier, label_l, label_r):
    """Đếm thao tác của MỘT lượt: từ kệ → giao 1-2 nhà máy → quay về kệ kế tiếp."""
    pose = nav.pose_at(nav.SHELF_TERMINAL[shelf])
    next_shelf = shelf if tier == 1 else shelf + 1
    back = nav.SHELF_TERMINAL.get(next_shelf)

    def chain(order):
        f = t = a = 0
        p = pose
        drops = 0
        for label in order:
            got, p = count_route(p, nav.FACTORY_TERMINAL[label])
            if got is None:
                return None
            f += got[0]; t += got[1]; a += got[2]
            drops += 1
        if back:
            got, p = count_route(p, back)
            if got is None:
                return None
            f += got[0]; t += got[1]; a += got[2]
        return f, t, a, drops

    if label_l == label_r:
        return chain([label_l])
    best = None
    for order in ((label_l, label_r), (label_r, label_l)):
        got = chain(order)
        if got and (best is None or got[0] + got[1] * 2 < best[0] + best[1] * 2):
            best = got
    return best


def seconds(ops, a):
    """ops = (giao lộ, xoay, advance, số lần thả) → giây."""
    f, t, adv, drops = ops
    return (f * a.forward + t * a.turn + adv * a.advance
            + (adv + 1) * a.approach          # mỗi advance kèm 1 lần tiếp cận + lùi
            + drops * a.lift                  # mỗi lần thả = 1 chu kỳ hạ/nâng càng
            + a.lift + a.scan)                # + nâng lúc pickup + quét nhận diện


def main():
    p = argparse.ArgumentParser(description="Ước tính thời gian trận từ số đo thật")
    p.add_argument("--forward", type=float, default=2.5, help="giây/1 khoảng giao lộ")
    p.add_argument("--turn", type=float, default=1.2, help="giây/1 lần xoay 90°")
    p.add_argument("--advance", type=float, default=2.0, help="giây bám line đoạn cuối")
    p.add_argument("--approach", type=float, default=3.0, help="giây tiếp cận + lùi ra")
    p.add_argument("--lift", type=float, default=None, help="giây nâng+hạ 1 lượt")
    p.add_argument("--scan", type=float, default=1.0, help="giây quét classify_pair")
    a = p.parse_args()
    if a.lift is None:
        a.lift = (config.LIFT_TIME_SHELF_1 + config.LIFT_TIME_SHELF_2) / 2 * 2

    print("=" * 72)
    print(" ƯỚC TÍNH THỜI GIAN TRẬN")
    print("=" * 72)
    print(f" {nav.board_summary()}")
    print(f"\n Số đo đang dùng: giao lộ {a.forward}s | xoay {a.turn}s | advance {a.advance}s")
    print(f"                  tiếp cận+lùi {a.approach}s | nâng/hạ {a.lift}s | quét {a.scan}s")
    print(" (đo lại trên sa bàn rồi truyền vào bằng --forward/--turn/... cho đúng)")

    labels = list(nav.FACTORY_TERMINAL)
    pairs = list(itertools.combinations_with_replacement(labels, 2))

    for title, pick in (("TỆ NHẤT (kiện xếp xấu nhất)", max),
                        ("NHẸ NHẤT (kiện xếp đẹp nhất)", min)):
        print(f"\n--- {title} ---")
        total = 0.0
        for shelf in (0, 1, 2):
            for tier in (1, 2):
                cand = []
                for l, r in pairs:
                    ops = lap_ops(shelf, tier, l, r)
                    if ops:
                        cand.append((seconds(ops, a), l, r, ops))
                secs, l, r, ops = pick(cand, key=lambda x: x[0])
                total += secs
                print(f"  {SHELF_NAMES[shelf]} tầng {tier}: {secs:6.1f}s  "
                      f"({l}+{r})  [{ops[0]} giao lộ, {ops[1]} xoay, {ops[2]} advance]")
        exit_start = a.forward + a.approach + 2 * a.turn + a.advance   # thoát start + dò nửa sân
        grand = total + exit_start
        print(f"  {'xuất phát + dò nửa sân':<20} {exit_start:6.1f}s")
        print(f"  {'TỔNG NV1':<20} {grand:6.1f}s / {config.MATCH_DURATION}s"
              f"   → {'✅ KỊP' if grand < config.MATCH_DURATION - config.SAFETY_MARGIN else '❌ KHÔNG KỊP'}"
              f"  (còn {config.MATCH_DURATION - grand:.0f}s cho NV2)")

    print("\n" + "=" * 72)
    print(" Cách dùng số này:")
    print("  1. Chạy `bash scripts/practice.sh` 1 lượt thật → xem bảng 'Thời gian từng chặng'")
    print("  2. Lấy số đo thật đó truyền lại vào tool này để dự đoán kịch bản TỆ NHẤT")
    print("  3. Nếu kịch bản tệ nhất KHÔNG kịp → tối ưu chặng ăn nhiều giây nhất trước")
    print("=" * 72)


if __name__ == "__main__":
    main()
