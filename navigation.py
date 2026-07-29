"""
Bản đồ sa bàn + bộ sinh route theo TRẠNG THÁI (vị trí + hướng).

VÌ SAO CÓ FILE NÀY (thay cho các bảng ROUTE_* tĩnh cũ trong config.py):

Bảng route tĩnh phải tự nhớ robot đang đứng ở đâu và quay mặt hướng nào. Thực tế
mỗi bảng cũ lại ngầm giả định một hướng khác nhau (bảng kệ→nhà máy giả định robot
quay mặt vào kệ, bảng giữa 2 kệ giả định quay lên, bảng nhà máy→kệ giả định quay
lên/quay ra tuỳ nhà máy, bảng giữa 2 nhà máy giả định quay xuống) và ngầm giả định
robot luôn xuất phát từ đúng MỘT kệ. Hệ quả: 9/12 tuyến kệ→nhà máy và toàn bộ
tuyến quay về kho đi sai chỗ. Ở đây thay bằng:

    - Mô tả sa bàn MỘT lần (node giao lộ + cạnh line thật sự nối chúng).
    - Robot luôn biết (vị trí, hướng) hiện tại.
    - Route được TÍNH RA bằng Dijkstra → tự chèn lệnh xoay đúng, tự đếm đúng số
      giao lộ, đúng cho mọi cặp điểm đi/đến.

BẢN ĐỒ LẤY TỪ ĐÂU: đo trực tiếp trên file in sa bàn chuẩn (docs/sa_ban.png — quét
pixel đen của đường line). Xem docs/SA_BAN.md để biết số đo và cách kiểm chứng lại.
Điểm quan trọng nhất khác với giả định cũ:

    - Hàng R1 và R3 CHỈ tồn tại từ cột giữa (C1) sang khu nhà máy — KHÔNG kéo tới
      cột kệ. Nên trên cột kệ chỉ có 3 giao lộ (R4/R2/R0): Kệ↔Kệ = 1 giao lộ, không
      phải 2.
    - Line ngang KẾT THÚC ở mép khu nhà máy, không cắt sống giữa sân → giữa các khu
      nhà máy KHÔNG có line nối dọc. Muốn đi từ nhà máy này sang nhà máy khác phải
      quay về cột C1 rồi đi dọc C1.
    - Hàng R2 (hàng Kệ 2) bị ĐỨT ~560mm ở vòng tròn ROBOCON giữa sân → cấm đi
      thẳng đoạn C0↔C1 trên R2, phải vòng qua R4 hoặc R0.
    - Hàng R0 đứt ~245mm ở ô xuất phát → đi được nhưng phải "trôi" qua khoảng trống
      (xem Motion.follow_line_until_intersection / config.LINE_GAP_COAST_TIME), nên
      cạnh này bị tính thêm chi phí để bộ tìm đường ưu tiên tuyến sạch khi tương đương.

HƯỚNG (heading): EAST=0 (về phía nhà máy), NORTH=1 (về phía R4), WEST=2 (về phía
kệ), SOUTH=3 (về phía R0/Kệ4). Xoay trái = +1, xoay phải = -1.

LỆNH ROUTE sinh ra: ("forward", N) | ("back", N) | ("left",) | ("right",) | ("advance",)
    ("advance",) = bám line đến HẾT line (vào kệ / khu nhà máy / Kệ 4) — những chỗ
    này là ĐIỂM CUỐI của line, không phải giao lộ nên không đếm được bằng forward.
    ("back", N) = LÙI ra khỏi điểm cuối, vẫn bám line, vẫn quay mặt vào kệ/nhà máy.
    Có nó thì không phải xoay 180° mỗi lần rút khỏi kệ — xem config.REVERSE_SPEED.
"""

import heapq

import config

# ============================================================
# Hướng
# ============================================================

EAST, NORTH, WEST, SOUTH = 0, 1, 2, 3

# Tên hướng được đặt lại sau khi biết nửa sân (xem MIRRORED bên dưới) — mô tả theo
# "phía kệ / phía nhà máy" thay vì Đông/Tây, để log đọc đúng ở cả 2 nửa sân.
HEADING_NAMES = {
    EAST: "Đông", NORTH: "Bắc", WEST: "Tây", SOUTH: "Nam",
}


def turn_left(heading: int) -> int:
    return (heading + 1) % 4


def turn_right(heading: int) -> int:
    return (heading - 1) % 4


def opposite(heading: int) -> int:
    return (heading + 2) % 4


