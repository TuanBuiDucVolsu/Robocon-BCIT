"""
Cấu hình toàn bộ hằng số có thể tinh chỉnh cho robot tự động Bảng O2.
Đội cần đo thực nghiệm và cập nhật các giá trị này.
"""

import os

# ============================================================
# GPIO PIN MAP
# ============================================================

# --- Động cơ di chuyển ---
# Cụm xe trái
IN1_XE_T = 17  # Tiến trái
IN2_XE_T = 27  # Lùi trái

# Cụm xe phải (có PWM chống lệch tốc độ)
IN1_XE_P = 23  # Tiến phải (PWM)
IN2_XE_P = 22  # Lùi phải

# --- Cơ cấu nâng (cẩu) ---
# Cẩu PHẢI (vật lý): mạch 2 chân (không có ENA)
IN3_CAU_T = 25  # Nâng phải
IN4_CAU_T = 24  # Hạ phải

# Cẩu TRÁI (vật lý): mạch có ENA bật/tắt
ENA_CAU_P = 5   # Enable cẩu trái
IN1_CAU_P = 13  # Nâng trái
IN2_CAU_P = 6   # Hạ trái

# --- Nút khởi động ---
START_BUTTON_PIN = 16  # Nút vật lý kích hoạt chế độ tự động

# --- MCP3008 ADC (SPI) — đọc QTR-8A + 2 IR pallet ---
# MCP3008 dùng SPI: GPIO 8(CE0), 9(MISO), 10(MOSI), 11(SCLK)
# CH0-5: QTR-8A 6 mắt dò line (analog 0-1023)
# CH6: IR pallet trái, CH7: IR pallet phải
MCP3008_SPI_PORT = 0         # SPI0
MCP3008_CS = 0               # CE0 (GPIO 8)
PALLET_LEFT_CHANNEL = 6      # Kênh MCP3008 cho IR càng trái
PALLET_RIGHT_CHANNEL = 7     # Kênh MCP3008 cho IR càng phải
PALLET_THRESHOLD = 500       # Ngưỡng analog: < 500 = có pallet, >= 500 = không có

# --- Cảm biến siêu âm HC-SR04 (đo khoảng cách phía trước) ---
ULTRASONIC_TRIG_PIN = 19     # Trigger
ULTRASONIC_ECHO_PIN = 20     # Echo
APPROACH_DISTANCE = 4.0      # Khoảng cách dừng trước kệ (cm) — đội đo thực tế
APPROACH_SPEED = 30          # Tốc độ lùi khỏi kệ (retreat) + fallback (0-100)
APPROACH_TIMEOUT = 5.0       # Timeout nếu không thấy kệ (giây)
RETREAT_DISTANCE = 15.0      # Khoảng cách lùi ra sau khi nâng/hạ (cm)

# Tiếp cận kệ 2 pha (nhanh ở xa → chậm ở gần để dừng chính xác)
APPROACH_FAST_SPEED = 60     # Tốc độ pha xa (nhanh)
APPROACH_SLOW_SPEED = 25     # Tốc độ pha gần (chính xác, dừng đúng vị trí)
APPROACH_SLOW_DISTANCE = 10  # cm — khi khoảng cách ≤ giá trị này thì chuyển sang chậm

# --- Cảm biến dò line QTR-8A (analog, qua MCP3008 SPI) ---
# Dùng 6 mắt (CH0-CH5), bỏ 2 mắt ngoài cùng để dành CH6-7 cho IR pallet

# ============================================================
# AUDIT GPIO - TỔNG SỐ CHÂN SỬ DỤNG
# ============================================================
# Động cơ xe:      4 chân (IN1_XE_T, IN2_XE_T, IN1_XE_P, IN2_XE_P)
# Động cơ cẩu:     5 chân (IN3_CAU_T, IN4_CAU_T, ENA_CAU_P, IN1_CAU_P, IN2_CAU_P)
# Nút khởi động:   1 chân (START_BUTTON_PIN)
# Siêu âm HC-SR04: 2 chân (TRIG, ECHO)
# MCP3008 SPI:     4 chân (CE0, MISO, MOSI, SCLK) — line sensor + IR pallet
# Camera:          CSI-2 (không dùng GPIO)
# ----------------------------------------------------------
# TỔNG:           16 chân GPIO  (giới hạn thể lệ: 16 chân) — vừa đúng

