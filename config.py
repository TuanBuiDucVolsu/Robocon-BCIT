"""
Hằng số tinh chỉnh cho robot Bảng O2. Giá trị cần đo thực nghiệm trên sa bàn.

Bản đồ sa bàn & sinh route: navigation.py (không khai báo route ở đây).
Đấu dây: docs/PHAN_CUNG.md — Lưới sa bàn: docs/SA_BAN.md
"""

import os

# ============================================================
# GPIO — 19 chân (BTC đã bỏ giới hạn số cổng I/O)
# 4 động cơ / giới hạn thể lệ 12 — ĐẠT
# ============================================================

# Bánh xe (PWM cả 2 chiều)
IN1_XE_T = 17                # Tiến trái
IN2_XE_T = 27                # Lùi trái
IN1_XE_P = 23                # Tiến phải
IN2_XE_P = 22                # Lùi phải

# Cẩu phải: mạch 2 chân. Cẩu trái: mạch có ENA
IN3_CAU_P = 25               # Nâng phải
IN4_CAU_P = 24               # Hạ phải
ENA_CAU_T = 5                # Enable cẩu trái
IN1_CAU_T = 13               # Nâng trái
IN2_CAU_T = 6                # Hạ trái

START_BUTTON_PIN = 16        # Nút bấm khởi động (nhả → GPIO nối GND khi bấm)

# MCP3008 ADC qua SPI (GPIO 8 CE0, 9 MISO, 10 MOSI, 11 SCLK)
# CH0-5 = QTR-8A dò line, CH6/CH7 = IR pallet trái/phải
MCP3008_SPI_PORT = 0
MCP3008_CS = 0
PALLET_LEFT_CHANNEL = 6
PALLET_RIGHT_CHANNEL = 7
PALLET_THRESHOLD = 500       # ADC < ngưỡng = có pallet

ULTRASONIC_TRIG_PIN = 19
ULTRASONIC_ECHO_PIN = 20

# Số mẫu gpiozero giữ trong hàng đợi trước khi lấy TRUNG VỊ trả về .distance.
# HC-SR04 cần ~60ms giữa 2 lần phát sóng, nên đây cũng là ĐỘ TRỄ của số đo:
#     queue_len × 60ms = bề rộng cửa sổ, độ trễ ≈ nửa cửa sổ
# Mặc định của gpiozero là 9 → cửa sổ 540ms → trễ ~270ms. Ở APPROACH_FAST_SPEED
# (~200mm/s) đó là 54mm — lớn hơn cả sai số cho phép khi dừng trước kệ, robot đi
# quá vạch từ lâu trước khi con số kịp tụt xuống.
# 3 mẫu vẫn đủ để trung vị loại được 1 giá trị nhiễu lẻ, mà chỉ trễ ~90mm/s → 18mm.
# Xuống 1 thì hết trễ nhưng MẤT lọc nhiễu: một lần đo lỗi là robot dừng sớm ngay.
ULTRASONIC_QUEUE_LEN = 3

# Encoder JGA25-370 (kênh C1, chỉ đếm xung — không đọc chiều).
# ⚠️ Cấp encoder VCC 3.3V cho xung ≤3.3V; bảng màu dây khác nhau theo lô.
ENCODER_LEFT_PIN = 26
ENCODER_RIGHT_PIN = 21
ENCODER_SAMPLE_TIME = 0.2    # Giây đếm xung mỗi lần lấy mẫu (calibrate/chẩn đoán)

# ============================================================
# NỬA SÂN — ⚠️ SAI LÀ MẤT ĐIỂM CẢ TRẬN MÀ LOG KHÔNG BÁO LỖI
# ============================================================
# Hai nửa sân quay 180° nên chiều trái/phải giống nhau, NHƯNG cụm nhà máy in trên
# tường không quay theo → thứ tự nhà máy theo hàng bị ĐẢO giữa 2 nửa.
# Đặt sai = giao Samsung vào Foxconn, IR vẫn báo thả OK.
#
# KIỂM: đứng ở ô xuất phát nhìn sang tường — cụm nhà máy CÙNG HÀNG ô xuất phát là gì?
# Chi tiết: docs/SA_BAN.md — Kiểm đấu dây + nhãn: python3 -m tools.check_board_side