# ============================================================
# Node giao lộ — nơi 2 đường line thật sự CẮT nhau
# ============================================================
# Toạ độ (cột, hàng): cột 0 = C0 (cột kệ), cột 1 = C1 (cột giữa).
# hàng 0..4 = R0..R4 (R4 ở phía trên sa bàn).

_CANONICAL_NODES: dict[str, tuple[int, int]] = {
    # Cột kệ — chỉ có giao lộ ở 3 hàng có line ngang (R4/R2/R0)
    "C0R0": (0, 0),
    "C0R2": (0, 2),
    "C0R4": (0, 4),
    # Cột giữa — có giao lộ ở cả 5 hàng
    "C1R0": (1, 0),
    "C1R1": (1, 1),
    "C1R2": (1, 2),
    "C1R3": (1, 3),
    "C1R4": (1, 4),
}

# ============================================================
# Nửa sân — lật gương nếu cần
# ============================================================
# Sa bàn chia đôi bởi bức tường giữa sân. Bản đồ ở trên dựng theo nửa trong
# docs/sa_ban.png (đứng ở ô xuất phát quay mặt về phía kệ thì Kệ 1 / Samsung ở bên
# TAY PHẢI). Nửa còn lại có thể là ẢNH GƯƠNG của nửa này — khi đó khoảng cách và số
# giao lộ y hệt, chỉ có chiều xoay trái/phải là ngược.
#
# Xử lý bằng cách lật CHÍNH BẢN ĐỒ (đảo dấu toạ độ cột + hoán Đông↔Tây), KHÔNG đảo
# từng lệnh route: mọi thứ phía sau (tìm đường, apply, log hướng) tự đúng theo, không
# có chỗ nào phải nhớ "đang ở nửa nào" nữa.
#
# Bắc/Nam giữ nguyên vì tường chia sân theo chiều dọc — hàng R0..R4 không đổi thứ tự.
# Giá trị mặc định lấy từ config; robot có thể TỰ DÒ rồi gọi set_mirrored() để đổi
# ngay giữa lúc chạy (xem main._handle_detect_side + Motion.probe_side_branch).
MIRRORED = bool(getattr(config, "BOARD_MIRRORED", False))

# Cụm nhà máy nằm cùng hàng ô xuất phát — quyết định thứ tự nhà máy trên tường
# (xem khối _FACTORY_ROW_BASE bên dưới). "foxconn" = nửa như docs/sa_ban.png.
FACTORY_AT_START_ROW = getattr(config, "FACTORY_AT_START_ROW", "foxconn")

NODES: dict[str, tuple[int, int]] = {}
TERMINALS: dict[str, tuple[str, int, str]] = {}
ADJACENCY: dict[str, dict[int, tuple[str, int]]] = {}
HEADING_NAMES: dict[int, str] = {}
TOWARD_SHELVES = WEST
TOWARD_FACTORIES = EAST
START_POSE = ("START", WEST)

# Cạnh line nối 2 node kề nhau: (node A, node B, chi phí phụ, ghi chú)
# Chi phí phụ > 0 = đoạn khó (line đứt) → bộ tìm đường tránh nếu có tuyến khác.
# KHÔNG khai báo = KHÔNG có line đi được giữa 2 node đó.
EDGES: list[tuple[str, str, int, str]] = [
    # --- Dọc cột kệ (C0): line liền mạch R0→R4, nhưng chỉ cắt ngang ở R2 ---
    ("C0R0", "C0R2", 0, "cột kệ R0↔R2"),
    ("C0R2", "C0R4", 0, "cột kệ R2↔R4"),
    # --- Dọc cột giữa (C1): đủ 5 hàng ---
    ("C1R0", "C1R1", 0, "cột giữa R0↔R1"),
    ("C1R1", "C1R2", 0, "cột giữa R1↔R2"),
    ("C1R2", "C1R3", 0, "cột giữa R2↔R3"),
    ("C1R3", "C1R4", 0, "cột giữa R3↔R4"),
    # --- Ngang ---
    ("C0R4", "C1R4", 0, "hàng R4 (Kệ 1 ↔ cột giữa)"),
    ("C0R0", "C1R0", config.EDGE_COST_START_GAP, "hàng R0 — ĐỨT ~245mm tại ô xuất phát"),
    # Hàng R2 (Kệ 2 ↔ cột giữa) KHÔNG có cạnh: line đứt ~560mm bởi vòng tròn
    # ROBOCON giữa sân. Robot phải đi vòng qua R4 hoặc R0.
]

