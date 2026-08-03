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

# Chiều trái/phải — bản in cho thấy cả 2 nửa đều False (quay 180° bảo toàn tay
# thuận). KHÔNG dò được thứ tự nhà máy ở trên — cái đó do CÔNG TẮC GẠT quyết định.
BOARD_MIRRORED = False

# ⚠️ TẮT TỰ DÒ. Lý do, theo thứ tự sức nặng:
#
# 1. THỪA. Công tắc gạt đã cho robot biết nó đang ở NỬA NÀO — đó cũng là thông tin
#    duy nhất bước dò có thể moi ra. Mà chiều trái/phải KHÔNG đổi theo nửa (cả hai
#    đều False), nên bước dò đang đo một HẰNG SỐ, không phải biến.
# 2. NÓ LÀM HỎNG LỆNH NGAY SAU. probe_side_branch() chạy hở hoàn toàn: xoay phải →
#    tiến 0.45s → lùi 0.45s → xoay trái, rồi tin mình về đúng chỗ cũ. Hai thứ nó
#    dựa vào đều chưa calibrate (TURN_TIME mới xác nhận chiều TRÁI; bù PWM chiều
#    LÙI thì option f không ghi), nên robot về LỆCH KHỎI VẠCH và advance_to_end kế
#    đó không tìm thấy line. Đo trên robot: smoke option 1 dừng ngay tại giao lộ.
# 3. ĐOÁN SAI THÌ MẤT CẢ TRẬN. Dò xong nó GỌI set_mirrored() — báo nhầm GƯƠNG là
#    nạp lại toàn bộ bản đồ theo chiều gương, mọi lệnh xoay đảo chiều tới hết trận.
#    Đã quan sát thấy nó lúc báo CHUẨN lúc báo GƯƠNG.
# 4. Tốn 2-4s đầu trận.
#
# Thứ nó bảo vệ chỉ là giả thuyết "bản in sai chiều" — kiểm bằng mắt 5 giây trên
# sân. Một cơ chế phòng lỗi mà tự nó gây lỗi nhiều hơn lỗi nó phòng thì nên bỏ.
# Bật lại: BOARD_AUTO_DETECT = True (main.py có sẵn cả 2 nhánh).
BOARD_AUTO_DETECT = False
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
# Hệ số giảm chấn khi calibrate bù PWM (test_motion option f): mỗi vòng chỉ đi
# ngần này phần đường tới giá trị tính được. Áp đủ 100% hiệu chỉnh dựa trên một
# phép đo có nhiễu là công thức chuẩn để DAO ĐỘNG — đã xảy ra thật khi đo chiều
# tiến 02/08: lệch 3.8% → 7.9% → 9.0%, biên độ tăng dần thay vì hội tụ.
PWM_CALIB_DAMPING = 0.5

# ✅ ĐO VẬT LÝ 02/08 (đặt giữa vạch R4 trên sa bàn, chạy MÙ 2s, đọc trôi ngang):
#     1.000 → lệch TRÁI rõ (bánh phải nhanh hơn)
#     0.940 → ĐI THẲNG ✓
# ⚠️ ĐỪNG calibrate lại bằng encoder. Encoder rớt xung: tỉ lệ 2 bánh tản ±5%, tổng
# xung tản ±10% giữa 3 lượt CÙNG cấu hình — nhiễu lớn hơn thứ cần đo. Vòng chỉnh
# theo encoder đã dao động thật (3.8% → 7.9% → 9.0%) và đẻ ra toàn số vô nghĩa.
# Dò lại bằng vạch thẳng: robot cong về phía bánh CHẬM, nên lệch TRÁI = hạ số này.
PWM_COMPENSATION = 0.940           # Bù bánh PHẢI khi tiến
# ĐO trên robot 02/08 (option f, chiều lùi): 0.95 → 1.000. Bánh phải KHÔNG cần hãm
# khi lùi. Đo tiếp thấy bánh TRÁI nhanh hơn 2.3% → phần cân còn lại nằm ở
# PWM_COMPENSATION_LEFT_REV, không phải ở đây (hệ số kẹp ≤ 1.0, không tăng thêm được).
PWM_COMPENSATION_REV = 1.000      # Bù bánh PHẢI khi lùi
PWM_COMPENSATION_LEFT = 1.000     # Bù bánh TRÁI khi tiến (đặt lại 02/08, xem trên)
# ĐÃ CALIBRATE trên robot 02/08 (option f, chiều lùi, hội tụ sau 1 vòng):
#     trước: trái=356 phải=339  → lệch 4.8%
#     sau  : trái=336 phải=338  → lệch 0.6%  ĐÃ CÂN
PWM_COMPENSATION_LEFT_REV = 0.952  # Bù bánh TRÁI khi lùi

# ============================================================
# CƠ CẤU NÂNG (giây)
# ============================================================
LIFT_TIME_FLOOR = 0.0
LIFT_TIME_SHELF_1 = 0.800
LIFT_TIME_SHELF_2 = 3.5

# Không có limit switch — home_to_floor() hạ liên tục bấy nhiêu giây để ép chạm đáy.
LIFT_HOME_DURATION = 3.7   # min_home_duration() = LIFT_TIME_SHELF_2 + LOWER_EXTRA lớn

# Bù lệch 2 càng theo VỊ TRÍ TUYỆT ĐỐI: thời gian từ SÀN lên tầng n = LIFT_TIME_SHELF_n
# + bù. Thời gian mỗi lần chạy = hiệu 2 mốc (Lift._level_time) → không cộng dồn khi đi
# 0→1→2, và càng lẻ dùng chung hệ số với khi chạy cả 2 càng.
LIFT_LEFT_EXTRA = -0.050          # Càng TRÁI khi nâng
LIFT_RIGHT_EXTRA = 0.000         # Càng PHẢI khi nâng
LIFT_LEFT_LOWER_EXTRA = 0.100     # Càng TRÁI khi hạ (tăng nếu bên đó khó hạ)
LIFT_RIGHT_LOWER_EXTRA = 0.150      # Càng PHẢI khi hạ — ĐÃ ĐO trên robot 02/08

# Home RÚT GỌN khi đã biết chắc đang ở tầng nào (Lift.home_from). Hạ từ tầng 1 chỉ
# cần ~0.9s trong khi home mặc định chạy 4.0s theo tầng cao nhất — hơn 3 giây motor
# ghì vào đáy vô ích, mà motor cẩu là DigitalOutputDevice nên ghì ở 100% duty và bào
# mòn dây curoa. Chỉ dùng ở menu test / công cụ đo; luồng THI ĐẤU vẫn chạy bản đầy đủ.
# ⚠️ 1.6 là số ĐẶT MÒ ban đầu → hạ từ tầng 1 mất 1.52s. Đo trên robot 02/08: 1 giây
# là đủ (thời gian lý thuyết 0.950s = LIFT_TIME_SHELF_1 0.800 + LOWER_EXTRA 0.150).
# 1.05 → 1.00s. Biên mỏng, nhưng đây là home DỌN DẸP chứ không phải home chuẩn mốc:
# chạy thiếu thì lần home ĐẦY ĐỦ sau đó sửa lại, và menu vẫn còn lựa chọn "?".
# Tăng lại nếu đổi pin, đổi dây curoa, hoặc thấy càng không chạm sàn hẳn.
LIFT_HOME_KNOWN_MARGIN = 1.05  # nhân vào thời gian lý thuyết của tầng đó
LIFT_HOME_MIN_DURATION = 0.8   # sàn tối thiểu — phòng _current_level lệch nhẹ

