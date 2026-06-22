"""
Cấu hình toàn bộ hằng số có thể tinh chỉnh cho robot tự động Bảng O2.
Đội cần đo thực nghiệm và cập nhật các giá trị này.
"""

# ============================================================
# GPIO PIN MAP
# ============================================================

# --- Động cơ di chuyển ---
# Cụm xe trái
IN1_XE_T = 17  # Tiến trái
IN2_XE_T = 27  # Lùi trái

# Cụm xe phải (có PWM chống lệch tốc độ)
IN1_XE_P = 22  # Tiến phải (PWM)
IN2_XE_P = 23  # Lùi phải

# --- Cơ cấu nâng (cẩu) ---
# Cụm cẩu trái
IN3_CAU_T = 24  # Nâng trái
IN4_CAU_T = 25  # Hạ trái

# Cụm cẩu phải (có ENA bật/tắt)
ENA_CAU_P = 5   # Enable cẩu phải
IN1_CAU_P = 6   # Nâng phải
IN2_CAU_P = 13  # Hạ phải

# --- Nút khởi động ---
START_BUTTON_PIN = 16  # Nút vật lý kích hoạt chế độ tự động

# --- Cảm biến dò line 8 mắt (I2C) ---
# Nếu dùng module I2C (VD: TCA9548A / PCF8574), chỉ cần 2 chân:
LINE_SENSOR_SDA = 2   # I2C SDA (GPIO2)
LINE_SENSOR_SCL = 3   # I2C SCL (GPIO3)
LINE_SENSOR_I2C_ADDR = 0x20  # Địa chỉ I2C của module dò line

# Nếu dùng digital trực tiếp (8 chân), bỏ comment và dùng list này:
# LINE_SENSOR_PINS = [4, 14, 15, 18, 7, 8, 11, 9]

# ============================================================
# AUDIT GPIO - TỔNG SỐ CHÂN SỬ DỤNG
# ============================================================
# Động cơ xe:      4 chân (IN1_XE_T, IN2_XE_T, IN1_XE_P, IN2_XE_P)
# Động cơ cẩu:     5 chân (IN3_CAU_T, IN4_CAU_T, ENA_CAU_P, IN1_CAU_P, IN2_CAU_P)
# Nút khởi động:   1 chân (START_BUTTON_PIN)
# Line sensor I2C: 2 chân (SDA, SCL)
# Camera:          CSI-2 (không dùng GPIO)
# ----------------------------------------------------------
# TỔNG:           12 chân GPIO  (giới hạn thể lệ: 16 chân)

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
LIFT_TIME_SHELF_1 = 0.8      # Thời gian nâng lên tầng 1 kệ
LIFT_TIME_SHELF_2 = 1.5      # Thời gian nâng lên tầng 2 kệ
LIFT_SPEED = 80              # Duty cycle động cơ nâng (0-100)
DROP_SPEED = 50              # Duty cycle khi hạ (chậm hơn để tránh đổ)

# ============================================================
# LINE FOLLOWING
# ============================================================
LINE_SENSOR_COUNT = 8
# Trọng số vị trí từng mắt cảm biến (mắt giữa = 0, lệch trái âm, lệch phải dương)
LINE_WEIGHTS = [-3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5]
LINE_KP = 15.0               # Hệ số P (PID đơn giản)
LINE_KD = 5.0                # Hệ số D
INTERSECTION_THRESHOLD = 6   # Số mắt phát hiện line đồng thời để nhận là giao lộ

# ============================================================
# CAMERA & NHẬN DIỆN MÀU HSV
# ============================================================
CAMERA_RESOLUTION = (320, 320)
CONFIDENCE_THRESHOLD = 0.15  # Tỷ lệ pixel tối thiểu để nhận là đúng (0.0-1.0)
MAX_SCAN_RETRIES = 3         # Số lần quét lại nếu confidence thấp

LABEL_TO_FACTORY = {
    "samsung": "Samsung",
    "foxconn": "Foxconn",
    "amkor": "Amkor",
    "hana_micron": "Hana Micron Vina",
}

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
    # Kiện 03 — Amkor: khối nhôm XÁM BẠC (saturation thấp)
    "amkor": [
        ([0, 0, 80], [179, 50, 220]),
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
# Kho hải quan: 3 giá kệ, mỗi kệ 240x120x240mm, 2 tầng, mỗi tầng 2 pallet
# Kho hàng rời: 1 giá kệ riêng, 1 pallet (4 khối khác loại)
# Pallet: 90x90x26mm — 2 pallet cạnh nhau vừa đúng 1 lần nâng
SHELVES_COUNT = 3            # Số giá kệ trong kho hải quan
TIERS_PER_SHELF = 2          # Số tầng mỗi kệ
PALLETS_PER_TIER = 2         # Số pallet mỗi tầng (nâng cùng lúc)
TOTAL_PACKAGES_TASK1 = 12    # Tổng kiện hàng nhiệm vụ 1 (3 kệ × 2 tầng × 2 pallet)
PICKUPS_TASK1 = 6            # Số lần nâng (12 ÷ 2)

# ============================================================
# STATE MACHINE - THỜI GIAN & ĐIỀU HƯỚNG
# ============================================================
MATCH_DURATION = 240         # Tổng thời gian trận đấu (giây)
SAFETY_MARGIN = 10           # Dừng lại trước khi hết giờ (giây)

# Số giao lộ cần vượt qua để đến từng vị trí (đội cần đo thực tế trên sa bàn)
NAV_START_TO_SHELF_0 = 2         # Từ xuất phát -> kệ đầu tiên
NAV_BETWEEN_SHELVES = 1          # Khoảng cách giữa 2 kệ liên tiếp
NAV_WAREHOUSE_TO_SAMSUNG = 3
NAV_WAREHOUSE_TO_FOXCONN = 4
NAV_WAREHOUSE_TO_AMKOR = 5
NAV_WAREHOUSE_TO_HANA = 6
NAV_FACTORY_TO_WAREHOUSE = 3     # Từ nhà máy quay về kho
NAV_WAREHOUSE_TO_LOOSE = 2       # Từ kho hải quan -> kho hàng rời
NAV_LOOSE_TO_JOINT_FACTORY = 4   # Từ kho hàng rời -> nhà máy liên hợp

FACTORY_NAV_MAP = {
    "samsung": NAV_WAREHOUSE_TO_SAMSUNG,
    "foxconn": NAV_WAREHOUSE_TO_FOXCONN,
    "amkor": NAV_WAREHOUSE_TO_AMKOR,
    "hana_micron": NAV_WAREHOUSE_TO_HANA,
}

# Khoảng cách giữa 2 nhà máy (giao lộ) — dùng khi giao 2 kiện liên tiếp
# Đội cần đo thực tế trên sa bàn
FACTORY_DISTANCE = {
    ("samsung", "foxconn"): 1,
    ("samsung", "amkor"): 2,
    ("samsung", "hana_micron"): 3,
    ("foxconn", "amkor"): 1,
    ("foxconn", "hana_micron"): 2,
    ("amkor", "hana_micron"): 1,
}

# ============================================================
# LOGGING & DEBUG
# ============================================================
LOG_FILE = "robot_log.txt"
DEBUG_MODE = True            # True = bật giao diện web để luyện tập; False = chế độ thi đấu
WEB_PORT = 5000               # Port cho giao diện web debug