# ============================================================
# Điểm cuối (terminal) — CUỐI đường line, không phải giao lộ
# ============================================================
# tên → (node gắn vào, hướng robot khi đứng tại đó, mô tả)
# Quy ước: "hướng" là hướng robot quay mặt khi ở điểm cuối (nhìn vào kệ/nhà máy).
#   - Từ node vào điểm cuối: lệnh ("advance",) — bám line tới hết line.
#   - Từ điểm cuối ra node: quay về hướng ngược lại rồi ("forward", 1).
#     (Sau retreat robot vẫn nằm giữa điểm cuối và node, chưa qua giao lộ.)

_FIXED_TERMINALS: dict[str, tuple[str, int, str]] = {
    "START":  ("C0R0", EAST,  "Ô xuất phát trên hàng R0"),
    "SHELF0": ("C0R0", WEST,  "Kệ 3 (R0 — cùng hàng ô xuất phát)"),
    "SHELF1": ("C0R2", WEST,  "Kệ 2 (R2)"),
    "SHELF2": ("C0R4", WEST,  "Kệ 1 (R4 — xa nhất)"),
    "LOOSE":  ("C1R0", SOUTH, "Kệ 4 — kho hàng rời (thụt ra ngoài R0)"),
}

# ============================================================
# THỨ TỰ NHÀ MÁY THEO HÀNG — KHÁC NHAU GIỮA 2 NỬA SÂN
# ============================================================
# Sa bàn chia đôi bởi BỨC TƯỜNG giữa sân. Hai nửa là bản QUAY 180° của nhau (robot
# mascot của đội đỏ vẽ lộn ngược — xem docs/Sa bàn đầy đủ.png), nên chiều trái/phải
# GIỮ NGUYÊN ở cả 2 nửa.
#
# NHƯNG các cụm nhà máy in trên TƯỜNG thì KHÔNG quay theo: hai đội nhìn chung một
# tấm panel, nên Samsung luôn ở một đầu tường và Foxconn ở đầu kia. Kết quả: xét
# trong hệ quy chiếu của chính robot, THỨ TỰ NHÀ MÁY BỊ ĐẢO NGƯỢC giữa 2 nửa:
#
#     Nửa có ô xuất phát cùng hàng FOXCONN   (đội xanh, góc dưới-trái):
#         R0=Foxconn  R1=Amkor  R2=Liên hợp  R3=Hana     R4=Samsung
#     Nửa có ô xuất phát cùng hàng SAMSUNG   (đội đỏ, góc trên-phải):
#         R0=Samsung  R1=Hana   R2=Liên hợp  R3=Amkor    R4=Foxconn
#
# ĐÂY mới là khác biệt thật giữa 2 nửa (không phải chiều xoay). Đặt sai = robot giao
# Samsung vào Foxconn và ngược lại — mất điểm mà robot vẫn báo "thành công".
#
# CÁCH KIỂM TRA TẠI SÂN (5 giây): đứng ở ô xuất phát nhìn thẳng sang tường giữa sân —
# cụm nhà máy NẰM CÙNG HÀNG với ô xuất phát là cụm nào? Đặt đúng tên đó vào
# config.FACTORY_AT_START_ROW.

# Hàng của từng nhà máy khi ô xuất phát cùng hàng Foxconn (nửa "xanh")
_FACTORY_ROW_BASE = {
    "foxconn": 0,
    "amkor": 1,
    "joint": 2,
    "hana_micron": 3,
    "samsung": 4,
}
FACTORY_AT_START_ROW_CHOICES = ("foxconn", "samsung")

# current_shelf (0=Kệ3, 1=Kệ2, 2=Kệ1) → terminal
SHELF_TERMINAL = {0: "SHELF0", 1: "SHELF1", 2: "SHELF2"}

# nhãn kiện hàng → terminal nhà máy
FACTORY_TERMINAL = {
    "foxconn": "F_foxconn",
    "amkor": "F_amkor",
    "hana_micron": "F_hana_micron",
    "samsung": "F_samsung",
}
JOINT_TERMINAL = "F_joint"
LOOSE_TERMINAL = "LOOSE"

# Giao lộ dùng để TỰ DÒ nửa sân: tại đây đường line dọc cột kệ chỉ chạy về MỘT phía
# (lên R2/R4), phía kia là mép sa bàn — xoay thử rồi đọc line là biết nửa nào.
PROBE_NODE = "C0R0"


# ============================================================
# Đồ thị dẫn xuất — dựng lại được khi đổi nửa sân
# ============================================================