# ============================================================
# AUDIT ĐỘNG CƠ
# ============================================================
# Động cơ xe trái:  1
# Động cơ xe phải:  1
# Động cơ cẩu trái: 1
# Động cơ cẩu phải: 1
# ----------------------------------------------------------
# TỔNG:             4 động cơ  (giới hạn thể lệ: 12 động cơ)

# ============================================================
# ĐỘNG CƠ - TỐC ĐỘ & PWM
# ============================================================
PWM_FREQUENCY = 100          # Hz
SPEED_DEFAULT = 70           # Duty cycle % mặc định (0-100)
SPEED_SLOW = 40              # Tốc độ chậm (căn chỉnh, đặt hàng)
SPEED_TURN = 55              # Tốc độ khi xoay
PWM_COMPENSATION = 0.95      # Hệ số bù lệch tốc độ bánh phải (< 1.0 nếu phải nhanh hơn)

# ============================================================
# CƠ CẤU NÂNG - THỜI GIAN (giây)
# ============================================================
LIFT_TIME_FLOOR = 0.0        # Thời gian hạ xuống mặt sàn (gốc 0)
LIFT_TIME_SHELF_1 = 0.150      # Thời gian nâng lên tầng 1 kệ (cơ sở)
LIFT_TIME_SHELF_2 = 1.5      # Thời gian nâng lên tầng 2 kệ (cơ sở)

# Bù sai lệch khi NÂNG (giây thêm/bớt — dương=chạy lâu hơn, âm=dừng sớm hơn)
LIFT_LEFT_EXTRA  = -0.050    # Bù cẩu TRÁI khi nâng
LIFT_RIGHT_EXTRA = 0.0       # Bù cẩu PHẢI khi nâng

# Bù riêng khi HẠ (nếu 1 bên khó hạ do ma sát cơ khí → tăng giá trị bên đó)
LIFT_LEFT_LOWER_EXTRA  = 0.300  # Bù cẩu TRÁI khi hạ
LIFT_RIGHT_LOWER_EXTRA = 0.0  # Bù cẩu PHẢI khi hạ

LIFT_SPEED = 80              # Duty cycle động cơ nâng (0-100) — dùng trong debug UI
PICKUP_MAX_RETRIES = 2       # Số lần thử nâng lại nếu cảm biến không thấy pallet
PICKUP_VERIFY_DELAY = 0.3    # Thời gian chờ sau nâng trước khi kiểm tra cảm biến (giây)

# ============================================================
# LINE FOLLOWING (QTR-8A analog qua MCP3008)
# ============================================================
LINE_SENSOR_COUNT = 6        # Dùng 6 mắt (CH0-CH5), bỏ 2 mắt ngoài cùng
LINE_THRESHOLD = 500         # Ngưỡng analog: < 500 = trên line (đen), >= 500 = ngoài line (trắng)
# ⚠️ POLARITY QTR-8A: code giả định "line đen = giá trị THẤP".
# Nhiều module QTR-8A lại đọc bề mặt ĐEN ra giá trị CAO (ngược lại).
# Calibrate: chạy `python3 -m tools.calibrate_line` (hoặc xem ADC trong web debug),
# đặt mắt lên line đen vs nền sáng. Nếu LINE ĐEN cho giá trị LỚN → đặt True.
# Đặt True sẽ tự đảo tín hiệu ngay tại nguồn → KHÔNG cần sửa gì khác.
LINE_BLACK_IS_HIGH = True
# Trọng số vị trí 6 mắt (lệch trái âm, lệch phải dương)
LINE_WEIGHTS = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]
LINE_KP = 15.0               # Hệ số P (PD control)
LINE_KD = 5.0                # Hệ số D
INTERSECTION_THRESHOLD = 5   # Số mắt phát hiện line đồng thời để nhận là giao lộ (5/6)