# Có home càng ở INIT không (trước lúc chờ nút, KHÔNG ăn vào 240s của trận).
# Tắt để đỡ bào mòn dây curoa: mỗi lần khởi động là 4s motor ghì vào đáy cơ khí ở
# 100% duty, mà ngồi test thì khởi động lại rất nhiều lần.
# ⚠️ TẮT = ĐỘI PHẢI TỰ HẠ CÀNG VỀ SÀN TRƯỚC KHI BẤM NÚT. Không có limit switch nên
# robot KHÔNG kiểm chứng được; nó chỉ tin `_current_level = 0`. Quên hạ càng thì mọi
# phép tính tầng sau đó lệch, và KHÔNG có tín hiệu nào báo — cùng loại lỗi im lặng
# với công tắc gạt nửa sân. main.py in một khối cảnh báo mỗi lần khởi động để không
# ai bỏ sót.
HOME_AT_INIT = False

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
# ⚠️ Từng bị nâng lên 15.0 sau một lần robot húc kệ, rồi TRẢ LẠI 11.9. Lần húc đó
# do đặt robot LỆCH LINE nên siêu âm dội vào mặt khác, không phải do mốc dừng sát.
# Nâng mốc dừng còn phản tác dụng: bước luồn càng phải bò từ đây vào ~3.6cm ở
# INSERT_SPEED=25 trong INSERT_TIMEOUT=4.0s, tức 11.9 cần 21mm/s còn 15.0 cần
# 28mm/s — đẩy vấn đề từ bước tiếp cận sang bước luồn.
APPROACH_DISTANCE = 11.9     # ĐÃ ĐO — measure_pickup ① (APPROACH_STANDOFF_DISTANCE)
# Cm dừng SỚM hơn APPROACH_DISTANCE. Bù độ trễ siêu âm, KHÔNG phải sửa mốc hình học
# — giữ APPROACH_DISTANCE đúng nghĩa "khoảng cách đo được tới khe pallet".
# gpiozero trả trung vị ULTRASONIC_QUEUE_LEN=3 mẫu × ~60ms → số báo về QUÁ KHỨ ~90ms,
# mà robot vẫn chạy trong 90ms đó. Cộng nhiễu trung vị trên mặt kệ gồ ghề → khoảng
# dừng tản rộng: đo trên robot 02/08 thấy "lúc dừng đúng, lúc chui vào gầm kệ 2cm".
# ⚠️ Lệch hẳn về phía DỪNG SỚM là CÓ CHỦ Ý, vì hai vế không cân nhau:
#     dừng sớm  → creep_until bò tiếp tới khi IR báo (còn 4s timeout, thừa) → không mất gì
#     dừng muộn → càng còn ở SÀN lúc này, chui vào gầm kệ → hỏng lượt bốc
# 2.0 nhắm phủ hết mức trôi quan sát được. Đo cm/s (NGHIEM_THU A3) rồi tính đúng:
#     bù = cm/s × 0.09s.  Đo khoảng dừng 5 lần (B3) thì cộng thêm nửa độ tản.
# ĐÃ ĐO trên robot 02/08 (approach_shelf tự in): lúc quyết định báo 13.3cm, đo lại
# khi đứng yên 9.8cm → trôi 3.5cm. Khớp phân tích: trễ siêu âm ~1.4 + ramp 0.06s
# ~0.9 + quãng phanh ~1.0. Bù 2.0 thiếu 2.1 → 4.1.
# ĐO 2 LẦN trên robot 02/08, ra HAI kết quả trái ngược:
#     trôi 3.5cm → dừng ở  9.8cm (quá GẦN, càng chạm gầm kệ)
#     trôi 1.4cm → dừng ở 14.6cm (quá XA, luồn càng timeout)
# Độ trôi TẢN — không giá trị bù nào đúng cho cả hai. Đặt 2.5 = trung bình, rồi để
# bước LUỒN nuốt phần tản còn lại: nó dừng theo TÍN HIỆU IR chứ không theo khoảng
# cách, nên đó mới là chỗ xử lý được tản.
APPROACH_STOP_MARGIN = 2.5

# --- ② LÙI RA ----------------------------------------------------------------
# Sau khi nhấc/thả xong, robot lùi tới khi đọc được ≥ số này thì dừng.
# Phải đủ xa để CÀNG RỜI HẲN KỆ, còn chỗ xoay 180° hoặc lùi tiếp mà không vướng.
#   ⚠️ PHẢI LỚN HƠN ① — nhỏ hơn thì retreat_from_shelf() thấy "đã đủ xa" ngay từ
#   đầu, trả True mà KHÔNG lùi tí nào (đúng lỗi đã gặp: RETREAT=10 < đo được 21.8).
# ⚠️ Biên hiện tại chỉ 1.0cm so với ① (12.9 vs 11.9) — mỏng so với nhiễu HC-SR04.
RETREAT_DISTANCE = 12.9      # ĐÃ ĐO — measure_pickup ④
# Lùi ra bằng siêu âm KHÔNG dùng được khi đang cõng kiện: pallet vừa nhấc nằm ngay
# trước cảm biến và đi CÙNG robot, nên số đo đứng yên và RETREAT_DISTANCE không bao
# giờ đạt. Đo 02/08, tương quan hoàn hảo: bốc thành công → lùi timeout 5s; bốc thất
# bại (không pallet) → lùi OK. Phát hiện bằng "số đo không TĂNG" rồi lùi theo giờ.
RETREAT_STUCK_TIME = 0.8     # Giây quan sát trước khi kết luận cảm biến bị che
RETREAT_STUCK_CM = 1.5       # Tăng ít hơn ngần này trong khoảng trên = bị che
RETREAT_BLIND_TIME = 1.5     # Tổng giây lùi khi đã chuyển sang lùi mù

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
# ⚠️ 3.0 CHẶN QUÁ SỚM. Thử trên robot: càng vào ĐÚNG khe pallet nhưng chưa đủ sâu,
# robot dừng ở 2.6cm vì chạm phanh này, IR chưa thấy pallet nên bốc hàng thất bại.
# Số 3.0 vốn suy ra từ "measure_pickup ② = 3.6cm luồn xong tầng 1" — thực tế cho
# thấy 3.6 KHÔNG phải điểm luồn xong.
# Hạ 3.0 → 1.5 để càng vào sâu thêm ~1.1cm. Vẫn giữ phanh vì đây là thứ duy nhất
# chặn robot ủi đổ giá kệ khi càng trượt ra NGOÀI khe pallet.
# Đã kẹp được hai đầu trên robot:
#     3.0 → dừng thật ở 2.6cm: càng trong khe nhưng CHƯA đủ sâu, IR không báo
#     1.5 → dừng thật ~1.1cm : QUÁ sâu, nâng lên là pallet chạm mặt tầng trên
# 2.2 nhắm dừng thật quanh 1.8cm — giữa hai mốc đó. Độ trễ siêu âm làm robot lố
# thêm ~0.4cm sau khi con số chạm ngưỡng, đã trừ hao.
INSERT_MIN_DISTANCE = 2.2    # ĐANG DÒ — cửa sổ đúng rất hẹp, chỉnh từng 0.2

# --- ④ NHẤC BỔNG (giây, không phải cm) --------------------------------------
# Càng đã luồn vào pallet rồi thì nâng THÊM bao nhiêu giây nữa để pallet rời hẳn
# mặt kệ. Chỉ vài phần mười giây — đây là phần dôi ra NGOÀI thang tầng.
#   Quá ngắn → pallet còn tì lên kệ, kéo ra là đổ.
#   Quá dài  → càng đội lên tầng trên (tầng 1) hoặc nóc kệ (tầng 2).
# Tăng 0.2 → 0.4: 0.2s không thấy càng nhúc nhích. Dây curoa có độ rơ, một xung
# ngắn có thể bị tiêu hết vào việc căng dây mà chưa kịp sinh chuyển động thật.
# ⚠️ ĐÂY LÀ HẰNG SỐ CÓ TRẦN. Nhấc quá tay thì ở TẦNG 1 càng đội vào mặt tầng 2,
# ở tầng 2 thì đội vào nóc kệ. Khe hở phía trên kiện hàng không nhiều — tăng tiếp
# thì phải nhìn tận mắt, đừng tăng mò.
LIFT_PICKUP_RAISE_TIME = 0.3    # ĐANG DÒ (measure_pickup ⑤ đo được 0.2, không đủ)