def _direction(a: str, b: str) -> int:
    """Hướng đi từ node a sang node b (2 node phải kề nhau trên 1 trục)."""
    (ca, ra), (cb, rb) = NODES[a], NODES[b]
    if ca == cb:
        return NORTH if rb > ra else SOUTH
    if ra == rb:
        return EAST if cb > ca else WEST
    raise ValueError(f"Cạnh chéo không hợp lệ: {a} → {b}")


_NODE_TERMINALS: dict[str, list[str]] = {}


def set_board(mirrored: bool | None = None,
              factory_at_start_row: str | None = None) -> None:
    """Dựng lại toàn bộ bản đồ theo nửa sân đang thi đấu.

    Gọi được GIỮA LÚC CHẠY (sau khi robot tự dò) — mọi thứ phía sau (tìm đường,
    apply, tên hướng trong log) tự đúng theo, không chỗ nào phải nhớ "đang ở nửa nào".

    mirrored: chiều trái/phải có bị lật không (theo bản in thì KHÔNG, cả 2 nửa
        cùng chiều vì là bản quay 180° của nhau — giữ tham số này làm van an toàn).
    factory_at_start_row: cụm nhà máy nằm CÙNG HÀNG ô xuất phát — "foxconn" hoặc
        "samsung". Đây mới là khác biệt thật giữa 2 nửa.
    """
    global MIRRORED, FACTORY_AT_START_ROW, NODES, TERMINALS, ADJACENCY, HEADING_NAMES
    global TOWARD_SHELVES, TOWARD_FACTORIES, START_POSE, _NODE_TERMINALS

    if mirrored is not None:
        MIRRORED = bool(mirrored)
    if factory_at_start_row is not None:
        if factory_at_start_row not in FACTORY_AT_START_ROW_CHOICES:
            raise ValueError(
                f"factory_at_start_row phải là một trong {FACTORY_AT_START_ROW_CHOICES}, "
                f"nhận được {factory_at_start_row!r}")
        FACTORY_AT_START_ROW = factory_at_start_row

    def _col(col):
        return -col if MIRRORED else col

    def _head(heading):
        if not MIRRORED:
            return heading
        return {EAST: WEST, WEST: EAST}.get(heading, heading)

    # Nửa có Samsung cùng hàng ô xuất phát → thứ tự nhà máy đảo ngược (hàng r → 4-r)
    reversed_order = FACTORY_AT_START_ROW == "samsung"

    NODES = {name: (_col(col), row) for name, (col, row) in _CANONICAL_NODES.items()}

    TERMINALS = {name: (node, _head(heading), desc)
                 for name, (node, heading, desc) in _FIXED_TERMINALS.items()}
    for label, base_row in _FACTORY_ROW_BASE.items():
        row = (4 - base_row) if reversed_order else base_row
        name = JOINT_TERMINAL if label == "joint" else f"F_{label}"
        desc = ("Nhà máy liên hợp (NV2)" if label == "joint"
                else f"Nhà máy {label}")
        TERMINALS[name] = (f"C1R{row}", _head(EAST), f"{desc} — hàng R{row}")

    TOWARD_SHELVES = _head(WEST)
    TOWARD_FACTORIES = _head(EAST)
    HEADING_NAMES = {
        TOWARD_FACTORIES: "về phía nhà máy",
        TOWARD_SHELVES: "về phía kệ",
        NORTH: "lên phía R4/Samsung",
        SOUTH: "xuống phía R0/Foxconn",
    }
    # Robot đặt trong ô start, quay mặt về phía Kệ 3 (9h ở nửa chuẩn, 3h ở nửa gương
    # — cùng một tư thế "quay mặt về phía kệ")
    START_POSE = ("START", TOWARD_SHELVES)

    ADJACENCY = {n: {} for n in NODES}
    for a, b, extra, _note in EDGES:
        ADJACENCY[a][_direction(a, b)] = (b, extra)
        ADJACENCY[b][_direction(b, a)] = (a, extra)

    _NODE_TERMINALS = {}
    for name, (node, _h, _desc) in TERMINALS.items():
        _NODE_TERMINALS.setdefault(node, []).append(name)


def set_mirrored(mirrored: bool) -> None:
    """Chỉ đổi chiều trái/phải (giữ nguyên thứ tự nhà máy)."""
    set_board(mirrored=mirrored)


def set_factory_order(factory_at_start_row: str) -> None:
    """Chỉ đổi thứ tự nhà máy theo nửa sân (giữ nguyên chiều trái/phải)."""
    set_board(factory_at_start_row=factory_at_start_row)