# ============================================================
# CAMERA & NHẬN DIỆN MÀU HSV
# ============================================================
CAMERA_RESOLUTION = (640, 480)
CONFIDENCE_THRESHOLD = 0.20  # Tỷ lệ pixel tối thiểu để nhận là đúng (0.0-1.0)
MAX_SCAN_RETRIES = 3         # Số lần quét lại mỗi lượt quét nếu confidence thấp
MAX_PAIR_SCAN_ATTEMPTS = 2   # Số lần quét lại cả cặp kiện sau khi tiếp cận kệ
SCAN_RETRY_DELAY = 0.1       # Thời gian chờ giữa các lần quét lại (giây)

LABEL_TO_FACTORY = {
    "samsung": "Samsung",
    "foxconn": "Foxconn",
    "amkor": "Amkor",
    "hana_micron": "Hana Micron Vina",
}

# --- Chiến lược phân loại ---
# Amkor là khối XÁM (vô sắc) → nền trắng/xám của kiện khác dễ lọt vào dải xám.
# Vì vậy ƯU TIÊN màu sắc nét (Samsung/Foxconn/Hana): nếu có màu chromatic đạt
# ngưỡng thì chọn nó, KỂ CẢ khi Amkor (nền) đếm được nhiều pixel hơn. Chỉ rơi về
# Amkor khi không màu nào đạt ngưỡng. Sửa lỗi "Amkor ăn mất Samsung/Hana".
CHROMATIC_LABELS = ("samsung", "foxconn", "hana_micron")
ACHROMATIC_LABEL = "amkor"
# Tỉ lệ cắt mỗi cạnh khi lấy vùng giữa ROI. Hana có ngoặc đỏ ở GÓC → nếu test thấy
# Hana hay bị nhầm Amkor, giảm giá trị này (vd 0.12) để giữ lại góc đỏ.
ROI_MARGIN = 0.2

# Dải màu HSV cho từng kiện hàng (OpenCV: H=0-179, S=0-255, V=0-255)
# Mỗi label có danh sách [(lower, upper), ...] — nhiều dải nếu màu wrap qua 0
# Đội cần chỉnh ngưỡng theo điều kiện ánh sáng thực tế trên sa bàn
COLOR_RANGES = {
    # Kiện 01 — Samsung: chip XANH DƯƠNG trên nền trắng
    "samsung": [
        ([90, 60, 40], [130, 255, 255]),
    ],
    # Kiện 02 — Foxconn: chip VÀNG đồng
    "foxconn": [
        ([15, 60, 80], [40, 255, 255]),
    ],
    # Kiện 03 — Amkor: khối nhôm XÁM BẠC (saturation thấp, value trung bình)
    "amkor": [
        ([0, 0, 100], [179, 40, 200]),
    ],
    # Kiện 04 — Hana Micron: QR code viền ĐỎ/HỒNG (đỏ wrap qua 0)
    "hana_micron": [
        ([0, 60, 60], [10, 255, 255]),     # đỏ phía dưới
        ([160, 60, 60], [179, 255, 255]),   # đỏ phía trên
    ],
}

# ============================================================
# BỐ TRÍ KỆ HÀNG (theo tài liệu thi công Bảng O2)
# ============================================================
# Kho hải quan: 4 giá kệ, mỗi kệ 240x120x240mm, 2 tầng, mỗi tầng 2 pallet
# Kệ 1-3: mỗi kệ 4 pallet (2 tầng × 2) = 12 pallet
# Kệ 4: chỉ có 1 pallet kho hàng rời (4 khối khác loại) → Nhiệm vụ 2
# Pallet: 90x90x26mm — 2 pallet cạnh nhau vừa đúng 1 lần nâng
SHELVES_TASK1 = 3            # Số kệ kho hải quan (NV1): kệ 0–2
TOTAL_PACKAGES_TASK1 = 12    # Tổng kiện hàng NV1 (3 kệ × 2 tầng × 2 pallet)
PICKUPS_TASK1 = 6            # Số lần nâng (12 ÷ 2)
MAX_TIER_RETRIES = 1         # Số lần thử lại tầng kệ trước khi bỏ qua
ROUTE_TURN_COST = 2          # Mỗi lần xoay 90° = N giao lộ forward khi so sánh route