# --- Tốc độ & timeout của bước luồn ------------------------------------------
# ⚠️ Nâng 25 → 32. Ở 25% robot bò CHÉO khi luồn càng, đẩy pallet lệch đi.
# 25% nằm trong VÙNG CHẾT của JGA25-370 qua L298N — đo được ở pha tiếp cận: 25% thì
# bò dưới 8mm/s và bị dừng oan, 32% mới chạy sạch. Trong vùng đó đường đặc tính
# duty–tốc độ dựng đứng và HAI MOTOR KHÔNG DỰNG GIỐNG NHAU, nên một bên còn ì trong
# khi bên kia đã quay → robot đi chéo.
# PWM_COMPENSATION không cứu được ca này: nó là MỘT hệ số dùng chung cho mọi tốc độ,
# đo ở tốc độ cao; sát vùng chết thì sai lệch 2 bánh không còn tỉ lệ.
# Nâng 32 → 40. Hai lý do, cùng một gốc là vùng chết:
#   1. Ở 32 bò chỉ ~5.7cm/s (đo: 7cm/1.23s) — hết INSERT_TIMEOUT trước khi tới nơi
#      nếu điểm dừng hơi xa. Đã gặp thật.
#   2. Lực lái = base − MOTOR_MIN_DUTY. Ở 32 chỉ còn ±2, tức KHÔNG lái được gì;
#      ở 40 được ±10. Muốn _forward_guided có tác dụng thì phải có khoảng hở này.
# Vẫn an toàn: điểm dừng do IR quyết định, cộng chặn cứng INSERT_MIN_DISTANCE.
INSERT_SPEED = 40            # % — bò khi luồn càng, đủ trên vùng chết để CÒN lái được
# Nâng 4.0 → 6.0. Điểm dừng của approach TẢN từ 9.8 đến 14.6cm (đo 02/08) nên quãng
# phải bò cũng tản theo. Thà thừa thời gian còn hơn timeout oan ở lần dừng xa —
# chặn cứng INSERT_MIN_DISTANCE mới là cơ chế chống húc kệ, không phải timeout.
INSERT_TIMEOUT = 6.0         # Giây, IR không báo thì dừng

# ============================================================
# TIẾP CẬN — 2 pha nhanh/chậm tới VỊ TRÍ CHỜ ①
# ============================================================
# --- Dừng có giảm tốc (Motion.stop_gently) ---
# stop() đặt cả 4 chân PWM về 0; EN của L298N nối cứng mức cao nên hai đầu motor
# cùng bị kéo xuống đất = PHANH ĐỘNG, không phải thả trôi. Phanh gấp ngay trước kệ
# sinh mô-men giật, hai bánh không phanh giống hệt nhau, cộng 2 bánh caster tự xoay
# → robot lệch vài độ TẠI CHỖ. Vài độ đó đủ làm càng không luồn thẳng vào khe
# pallet, mà bước đó không còn line để tự sửa.
# Dùng ở 3 chỗ tư thế robot quan trọng: cuối approach_shelf, cuối creep_until (càng
# đang trong khe pallet), cuối advance_to_end.
# ⚠️ Giảm dần thì robot TRÔI THÊM so với phanh gấp. Đo lại APPROACH_DISTANCE sau khi
# bật; dừng sát kệ hơn trước thì HẠ STOP_RAMP_TIME, đừng vội đổi APPROACH_DISTANCE
# (khoảng cách đó còn ràng buộc với vị trí khe pallet).
# ⚠️ 0.12 ĐÃ THỬ TRÊN ROBOT — TIẾN QUÁ. Càng (còn ở sàn lúc tiếp cận) lấn vào khe hở
# dưới gầm kệ, tức robot dừng sát hơn APPROACH_DISTANCE. Hạ 0.12 → 0.06.
# Lưu ý về chính cơ chế này: ramp 4 bậc từ 32% cho ra 24 → 16 → 8, cả ba đều nằm
# TRONG vùng chết (25% motor đã đứng). Nên nó không giảm tốc êm mà là THẢ TRÔI rồi
# mới phanh — vẫn tránh được cú giật phanh, nhưng cái giá là trôi thêm đúng quãng đó.
# Còn lấn gầm kệ thì hạ tiếp 0.06 → 0.03 → 0. Đặt 0 là về đúng hành vi cũ (phanh
# gấp), lúc đó khoảng dừng chắc chắn đúng nhưng cú giật phanh quay lại.
# TUYỆT ĐỐI KHÔNG bù bằng cách tăng APPROACH_DISTANCE: số đó ràng buộc với vị trí
# khe pallet trên kệ, nới ra là bước luồn càng phải bò xa thêm đúng bấy nhiêu.
STOP_RAMP_TIME = 0.06        # Giây giảm dần PWM về 0
STOP_RAMP_STEPS = 4          # Số bậc giảm
STOP_SETTLE_TIME = 0.15      # Giây đứng yên cho khung xe hết chòng chành

APPROACH_TIMEOUT = 5.0       # Timeout tiếp cận / lùi ra (giây)
# ⚠️ 30 QUÁ SÁT VÙNG CHẾT (MOTOR_MIN_DUTY = 30). Đo trên robot 02/08: lùi ra khỏi
# kệ TIMEOUT sau 5s — robot cõng 2 kiện nên càng ì, 30% không đủ thắng ma sát.
# Cùng đúng lý do đã buộc nâng INSERT_SPEED 25 → 32. Nâng 30 → 40.
# Lùi ra là thao tác ÍT RỦI RO nhất để chạy nhanh: phía sau trống, và điểm dừng do
# siêu âm quyết định chứ không phải thời gian. Trong trận mọi tuyến giao đều mở đầu
# bằng lùi, nên chặng này hỏng là hỏng cả lượt.
APPROACH_SPEED = 40          # Tốc độ lùi ra
APPROACH_FAST_SPEED = 60     # Pha xa
# ⚠️ 25 là QUÁ THẤP với JGA25-370 qua L298N (sụt ~2V): robot chỉ nhích từng tí,
# chậm hơn ngưỡng 0.83cm/s của cơ chế chống húc kệ → approach_shelf() bị dừng oan
# giữa đường, báo "càng đã chạm kệ" trong khi còn cách kệ rất xa (đã gặp thật ở
# test_motion option 9: khựng ở 18.9cm trong khi mục tiêu 11.9cm).
# Vùng ~25% là chỗ đường đặc tính duty–tốc độ dựng đứng, không bao giờ ổn định.
# ⚠️ NÂNG 32 → 40. Không phải vì 32 chạy không được (nó chạy được), mà vì LỰC LÁI:
# _forward_guided bám line ở pha này, và lực lái = base − MOTOR_MIN_DUTY. Ở 32 chỉ
# còn ±2 — robot gần như KHÔNG lái được suốt quãng tiếp cận cuối, nên dừng ở tư thế
# nào chịu tư thế đó. Đo trên robot 02/08: robot dừng CHỆCH một chút, bước luồn đâm
# vào theo hướng lệch sẵn, càng vướng mép pallet → IR không xác nhận.
# Đánh đổi: chạy nhanh hơn thì trôi thêm khi dừng. Chấp nhận, vì hai vế không cân —
# sai khoảng cách thì bước luồn (IR dẫn) nuốt được, sai TƯ THẾ thì không gì cứu.
APPROACH_SLOW_SPEED = 40     # Pha gần — đủ trên vùng chết để CÒN lái được (±10)
                             # 25 quá chậm (bò từng tí, bị cơ chế chống húc kệ dừng
                             # oan), 40 vọt quá đà. 32 chạy sạch.