BOARD_SIDE_SWITCH_PIN = 12       # Công tắc gạt (None = chưa lắp). Cách chọn CHÍNH.
BOARD_SIDE_SWITCH_CLOSED = "samsung"   # Gạt về phía nối GND = nửa nào
FACTORY_AT_START_ROW = "foxconn"       # Dự phòng khi không đọc được công tắc

# Chiều trái/phải — bản in cho thấy cả 2 nửa đều False. Robot tự dò để kiểm chứng:
# tại giao lộ Kệ 3 xoay phải, tiến ra xem có nhánh line không (line dọc cột kệ chỉ
# chạy về một phía). KHÔNG dò được thứ tự nhà máy ở trên — hai nửa giống hệt nhau
# qua cảm biến line.
BOARD_MIRRORED = False
BOARD_AUTO_DETECT = True
PROBE_SPEED = 35             # Tốc độ tiến/lùi khi dò (0-100)
PROBE_TRAVEL_TIME = 0.45     # Giây tiến ra khỏi giao lộ rồi lùi lại đúng bấy nhiêu.
                             # Đủ thoát vạch ngang (~10-15cm), chưa tới mép sa bàn.
PROBE_SAMPLE_TIME = 0.3      # Giây lấy mẫu cảm biến line khi đã ra tới nơi

# ============================================================
# ĐỘNG CƠ — TỐC ĐỘ & PWM
# ============================================================
# ⚠️ Toàn bộ số dưới đây đặt cho motor CŨ, chưa đo lại cho JGA25-370 + bánh 65mm.
# Quy trình tăng tốc: chạy 50 → bám line ổn định → tăng từng nấc +10, mỗi nấc test
# lại đếm giao lộ → dừng ở mức cao nhất không trượt giao lộ → mới chỉnh LINE_KP/KD.
# Chi tiết: tests/DEBUG_DONG_CO.md
PWM_FREQUENCY = 100          # Hz
SPEED_DEFAULT = 50           # Duty cycle % — mức bring-up an toàn (cũ: 82)
SPEED_SLOW = 40              # Căn chỉnh, đặt hàng
SPEED_TURN = 62              # ⚠️ CHỐT trước khi calibrate TURN_TIME (đổi sau làm sai lại)
PWM_COMPENSATION = 0.95           # Bù bánh PHẢI khi tiến
PWM_COMPENSATION_REV = 0.95       # Bù bánh PHẢI khi lùi
PWM_COMPENSATION_LEFT = 1.00      # Bù bánh TRÁI khi tiến
PWM_COMPENSATION_LEFT_REV = 1.00  # Bù bánh TRÁI khi lùi

# ============================================================
# CƠ CẤU NÂNG (giây)
# ============================================================
LIFT_TIME_FLOOR = 0.0
LIFT_TIME_SHELF_1 = 0.800
LIFT_TIME_SHELF_2 = 3.9

# Không có limit switch — home_to_floor() hạ liên tục bấy nhiêu giây để ép chạm đáy.
# ⚠️ PHẢI > LIFT_TIME_SHELF_2, không thì đang ở tầng 2 sẽ không hạ hết và
# _current_level bị khai sai = 0. Stall vài giây không sao, đừng để quá lâu.
LIFT_HOME_DURATION = 4.0   # = min_home_duration() sau calibrate (3.9 + LOWER_EXTRA
                           # trái 0.1). Hạ từ 4.5 vì motor là DigitalOutputDevice
                           # (100% duty), kịch sàn rồi vẫn ghì → curoa trượt. Thấp
                           # hơn nữa vô ích: home_to_floor() kẹp ngược lên 4.0.