set_board(mirrored=MIRRORED, factory_at_start_row=FACTORY_AT_START_ROW)


def pose_at(terminal: str) -> tuple[str, int]:
    """Trạng thái robot khi đã đứng tại điểm cuối `terminal`."""
    node, heading, _ = TERMINALS[terminal]
    return terminal, heading


def describe(pose: tuple[str, int]) -> str:
    place, heading = pose
    return f"{place} (quay {HEADING_NAMES.get(heading, '?')})"


def board_summary() -> str:
    """Mô tả bản đồ đang dùng — in ra log lúc khởi động để không bao giờ chạy nhầm
    nửa sân mà không ai biết."""
    order = " → ".join(
        f"R{row}:{label}"
        for label, row in sorted(
            ((lb, TERMINALS[JOINT_TERMINAL if lb == "joint" else f"F_{lb}"][0][-1])
             for lb in _FACTORY_ROW_BASE),
            key=lambda kv: kv[1]))
    return (
        "Bản đồ sa bàn: nhà máy cùng hàng ô xuất phát = %s | %s | %d giao lộ\n"
        "  Thứ tự nhà máy: %s"
        % (FACTORY_AT_START_ROW.upper(),
           "chiều trái/phải LẬT GƯƠNG" if MIRRORED else "chiều trái/phải chuẩn",
           len(NODES), order))


# ============================================================
# Tìm đường
# ============================================================

def _neighbours(place: str, heading: int, goal: str):
    """Sinh (chi phí, trạng thái mới, lệnh) từ trạng thái hiện tại."""
    # Xoay tại chỗ
    yield config.ROUTE_TURN_COST, (place, turn_left(heading)), ("left",)
    yield config.ROUTE_TURN_COST, (place, turn_right(heading)), ("right",)

    if place in NODES:
        # Đi tới node kề theo hướng đang quay
        step = ADJACENCY[place].get(heading)
        if step is not None:
            nb, extra = step
            yield 1 + extra, (nb, heading), ("forward", 1)
        # Vào điểm cuối — CHỈ khi đó là đích (không đi xuyên qua điểm cuối)
        for term in _NODE_TERMINALS.get(place, ()):
            if term == goal and TERMINALS[term][1] == heading:
                yield config.ADVANCE_COST, (term, heading), ("advance",)
    else:
        # Đang ở điểm cuối: ra được node bằng 2 cách
        node, term_heading, _ = TERMINALS[place]
        # 1) Đã quay đầu rồi thì tiến ra
        if heading == opposite(term_heading):
            yield 1, (node, heading), ("forward", 1)
        # 2) Còn đang quay mặt VÀO kệ/nhà máy thì LÙI ra, giữ nguyên hướng — bỏ được
        #    2 lần xoay khi chặng kế tiếp đi vuông góc (lên/xuống dọc cột). Bộ tìm
        #    đường tự cân nhắc: đi thẳng tiếp theo hướng cũ thì quay đầu vẫn rẻ hơn.
        if heading == term_heading:
            yield 1 + config.EDGE_COST_REVERSE, (node, heading), ("back", 1)


def _search(pose: tuple[str, int], goal: str):
    """Dijkstra trên trạng thái (vị trí, hướng). Trả (chi phí, danh sách lệnh) hoặc None."""
    if goal not in NODES and goal not in TERMINALS:
        raise KeyError(f"Đích không có trên bản đồ: {goal}")

    start = tuple(pose)
    best = {start: 0}
    prev: dict[tuple, tuple] = {}
    queue = [(0, start)]

    # Tới điểm cuối là phải QUAY MẶT vào nó (vào kệ để nâng, vào nhà máy để thả).
    # Nếu chỉ xét vị trí, trường hợp "đang ở sẵn điểm cuối nhưng sai hướng" (ví dụ
    # route trước hỏng ngay sau lúc quay đầu) sẽ trả route rỗng và robot tưởng mình
    # đang quay mặt vào kệ trong khi thực tế quay ra ngoài.
    goal_heading = TERMINALS[goal][1] if goal in TERMINALS else None

    def _reached(state):
        return state[0] == goal and (goal_heading is None or state[1] == goal_heading)

    while queue:
        cost, state = heapq.heappop(queue)
        if cost > best.get(state, float("inf")):
            continue
        if _reached(state):
            # Dựng lại chuỗi lệnh
            steps = []
            cur = state
            while cur in prev:
                cur, cmd = prev[cur]
                steps.append(cmd)
            steps.reverse()
            return cost, steps
        for step_cost, nxt, cmd in _neighbours(state[0], state[1], goal):
            new_cost = cost + step_cost
            if new_cost < best.get(nxt, float("inf")):
                best[nxt] = new_cost
                prev[nxt] = (state, cmd)
                heapq.heappush(queue, (new_cost, nxt))
    return None