# PHẢI LỚN HƠN ①, không thì pha chậm không bao giờ chạy và robot lao hết tốc độ
# tới tận lúc dừng.
# Hạ 35 → 20 vì ① đã tụt từ 25.0 xuống 11.9: giữ 35 là bắt robot bò suốt 23cm thay
# vì 10cm như thiết kế ban đầu, vừa tốn giây vừa kéo dài đoạn dễ bị dừng oan.
APPROACH_SLOW_DISTANCE = 20  # cm — dưới mức này thì chuyển sang chậm

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
LINE_THRESHOLD = 200         # ADC 0-1023: < ngưỡng = trên line (đen)

# --- Ngưỡng TƯƠNG ĐỐI, tự trôi theo ánh sáng (LineSensor.nguong_cho) ---
# QTR-8A đo PHẢN XẠ: ánh sáng nền tối đi thì nền trắng phản xạ ít hơn, mọi giá trị
# tụt xuống, và mắt ở RÌA vạch rơi xuống dưới LINE_THRESHOLD cố định → bị đếm là
# đen → đủ 4 mắt là báo GIAO LỘ GIẢ giữa đoạn thẳng.
# Đo trên robot buổi tối 02/08: hay nhầm giao lộ dù đang đi trên đường thẳng.
# Thể lệ ghi rõ ánh sáng ở sân thi KHÔNG đảm bảo ổn định, nên đây không phải chuyện
# riêng của buổi tối.
# ⚠️ KHÔNG chữa được bằng cách nâng INTERSECTION_THRESHOLD lên 5: C0R0 là NGÃ BA,
# chỉ cho 4/6 mắt — nâng lên là mất luôn giao lộ thật.
# Ngưỡng = min + (max−min) × FRACTION, tính lại MỖI lần đọc nên trôi theo ánh sáng.
# Khi cả thanh cùng đen (giữa giao lộ) hoặc cùng trắng (mất line) thì dải hẹp hơn
# MIN_RANGE, công thức vô nghĩa → rơi về LINE_THRESHOLD tuyệt đối như cũ.
LINE_ADAPTIVE = True
LINE_ADAPTIVE_FRACTION = 0.30   # 0.3 = ngả về phía TỐI, ưu tiên không nhận nhầm đen
LINE_ADAPTIVE_MIN_RANGE = 250   # ADC: dải hẹp hơn ngần này thì dùng ngưỡng tuyệt đối
# ⚠️ Nhiều module QTR-8A đọc bề mặt ĐEN ra giá trị CAO (ngược giả định của code).
# Chạy `python3 -m tools.calibrate_line` để chốt cờ này — code tự đảo tại nguồn.
LINE_BLACK_IS_HIGH = True
LINE_WEIGHTS = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]   # Lệch trái âm, phải dương
# ĐIỂM ĐẶT của bộ bám line, tính bằng ĐƠN VỊ TRỌNG SỐ (1.0 = một khoảng cách giữa 2
# mắt ≈ 9.5mm). Trừ thẳng vào sai số, nên robot sẽ giữ line ở đúng chỗ này thay vì
# giữa thanh cảm biến.
# ⚠️ ĐO TRÊN ROBOT 02/08, bằng test_motion option 5 (raw ADC), so hai tư thế:
#     robot LỆCH  → mắt 1,2,3 đen → err = −0.50
#     robot CHUẨN → mắt 2,3,4 đen → err = +0.50   ← vị trí càng thẳng khe pallet
# Tức thanh cảm biến LẮP LỆCH TÂM ~5mm so với càng: "line giữa thanh" (err = 0)
# KHÔNG phải "càng thẳng khe pallet". Không có hằng số này thì follow_line chủ động
# kéo robot về đúng chỗ SAI, và mọi lần tiếp cận kệ đều chệch một tẹo — đúng triệu
# chứng đã gặp: càng vướng mép pallet, IR không xác nhận.
# Đặt 0 để tắt (bám giữa thanh như cũ). Đo lại nếu tháo/lắp lại thanh cảm biến.
LINE_CENTER_OFFSET = 0.5
# Duty tối thiểu để bánh CÒN QUAY. Dưới mức này JGA25-370 qua L298N đứng hẳn.
# Dùng để chặn hiệu chỉnh bám line (Motion._clamp_correction): LINE_KP chỉnh cho
# SPEED_DEFAULT = 50, nhưng bám line còn chạy ở 32% (APPROACH_SLOW_SPEED,
# INSERT_SPEED) — ở đó chỉ cần sai số 0.44 là bánh trong tụt xuống dưới vùng chết,
# ĐỨNG HẲN, và robot xoay quanh nó thay vì lượn. Đã gặp thật ở smoke option 2: robot
# đi chệch hướng, một càng thọc sâu hơn càng kia.
# Hệ quả: ở base 32 lực lái chỉ còn ±7. Đó là giới hạn VẬT LÝ — muốn lái mạnh hơn
# thì NÂNG base_speed cho có khoảng hở, đừng bỏ kẹp.
# Đặt 0 để tắt kẹp (về đúng hành vi cũ).
# ⚠️ 25 là SAI: chính config này ghi 25% "robot chỉ nhích từng tí", tức 25 đã nằm
# TRONG vùng không dùng được chứ không phải mép an toàn. Kẹp tới 25 là để bánh trong
# ngồi đúng ngưỡng chết — đo trên robot: luồn càng bò ~5.7cm/s rồi timeout.
# 30 là mép dùng được thật (32 đã xác nhận chạy sạch, test_motion #9).
MOTOR_MIN_DUTY = 30
LINE_KP = 16.0               # CHƯA calibrate thật
LINE_KD = 6.5                # CHƯA calibrate thật
INTERSECTION_THRESHOLD = 4   # Số mắt (/6) thấy line cùng lúc để nhận là giao lộ

# Ngưỡng "đen ĐẬM" — chặt hơn hẳn ngưỡng thích nghi, dùng khi cần BẰNG CHỨNG chứ
# không chỉ cần tín hiệu. Đo trên robot 03/08, cùng một robot cùng một buổi:
#
#   giao lộ C0R0 THẬT     ADC [921, 921,   0,   0,   0,   0]  → 4 mắt đen đậm
#   "giao lộ" lúc căn giữa ADC [224, 232,   0,   0, 263, 826]  → 2 mắt đen đậm
#
# 224 và 232 KHÔNG phải đen — chúng chỉ lọt xuống dưới ngưỡng thích nghi (248) vì
# dải sáng-tối lúc đó hẹp. Đó là MÉP MỜ của vạch R0 khi robot còn xiên, mà bước căn
# giữa thì robot đang xiên theo đúng định nghĩa của nó. Nên đếm theo ngưỡng thích
# nghi là bước căn giữa gần như luôn tự bịa ra một giao lộ.
# 0.15 × 1023 ≈ ADC 153: dưới mức đó là mặt in đen thật, không phải mép vạch.
LINE_STRICT_BLACK = 0.15

# Đo lại khi ĐỨNG YÊN mà GẦN hơn mục tiêu quá mức này → approach_shelf THẤT BẠI,
# không trả True nữa. Đứng gần hơn mục tiêu nhiều nghĩa là có gì đó ở TRƯỚC đã sai
# (pose lệch một giao lộ, route đi lố), và bước kế tiếp — luồn càng — sẽ tiến MÙ
# theo niềm tin "còn cách 11.9cm". Đó chính là cú húc vào kệ ngày 03/08: log đã in
# rõ "bù THIẾU, nâng APPROACH_STOP_MARGIN 8.6 cm" rồi vẫn báo ✅ và đi tiếp.
# Đây là lưới an toàn ĐỘC LẬP với mọi cơ chế điều hướng phía trên: dù pose sai kiểu
# gì, dừng cách kệ 3cm là không thể coi là "đã tới vị trí lấy hàng".
APPROACH_ARRIVAL_TOLERANCE = 4.0   # cm