# Bù lệch 2 càng theo VỊ TRÍ TUYỆT ĐỐI: thời gian từ SÀN lên tầng n = LIFT_TIME_SHELF_n
# + bù. Thời gian mỗi lần chạy = hiệu 2 mốc (Lift._level_time) → không cộng dồn khi đi
# 0→1→2, và càng lẻ dùng chung hệ số với khi chạy cả 2 càng.
LIFT_LEFT_EXTRA = -0.050          # Càng TRÁI khi nâng
LIFT_RIGHT_EXTRA = 0.100         # Càng PHẢI khi nâng
LIFT_LEFT_LOWER_EXTRA = 0.100     # Càng TRÁI khi hạ (tăng nếu bên đó khó hạ)
LIFT_RIGHT_LOWER_EXTRA = 0.0      # Càng PHẢI khi hạ

LIFT_SPEED = 80              # Duty cycle motor nâng — chỉ dùng trong web debug
PICKUP_MAX_RETRIES = 2       # Số lần nâng lại nếu IR không thấy pallet
PICKUP_VERIFY_DELAY = 0.2    # Giây chờ sau nâng trước khi đọc IR

# ============================================================
# BỐC HÀNG — 4 MỐC KHOẢNG CÁCH & 1 MỐC THỜI GIAN
# ============================================================
# ⚠️ MỌI SỐ cm Ở ĐÂY ĐO TỪ CẢM BIẾN SIÊU ÂM, KHÔNG PHẢI TỪ MŨI CÀNG.
# HC-SR04 lắp GIỮA 2 CÀNG (docs/PHAN_CUNG.md) nên càng chìa ra xa hơn cảm biến —
# lúc mũi càng chạm kệ thì cảm biến vẫn còn cách kệ cả chục centimet.
#
#          cảm biến HC-SR04
#                 │
#      ┌──────────┴──────┐                          ┌──────────────┐
#      │     ROBOT       │══════ càng ══════▶       │     KỆ       │
#      └─────────────────┘                          │  ┌────────┐  │
#                                                   │  │ pallet │  │
#                                                   │  └────────┘  │
#                                                   └──────────────┘
#      │←────────── con số siêu âm đọc được ───────────→│
#
# Cơ cấu là XE NÂNG THẬT: càng phải LUỒN VÀO pallet rồi mới nhấc lên được. Nên
# thứ tự bắt buộc là CHỜ → NÂNG → LUỒN → NHẤC (control/handling.py). Không thể
# tiến vào lúc càng còn ở sàn rồi nâng thẳng lên: càng sẽ đi lên trong không khí
# trước mặt kệ, và với tầng 2 thì đội vào mặt tầng 1.
#
# ĐO TẤT CẢ BẰNG:  python3 -m tools.measure_pickup
# (tool nâng càng + đọc siêu âm cùng lúc; motor bánh không chạy, bạn đẩy tay robot)

# --- ① VỊ TRÍ CHỜ ------------------------------------------------------------
# Robot dừng ở đây, CÀNG CÒN Ở SÀN, rồi mới nâng càng lên ngang tầng.
# Phải đủ XA để nâng càng lên TẦNG 2 mà càng không quệt vào kệ.
#   Đặt quá GẦN → nâng càng lên là đập vào mặt kệ.
#   Đặt quá XA  → bước luồn phải bò lâu hơn, tốn giây (không nguy hiểm).
# Giá trị cũ 4.0 là BẤT KHẢ THI (mũi càng chạm kệ khi cảm biến còn ~13.5cm) nên
# robot húc kệ trọn 5 giây cho tới timeout.
# ⚠️ Con số ~13.5cm ở dòng trên là ƯỚC LƯỢNG cũ, số đo thật bên dưới mâu thuẫn với
#   nó (11.9 < 13.5) — đo lại nếu thấy càng chạm kệ lúc nâng.
APPROACH_DISTANCE = 11.9     # ĐÃ ĐO — measure_pickup ① (APPROACH_STANDOFF_DISTANCE)