# ============================================================
# XUẤT PHÁT — TÌM LINE ĐẦU TIÊN
# ============================================================
# Ô start 400x400mm không có line (GAP trên R0) → tiến thẳng ra chạm line
# Robot đặt QUAY MẶT SANG TRÁI (hướng 9h, về Kệ 3) — xem sơ đồ ROUTE bên dưới
# exit_start_zone(): chỉ tìm line; ROUTE_START_TO_SHELF_0 đếm giao lộ
EXIT_START_SPEED = 50        # Tốc độ tiến ra khỏi ô start (0-100)
EXIT_START_TIMEOUT = 5.0     # Timeout nếu không tìm thấy line (giây)
EXIT_START_ALIGN_TIME = 0.4  # Giây bám line ngắn sau khi chạm line (căn giữa)

# ============================================================
# STATE MACHINE - THỜI GIAN & ĐIỀU HƯỚNG
# ============================================================
MATCH_DURATION = 240         # Tổng thời gian trận đấu (giây)
SAFETY_MARGIN = 10           # Dừng lại trước khi hết giờ (giây)
TURN_TIME = 0.6              # Thời gian xoay 90° (giây) — đội đo thực tế
# File lưu mốc bắt đầu trận: nếu robot lỗi (exception) → thoát mã 1 → systemd restart
# → đọc lại file này để chạy NỐT thời gian còn lại (không reset 240s). Xoá khi xong sạch.
# Ở /tmp nên tự mất sau reboot (trận cũ không "ám" trận mới).
MATCH_STATE_FILE = "/tmp/robot_match_state"

# ============================================================
# NAVIGATION ROUTES (bản đồ sa bàn phía xanh)
# ============================================================
# Mỗi route = danh sách lệnh: ("forward", N) hoặc ("left") hoặc ("right")
# "forward" = bám line qua N giao lộ, "left"/"right" = xoay 90° tại giao lộ
#
# Bố trí sa bàn (phía xanh) — nhìn từ trên xuống:
#
#   Col0(kệ/trái)  Col1(giữa)   Col2(nhà máy/phải)
#     │               │              │
#  R4 [Kệ1]──────────┼──[Samsung]───┤   ← Kệ 1 thẳng Samsung
#     │               │              │
#  R3 │               │──[Hana M.]───┤
#     │       ◉       │              │
#  R2 [Kệ2]──────────┼──[Liên hợp]──┤   ← Kệ 2 thẳng vòng tròn / Liên hợp
#     │               │              │
#  R1 │               │──[Amkor]─────┤
#     │               │              │
#  R0 [Kệ3]──line──┃GAP┃──line──[Foxconn]  ← Line R0 đứt quãng tại ô start
#     │             ┃   ┃              │
#     │          ←■Start┃              │   Robot đặt hướng 9h (quay trái, về Kệ 3)
#     │             [Kệ4]             │   Kệ 4 thụt xuống, bên phải Start
#
# Kệ 1-3: cạnh TRÁI, cách nhau 2 hàng (R4, R2, R0)
# Kệ 4:   bên PHẢI ô start, cạnh Foxconn (kho hàng rời — NV2)
# Nhà máy: cạnh PHẢI (Samsung R4 / Hana R3 / Liên hợp R2 / Amkor R1 / Foxconn R0)
# Robot đặt trong ô start quay mặt SANG TRÁI (hướng 9h, về phía Kệ 3)
# exit_start_zone() tiến thẳng → chạm line R0 → căn line
# ROUTE_START_TO_SHELF_0 ("forward", 1) bám line sang trái → 1 giao lộ → Kệ 3
#
# ✅ ĐÃ ĐỐI CHIẾU với file in sa bàn chuẩn O2 (Hiflex 4x2m, Google Drive thể lệ).
#    Lưới đo được (toạ độ % theo nửa sân):
#      - 3 cột dọc:  C0 kệ (x≈12.5%), C1 trung chuyển (x≈37.5%), C2 sống giữa/nhà máy (x≈50%)
#      - 5 hàng ngang: R4(y≈17%) R3(33%) R2(50%) R1(67%) R0(83%); 2 hàng kề nhau = 1 giao lộ
#      - Kệ chỉ ở R4/R2/R0 trên C0; nhà máy ở cả 5 hàng trên C2; Kệ4 ở C1 ngay dưới R0
#    → Toàn bộ số ("forward", N) bên dưới đã được xác nhận khớp lưới chuẩn.
#    Xem sơ đồ: docs/sa_ban.png. (Vẫn cần calibrate TIMING:
#    TURN_TIME, line PD, ngưỡng cảm biến — không phải số giao lộ.)