# --- Rời khỏi giao lộ (Motion._escape_intersection) ---
# Chạy tới khi CẢM BIẾN hết báo giao lộ, không chạy mù một khoảng cố định.
# Bản cũ chạy mù 0.3s — số viết cứng, chưa đo. Đo trên bản in: vạch dọc C0 rộng 20mm
# theo hướng robot đi, ra khỏi tâm ±1.2cm là cảm biến bình thường trở lại. ADVANCE_SPEED
# = 40 nằm không xa vùng chết nên 0.3s có thể chỉ đi 1.5-2cm — đúng ranh giới, và
# smoke option 1 đã gãy thật vì chuyện này ("Advance: gặp giao lộ" ngay tại C0R0).
ESCAPE_MIN_TIME = 0.15       # Giây tối thiểu vẫn chạy, kể cả khi cảm biến đã sạch ngay
# Giây cảm biến phải sạch LIÊN TỤC mới coi là đã ra khỏi giao lộ. Không phải "vài
# nhịp": 3 nhịp chỉ là 30ms, ở ADVANCE_SPEED=40 robot mới nhích ~0.5cm — vừa chớm ra
# khỏi mép vạch chứ chưa qua hẳn, lắc nhẹ là cán lại vào. Robot VẪN CHẠY trong lúc
# chờ đủ khoảng này, nên nó vừa là bộ lọc nhiễu vừa là quãng dư an toàn.
ESCAPE_CLEAR_TIME = 0.25
ESCAPE_MAX_TIME = 1.2        # Chặn trên: hết ngần này mà vẫn báo giao lộ thì bỏ cuộc

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
# Giây tối đa để advance TÌM THẤY line kể từ lúc bắt đầu. Khác hẳn
# LINE_END_CONFIRM_TIME: đó là "thấy rồi mới mất" = hết line (THÀNH CÔNG), còn đây
# là "chưa từng thấy" = robot không nằm trên line (THẤT BẠI). Gộp hai cái làm
# advance báo đã tới kệ trong khi robot vẫn đứng ở giao lộ — xem docstring
# Motion.advance_to_end. Đủ dài để bù 0.3s chạy mù của _escape_intersection, đủ
# ngắn để không lao mù ở ADVANCE_SPEED.
ADVANCE_ACQUIRE_TIME = 0.8
# ✅ ĐO NGÀY 02/08 (tools.check_load_blocks_sonar): KIỆN HÀNG CÕNG KHÔNG CHE SIÊU ÂM.
#     càng ở SÀN 74.6cm · TẦNG 1 76.8cm · TẦNG 2 72.6cm  (phía trước trống)
# Nên luồng giao hàng dùng siêu âm BÌNH THƯỜNG. Cơ chế "chống kiện che" từng thêm
# ngày 02/08 đã bị XOÁ: nó dựa trên giả định sai này và gây 2 lần robot lao vào kệ,
# vì nhánh dự phòng của nó là "đi tới khi hết line" — mà line kéo tới tận chân kệ.
# ⚠️ Bài học: đừng thêm phòng thủ cho một tình huống chưa ai đo. Số đo mất 2 phút.

# ⛔ CHẶN CỨNG của advance_to_end: siêu âm báo dưới mức này là DỪNG, đặt TRƯỚC mọi
# logic khác trong vòng lặp. Giữ lại DÙ giả định "kiện che cảm biến" đã bị bác bỏ —
# nó là lưới an toàn cho MỌI nguyên nhân, không riêng nguyên nhân nào.
# Cần vì nhánh "đi tới khi hết line" của advance VỀ BẢN CHẤT là đâm vào kệ: line kéo
# tới cách chân kệ 1mm (SA_BAN.md mục 3b). Nhánh đó chỉ an toàn ở khu nhà máy, nơi
# line dừng ở mép khu.
# An toàn với hàng đang cõng: kiện đọc 72-77cm, xa hơn mốc này rất nhiều.
# Giây tối đa được phép DI CHUYỂN trên một số đo siêu âm KHÔNG ĐỔI, khi tiếp cận kệ.
# Quá mức này thì DỪNG và chờ số mới, thay vì chạy mù.
# Đo trên robot 03/08: số đo đứng yên ở 16.3cm suốt 0.7 giây rồi nhảy thẳng xuống
# 5.9cm — robot chạy mù hết 0.7s đó và vượt điểm dừng ~10cm, lao vào kệ. Cơ chế
# APPROACH_NO_PROGRESS_TIME = 1.2s không bắt được vì đóng băng ngắn hơn thế.
# Gốc rễ: gpiozero bấm giờ xung echo bằng PHẦN MỀM (cảnh báo PWMSoftwareFallback mỗi
# lần khởi động) nên luồng nền có lúc kẹt. Cách sửa gốc là cài pigpio — xem
# docs/PHAN_CUNG.md. Hằng số này chỉ đổi "vượt đà" thành "khựng một nhịp".
ULTRASONIC_STALE_TIME = 0.15

ADVANCE_HARD_STOP_CM = 11.9

ADVANCE_TIMEOUT = 6.0

# --- advance_to_end: chống MÙ SIÊU ÂM ------------------------------------
# advance_to_end có 3 lối dừng, nhưng chỉ 2 lối đầu cần siêu âm. Lối thứ ba
# ("hết line") KHÔNG cần — và ở kệ thì nó CHÍNH LÀ ĐÂM VÀO KỆ: vạch line kéo
# tới cách chân kệ 1mm (docs/SA_BAN.md mục 3b). Nên siêu âm mù = robot chạy
# thẳng vào kệ, không cơ chế nào chặn được. approach_shelf đã có
# APPROACH_BLIND_TIMEOUT lo chuyện này từ lâu; advance_to_end thì không.
#
# Đo trên robot 03/08: sau khi dừng trước kệ, đo lại lúc ĐỨNG YÊN ra 100.0cm
# = kịch trần = MẤT TIẾNG VỌNG, trong khi kệ đang ở ngay trước mũi.
ADVANCE_BLIND_TIMEOUT = 2.5   # Giây: chưa từng thấy gì ≤ APPROACH_DETECT_DISTANCE
                              # thì DỪNG. Ở kệ, mục tiêu cách giao lộ 35.4cm nên
                              # nhịp ĐẦU TIÊN đã phải thấy (ngưỡng 45cm). Để rộng
                              # cho chặng vào khu nhà máy — chặng đó dài hơn.
ADVANCE_MAX_RANGE_CM = 99.0   # ≥ mức này coi như KỊCH TRẦN (mất tiếng vọng),
                              # không phải "mục tiêu ở xa"
ADVANCE_LOST_ECHO_COUNT = 3   # Số nhịp kịch trần LIÊN TIẾP, SAU KHI đã thấy mục
                              # tiêu, thì dừng. Đây mới là ca giết robot: thấy
                              # 30→25→22 rồi 100,100,100 mà vẫn chạy tiếp.

# --- Cửa sổ ÂN HẠN đầu advance -------------------------------------------
# advance_to_end() luôn khởi hành khi robot ĐANG ĐỨNG TRÊN một giao lộ, và mở đầu
# bằng _escape_intersection() để rời khỏi nó. Nhưng escape có CHẶN TRÊN
# (ESCAPE_MAX_TIME) và đo trên robot 03/08 thì nó thường xuyên CHẠM TRẦN rồi bỏ
# cuộc chứ không thoát được:
#
#     Rời giao lộ: hết 1.21s mà cảm biến vẫn báo giao lộ
#     Advance: ... Vệt: 0.00s:30.1        ← mới đi được ~5cm khỏi C0R0 (kệ 35.4cm)
#
# Khi đó nhịp đọc đầu của advance có thể thấy lại CHÍNH giao lộ đó và báo "bản đồ
# không khớp" → dừng hẳn giữa đường. Chạy 5 lượt option 5: 3 đúng, 2 sai — đúng
# kiểu của một ranh giới, không phải một lỗi logic.
#
# Nới ESCAPE_MAX_TIME là hướng SAI: escape chạy forward() THẲNG, KHÔNG LÁI, mà kệ
# chỉ cách 35.4cm — cho chạy mù lâu hơn là đổi lỗi này lấy lỗi khác. Thay vào đó
# cho advance bỏ qua ĐÚNG MỘT giao lộ trong cửa sổ đầu: nó chỉ có thể là cái vừa
# thoát. Phần đi thêm khi đó nằm dưới BÁM LINE (có lái), không phải chạy mù.
ADVANCE_START_GRACE = 0.6   # giây kể từ sau escape