# --- ② LÙI RA ----------------------------------------------------------------
# Sau khi nhấc/thả xong, robot lùi tới khi đọc được ≥ số này thì dừng.
# Phải đủ xa để CÀNG RỜI HẲN KỆ, còn chỗ xoay 180° hoặc lùi tiếp mà không vướng.
#   ⚠️ PHẢI LỚN HƠN ① — nhỏ hơn thì retreat_from_shelf() thấy "đã đủ xa" ngay từ
#   đầu, trả True mà KHÔNG lùi tí nào (đúng lỗi đã gặp: RETREAT=10 < đo được 21.8).
# ⚠️ Biên hiện tại chỉ 1.0cm so với ① (12.9 vs 11.9) — mỏng so với nhiễu HC-SR04.
RETREAT_DISTANCE = 12.9      # ĐÃ ĐO — measure_pickup ④

# --- ③ CHẶN CỨNG KHI LUỒN CÀNG ----------------------------------------------
# Bước luồn dừng theo CẢM BIẾN IR trên mặt càng (IR đo thẳng "pallet đã trên càng
# chưa" — miễn nhiễm với robot lệch ngang hay pallet đặt lệch). Siêu âm ở bước này
# CHỈ làm phanh cuối: dù IR chưa báo cũng TUYỆT ĐỐI không tiến gần hơn số này.
# Đặt nhỏ hơn khoảng cách lúc càng đã luồn hết, nhưng đủ lớn để robot không ủi kệ
# khi càng trượt ra ngoài khe pallet.
# Số đo luồn xong: TẦNG 1 = 3.6cm (②), TẦNG 2 = 4.9cm (③). Không bằng nhau nên
# phanh phải đặt dưới cái NHỎ HƠN (3.6), nếu không tầng 1 bị chặn giữa chừng.
# ⚠️ Giá trị cũ 4.0 LỚN HƠN 3.6 → phanh siêu âm cắt bước luồn tầng 1 trước khi càng
#   vào hết khe pallet. Đó là lỗi thật, số đo mới vừa phơi ra.
INSERT_MIN_DISTANCE = 3.0    # ĐÃ ĐO gián tiếp — dưới ② (3.6) một khoảng an toàn

# --- ④ NHẤC BỔNG (giây, không phải cm) --------------------------------------
# Càng đã luồn vào pallet rồi thì nâng THÊM bao nhiêu giây nữa để pallet rời hẳn
# mặt kệ. Chỉ vài phần mười giây — đây là phần dôi ra NGOÀI thang tầng.
#   Quá ngắn → pallet còn tì lên kệ, kéo ra là đổ.
#   Quá dài  → càng đội lên tầng trên (tầng 1) hoặc nóc kệ (tầng 2).
LIFT_PICKUP_RAISE_TIME = 0.2    # ĐÃ ĐO — measure_pickup ⑤

# --- Tốc độ & timeout của bước luồn ------------------------------------------
INSERT_SPEED = 25            # % — bò chậm khi luồn càng
INSERT_TIMEOUT = 4.0         # Giây, IR không báo thì dừng (đừng đẩy đổ kệ)

# ============================================================
# TIẾP CẬN — 2 pha nhanh/chậm tới VỊ TRÍ CHỜ ①
# ============================================================
APPROACH_TIMEOUT = 5.0       # Timeout tiếp cận / lùi ra (giây)
APPROACH_SPEED = 30          # Tốc độ lùi ra
APPROACH_FAST_SPEED = 60     # Pha xa
APPROACH_SLOW_SPEED = 25     # Pha gần (dừng chính xác)
# PHẢI LỚN HƠN ①, không thì pha chậm không bao giờ chạy và robot lao hết tốc độ
# tới tận lúc dừng.
APPROACH_SLOW_DISTANCE = 35  # cm — dưới mức này thì chuyển sang chậm

# Chặn chạy mù: mất echo (tường check-in chỉ cao 5cm) mà cứ tiến hết timeout ở tốc
# độ cao là robot ra khỏi sa bàn / sang sân đối phương (reject −10 điểm).
APPROACH_DETECT_DISTANCE = 45.0  # cm — coi là "đã thấy mục tiêu" (> SLOW_DISTANCE)
APPROACH_BLIND_TIMEOUT = 1.5     # Giây chạy mù tối đa khi chưa thấy gì