# Từ xuất phát → Kệ 3 (robot đã quay mặt sang trái)
# ✅ Verified: start ở ~x24% (giữa C0 và C1) trên hàng R0; Kệ3 ở C0/R0.
#    Đi sang trái dọc R0 → 1 giao lộ (node C0) → Kệ 3.
ROUTE_START_TO_SHELF_0 = [
    ("forward", 1),    # Tiến thẳng đến Kệ 3 (đã hướng đúng)
]

# Giữa các kệ (dọc cạnh trái, cách nhau 2 hàng: R0→R2→R4)
ROUTE_BETWEEN_SHELVES = [
    ("forward", 2),    # Kệ cách nhau 2 giao lộ
]

# Từ kệ → từng nhà máy
# Robot đang quay mặt vào kệ (hướng trái)
# Kệ 3 ở R0, Kệ 2 ở R2, Kệ 1 ở R4
# Nhà máy ở cùng hàng → chỉ cần đi ngang sang phải
ROUTE_SHELF_TO_FACTORY = {
    # Samsung ở R4, cùng hàng Kệ 1 → đi ngang
    "samsung": [
        ("right",),        # Quay ra (hướng lên)
        ("right",),        # Rẽ phải (hướng sang phải)
        ("forward", 2),    # Đi ngang đến Samsung
    ],
    # Hana ở R3, giữa Kệ 1 (R4) và Kệ 2 (R2)
    "hana_micron": [
        ("right",),        # Quay ra
        ("right",),        # Hướng sang phải
        ("forward", 2),    # Đi ngang đến cột nhà máy
        ("right",),        # Rẽ phải (hướng xuống)
        ("forward", 1),    # Xuống 1 đến Hana (R3)
    ],
    # Amkor ở R1, giữa Kệ 2 (R2) và Kệ 3 (R0)
    "amkor": [
        ("right",),
        ("right",),
        ("forward", 2),
        ("right",),
        ("forward", 1),    # Xuống 1 đến Amkor (R1)
    ],
    # Foxconn ở R0, cùng hàng Kệ 3 → đi ngang
    "foxconn": [
        ("right",),        # Quay ra
        ("right",),        # Hướng sang phải
        ("forward", 2),    # Đi ngang đến Foxconn
    ],
}

# Từ nhà máy → quay về khu kệ (đoạn cơ bản: nhà máy → cột kệ cùng hàng)
# Dùng get_return_route() để ghép thêm đoạn dọc đúng hàng kệ đích.
ROUTE_FACTORY_TO_SHELF = {
    "samsung": [
        ("left",),         # Quay ra từ Samsung (hướng sang trái)
        ("forward", 2),    # Đi ngang về cột kệ
    ],
    "hana_micron": [
        ("left",),
        ("forward", 1),    # Đi lên R4 hoặc xuống R2
        ("left",),
        ("forward", 2),    # Đi ngang về cột kệ
    ],
    "amkor": [
        ("right",),
        ("forward", 1),    # Đi xuống R0 hoặc lên R2
        ("right",),
        ("forward", 2),    # Đi ngang về cột kệ
    ],
    "foxconn": [
        ("left",),         # Quay ra (hướng sang trái)
        ("forward", 2),    # Đi ngang về cột kệ
    ],
}

# Hàng R trên sa bàn (0=R0 … 4=R4) — dùng cho route quay về đúng kệ
FACTORY_BOARD_ROW = {
    "samsung": 4,
    "hana_micron": 3,
    "amkor": 1,
    "foxconn": 0,
}

# current_shelf (0=Kệ3, 1=Kệ2, 2=Kệ1) → hàng R
SHELF_BOARD_ROW = {
    0: 0,
    1: 2,
    2: 4,
}