# --- XÁC NHẬN LẠI KHI ĐỨNG YÊN -------------------------------------------
# Đo trên robot 03/08 (tools.check_sonar_jitter, 30 giây): robot ĐỨNG YÊN cho
# 997 mẫu, trung vị 74.6cm, độ lệch chuẩn 0.20cm, KHÔNG một mẫu nào lệch quá
# 2cm và KHÔNG mẫu nào kịch trần. Cảm biến hoàn toàn tốt.
# Nhưng CÙNG cảm biến đó, lúc ĐANG CHẠY, báo 4.6cm khi kệ ở ~35cm — hai lần
# liên tiếp, ổn định. Khác biệt duy nhất: động cơ đang quay. gpiozero bấm giờ
# xung echo bằng PHẦN MỀM (cảnh báo PWMSoftwareFallback), nên nhiễu L298N hoặc
# CPU bị tranh chiếm sinh ra xung giả rất ngắn — 4.6cm ≈ 268µs, đúng cỡ một gai.
# pigpio (bấm giờ phần cứng) chữa tận gốc nhưng phantom chưa tải được gói.
#
# Vá theo đúng thứ vừa đo được: cảm biến ĐÁNG TIN KHI ĐỨNG YÊN, nên mọi quyết
# định DỪNG đều phải hỏi lại lúc đứng yên. Dừng thì luôn an toàn; còn tin nhầm
# một gai nhiễu thì robot đứng cách kệ 35cm mà tưởng đã tới — rồi bước luồn
# càng tiến lên mù và HÚC THẲNG VÀO KỆ. Đó chính là lỗi ngày 03/08.
ULTRASONIC_VERIFY_TOLERANCE = 5.0  # cm: đo lại lệch quá mức này = số lúc chạy
                                   # là gai nhiễu, không phải khoảng cách thật
ULTRASONIC_MAX_GLITCH = 3          # Số lần bỏ qua gai nhiễu tối đa mỗi chặng.
                                   # Hết quota thì TIN số đo và dừng — thà dừng
                                   # sớm còn hơn lặp vô hạn cạnh kệ.

# ============================================================
# LÙI RA KHỎI KỆ / NHÀ MÁY — lệnh ("back", N)
# ============================================================
# Rút khỏi điểm cuối bằng cách LÙI thay vì xoay 180° rồi tiến. Mỗi lần bỏ được 2 lần
# xoay; đo trên toàn bộ 6 lượt thì bớt ~28 lần xoay ở kịch bản tệ nhất (~34s) — chi
# phí cố định lớn nhất của trận. Robot vẫn BÁM LINE khi lùi (thanh cảm biến ở đầu xe
# lúc này thành đuôi), không chạy mù.
# ⚠️ NÂNG 35 → 40, cùng lý do: ở 35 lực lái chỉ còn ±5. Mà lùi bám line là chặng
# TINH TẾ NHẤT (thanh cảm biến thành đuôi, hiệu chỉnh phải đảo dấu) và nó mở đầu
# MỌI tuyến giao hàng — ~28 lần mỗi trận.
REVERSE_SPEED = 40           # Đủ trên vùng chết để CÒN lái được (±10)
REVERSE_TIMEOUT = 8.0
EDGE_COST_REVERSE = 1        # Phụ phí so với tiến 1 giao lộ → hoà thì vẫn ưu tiên tiến

# Sau khi lùi tới giao lộ, thân xe nằm QUÁ giao lộ một đoạn bằng khoảng cách từ trục
# bánh tới thanh cảm biến (tiến thì thân nằm trước giao lộ đúng bấy nhiêu). Nếu xoay
# xong hay bị trượt line thì đặt số giây tiến bù ở đây (đo bằng test_motion option 15).
# Đo trên robot: sau khi lùi tới giao lộ, trục bánh dẫn động nằm QUÁ vạch ngang
# 12cm — đúng bằng khoảng cách trục → thanh cảm biến. Cần tiến bù đoạn đó để tâm
# xoay về đúng giao lộ.
# Dò trên robot: 1.5s thì tiến QUÁ vạch một chút → 35% duty đi hơn 12cm trong 1.5s,
# tức ~90mm/s (nội suy lý thuyết cho 65mm/s, thực tế nhanh hơn). 12cm ÷ 90mm/s ≈ 1.3s.
# Tiến bù là tiến VỀ PHÍA KỆ nên thà thiếu còn hơn thừa.
# ⚠️ TỐC ĐỘ của đoạn tiến bù — TÁCH RIÊNG khỏi REVERSE_SPEED. Đoạn này chạy MÙ theo
# thời gian nên quãng đường tỉ lệ thẳng với tốc độ: đổi tốc độ là 1.3s mất hiệu lực.
# 35 là tốc độ mà 1.3s ĐƯỢC ĐO RA (xem ghi chú ngay trên). Đã gặp thật: nâng
# REVERSE_SPEED 35 → 40 làm robot tiến bù quá vạch, xoay phải xong thanh cảm biến đã
# qua khỏi giao lộ → mất line (option 8).
# Đổi số này thì PHẢI đo lại REVERSE_RECENTER_TIME bằng test_motion option 15/18.
# Dùng cho CẢ HAI chiều, vì cả hai đều cần tiến thêm đúng 12cm (khoảng cách trục
# bánh → thanh cảm biến):
#   sau khi LÙI tới giao lộ  : trục đã QUÁ vạch 12cm  → tiến bù về
#   sau khi TIẾN tới giao lộ : trục còn CÁCH vạch 12cm → tiến bù tới
# Không bù ở chiều tiến thì xoay tại chỗ là quay quanh điểm nằm TRƯỚC giao lộ, xoay
# xong thanh cảm biến văng ra vùng trắng. Đo trên robot (smoke option 8):
#     xoay sau khi LÙI  → [0,0,0,1,1,0]  còn thấy line
#     xoay sau khi TIẾN → [0,0,0,0,0,0]  TRẮNG HẾT → mất line, route gãy
# (BACK_MIN_TRAVEL_TIME đã BỎ — xem back_to_intersection.)
# Điều kiện chặn giao lộ giả khi lùi giờ là "phải thấy VẠCH LINE THƯỜNG ít nhất một
# lần trước đã", không phải một mốc thời gian. Mốc thời gian phụ thuộc cm/s mà cm/s
# chưa ai đo — đặt 0.6s thì lùi nhanh hơn ước lượng là nuốt luôn giao lộ THẬT, robot
# lùi tiếp, mà từ C0R0 về phía đông giao lộ kế cách 100cm. Đã gặp ở option 5.

REVERSE_RECENTER_SPEED = 35
REVERSE_RECENTER_TIME = 1.3
# Giây tiến bù TRƯỚC KHI XOAY, khi vừa TIẾN tới giao lộ (chặng "forward" ngay trước
# lệnh xoay). TÁCH RIÊNG khỏi REVERSE_RECENTER_TIME để chỉnh/tắt được độc lập —
# hai chiều dừng ở hai mép khác nhau của vạch nên quãng bù có thể không bằng nhau.
#   ĐẶT 0 = TẮT HẲN, về đúng hành vi trước ngày 02/08.
# Vì sao cần: thanh cảm biến ở đầu xe, trục bánh cách nó 12cm về sau. Tiến tới giao
# lộ thì cảm biến TRÊN vạch còn trục còn CÁCH vạch 12cm — xoay lúc đó là quay quanh
# điểm nằm TRƯỚC giao lộ, xoay xong cảm biến văng ra vùng trắng. Đo trên robot
# (smoke option 8): xoay sau khi LÙI → [0,0,0,1,1,0] còn thấy line;
#                   xoay sau khi TIẾN → [0,0,0,0,0,0] TRẮNG HẾT → route gãy.
# ⚠️ CHƯA CHỐT ĐƯỢC GIÁ TRỊ. 1.3 lấy tạm từ chiều lùi (≈12cm ở 35%). Bù THỪA thì
# robot đi quá giao lộ rồi mới xoay — cũng lệch, chỉ là lệch phía kia. Chỉnh dần
# 1.3 → 0.9 → 0.6 và xem cảm biến ngay sau khi xoay (log "Rời giao lộ ... cảm biến"):
# còn thấy line = đúng, trắng hết = còn sai.
TURN_RECENTER_TIME = 1.3