# Chặn HÚC KỆ: "thấy mục tiêu" KHÔNG có nghĩa là đang tiến lại gần. Mũi càng chạm
# kệ / cảm biến kẹt / bánh trượt đều cho số đo ĐỨNG YÊN ở một giá trị trông rất
# hợp lý, và APPROACH_BLIND_TIMEOUT (chỉ bắt "không thấy gì") để lọt hết.
APPROACH_NO_PROGRESS_TIME = 1.2  # Giây không lại gần thêm được thì bỏ cuộc
APPROACH_NO_PROGRESS_CM = 1.0    # cm — giảm ít hơn mức này coi như đứng yên

# ============================================================
# BÁM LINE (QTR-8A analog qua MCP3008)
# ============================================================
LINE_SENSOR_COUNT = 6        # CH0-CH5, bỏ 2 mắt ngoài cùng (dành CH6-7 cho IR)
LINE_THRESHOLD = 400         # ADC 0-1023: < ngưỡng = trên line (đen)
# ⚠️ Nhiều module QTR-8A đọc bề mặt ĐEN ra giá trị CAO (ngược giả định của code).
# Chạy `python3 -m tools.calibrate_line` để chốt cờ này — code tự đảo tại nguồn.
LINE_BLACK_IS_HIGH = True
LINE_WEIGHTS = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]   # Lệch trái âm, phải dương
LINE_KP = 16.0               # CHƯA calibrate thật
LINE_KD = 6.5                # CHƯA calibrate thật
INTERSECTION_THRESHOLD = 4   # Số mắt (/6) thấy line cùng lúc để nhận là giao lộ

# --- Đếm giao lộ mà KHÔNG dừng lại ở từng cái ---
# Chế độ mặc định dừng hẳn ở mỗi giao lộ rồi chạy mù 0.3s để thoát ra
# (_escape_intersection). Kịch bản tệ nhất đi qua ~65 giao lộ nên riêng phần phanh +
# chạy mù + tăng tốc lại đã ăn hàng chục giây — đây là đòn bẩy phần mềm lớn nhất cho
# ngân sách 240s (xem tools.estimate_time).
# ⚠️ MẶC ĐỊNH TẮT: nó đụng vào vòng lặp quan trọng nhất và CHƯA chạy trên robot thật.
# Bật lên rồi chạy test_motion option 11 hai lần (tắt/bật), so số giao lộ đếm được và
# thời gian. Đếm thiếu/thừa giao lộ nghĩa là phải chỉnh 2 ngưỡng dưới.
CONTINUOUS_INTERSECTIONS = False
# Trễ hai ngưỡng chống đếm trùng: đếm khi ≥ INTERSECTION_THRESHOLD mắt thấy line,
# chỉ cho đếm cái kế sau khi đã tụt xuống ≤ ngưỡng này (tức đã ra khỏi vạch cắt).
INTERSECTION_CLEAR_THRESHOLD = 2
CONTINUOUS_TIMEOUT_PER_HOP = 15.0   # Giây tối đa cho mỗi khoảng giữa 2 giao lộ

# Sa bàn có khoảng ĐỨT line thật ở ô xuất phát (~245mm). Mất line thì giữ lái và trôi
# thẳng bấy nhiêu giây rồi mới coi là lạc và quét tìm lại. Ngắn quá → quay ngang giữa
# khoảng đứt; dài quá → lạc thật mà vẫn chạy. Đo lại theo tốc độ thật.
LINE_GAP_COAST_TIME = 1.2

# Lệnh ("advance",) — bám line tới HẾT line (vào kệ / khu nhà máy / Kệ 4). Những chỗ
# đó là điểm cuối của line, không phải giao lộ nên không đếm bằng ("forward", N).
ADVANCE_SPEED = 40
LINE_END_CONFIRM_TIME = 0.25 # Giây mất line liên tục để kết luận "hết line"
ADVANCE_TIMEOUT = 6.0