def _compress(steps: list) -> list:
    """Gộp các bước ("forward", 1) liên tiếp thành ("forward", N)."""
    out: list = []
    for cmd in steps:
        if cmd[0] == "forward" and out and out[-1][0] == "forward":
            out[-1] = ("forward", out[-1][1] + cmd[1])
        else:
            out.append(cmd)
    return out


def plan(pose: tuple[str, int], goal: str) -> tuple[list, tuple[str, int]] | tuple[None, tuple[str, int]]:
    """
    Sinh route từ trạng thái `pose` đến `goal` (tên terminal hoặc node).

    Trả về (route, pose_mới). Route RỖNG nghĩa là robot đã ở sẵn đích (hợp lệ —
    ví dụ lấy tầng 2 cùng kệ). Trả (None, pose) nếu không có đường đi.
    """
    found = _search(pose, goal)
    if found is None:
        return None, tuple(pose)
    _cost, steps = found
    route = _compress(steps)
    if goal in TERMINALS:
        new_pose = pose_at(goal)
    else:
        # Đích là node: hướng cuối cùng = hướng sau khi chạy hết route
        heading = pose[1]
        for cmd in route:
            if cmd[0] == "left":
                heading = turn_left(heading)
            elif cmd[0] == "right":
                heading = turn_right(heading)
        new_pose = (goal, heading)
    return route, new_pose


def apply(pose: tuple[str, int], route: list) -> tuple[str, int]:
    """
    Chạy `route` trên bản đồ (không có robot) → trạng thái mới.

    Dùng để cập nhật vị trí khi route chỉ chạy được MỘT PHẦN (mất line giữa chừng):
    Motion.execute_route ghi lại các bước đã hoàn thành, main áp vào đây để biết robot
    thật sự đang ở đâu, thay vì đoán bừa là đã tới đích.

    Gặp bước không hợp lệ (bản đồ không có line đó) → dừng lại, trả trạng thái cuối
    cùng còn hợp lệ.
    """
    place, heading = pose
    for cmd in route:
        if cmd[0] == "left":
            heading = turn_left(heading)
        elif cmd[0] == "right":
            heading = turn_right(heading)
        elif cmd[0] == "forward":
            for _ in range(cmd[1]):
                if place in TERMINALS:
                    node, term_heading, _ = TERMINALS[place]
                    if heading != opposite(term_heading):
                        return place, heading
                    place = node
                    continue
                step = ADJACENCY.get(place, {}).get(heading)
                if step is None:
                    return place, heading
                place = step[0]
        elif cmd[0] == "back":
            # Chỉ dùng để RÚT khỏi điểm cuối, vẫn quay mặt vào kệ/nhà máy
            for _ in range(cmd[1]):
                if place not in TERMINALS:
                    return place, heading
                node, term_heading, _ = TERMINALS[place]
                if heading != term_heading:
                    return place, heading
                place = node
        elif cmd[0] == "advance":
            terms = [t for t, (n, h, _) in TERMINALS.items()
                     if n == place and h == heading]
            if not terms:
                return place, heading
            place = terms[0]
    return place, heading


def route_cost(pose: tuple[str, int], goal: str) -> int:
    """Chi phí ước lượng (số giao lộ quy đổi) — dùng để so sánh thứ tự giao hàng."""
    found = _search(pose, goal)
    if found is None:
        return 10 ** 6      # không tới được → phạt nặng để không bao giờ được chọn
    return found[0]


def route_to_text(route: list) -> str:
    """Chuỗi route dễ đọc cho log/test."""
    if not route:
        return "(đã ở đích)"
    parts = []
    for cmd in route:
        if cmd[0] == "forward":
            parts.append(f"tiến {cmd[1]} giao lộ")
        elif cmd[0] == "back":
            parts.append(f"LÙI {cmd[1]} giao lộ")
        elif cmd[0] == "left":
            parts.append("xoay trái")
        elif cmd[0] == "right":
            parts.append("xoay phải")
        elif cmd[0] == "advance":
            parts.append("bám line tới hết line")
        else:
            parts.append(str(cmd))
    return " → ".join(parts)