# ============================================================
# CHI PHÍ TÌM ĐƯỜNG (navigation.py) — quy đổi ra "1 giao lộ đi thẳng"
# ============================================================
ROUTE_TURN_COST = 2          # Giá 1 lần xoay 90°
ADVANCE_COST = 2             # Giá lệnh ("advance",)
EDGE_COST_START_GAP = 3      # Phụ phí đoạn ngang R0 (trôi qua khoảng đứt ô xuất phát)

# ============================================================
# CAMERA & NHẬN DIỆN KIỆN HÀNG
# ============================================================
# ⚠️ ĐỔI ĐỘ PHÂN GIẢI LÀ PHẢI CHỤP LẠI TOÀN BỘ ẢNH MẪU ORB — ảnh mẫu cắt ở độ phân
# giải này, đem so với khung ở độ phân giải khác là tự chuốc lệch tỉ lệ.
# 1296x972 thay cho 640x480: gấp đôi mỗi chiều, gấp bốn pixel, CÙNG tỉ lệ 4:3 nên mọi
# hằng số ROI (tính theo phần trăm) giữ nguyên hiệu lực.
# Lý do: kiện ở TẦNG 1 nằm xa camera nên hiện ra rất nhỏ — ở 640x480 ảnh mẫu tầng 1
# chỉ 178x130 với 130-220 keypoint, và kiện THẬT ở tầng 1 chỉ đạt 9 inlier, trong khi
# ô TRỐNG ở tầng 2 cũng cho 10 inlier. Hai ca cùng dấu vân tay, không ngưỡng nào tách
# được. Ở 1296x972 vùng đó thành ~356x260, đủ chi tiết để tách.
# Chi phí đo trên Pi 4: classify_pair 360ms → 585ms, tức +225ms mỗi lần quét, cả trận
# 6 lượt ≈ +1.4s trên ngân sách 240s.
CAMERA_RESOLUTION = (1296, 972)
# Hạ 0.20 → 0.12 để HANA đủ tư cách lên tiếng. Decal hana nền TRẮNG nên dải amkor
# ("vô sắc và sáng") luôn ăn nhiều pixel hơn — trên kiện hana thật: amkor 47.0% còn
# hana chỉ 15.4%. Hana không cần thắng amkor về SỐ pixel, vì màu đỏ của nó là đặc
# trưng RIÊNG, sạch hơn hẳn mọi thứ khác:
#     điểm dải hana trên kiện hana 15.4%, trên 3 loại kia chỉ 0.6-0.9% → chênh >20x
# Nó chỉ cần vượt ngưỡng để cơ chế ưu tiên nhãn chromatic (CHROMATIC_LABELS) kích
# hoạt và chặn amkor lại.
# ⚠️ PHẢI đi kèm việc nâng sàn S của samsung lên 90. Hạ ngưỡng một mình thì samsung
# (31.1% trên kiện AMKOR) sẽ thắng ở ô đó — chữa ô này hỏng ô kia.
CONFIDENCE_THRESHOLD = 0.08  # Tỷ lệ pixel tối thiểu (đường HSV)
# Hạ tiếp 0.12 → 0.08. Ở 0.12, hana chỉ vượt ngưỡng đúng 0.5 điểm phần trăm
# (đo được 12.5%) — ánh sáng đổi chút hoặc robot dừng lệch vài mm là tụt xuống dưới,
# cơ chế ưu tiên chromatic không kích hoạt, và amkor (23.9%) thắng. ĐÃ GẶP THẬT.
# Toàn bộ số đo cho thấy có một khoảng trống rất rộng để đặt ngưỡng vào giữa:
#     dải hana trên kiện hana thật : 12.5% – 26.9%
#     dải hana trên 3 loại kia     :  0.6% –  1.3%
#     dương tính giả của samsung/foxconn sau khi siết sàn S: 0.7% – 4.9%
# 0.08 nằm trên mọi dương tính giả đo được, mà vẫn để hana dư 1.6x ở ca xấu nhất.
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
                             # CHỈ dùng cho đường CŨ không biết tầng (classify_package
                             # không truyền level). Đường quét cặp dùng bộ 3 dưới đây.

# --- VÙNG QUÉT THEO TẦNG — ⚠️ SAI LÀ NHẬN DIỆN KHÔNG BAO GIỜ ĐÚNG ---------------
# Camera gắn CỐ ĐỊNH vào thân robot, nên tầng 1 và tầng 2 rơi vào hai độ cao KHÁC
# NHAU trong khung hình. Kệ lúc thi đấu có hàng ở CẢ HAI tầng, nên một khung cắt
# giữa cố định sẽ ôm trọn hai loại kiện khác nhau cùng lúc → HSV trộn màu 2 kiện,
# ORB so một vùng chứa 2 decal với ảnh mẫu 1 decal. Không ngưỡng nào cứu được.
#
# Đo trên robot thật (khung 640x480, siêu âm 10.8cm, càng sát kệ):
#     kiện tầng 2: y ≈  75..215, tâm 145  → 145/480 = 0.30
#     kiện tầng 1: y ≈ 300..430, tâm 365  → 365/480 = 0.76
# ĐO LẠI khi đổi góc camera / chiều cao lắp / khoảng cách dừng: chụp bằng
# `tests/test_vision.py` option 1 rồi đọc toạ độ kiện trong khung.
# Đo lại ở 1296x972 với hàng ở cả 4 ô (số cũ đo hồi còn 640x480):
#     kiện tầng 2 ở y 140..430, kiện tầng 1 ở y 620..860
#     ROI cũ tầng 1 = y 556..920 → 60px CUỐI là sàn lộ ra dưới kệ, và VẠCH XANH TÍM
#     của sa bàn ở đó rơi đúng dải hue samsung: trên kiện hana thật, samsung ăn
#     11-12% chỉ nhờ dải y 856..916, đủ để vượt mặt hana (9.4%).
# Thu chiều cao 0.375 → 0.30 và dịch tâm tầng 1 0.76 → 0.74 để cắt đúng phần đó:
#     tầng 2 → y 143..435 (kiện 140..430, vừa khít)
#     tầng 1 → y 573..865 (kiện 620..860, bỏ được dải sàn)
ROI_Y_CENTER = {1: 0.74, 2: 0.295}  # tâm dọc vùng quét theo tầng (tỉ lệ chiều cao)
ROI_HEIGHT = 0.30            # chiều cao vùng quét (tỉ lệ) ≈ 292px
ROI_MARGIN_X = 0.10          # cắt ngang mỗi bên của NỬA khung. 0.2 xén hụt cả 2 mép:
                             # kiện trong nửa trái trải x≈20..270 mà ROI chỉ lấy 64..256
CENTER_WEIGHT_SIGMA = 0.85   # Trọng số Gauss theo khoảng cách tới tâm ROI: pixel nền
                             # ở rìa tính nhẹ hơn. Giảm → tập trung tâm mạnh hơn.
NO_CENTER_WEIGHT_LABELS = ("hana_micron",)   # Hana đếm đều toàn ROI (ngoặc đỏ ở góc)