# ============================================================
# LÙI RA KHỎI KỆ / NHÀ MÁY — lệnh ("back", N)
# ============================================================
# Rút khỏi điểm cuối bằng cách LÙI thay vì xoay 180° rồi tiến. Mỗi lần bỏ được 2 lần
# xoay; đo trên toàn bộ 6 lượt thì bớt ~28 lần xoay ở kịch bản tệ nhất (~34s) — chi
# phí cố định lớn nhất của trận. Robot vẫn BÁM LINE khi lùi (thanh cảm biến ở đầu xe
# lúc này thành đuôi), không chạy mù.
REVERSE_SPEED = 35           # Chậm hơn tiến: sai số lái nằm ở đầu kia của xe
REVERSE_TIMEOUT = 8.0
EDGE_COST_REVERSE = 1        # Phụ phí so với tiến 1 giao lộ → hoà thì vẫn ưu tiên tiến

# Sau khi lùi tới giao lộ, thân xe nằm QUÁ giao lộ một đoạn bằng khoảng cách từ trục
# bánh tới thanh cảm biến (tiến thì thân nằm trước giao lộ đúng bấy nhiêu). Nếu xoay
# xong hay bị trượt line thì đặt số giây tiến bù ở đây (đo bằng test_motion option 15).
REVERSE_RECENTER_TIME = 0.0

# ============================================================
# CHI PHÍ TÌM ĐƯỜNG (navigation.py) — quy đổi ra "1 giao lộ đi thẳng"
# ============================================================
ROUTE_TURN_COST = 2          # Giá 1 lần xoay 90°
ADVANCE_COST = 2             # Giá lệnh ("advance",)
EDGE_COST_START_GAP = 3      # Phụ phí đoạn ngang R0 (trôi qua khoảng đứt ô xuất phát)

# ============================================================
# CAMERA & NHẬN DIỆN KIỆN HÀNG
# ============================================================
CAMERA_RESOLUTION = (640, 480)
CONFIDENCE_THRESHOLD = 0.20  # Tỷ lệ pixel tối thiểu (đường HSV)
MAX_SCAN_RETRIES = 3         # Số lần chụp lại trong 1 lượt quét
MAX_PAIR_SCAN_ATTEMPTS = 2   # Số lần quét lại cả cặp sau khi tiếp cận kệ
SCAN_RETRY_DELAY = 0.05      # Giây chờ giữa 2 lần chụp

LABEL_TO_FACTORY = {
    "samsung": "Samsung",
    "foxconn": "Foxconn",
    "amkor": "Amkor",
    "hana_micron": "Hana Micron Vina",
}

# Ngưỡng inlier ORB (nhận diện CHÍNH). Hạ từ 10 xuống 6 theo số đo thật trên Pi:
# decal Foxconn chỉ đạt ~7 inlier dù đúng kiện, kiện SAI cao nhất ~3. Tăng lại nếu
# thấy báo nhận nhầm lúc KHÔNG có kiện hàng nào trong khung.
SHAPE_MIN_INLIERS = 6

# Kiện thắng phải có inlier ≥ ngần này lần kiện đứng THỨ 2 mới được nhận. Chặn ca
# bệ trống: nền vẫn cho 1-2 nhãn sát nút nhau (vd 4 so với 3), kiện thật thì cách
# biệt rõ (7 so với 3). Tăng = khắt khe hơn (hay rơi về HSV), giảm = dễ nhận nhầm.
# vision/shape_match.py VẪN ĐỌC hằng số này qua getattr — trước đây nó không có
# trong file này nên chỉnh mãi không thấy tác dụng vì không ai biết nó tồn tại.
SHAPE_MARGIN_RATIO = 1.8

# --- HSV (dự phòng khi ORB không đủ tự tin) ---
# Amkor là khối XÁM nên nền trắng/xám dễ lọt vào dải của nó → ưu tiên màu chromatic
# đạt ngưỡng, kể cả khi Amkor đếm nhiều pixel hơn.
CHROMATIC_LABELS = ("samsung", "foxconn", "hana_micron")
ACHROMATIC_LABEL = "amkor"
ROI_MARGIN = 0.2             # Tỉ lệ cắt mỗi cạnh lấy vùng giữa. Giảm (vd 0.12) nếu
                             # Hana hay bị nhầm Amkor — ngoặc đỏ của Hana nằm ở GÓC.
