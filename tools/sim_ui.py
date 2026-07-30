#!/usr/bin/env python3
"""
Xuất trang HTML MÔ PHỎNG robot chạy trên sa bàn — mở bằng trình duyệt, xem robot đi.

    python3 -m tools.sim_ui                    # ghi ra sim_view.html
    python3 -m tools.sim_ui --out /tmp/a.html
    python3 -m tools.sim_ui --scenario "samsung,foxconn amkor,amkor ..."

VÌ SAO KHÔNG VIẾT LOGIC BẰNG JAVASCRIPT: viết lại bản đồ + sinh route bằng JS là tạo
NGUỒN SỰ THẬT THỨ HAI — đúng cái sai đã xảy ra với các bảng ROUTE_* cũ (9/12 tuyến đi
sai chỗ mà không ai biết). Ở đây trang web KHÔNG có logic nào: nó chỉ phát lại một
danh sách bước do `tools.dry_run` ghi được khi chạy CHÍNH state machine của main.py
với phần cứng giả lập. Sửa navigation hay main thì chạy lại lệnh này, trang tự đổi
theo. Trang không khớp robot = tại bước ghi, không tại trang.

Toạ độ sa bàn (mm, nửa sân 2000x2000) lấy từ số đo trong docs/SA_BAN.md mục 3 — vẽ
đúng tỉ lệ, gồm cả 2 chỗ line ĐỨT thật và vòng tròn ROBOCON, để nhìn là đối chiếu
được với sa bàn trước mặt.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

import config
import navigation as nav
from tools import dry_run

# ============================================================
# Hình học sa bàn (mm) — nửa sân 2000 x 2000, gốc góc trên-trái
# ============================================================

BOARD = 2000
COL_X = {0: 500, 1: 1500}                       # C0 cột kệ, C1 cột giữa
ROW_Y = {4: 315, 3: 655, 2: 995, 1: 1330, 0: 1670}
SHELF_X = 180                                    # tâm giá kệ
FACTORY_X = 1790                                 # điểm robot dừng ở mép khu nhà máy
ZONE_X0, ZONE_X1 = 1750, 2000                    # khu nhà máy 250x250
LOOSE_Y = 1900                                   # Kệ 4, dưới R0 trên cột C1
START_X = 980                                    # ô xuất phát trên hàng R0
GAP_R0 = (880, 1120)                             # line R0 đứt ở ô xuất phát
CIRCLE = (1000, 995, 300)                        # vòng tròn ROBOCON cắt hàng R2

ZONE_COLOR = {                                   # màu viền lấy từ bản in sa bàn
    "F_samsung": "#d23b3b", "F_hana_micron": "#e0b41b", "F_joint": "#ef8a24",
    "F_amkor": "#2f9e44", "F_foxconn": "#1b6ef3",
}


def node_xy(name: str):
    col, row = nav.NODES[name]
    return COL_X[abs(col)], ROW_Y[row]


def place_xy(place: str):
    """Toạ độ mm của một node giao lộ hoặc điểm cuối."""
    if place in nav.NODES:
        return node_xy(place)
    node, heading, _ = nav.TERMINALS[place]
    _nx, ny = node_xy(node)
    if place == "START":
        return START_X, ROW_Y[0]
    if place == "LOOSE":
        return COL_X[1], LOOSE_Y
    if place.startswith("SHELF"):
        return SHELF_X, ny
    return FACTORY_X, ny                          # F_*


def build_board():
    rows_with_full_line = [0, 2, 4]
    segments = []
    # dọc cột kệ
    segments.append([COL_X[0], ROW_Y[4], COL_X[0], ROW_Y[0]])
    # dọc cột giữa (chạy quá R0 xuống Kệ 4)
    segments.append([COL_X[1], ROW_Y[4], COL_X[1], LOOSE_Y])
    for row, y in ROW_Y.items():
        if row in rows_with_full_line:
            x0 = SHELF_X
        else:
            x0 = COL_X[1]                          # R1/R3 chỉ có từ cột giữa
        if row == 0:
            segments.append([x0, y, GAP_R0[0], y])        # đứt ở ô xuất phát
            segments.append([GAP_R0[1], y, ZONE_X0, y])
        elif row == 2:
            segments.append([x0, y, CIRCLE[0] - CIRCLE[2], y])   # đứt ở vòng tròn
            segments.append([CIRCLE[0] + CIRCLE[2], y, ZONE_X0, y])
        else:
            segments.append([x0, y, ZONE_X0, y])

    zones = []
    for term, (node, _h, _d) in nav.TERMINALS.items():
        if term.startswith("F_"):
            _c, row = nav.NODES[node]
            label = term[2:].replace("_", " ")
            zones.append({"x": ZONE_X0, "y": ROW_Y[row] - 125, "w": ZONE_X1 - ZONE_X0,
                          "h": 250, "label": label, "color": ZONE_COLOR.get(term, "#888")})

    shelves = [{"x": SHELF_X - 60, "y": ROW_Y[nav.NODES[nav.TERMINALS[t][0]][1]] - 120,
                "w": 120, "h": 240, "label": name}
               for t, name in (("SHELF0", "Kệ 3"), ("SHELF1", "Kệ 2"), ("SHELF2", "Kệ 1"))]
    shelves.append({"x": COL_X[1] - 60, "y": LOOSE_Y - 60, "w": 120, "h": 120,
                    "label": "Kệ 4"})

    return {
        "size": BOARD,
        "segments": segments,
        "zones": zones,
        "shelves": shelves,
        "circle": {"cx": CIRCLE[0], "cy": CIRCLE[1], "r": CIRCLE[2]},
        "start": {"x": START_X, "y": ROW_Y[0], "w": 400, "h": 400},
        "gaps": [{"x0": GAP_R0[0], "y": ROW_Y[0], "x1": GAP_R0[1], "label": "đứt ~245mm"},
                 {"x0": CIRCLE[0] - CIRCLE[2], "y": ROW_Y[2],
                  "x1": CIRCLE[0] + CIRCLE[2], "label": "đứt ~560mm"}],
    }


HEADING_DEG = {nav.EAST: 0, nav.NORTH: -90, nav.WEST: 180, nav.SOUTH: 90}


def collect(args):
    """Chạy state machine thật → danh sách bước kèm vị trí."""
    scenario = dry_run.parse_scenario(args.scenario) if args.scenario else dry_run.DEFAULT_SCENARIO
    rec = dry_run.Recorder(args)
    robot = dry_run.build_robot(scenario, rec)
    blocks = dry_run.run(robot, rec)

    # gắn tên state cho từng sự kiện
    idx, states = 0, []
    for label, rows, shelf, tier in blocks:
        for _ in rows:
            states.append(label)
    steps, pkg, nv2_done = [], 0, False
    for i, ev in enumerate(rec.events):
        pkg += ev["pkg"]
        if ev["nv2"]:
            nv2_done = True
        steps.append({
            "kind": ev["kind"], "text": ev["text"], "secs": ev["secs"], "clock": ev["clock"],
            "state": states[i] if i < len(states) else "",
            "x0": place_xy(ev["from"])[0], "y0": place_xy(ev["from"])[1],
            "x1": place_xy(ev["to"])[0], "y1": place_xy(ev["to"])[1],
            "a0": HEADING_DEG[ev["h0"]], "a1": HEADING_DEG[ev["h1"]],
            "pkg": pkg, "nv2": nv2_done,
            "points": pkg * 20 + (30 if nv2_done else 0),
            # Chỉ quãng ĐI mới nhanh lên theo SPEED_DEFAULT. Xoay dùng SPEED_TURN,
            # tiếp cận dùng APPROACH_*, nâng/hạ và quét thì không liên quan tốc độ —
            # gộp chung sẽ thổi phồng lợi ích của việc tăng tốc.
            "spd": ev["kind"] == "đi",
        })
    return scenario, steps


def main():
    p = argparse.ArgumentParser(description="Xuất trang mô phỏng robot chạy sa bàn")
    p.add_argument("--out", default="sim_view.html")
    p.add_argument("--scenario", default=None)
    p.add_argument("--forward", type=float, default=2.5)
    p.add_argument("--reverse", type=float, default=3.0)
    p.add_argument("--turn", type=float, default=1.2)
    p.add_argument("--advance", type=float, default=2.0)
    p.add_argument("--approach", type=float, default=1.8)
    p.add_argument("--retreat", type=float, default=1.2)
    p.add_argument("--lift", type=float, default=None)
    p.add_argument("--scan", type=float, default=1.0)
    p.add_argument("--exit", type=float, default=2.5)
    p.add_argument("--probe", type=float, default=3.0)
    p.add_argument("--speed", type=float, default=None,
                   help="Chạy thử ở mức tốc độ nào (mặc định: config.SPEED_DEFAULT). "
                        "Các số giây bên trên coi như đo ở --speed-ref.")
    p.add_argument("--speed-ref", type=float, default=None,
                   help="Các số giây bên trên đo ở tốc độ nào (mặc định SPEED_DEFAULT)")
    args = p.parse_args()

    # KHÔNG quy đổi tốc độ ở đây: các số giây ghi ra luôn là số ở --speed-ref, còn
    # việc quy đổi do TRANG làm (đổi tốc độ ngay trên trang, không phải sinh lại file).
    # Quy đổi cả 2 nơi là lại có 2 nguồn số liệu lệch nhau.
    args.speed_ref = args.speed_ref or config.SPEED_DEFAULT
    args.speed = args.speed or config.SPEED_DEFAULT
    if args.lift is None:
        args.lift = (config.LIFT_TIME_SHELF_1 + config.LIFT_TIME_SHELF_2) / 2 * 2

    scenario, steps = collect(args)
    data = {
        "board": build_board(),
        "steps": steps,
        "scenario": [{"shelf": dry_run.SHELF_NAMES[i // 2], "tier": i % 2 + 1,
                      "left": l, "right": r} for i, (l, r) in enumerate(scenario)],
        "limit": config.MATCH_DURATION,
        "summary": nav.board_summary(),
        "timing": {k: getattr(args, k) for k in
                   ("forward", "reverse", "turn", "advance", "approach", "retreat",
                    "lift", "scan")},
        "speed": {"run": args.speed, "ref": args.speed_ref,
                  "cfg": config.SPEED_DEFAULT},
    }

    here = os.path.dirname(os.path.abspath(__file__))
    template = open(os.path.join(here, "sim_ui.html"), encoding="utf-8").read()
    # Kiểm mốc có thật: thay thế im lặng không khớp thì trang ra với data=null,
    # mở lên chỉ thấy TRẮNG mà không lỗi nào — đã bị đúng một lần.
    marker = "/*__DATA__*/null"
    assert marker in template, f"tools/sim_ui.html thiếu mốc {marker!r}"
    body = template.replace(marker, json.dumps(data, ensure_ascii=False))

    # Khuôn KHÔNG có <!doctype>/<html>/<body> (đúng yêu cầu của hệ xuất bản Artifact,
    # nơi phần vỏ được thêm tự động). Nhưng file mở CỤC BỘ mà thiếu doctype thì trình
    # duyệt vào chế độ QUIRKS — layout vỡ, canvas không hiện gì cả; thiếu charset thì
    # tiếng Việt thành mojibake. Nên bọc lại khi ghi ra đĩa.
    # <title> phải nằm trong <head>, phần còn lại (style/markup/script) vào <body>.
    title, rest = "Mô phỏng robot Bảng O2", body
    m = re.match(r"\s*<title>(.*?)</title>\s*", body, re.S)
    if m:
        title, rest = m.group(1), body[m.end():]
    html = (
        "<!doctype html>\n"
        '<html lang="vi">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        "</head>\n<body>\n" + rest.strip() + "\n</body>\n</html>\n"
    )
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    k = args.speed_ref / args.speed
    clock, scaled = 0.0, []
    for st in steps:
        clock += st["secs"] * (k if st["spd"] else 1)
        scaled.append((clock, st))
    total = clock
    fit = [st for c, st in scaled if c <= config.MATCH_DURATION]
    if args.speed != args.speed_ref:
        print(f"Tốc độ {args.speed:.0f}% (số đo gốc ở {args.speed_ref:.0f}%)")
    print(f"Đã ghi {args.out}")
    print(f"  {len(steps)} bước, ước tính {total:.0f}s")
    if fit:
        print(f"  Trong {config.MATCH_DURATION}s: {fit[-1]['pkg']} kiện NV1"
              f"{' + NV2' if fit[-1]['nv2'] else ''} → {fit[-1]['points']} điểm")
    print("  Đổi tốc độ NGAY TRÊN TRANG bằng các nút 50/65/80/100%.")


if __name__ == "__main__":
    main()