# Dải HSV (OpenCV H=0-179, S/V=0-255). Nhiều dải nếu màu wrap qua 0.
# Calibrate: python3 -m tools.calibrate_vision (chạy lại nếu đổi ánh sáng/camera).
# Chốt bằng `python3 -m tools.calibrate_vision` chạy ở TẦNG 2, trên robot thật,
# sau khi ROI đã dịch theo tầng (commit 01e023a) — bộ số trước đó chốt trên vùng
# vắt ngang 2 tầng nên không dùng lại được.
COLOR_RANGES = {
    # ⚠️ Sàn S nâng 52 → 90 BẰNG TAY. Decal "Al Aluminum" của amkor có nền xanh xám
    # nhạt, rơi đúng dải hue này — đo trên kiện amkor thật: dải samsung ăn 31.1% còn
    # dải amkor chỉ 18.5%, tức HSV gọi kiện amkor thành samsung. Chip xanh của samsung
    # là màu IN ĐẬM còn ánh xanh trên nhôm thì nhạt, nên tách được bằng độ bão hoà:
    #     S>=52 : samsung thật 33.3% / amkor giả 16.7%  → 2.0x  ❌
    #     S>=90 : samsung thật 23.4% / amkor giả  5.7%  → 4.1x  ✅
    # Đừng nâng quá 110: samsung thật tụt còn 20.3%, sát ngưỡng, thiếu dư địa khi
    # ánh sáng tối đi.
    "samsung": [                                # chip xanh dương
        ([85, 90, 21], [116, 255, 226]),
    ],
    "foxconn": [                                # chip vàng đồng
        ([11, 49, 29], [42, 206, 232]),
    ],
    # ⚠️ V bị SIẾT BẰNG TAY 44→130 và 231→230, KHÔNG dùng nguyên số tool đề xuất.
    # Amkor là nhãn ACHROMATIC nên dải của nó phủ mọi hue ở S thấp — mà khung kệ
    # đen và mặt bàn trắng cũng vô sắc. Với dải gốc [0,0,44]-[179,52,231] thì
    # KỆ TRỐNG khớp 41.6%, tự nó vượt CONFIDENCE_THRESHOLD=0.20 → ô trống bị đọc
    # thành amkor (chính tool cũng cảnh báo).
    # Đo trên ROI tầng 2 nửa trái, so khung kệ trống với khung có kiện amkor:
    #     kệ trống : V p5=36  p25=97  p50=159 p75=246 p95=254  (đen ở dưới, bàn trắng ở trên)
    #     có amkor : V p5=42  p25=141 p50=170 p75=190 p95=221  (decal nhôm nằm giữa)
    #     V 44..231 → trống 41.6% / amkor 79.5%   ❌
    #     V 130..230 → trống 14.8% / amkor 68.9%  ✅ dưới ngưỡng
    # Đo lại bằng cùng cách nếu đổi ánh sáng hoặc đổi màu kệ.
    "amkor": [                                  # khối nhôm xám bạc
        ([0, 0, 130], [179, 52, 230]),
    ],
    "hana_micron": [                            # QR viền đỏ (wrap qua 0)
        ([0, 51, 32], [17, 189, 239]),
        ([165, 51, 32], [179, 189, 239]),
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
# CHẶN TRÊN cho cửa sổ mù khi rời ô xuất phát — bỏ qua cảm biến trong khoảng này.
# Cần vì ô xuất phát nằm trong khoảng đứt của R0 và chỗ đó IN HÌNH MASCOT, mặt robot
# đen tuyền: không có bước mù thì exit_start_zone() bắt "line" ngay mẫu đầu tiên rồi
# căn giữa trên mặt con mascot.
#
# Đo trên bản in, dọc vệt thanh cảm biến (docs/SA_BAN.md mục 3c):
#     −10 → 10.2cm : MASCOT, tới 14/23 px đen — robot NGỒI TRÊN vùng này
#     10.2 → 21.9  : sạch
#     21.9cm →     : line R0 thật (7/23 px)
#     51.2cm       : giao lộ C0R0
# → cửa sổ mù phải kết thúc trong 10.2..51.2cm. Ngắn quá thì vẫn dính mascot; dài
#   quá thì vượt C0R0 mà không đếm, và ("forward", 1) sau đó chạy tới tận kệ.
#
# BÌNH THƯỜNG KHÔNG DÙNG TỚI SỐ NÀY. exit_start_zone() thoát cửa sổ mù ngay khi ĐI
# QUA HẾT vùng in (thấy đen rồi thấy sạch) — bám theo hình in, nên đúng ở mọi tốc độ
# và mọi chỗ đặt. Hằng số dưới chỉ là chặn trên cho trường hợp robot được đặt ở chỗ
# KHÔNG có hình in nào dưới cảm biến, lúc đó không có gì để "thấy đen rồi sạch".
#
# 1.5s an toàn khi robot chạy ≤ 34cm/s (1.5 × 34 = 51cm, sát C0R0). Nếu đo được
# nhanh hơn thế thì phải hạ xuống. Cách đo: forward 1.0s ở EXIT_START_SPEED trên sàn
# thi, đo bằng thước ra cm/s; giá trị an toàn = 45 / (cm/s).
EXIT_START_BLIND_TIME = 1.5
# Nới 0.4 → 1.0: robot vượt khoảng đứt ở ô xuất phát bằng forward() MÙ (không lái),
# hai bánh chưa cân nên nó tới line theo đường CHÉO — chạm mép line rồi mà 0.4s chưa
# đủ để bám vào và duỗi thẳng, thành ra vào route với hướng lệch sẵn.
# ⚠️ Đây chỉ là ĐỠ TRIỆU CHỨNG. Gốc rễ là forward() không chạy thẳng — sửa bằng
# test_motion option `f` (calibrate PWM_COMPENSATION bằng encoder). Mọi chỗ chạy mù
# khác (tiếp cận kệ, luồn càng, lùi ra) đều lệch theo cùng nguyên nhân.
# Đừng nới quá tay: căn lâu quá thì robot bám line tới tận giao lộ C0R0, lúc đó lệnh
# "tiến 1 giao lộ" của route sẽ đếm sang giao lộ KẾ TIẾP và đi lố.
# (Viết trên phantom trước 02/08. Hai chi tiết nay đã lạc hậu: khoảng đứt KHÔNG phải
#  245mm — số đó là bề rộng con mascot TRẮNG, do tiêu chí quét thang xám đếm nhầm nền
#  xanh bão hoà là line; xem docs/SA_BAN.md mục 3b/3c. Và bước dò nửa sân đã tắt.)
EXIT_START_ALIGN_TIME = 1.0  # Giây bám line ngắn để căn giữa sau khi chạm line

MATCH_DURATION = 240
SAFETY_MARGIN = 10           # Giây dừng sớm trước khi hết giờ

# NV2 (30đ) chỉ được làm SAU khi xong 100% NV1, và tốn khoảng 20-25s cho cả chuyến
# nhà máy → Kệ 4 → nhấc → liên hợp → thả. Dùng chung SAFETY_MARGIN (10s) thì robot
# vẫn khởi hành khi còn 15s — chuyến chắc chắn không kịp, lại kết thúc trận trong
# lúc đang chạy giữa sân thay vì đứng yên. Đo lại bằng tools.measure_phases rồi
# chỉnh cho khớp thời gian NV2 thật.
TASK2_MIN_TIME = 30          # Giây tối thiểu còn lại thì mới bắt đầu NV2
TURN_TIME = 0.95             # 0.5 (số của motor CŨ) chỉ quay được 45° trên JGA25-370
                             # → nhân đôi, trừ hao phần tăng tốc đầu mỗi lượt xoay
                             # (kéo dài gấp đôi cho HƠN gấp đôi góc).
                             # ⚠️ Mới xác nhận xoay TRÁI đạt 90° (test_motion op.10);
                             # xoay PHẢI chưa kiểm riêng. TURN_TIME dùng CHUNG cho cả
                             # 2 chiều nên nếu 2 chiều lệch nhau thì không giá trị nào
                             # đúng cả hai — lúc đó vấn đề ở bù PWM, không ở đây.
                             # SPEED_TURN phải CHỐT trước, đổi sau là sai lại toàn bộ.

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