CENTER_WEIGHT_SIGMA = 0.85   # Trọng số Gauss theo khoảng cách tới tâm ROI: pixel nền
                             # ở rìa tính nhẹ hơn. Giảm → tập trung tâm mạnh hơn.
NO_CENTER_WEIGHT_LABELS = ("hana_micron",)   # Hana đếm đều toàn ROI (ngoặc đỏ ở góc)

# Dải HSV (OpenCV H=0-179, S/V=0-255). Nhiều dải nếu màu wrap qua 0.
# Calibrate: python3 -m tools.calibrate_vision (chạy lại nếu đổi ánh sáng/camera).
COLOR_RANGES = {
    "samsung": [                                # chip xanh dương
        ([90, 53, 44], [112, 255, 172]),
    ],
    "foxconn": [                                # chip vàng đồng
        ([19, 51, 48], [49, 200, 193]),
    ],
    "amkor": [                                  # khối nhôm xám bạc
        ([0, 4, 128], [179, 49, 240]),
    ],
    "hana_micron": [                            # QR viền đỏ (wrap qua 0)
        ([0, 52, 53], [15, 167, 184]),
        ([170, 52, 53], [179, 167, 184]),
    ],
}

# ============================================================
# NHIỆM VỤ
# ============================================================
# Kệ 240x120x240mm, 2 tầng × 2 pallet. Kệ 1-3 = 12 kiện (NV1). Kệ 4 = hàng rời (NV2).
SHELVES_TASK1 = 3            # Kệ 0-2
TOTAL_PACKAGES_TASK1 = 12    # 3 kệ × 2 tầng × 2 pallet
PICKUPS_TASK1 = 6            # 12 ÷ 2 kiện mỗi lượt nâng
MAX_TIER_RETRIES = 1         # Số lần thử lại tầng kệ trước khi bỏ qua

# ============================================================
# XUẤT PHÁT & THỜI GIAN TRẬN
# ============================================================
# Ô start không có line → tiến thẳng ra chạm line R0 rồi căn giữa. Robot đặt quay mặt
# về phía Kệ 3. exit_start_zone() KHÔNG đếm giao lộ — bộ tìm đường lo phần đó.
EXIT_START_SPEED = 50
EXIT_START_TIMEOUT = 5.0     # Giây, không thấy line thì báo lỗi
EXIT_START_ALIGN_TIME = 0.4  # Giây bám line ngắn để căn giữa sau khi chạm line

MATCH_DURATION = 240
SAFETY_MARGIN = 10           # Giây dừng sớm trước khi hết giờ

# NV2 (30đ) chỉ được làm SAU khi xong 100% NV1, và tốn khoảng 20-25s cho cả chuyến
# nhà máy → Kệ 4 → nhấc → liên hợp → thả. Dùng chung SAFETY_MARGIN (10s) thì robot
# vẫn khởi hành khi còn 15s — chuyến chắc chắn không kịp, lại kết thúc trận trong
# lúc đang chạy giữa sân thay vì đứng yên. Đo lại bằng tools.measure_phases rồi
# chỉnh cho khớp thời gian NV2 thật.
TASK2_MIN_TIME = 30          # Giây tối thiểu còn lại thì mới bắt đầu NV2
TURN_TIME = 0.5              # ⚠️ CHƯA đo cho JGA25-370 — ƯU TIÊN #1, test_motion op.10

# Mốc bắt đầu trận: lỗi giữa trận → thoát mã 1 → systemd restart → đọc lại file này
# để chạy NỐT thời gian còn lại. Ở /tmp nên tự mất sau reboot.
MATCH_STATE_FILE = "/tmp/robot_match_state"

# ============================================================
# LOGGING & DEBUG
# ============================================================
LOG_FILE = "robot_log.txt"
WEB_PORT = 5000
DEBUG_MODE = True            # True = web debug (luyện tập); False = thi đấu
if os.environ.get("ROBOT_COMPETE") == "1":   # scripts/start.sh đặt cờ này
    DEBUG_MODE = False