def _vertical_on_shelf_column(from_row: int, to_row: int) -> list:
    """Dọc cột kệ trái giữa 2 hàng. Số giao lộ = |to_row-from_row| (đã verify:
    2 hàng kề nhau = 1 giao lộ trên lưới chuẩn). Vẫn cần kiểm hướng quay thực tế."""
    if from_row == to_row:
        return []
    count = abs(to_row - from_row)
    if to_row < from_row:
        # Xuống hàng thấp hơn (vd. R4→R0)
        return [("right",), ("forward", count), ("left",)]
    # Lên hàng cao hơn (vd. R0→R4)
    return [("left",), ("forward", count), ("right",)]


def get_return_route(from_factory: str, target_shelf: int) -> list:
    """
    Route từ nhà máy vừa giao → cột kệ đúng hàng pickup tiếp theo.
    target_shelf: index kệ sau _advance_position() (0=Kệ3/R0, 1=Kệ2/R2, 2=Kệ1/R4).
    """
    base = list(ROUTE_FACTORY_TO_SHELF.get(from_factory, []))
    from_row = FACTORY_BOARD_ROW.get(from_factory)
    to_row = SHELF_BOARD_ROW.get(target_shelf)
    if from_row is None or to_row is None:
        return base
    return base + _vertical_on_shelf_column(from_row, to_row)

# Giữa 2 nhà máy (giao kiện 2 liên tiếp)
# Các nhà máy xếp dọc: Samsung(R4) - Hana(R3) - Liên hợp(R2) - Amkor(R1) - Foxconn(R0)
# Đi xuống = forward, đi lên = quay đầu + forward
ROUTE_BETWEEN_FACTORIES = {
    ("samsung", "hana_micron"):   [("forward", 1)],
    ("samsung", "amkor"):         [("forward", 3)],
    ("samsung", "foxconn"):       [("forward", 4)],
    ("hana_micron", "samsung"):   [("right",), ("right",), ("forward", 1)],
    ("hana_micron", "amkor"):     [("forward", 2)],
    ("hana_micron", "foxconn"):   [("forward", 3)],
    ("amkor", "foxconn"):         [("forward", 1)],
    ("amkor", "hana_micron"):     [("right",), ("right",), ("forward", 2)],
    ("amkor", "samsung"):         [("right",), ("right",), ("forward", 3)],
    ("foxconn", "amkor"):         [("right",), ("right",), ("forward", 1)],
    ("foxconn", "hana_micron"):   [("right",), ("right",), ("forward", 2)],
    ("foxconn", "samsung"):       [("right",), ("right",), ("forward", 4)],
}

# Từ nhà máy cuối → Kệ 4 (thụt xuống dưới R0, bên phải start)
# Robot phải đi xuống R0 rồi xuống thêm 1 giao lộ nữa đến Kệ 4
ROUTE_FACTORY_TO_LOOSE = {
    "samsung": [
        ("forward", 4),             # R4 xuống R0
        ("forward", 1),             # Xuống thêm 1 đến hàng Kệ 4
        ("left",),                  # Rẽ trái đến Kệ 4
        ("forward", 1),
    ],
    "hana_micron": [
        ("forward", 3),             # R3 xuống R0
        ("forward", 1),
        ("left",),
        ("forward", 1),
    ],
    "amkor": [
        ("forward", 1),             # R1 xuống R0
        ("forward", 1),
        ("left",),
        ("forward", 1),
    ],
    "foxconn": [
        ("forward", 1),             # R0 xuống 1 đến hàng Kệ 4
        ("left",),
        ("forward", 1),
    ],
}

# Từ Kệ 4 (thụt dưới R0) → nhà máy liên hợp (R2)
ROUTE_LOOSE_TO_JOINT = [
    ("right",),         # Quay ra
    ("forward", 1),     # Đến cột nhà máy
    ("left",),          # Rẽ trái (hướng lên)
    ("forward", 3),     # Lên 3 giao lộ: dưới R0 → R0 → R1 → R2 (liên hợp)
]

# ============================================================
# LOGGING & DEBUG
# ============================================================
LOG_FILE = "robot_log.txt"
DEBUG_MODE = True           # True = bật giao diện web để luyện tập; False = chế độ thi đấu
# systemd/scripts/start.sh đặt ROBOT_COMPETE=1 → luôn chạy state machine dù DEBUG_MODE=True
if os.environ.get("ROBOT_COMPETE") == "1":
    DEBUG_MODE = False
WEB_PORT = 5000               # Port cho giao diện web debug
