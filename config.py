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
LIFT_TIME_SHELF_1 = 0.55
LIFT_TIME_SHELF_2 = 3.65  # ĐO trên robot 04/08 (PIN ĐẦY — pin yếu cho 4.20); đội cộng thêm 0.1 rồi 0.15

# Không có limit switch — home_to_floor() hạ liên tục bấy nhiêu giây để ép chạm đáy.
LIFT_HOME_DURATION = 4.3   # min_home_duration() = LIFT_TIME_SHELF_2 + LOWER_EXTRA lớn

# Bù lệch 2 càng theo VỊ TRÍ TUYỆT ĐỐI: thời gian từ SÀN lên tầng n = LIFT_TIME_SHELF_n
# + bù. Thời gian mỗi lần chạy = hiệu 2 mốc (Lift._level_time) → không cộng dồn khi đi
# 0→1→2, và càng lẻ dùng chung hệ số với khi chạy cả 2 càng.
LIFT_LEFT_EXTRA = -0.150         # Càng TRÁI khi nâng
LIFT_RIGHT_EXTRA = 0.100         # Càng PHẢI khi nâng

# Bù RIÊNG THEO TỪNG TẦNG khi nâng — GHI ĐÈ hai hằng số trên cho tầng có mặt ở đây.
# Vì sao cần: LIFT_*_EXTRA áp cho MỌI tầng, nhưng độ lệch 2 càng KHÔNG tỉ lệ với độ
# cao. Đo trên robot 03/08: tầng 1 hai càng khớp, tầng 2 CÀNG PHẢI NÂNG THIẾU nên
# luồn vào không tới khe pallet — lùi ra chỉ càng trái bốc được kiện.
# Dây curoa mỗi bên căng khác nhau, và độ trượt tăng theo quãng chạy, nên sai lệch
# ở tầng 2 (3.9s) lớn hơn hẳn tầng 1 (0.8s). Một hằng số cho cả hai tầng không tả
# được chuyện đó.
# Để {} là dùng hằng số chung như cũ. Chốt bằng test_lift option e, CHỌN TỪNG TẦNG.
LIFT_LEFT_EXTRA_BY_LEVEL: dict[int, float] = {}
LIFT_RIGHT_EXTRA_BY_LEVEL: dict[int, float] = {}

# Nâng THÊM bấy nhiêu giây ở bước chuẩn bị LUỒN CÀNG (raise_to_insert), so với độ
# cao tầng bình thường. Càng nhỉnh hơn đáy khe pallet một chút thì mũi càng không
# vướng mép dưới của khe khi bò vào.
# ⚠️ CHỈ áp cho bước luồn. Độ cao dùng ở mọi chỗ khác (thả hàng, home, đi lại)
# không đổi — nếu cộng vào LIFT_TIME_SHELF_n thì mọi bước đều bị đội lên theo.
# `_current_level` giữ nguyên là tầng đó, giống hệt cách lift_off() làm: phần dôi
# ra nằm NGOÀI thang tầng, và home_to_floor() xoá sạch sai lệch tích luỹ.
LIFT_INSERT_EXTRA = 0.20
LIFT_LEFT_LOWER_EXTRA = 0.250     # Càng TRÁI khi hạ — ĐÃ ĐO trên robot 03/08
LIFT_RIGHT_LOWER_EXTRA = 0.350      # Càng PHẢI khi hạ — ĐÃ ĐO trên robot 03/08

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
LIFT_PICKUP_RAISE_TIME = 0.4    # ĐANG DÒ (measure_pickup ⑤ đo được 0.2, không đủ)

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
INSERT_TIMEOUT = 8.0         # Giây, IR không báo thì dừng. NÂNG 6.0 → 8.0 vì bỏ
                             # bước tiếp cận: càng phải bò từ ~20cm thay vì ~9cm.
                             # Chặn cứng thật giờ là ENCODER (xem INSERT_STALL_*),
                             # không phải timeout này.

# --- CHẶN KẸT BẰNG ENCODER khi luồn càng ---------------------------------
# INSERT_MIN_DISTANCE dựa vào siêu âm, và ĐO NGÀY 03/08 CHO THẤY NÓ VÔ DỤNG ở đây:
# đặt robot cách kệ ĐÚNG 12cm (đo bằng thước), cảm biến báo 35.7cm với σ = 3.24cm.
# Giá kệ in 3D có mặt trước HỞ nên chùm siêu âm lọt qua và dội về từ vật cách ~36cm
# phía sau. Nó chỉ THỈNH THOẢNG quét trúng cạnh khung — nên lúc đúng lúc sai, đúng
# kiểu "lúc dừng đúng, lúc chui vào gầm kệ" đuổi suốt hai ngày.
# Cùng cảm biến đó ngoài chỗ trống đọc σ = 0.20cm trên 997 mẫu, nên KHÔNG phải nó hỏng.
#
# Encoder thì không cần calibrate cm cho việc này — chỉ cần biết bánh CÓ QUAY không.
# Càng chạm kệ là bánh kẹt, xung im ngay. Đó là chặn cứng đúng bản chất hơn hẳn.
INSERT_STALL_TIME = 0.5      # Giây cửa sổ xét kẹt
INSERT_STALL_PULSES = 3      # Tổng xung 2 bánh trong cửa sổ, dưới mức này = KẸT
INSERT_STALL_GRACE = 0.5     # Giây đầu bỏ qua — motor còn đang khởi động

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

# ĐEN SÂU — phải có ÍT NHẤT MỘT mắt đọc dưới mức này thì mới là VẠCH LINE THẬT.
# Vạch line in đen tuyền nên mắt nằm trên nó đọc ~0. Mảng IN trên sa bàn (vòng
# tròn ROBOCON, tấm ảnh nhà máy, hình mascot) thì xam xám — tối nhất cũng chỉ ~53.
# Số đo trên robot 03/08, tất cả đều là "≥4 mắt đen đậm" nên bộ lọc cũ cho qua hết:
#
#   GIAO LỘ THẬT   ADC [917, 914,   0,   0,   0,   0]   tối nhất   0
#                  ADC [265, 246,   0,   0,   0,   0]   tối nhất   0
#                  ADC [396, 420,  74,   0,   0,   0]   tối nhất   0
#   MẢNG IN        ADC [120, 154,  69, 142, 111, 127]   tối nhất  69  ← vòng tròn ROBOCON
#                  ADC [141, 119,  53, 148, 101, 131]   tối nhất  53  ← tấm in nhà máy
#                  ADC [ 56, 139,  73, 197, 171, 208]   tối nhất  56
#
# Đây là dấu hiệu tách được hai loại, khác với ĐỘ SÁNG (đã thử và loại: ngã tư
# thật cho cả 6 mắt đọc 0 nên "phải có mắt sáng" là sai).
# 0.04 × 1023 ≈ ADC 41 — nằm giữa 0 và 53, cách xa cả hai phía.
LINE_DEEP_BLACK = 0.06
# Đòi ÍT NHẤT bấy nhiêu mắt đen sâu. Đếm SỐ MẮT chắc hơn hẳn nhìn mắt tối nhất —
# số đo trên robot (cột phải là số mắt ≤61):
#     giao lộ            0,0,0,0,74/52    → 3, 4, 4, 5, 6 mắt
#     vòng tròn ROBOCON  min 69           → 0 mắt
#     tấm in nhà máy     min 53, 56       → 1 mắt
# Biên giữa hai nhóm là 1↔3, rộng gấp nhiều lần so với so mắt tối nhất (34↔53).
# ⚠️ 2 LÀ QUÁ THẤP — nó nằm ĐÚNG trên ranh giới. Đo lại trên robot 04/08, chặng
# rời kệ đi giao hàng, số mắt ≤ LINE_DEEP_BLACK:
#     giao lộ THẬT :  [306, 372, 0, 0, 0, 46] → 4      [0,0,0,0,0,0] → 6
#                     (các lần đo trước: 3, 4, 4, 6)
#     TẤM IN       :  [0, 91, 51, 133, 101, 116] → 2   [0, 220, 95, 198, 138, 150] → 1
#                     [0, 38, 126, 250, 194, 165] → 2  (trước đó: 0, 1, 1)
# Với mốc 2, tấm in [0, 91, 51, ...] LỌT: cả 6 mắt đều ≤ LINE_STRICT_BLACK nên
# điều kiện đầu đạt, và đúng 2 mắt (0 và 51) lọt xuống dưới 61. Robot đếm mảng in
# thành giao lộ, lệch hàng, rồi THẢ HÀNG Ở LOGO TRUNG TÂM.
# Mốc 3 tách sạch: thật ≥3, in ≤2.
LINE_DEEP_BLACK_COUNT = 3

# Đo lại khi ĐỨNG YÊN mà GẦN hơn mục tiêu quá mức này → approach_shelf THẤT BẠI,
# không trả True nữa. Đứng gần hơn mục tiêu nhiều nghĩa là có gì đó ở TRƯỚC đã sai
# (pose lệch một giao lộ, route đi lố), và bước kế tiếp — luồn càng — sẽ tiến MÙ
# theo niềm tin "còn cách 11.9cm". Đó chính là cú húc vào kệ ngày 03/08: log đã in
# rõ "bù THIẾU, nâng APPROACH_STOP_MARGIN 8.6 cm" rồi vẫn báo ✅ và đi tiếp.
# Đây là lưới an toàn ĐỘC LẬP với mọi cơ chế điều hướng phía trên: dù pose sai kiểu
# gì, dừng cách kệ 3cm là không thể coi là "đã tới vị trí lấy hàng".
APPROACH_ARRIVAL_TOLERANCE = 4.0   # cm

# Khoảng cách TỐI ĐA tới kệ còn coi là "robot đang đứng trước kệ", kiểm ngay trước
# khi bốc hàng. Vì sao cần:
# Chặng QUAY VỀ KỆ sau khi giao xong là chặng DÀI NHẤT trận — tới 4 lần xoay và
# 6-7 giao lộ — nên sai một chỗ là cộng dồn. Mà sau khi về, robot KHÔNG kiểm chứng
# gì cả: nó nâng càng và luồn vào ngay (bước tiếp cận đã bỏ). Lệch chỗ thì nó luồn
# vào chỗ trống suốt INSERT_TIMEOUT = 8s rồi mới báo lỗi, mất cả lượt.
# Lúc này siêu âm DÙNG ĐƯỢC (đã thả hết hàng, không còn kiện chắn) và ở ~20cm nó
# đọc mặt kệ rất chuẩn — advance vừa dừng bằng chính số đo đó. Nên một phép đo là
# đủ để bắt "chặng về đi lạc" TRƯỚC khi phí 8 giây.
# 35cm: advance dừng ở 20cm (APPROACH_SLOW_DISTANCE) cộng dư địa cho trôi và nhiễu.
# Đọc lỗi (-1) thì KHÔNG chặn — thà thử bốc còn hơn bỏ tầng vì cảm biến hỏng.
PICKUP_MAX_SHELF_DISTANCE = 35.0

# --- Đoạn cuối tiếp cận: ĐI TỪNG NHỊP, DỪNG, ĐO ------------------------------
# Vệt siêu âm thật khi tiếp cận kệ (robot 03/08, option 5 tầng 1):
#
#   0.00s:16.5  0.17s:15.9  0.37s:23.2  0.44s:23.5  0.50s:23.2  0.57s:22.6
#   0.63s:16.6  0.70s:8.8        ← đo lại lúc đứng yên: 6.4cm
#
# Cảm biến MẤT MỤC TIÊU 0.2 giây ngay giữa đoạn quyết định, báo 23cm trong khi kệ
# ở ~15cm; rồi nhảy thẳng 16.6 → 8.8, BỎ QUA hoàn toàn mốc dừng 14.4cm.
#
# Không hằng số nào cứu được ca này. Từ 16.5cm tới điểm dừng chỉ còn 2.1cm, mà mỗi
# nhịp cập nhật (queue_len × 60ms) robot đã đi ~2.5cm — biên bằng ĐÚNG MỘT nhịp đo.
#
# Thứ duy nhất đã chứng minh được bằng số là cảm biến đọc rất chuẩn khi ĐỨNG YÊN:
# tools.check_sonar_jitter 30 cho 997 mẫu, σ = 0.20cm, 0 mẫu lệch > 2cm, 0 mẫu kịch
# trần. Nên đoạn cuối đi TỪNG NHỊP rồi DỪNG LẠI MÀ ĐO, không đo trong lúc chạy.
# Giá: thêm ~2-3 giây mỗi lần tiếp cận. Đổi lấy việc không húc kệ thì rẻ.
APPROACH_STEPPED = True       # False = về hành vi cũ (chạy liền, đo khi đang chạy)
APPROACH_STEP_TIME = 0.15     # Giây chạy mỗi nhịp trong vùng gần

# --- Rời khỏi giao lộ (Motion._escape_intersection) ---
# Chạy tới khi CẢM BIẾN hết báo giao lộ, không chạy mù một khoảng cố định.
# Bản cũ chạy mù 0.3s — số viết cứng, chưa đo. Đo trên bản in: vạch dọc C0 rộng 20mm
# theo hướng robot đi, ra khỏi tâm ±1.2cm là cảm biến bình thường trở lại. ADVANCE_SPEED
# = 40 nằm không xa vùng chết nên 0.3s có thể chỉ đi 1.5-2cm — đúng ranh giới, và
# smoke option 1 đã gãy thật vì chuyện này ("Advance: gặp giao lộ" ngay tại C0R0).
ESCAPE_MIN_TIME = 0.15       # Giây tối thiểu vẫn chạy, kể cả khi cảm biến đã sạch ngay
# ⛔ SÀN/TRẦN CỦA "THOÁT GIAO LỘ" ĐO BẰNG QUÃNG ĐƯỜNG, không bằng đồng hồ.
# Gốc của cú đâm kệ 04/08: sàn thời gian ≈0.4s là một cú CHẠY MÙ, quãng của nó gắn
# với VIÊN PIN — pin yếu ~5cm, pin đầy ~8cm. Route START → SHELF0 bỏ robot lại rất
# gần C0R0 mà chưa tới; 8cm là bước qua hẳn nó, bước đếm giao lộ chẳng còn gì để
# gặp nên chạy thẳng tới kệ (thước đo: bánh dừng cách C0R0 25cm).
# 3cm đủ ra khỏi vạch rộng 2cm, và 3cm thì không bao giờ nhảy qua được một giao lộ.
ESCAPE_MIN_CM = 3.0
ESCAPE_MAX_CM = 8.0
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

# Số mắt đen ĐẬM tối thiểu để advance_to_end() coi là GIAO LỘ THẬT (và báo "bản đồ
# không khớp"). CAO HƠN INTERSECTION_THRESHOLD có chủ ý.
#
# Đo trên robot 03/08, chặng tới khu Samsung — CÙNG một vạch line, cách nhau vài
# chục mili-giây, mắt 2 đọc lần lượt:
#       270, 194, 183, 169, 154, 129, 119, 98, 76
# Nó nằm ĐÚNG MÉP vạch nên nhấp nháy qua mọi ngưỡng: lúc 4 mắt đen đậm, lúc 3.
# Không ngưỡng nào trên mức 4 mắt phân biệt được vạch thường với giao lộ ở đây.
#
# Nhưng trong advance_to_end, "gặp giao lộ" là điều kiện LỖI chứ không phải điều
# kiện dừng bình thường — điểm dừng là HẾT LINE (hoặc siêu âm khi không cõng hàng).
# Nên đòi bằng chứng mạnh hơn ở đây chỉ làm nó ít báo lỗi oan; bỏ sót một giao lộ
# thật thì robot chạy tới hết line, đúng thứ nó phải làm. Ngã tư thật cho 6 mắt,
# ngã ba C0R0 cho 4 — nhưng advance không được phép gặp C0R0 ngoài cửa sổ ân hạn.
ADVANCE_INTERSECTION_DAM = 5

# --- Vào khu nhà máy: MẢNG IN ĐẬM là tín hiệu ĐÃ TỚI, không phải giao lộ -----
# Đo trên robot 03/08, chặng tới khu Samsung — cả thanh cảm biến TỐI DẦN ĐỀU trong
# 0.14 giây, không phải một vạch cắt ngang:
#     mắt 6:  913 → 901 → 878 → 852 → 820 → 789 → 749 → 706 → 666 → 531 → 499
#     mắt 1:  633 → 504 → 434 → 401 → 358 → 321 → 311 → 138
#     ngưỡng: 274 → 268 → 261 → 257 → 237 → 212 → 150
# Đó là robot đi vào MẢNG IN của khu nhà máy (ảnh nhà máy nền tối, viền màu). Tức
# nó ĐÃ TỚI NƠI, nhưng advance đọc ra "giao lộ" và báo lỗi bản đồ.
#
# Ở khu nhà máy KHÔNG có giao lộ nào để gặp — line kết thúc vào mảng in. Nên khi
# đang cõng hàng, mảng tối đậm chính là điểm dừng.
# Đòi thêm quãng đường tối thiểu để mảng đen của CHÍNH giao lộ vừa thoát không bị
# tính nhầm (cửa sổ ân hạn lo phần đầu, số này lo phần sau).
# Quãng đi tối đa từ GIAO LỘ vào kệ, đo bằng ENCODER — dừng ở đây bất kể siêu âm.
# ⚠️ Đây là chốt chặn CHÍNH cho chặng vào kệ, không phải phương án dự phòng.
# Siêu âm KHÔNG đáng tin ở kệ, đã đo hai chiều và cả hai đều sai:
#     thước 12cm  → siêu âm báo 35.7cm   (04/08, giá kệ hở nên sóng lọt qua)
#     thật ~35cm  → siêu âm báo 12.2cm   (04/08, robot còn ở giao lộ)
# Lần thứ hai làm robot dừng NGAY nhịp đầu của advance rồi bước luồn càng tiến mù
# ~20cm và chui vào gầm kệ. Sau đó đo thời gian thực (test_motion option 8) thấy nó
# đọc ĐÚNG 12.2cm bất kể robot ở đâu — tức đang nhìn một vật cố định trên robot.
# ⚠️ MỐC 15.0 CŨ LÀ SAI, và sai theo kiểu không bao giờ cứu được gì. Nó lấy từ
# C0R0 → chân kệ = 35.4cm (docs/SA_BAN.md 3b, đo TRÊN BẢN IN) rồi trừ 20cm.
# Nhưng 35.4cm là khoảng cách trên SA BÀN, còn CÀNG NHÔ RA TRƯỚC BÁNH XE hơn 20cm.
# Đo trên robot 04/08: bánh xe mới rời giao lộ 12cm (encoder báo 10.9cm — khớp,
# encoder ĐÚNG) mà càng đã chui vào gầm kệ. Mốc 15cm luôn tới MUỘN hơn cú va.
# Điểm dừng đúng là BÁNH XE NẰM TRÊN GIAO LỘ — tức quãng đi gần bằng 0, và bước
# luồn càng (creep_until, dựa vào IR pallet) lo nốt đoạn cuối.
# Quãng này đo TỪ GIAO LỘ. Ở chặng vào kệ advance KHÔNG thoát giao lộ nữa: escape
# một mình đã ngốn ~7.9cm, quá nửa quãng cho phép.
# 04/08, mốc 3.0: advance dừng ĐÚNG 3.0cm và báo ✅, robot vẫn ở trong kệ. Nhưng
# log cùng lúc cho ADC [0, 0, 0, 0, 0, 0] — SÁU SỐ 0 TUYỆT ĐỐI, lặp lại suốt, và
# siêu âm 6.2cm ngay nhịp đầu. Giao lộ thật không bao giờ cho thế: các chữ ký đã
# đo là [74,52,0,0,0,34] và [32,0,0,0,0,0]. Sáu số 0 nghĩa là KHÔNG CÓ MẶT PHẢN XẠ
# trong tầm — thanh cảm biến đang ở khoảng trống dưới gầm kệ.
# Tức robot đã ở kệ TRƯỚC KHI advance chạy; bước đếm giao lộ đọc gầm kệ thành giao
# lộ. Hạ mốc về gần 0 để advance không cộng thêm gì trong lúc truy chuyện đó.
# = RECENTER_CM. Đây KHÔNG phải số ướm — nó là khoảng cách THANH CẢM BIẾN → TRỤC
# BÁNH, đã đo trên robot. follow_line dừng khi THANH CẢM BIẾN chạm giao lộ, lúc đó
# TRỤC BÁNH còn cách giao lộ đúng chừng ấy. Đi thêm 12cm = bánh xe nằm trên giao
# lộ, đúng tư thế bốc hàng.
# (Mốc 15.0 lúc đầu lấy từ "C0R0 → chân kệ = 35.4cm trên sa bàn" rồi trừ 20 — sai
# vì 35.4cm là khoảng cách TRÊN SA BÀN còn càng nhô ra trước bánh hơn 20cm, nên nó
# luôn tới muộn hơn cú va. Mốc 0.5 là để khoá advance lại trong lúc truy lỗi.)
# 12.0 = RECENTER_CM đưa TRỤC BÁNH tới đúng giao lộ. Đội thấy càng vẫn còn xa
# pallet ở tư thế đó nên xin thêm 5cm — 17.0. Số này giờ KHÔNG còn thuần hình học
# nữa, nó là 12.0 (đo được) + 5.0 (chọn tay), sửa tiếp thì sửa phần cộng thêm.
# ⚠️ ĐO TỪ LÚC CẢM BIẾN CHẠM GIAO LỘ, KHÔNG PHẢI TỪ TRỤC BÁNH.
# Thanh cảm biến nằm TRƯỚC trục bánh 12cm (RECENTER_CM), và follow_line dừng khi
# THANH CẢM BIẾN chạm giao lộ. Nên quãng này bị "ăn" mất 12cm đầu chỉ để kéo trục
# bánh lên tới giao lộ:
#       quãng đặt ở đây   trục bánh qua giao lộ được
#            12.0                  0.0cm   (bánh NẰM TRÊN giao lộ)
#            17.0                  5.0cm   ← đội quan sát: "bánh còn chưa qua giao lộ"
#            24.0                 12.0cm
# Giao lộ C0R0 → chân kệ = 35.4cm (docs/SA_BAN.md 3b), nên 24.0 để thanh cảm biến
# cách chân kệ 11.4cm, phần còn lại do creep_until bò vào bằng cảm biến IR pallet.
# CHỈNH BẰNG THƯỚC, không đoán: đo mũi càng cách pallet bao nhiêu sau khi nó dừng,
# rồi đặt = giá trị hiện tại + (số đo − 4). Chừa 4cm cuối cho creep_until.
# 06/08: ở 24.0 robot dừng CÒN XA KỆ, camera nhận diện kiện không chuẩn — ảnh mẫu
# ORB và dải HSV đều chốt ở khoảng cách dừng CŨ, xa hơn là kiện nhỏ đi trong khung
# và tỉ lệ pixel đúng màu tụt. Nâng 24.0 → 29.0 (thanh cảm biến cách chân kệ 6.4cm).
ADVANCE_SHELF_STOP_CM = 29.0

# Bao lâu KHÔNG có xung encoder thì coi như encoder CHẾT và dừng khẩn.
# 04/08, sau khi giao quyền dừng cho quãng đường: log in đúng dòng "dừng theo QUÃNG
# ĐƯỜNG 15.0cm — bỏ qua siêu âm" rồi robot chạy thẳng vào kệ, KHÔNG hề in dòng "ĐÃ
# ĐI ...cm". Chữ ký của encoder chết: mọi nhánh vẫn đúng, chỉ là con số không bao
# giờ nhúc nhích, nên không mốc nào bị chạm — kể cả lưới an toàn
# ADVANCE_MAX_TRAVEL_CM, vì nó cũng đo bằng chính encoder đó.
# `WheelEncoder.available` KHÔNG bắt được ca này: nó chỉ nói GPIO có mở được không.
# Rút hẳn dây ra thì available vẫn True.
# Ở SPEED_DEFAULT, 1 giây chạy cho hàng trăm xung, nên 1.5s mà dưới 20 xung thì
# không thể là bánh đang quay. Chẩn bằng: python3 -m tools.check_encoder_alive
# Bao lâu in một dòng nhịp tim quãng đường trong advance. Không có số trong vòng
# lặp thì mọi giả thuyết về "vì sao nó không dừng" đều là đoán — 04/08 tôi đoán
# encoder chết, đo ra encoder sống, mất một lượt chạy vô ích.
ADVANCE_HEARTBEAT_TIME = 0.25

ADVANCE_ENCODER_DEAD_TIME = 1.5
ADVANCE_ENCODER_DEAD_PULSES = 20

# ⛔ CHỐT CHÍNH khi vào KHU NHÀ MÁY: dừng theo QUÃNG ĐƯỜNG, y như chặng vào kệ.
# Cách cũ dò TẤM IN, và nó cho điểm dừng NGẪU NHIÊN: phép kiểm bị nhốt trong nhánh
# `if at_intersection`, tức chỉ được đánh giá ở những nhịp follow_line() TÌNH CỜ báo
# giao lộ — mà cái đó dùng ngưỡng THÍCH NGHI, tự co giãn theo dải sáng-tối từng lần
# đọc. Trên tấm in tối dần đều, thời điểm ngưỡng bật là ngẫu nhiên. Đo trong một
# chặng ngày 04/08, ngưỡng nhảy: 139, 148, 156, 160, 169, 175, 200, 228, 250, 272.
# Và lúc tuyên bố "đã vào khu nhà máy", ADC là [349, 0, 104, 0, 587, 0] — sáng tối
# xen kẽ, KHÔNG phải mảng in đồng đều: nó bắt một trạng thái chuyển tiếp.
#
# 12.0 lấy từ hai lượt chạy ĐÚNG hôm đó, cả hai đều dừng sau khi đi 12.1cm. Đây là
# số ĐO ĐƯỢC, nhưng đo ở điểm dừng của cơ chế cũ — CHƯA phải điểm thả tối ưu.
# Cách chỉnh: đẩy robot bằng tay tới đúng chỗ muốn thả, đo từ vạch giao lộ tới TRỤC
# BÁNH, đặt vào đây. Bước xoay trước đó đã có tien_bu_cm(RECENTER_CM) nên lúc xoay
# trục bánh nằm ĐÚNG trên giao lộ — quãng này đo từ đó.
# Đặt 0 để quay về cách dò tấm in.
ADVANCE_FACTORY_STOP_CM = 12.0

# Sàn cho mốc trên sau khi TRỪ phần tránh kiện cũ. Mỗi nhà máy nhận 3 kiện, kiện đã
# thả nằm ĐÚNG trên đường robot sắp đi vào — nên mỗi lần thả sau phải dừng SỚM HƠN
# đúng bằng FACTORY_STACK_BACKOFF_CM × số kiện đã có.
# ⚠️ SỐ HỌC KHÔNG ĐỦ CHỖ CHO KIỆN THỨ 3: 12.0 − 2×9.0 = −6.0. Đây không phải lỗi
# phần mềm mà là ràng buộc VẬT LÝ đã ghi trong docs/HAPPY_CASE.md — 3 × 9cm = 27cm
# lớn hơn chiều sâu khu nhà máy 25cm, ba kiện xếp một hàng KHÔNG lọt. Cách chữa nêu
# trong tài liệu đó là thả SO LE trái/phải (2 cột × 2 hàng), chưa làm.
# Kẹp ở sàn này để robot vẫn thả được thay vì lùi vào chỗ âm; kiện thứ 3 sẽ chồng
# lấn kiện thứ 2 — mất điểm kiện đó, nhưng không kẹt robot.
ADVANCE_FACTORY_MIN_STOP_CM = 3.0

ADVANCE_FACTORY_DARK_MIN_CM = 4.0
# ⚠️ 10.0 → 4.0 ngày 03/08. Ô FOXCONN nằm SÁT NGAY giao lộ (không như Samsung/Hana
# ở xa hơn), nên advance chạm tấm in khi mới đi ~8cm. Với mốc 10 thì tín hiệu "đã
# tới" bị chặn, rơi xuống nhánh kiểm giao lộ và báo "bản đồ không khớp" — robot
# dừng đúng chỗ đẹp trên ô mà vẫn coi là thất bại. Số đo lúc đó:
#     0.78s  ADC [756, 332, 0, 0, 0, 0]   4 mắt đen, sáng nhất 756
#     0.82s  ADC [559, 149, 0, 0, 0, 0]   5 mắt đen, sáng nhất 559
# Cả hai đều THOẢ tiêu chí tấm in, chỉ thiếu quãng đường.
#
# KHÔNG hạ được về 0. Điều kiện "cả vùng đều tối" KHÔNG phân biệt được tấm in với
# một GIAO LỘ ĐỦ 6 MẮT — ở giao lộ mọi mắt đọc 0 nên mắt sáng nhất cũng bằng 0,
# thoả luôn ngưỡng độ sáng. Quãng đường mới là thứ tách hai ca đó.
# 4.0 an toàn vì _escape_intersection() chạy TRƯỚC vòng lặp advance và đã đưa robot
# ra khỏi vạch giao lộ (rộng 20mm) — log xác nhận "Rời giao lộ sau 0.42s, cảm biến
# [0,0,0,0,0,0]" tức đã trắng hẳn trước khi advance bắt đầu đếm.
# Số mắt đen ĐẬM tối thiểu để coi là đã vào khu nhà máy. THẤP hơn
# ADVANCE_INTERSECTION_DAM: tấm in Hana chỉ cho 4 mắt (ADC [0, 0, 15, 123, 509, 446])
# nên đòi 5 là bỏ sót, robot đi quá khỏi ô nhà máy — đo trên robot 03/08.
ADVANCE_FACTORY_DARK_EYES = 4
# ...nhưng 4 mắt KHÔNG đủ để phân biệt: vạch line thường cũng cho 4. Chỗ khác nhau
# nằm ở những mắt KHÔNG đen — trên TẤM IN thì cả vùng đều tối, không mắt nào thấy
# nền trắng sạch. Số đo trên robot 03/08:
#     tấm in nhà máy   4 mắt đen, sáng nhất 509   ← xám
#     tấm in nhà máy   6 mắt đen, sáng nhất 138
#     vạch line thường 4 mắt đen, sáng nhất 926   ← trắng sạch
#     giao lộ thật     4 mắt đen, sáng nhất 911
ADVANCE_FACTORY_MAX_BRIGHT = 0.75   # 0.75 × 1023 ≈ 767

# ⛔ CHẶN CỨNG QUÃNG ĐƯỜNG của advance (đo bằng encoder). Thể lệ: robot rời sa bàn
# là BỊ RESET (-10 điểm). Ngày 03/08 robot đã chạy đè qua khu Samsung và thò càng
# ra ngoài mép sa bàn (có ảnh) vì tấm in đọc ra "vẫn còn line" nên nó không bao giờ
# thấy hết line. Nguyên nhân gốc đã sửa (LineSensor.nguong_cho đòi có đen THẬT),
# nhưng lưới này giữ cho MỌI nguyên nhân khác — nó không phụ thuộc cảm biến line.
# ⚠️ 80 là số ĐẶT TẠM, chưa đo. Chặng advance dài nhất là C1 → khu nhà máy; đo
# bằng thước rồi siết lại. Đặt quá nhỏ thì robot dừng non và không giao được hàng.
ADVANCE_MAX_TRAVEL_CM = 80.0


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
EDGE_COST_REVERSE = 0        # Rút khỏi điểm cuối bằng LÙI — không phụ phí
# ⚠️ 1 → 0 ngày 03/08. Với phụ phí 1, tuyến VỀ từ Samsung mở đầu bằng "xoay trái →
# xoay trái", tức QUAY ĐẦU 180° NGAY TẠI KHU NHÀ MÁY. Hai thứ hỏng theo:
#   • execute_route chỉ chèn TIẾN BÙ khi lệnh trước là `forward`; route mở đầu bằng
#     xoay thì không có gì, nên robot quay quanh chỗ retreat bỏ nó lại — tâm xoay
#     sai, xoay xong cảm biến văng khỏi vạch. Đo trên robot: "bám line một lúc rồi
#     đi lung tung, không về được kệ".
#   • cổng quãng đường nhận diện "vừa rời điểm cuối" bằng route[0] == "back", nên
#     route mở đầu bằng xoay thì cổng TẮT và robot đếm tấm in thành giao lộ.
# Cùng loại lỗi đã gặp với tuyến ĐI tới foxconn (xoay phải hai lần tại kệ).
#
# Hạ về 0 thì bộ tìm đường luôn rút khỏi điểm cuối bằng LÙI — đường đã được đo kỹ
# (back_to_intersection có cả bằng chứng vạch, cổng quãng đường, tiến bù riêng).
# Không phải đánh đổi: tổng chi phí 4 nhà máy đi+về còn GIẢM 131 → 124.

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

# --- TIẾN BÙ ĐO BẰNG ENCODER thay vì bằng đồng hồ -------------------------
# Xoay 90° tại chỗ thì TRỤC BÁNH phải nằm trong ~±1.5cm của giao lộ (vạch rộng
# 20mm, thanh cảm biến trải 47mm) — lệch hơn là xoay xong cảm biến văng ra vùng
# trắng. Mà REVERSE_RECENTER_TIME là một con số THỜI GIAN: quãng đường nó đi đổi
# theo pin, ma sát sàn, và tải trên càng (cõng 2 kiện nặng hơn hẳn lúc đi không).
# Đo trên robot 03/08: lùi-rồi-tiến-để-xoay chạy KHÔNG ỔN ĐỊNH — lúc xoay đúng vào
# line, lúc lùi ít quá, lúc tiến quá đà rồi va vào kệ khi xoay.
#
# Encoder biến nó thành QUÃNG ĐƯỜNG thật. Cần đúng hai số ĐO ĐƯỢC:
#   RECENTER_CM            — khoảng cách thanh cảm biến → trục bánh, đo bằng thước
#   ENCODER_PULSES_PER_CM  — chốt bằng python3 -m tools.calibrate_encoder_cm
# Chưa calibrate (= 0) thì tự động rơi về cách cũ theo thời gian.
ENCODER_PULSES_PER_CM = 35.940  # ĐÃ CHỐT trên robot 03/08 — 3 lần nhất quán
                                # (tools/calibrate_encoder_cm.py). 0 = chưa calibrate
RECENTER_CM = 12.0            # cm — ĐO BẰNG THƯỚC trên robot, không phải số đoán
RECENTER_MAX_TIME = 5.0       # Giây chặn trên: encoder hỏng thì không chạy vô hạn

# Bước tiến bù 12cm trước khi xoay có BÁM LINE không (thay vì chạy mù).
# Đây là 12cm NGAY TRƯỚC MỘT CÚ XOAY — đoạn quyết định tư thế của cả chặng sau.
# Đo trên robot 04/08: test_motion option 10 cho ĐÚNG 90°, nhưng chạy thật ở giao
# lộ Samsung robot quay ~135° rồi lạc khỏi line. Cú xoay KHÔNG sai — tư thế lúc
# xoay mới sai. Samsung ở R4 (nhà máy xa nhất) nên chặng lùi về nó dài nhất, sai
# lệch hướng tích luỹ nhiều nhất, rồi 12cm chạy mù khuếch đại nốt: robot xoay đủ
# 90° nhưng quanh một tư thế đã xiên, so với vạch thành ~135°.
# Cùng bài học đã ghi cho _forward_guided ("robot không đi thẳng tuyệt đối nên nó
# lệch dần"). Mất line thì rơi về forward() y như cũ, nên không xấu đi ở chỗ
# không có vạch. Đặt False để về hành vi cũ.
RECENTER_BAM_LINE = True
# ⚠️ 3.0 → 5.0 ngày 03/08. Số 3.0 đặt hồi robot đi 12cm trong 1.2s. Về cuối buổi
# nó chậm dần — cùng 12cm mất 1.8-2.2s, và có lượt CHỈ ĐI ĐƯỢC 287/431 rồi 207/431
# xung trước khi chạm trần:
#     Tiến bù 12.0cm: 287/431 xung trong 3.01s — HẾT CHẶN TRÊN
# Tức robot mới đi 6-8cm thay vì 12 → tâm xoay sai → mọi bước sau lệch theo.
# Chặn này chỉ để phòng encoder chết, không phải để giới hạn quãng đường, nên nới
# rộng là đúng. NHƯNG robot chậm dần như vậy thường là PIN YẾU — kiểm pin trước
# khi tin vào bất kỳ số đo thời gian nào.

# Lùi ra khỏi kệ = lùi ĐÚNG quãng đã luồn vào, nhân hệ số dư này. creep_until()
# đếm sẵn quãng luồn vào bằng encoder nên không phải đoán thêm hằng số nào. Hệ số
# > 1 để càng ra HẲN khỏi khe pallet chứ không dừng ngay ở mép.
RETREAT_BACKOUT_MARGIN = 1.15

# Quãng LÙI sau khi THẢ HÀNG ở nhà máy (cm, đo bằng encoder).
# ⚠️ KHÁC hẳn lùi sau khi BỐC. Lùi sau khi bốc phải rút càng ra khỏi khe pallet nên
# dùng đúng quãng đã luồn vào (~17-20cm). Nhưng ở NHÀ MÁY robot KHÔNG hề luồn càng
# — nó chỉ tiến vào mảng in rồi hạ càng. Dùng lại quãng luồn của lần bốc là lùi QUÁ
# XA: robot vượt qua giao lộ, rồi lệnh "LÙI 1 giao lộ" kế đó đi tìm giao lộ PHÍA
# SAU NỮA → sai hàng, và mọi chặng sau lệch theo.
# Đo trên robot 03/08: thả xong ở nhà máy 1, sang nhà máy 2 thì "đi quá và thả
# lệch", rồi lùi về là sai đường và mất bám line.
# Ở đây chỉ cần lùi đủ để càng KHÔNG QUỆT vào kiện vừa đặt khi nâng lên — kiện sâu
# 9cm, nên 10cm là vừa, và vẫn còn cách giao lộ một đoạn để lệnh LÙI làm việc.
RETREAT_AFTER_DROP_CM = 10.0

# --- XẾP CHỒNG KIỆN Ở NHÀ MÁY -------------------------------------------------
# 12 kiện chia 4 nhà máy = MỖI NHÀ MÁY 3 KIỆN. Kiện thứ 2 và thứ 3 phải tránh
# kiện đã thả trước, nếu không robot đâm vào chúng hoặc thả chồng lên.
# Khu nhà máy sâu 25cm, kiện sâu 9cm → 3 kiện nối đuôi = 27cm, KHÔNG LỌT. Nhưng
# hai càng cách nhau 12cm nên kiện nằm được ở HAI CỘT trái/phải → 2 cột × 2 hàng
# đủ chỗ cho 3 kiện. Càng nào thả thì do nhãn quyết định, không chọn được.
#
# Cơ chế: sau khi advance báo đã vào khu nhà máy, LÙI thêm
#     FACTORY_STACK_BACKOFF_CM × (số kiện nhà máy đó ĐÃ nhận)
# rồi mới thả — kiện sau nằm nông hơn kiện trước.
#
# ĐÃ ĐO ngày 04/08 (tools.check_sees_dropped_package), số rất sạch:
#     CÓ kiện    24.9cm  (tản 0.1)
#     KHÔNG kiện 73.6cm  (tản 0.5)      chênh +48.7cm
# Siêu âm nhìn kiện dưới sàn RẤT TỐT — tốt hơn hẳn nhìn giá kệ (kệ hở nên sóng lọt
# qua, kiện thì đặc).
#
# ⚠️ NHƯNG KHÔNG DÙNG ĐƯỢC ĐỂ TỰ TRÁNH. Phép đo trên làm với càng Ở SÀN, KHÔNG
# mang gì. Lúc giao hàng thì robot ĐANG CÕNG KIỆN, và chính kiện đó chắn chùm sóng
# — đo hôm 03/08: cõng hàng đọc 8-10cm suốt, thả xong cùng cảm biến đọc 100cm.
# Nên tuy siêu âm "thấy" được kiện cũ, nó không thấy vào ĐÚNG LÚC cần.
# → BẮT BUỘC đếm kiện. Đó là lý do hằng số này được BẬT.
#
# 9.0 = bề sâu một kiện. Kiểm bằng mắt ở lượt đầu có 2 kiện vào cùng một nhà máy:
# kiện thứ hai phải nằm NÔNG hơn và KHÔNG chồng lên kiện thứ nhất, cả hai vẫn
# trong ô 25cm. Lệch thì chỉnh số này, đừng chỉnh chỗ khác.
FACTORY_STACK_BACKOFF_CM = 9.0

# Quãng LÙI tối thiểu trước khi tin một tín hiệu giao lộ (đo bằng encoder).
# Vì sao không lọc bằng HÌNH DẠNG tín hiệu: đo trên robot 03/08 cho thấy chữ ký
# GIẢ ở chân kệ và chữ ký THẬT ở giao lộ có cùng một dạng —
#     giả  ADC [504,   0, 106, 454,   0,   0]   đen ở 2,3,5,6
#     thật ADC [  0, 703,   0,   0,   0, 926]   đen ở 1,3,4,5
# cả hai đều 4 mắt đen với đúng một mắt hở ở giữa. Đòi dãy LIỀN NHAU (bộ lọc dùng
# cho exit_start_zone) thì bác luôn cả cái thật: robot bỏ qua giao lộ và lùi tới
# 3.2s, tức đã vượt xa C0R0.
# Quãng đường thì phân biệt được: mảng đen chân kệ nằm NGAY ĐẦU chặng lùi, còn
# giao lộ thì cách một đoạn. Để nhỏ thôi — sau retreat_from_shelf robot đã lùi
# sẵn ~20cm nên phần còn lại tới giao lộ không nhiều.
# ⚠️ 5.0 LÀ QUÁ LỚN KỂ TỪ KHI ADVANCE_SHELF_STOP_CM LÊN 17.0.
# Hình học: robot dừng cách giao lộ 17.0cm, retreat_from_shelf lùi 12.9cm → giao lộ
# chỉ còn cách 4.1cm khi chặng lùi bắt đầu. Cổng 5.0 bác ĐÚNG cái giao lộ cần tìm.
# Đo trên robot 04/08:
#     Phát hiện giao lộ  ADC [276, 292, 0, 0, 0, 0]   ← 4 mắt đen sâu + 2 mắt sáng,
#                                                       khớp hệt giao lộ thật đã
#                                                       xác nhận [306,372,0,0,0,46]
#     Lùi: bỏ qua — mới lùi 4.6cm (cần 5.0)           ← thiếu 0.4cm
#     ERROR Lùi: mất line quá 1.2s — dừng an toàn
# Rồi tuyến tới nhà máy hỏng ngay bước đầu và robot thả kiện tại chỗ.
# 3.0 vẫn đủ chặn mảng đen chân kệ (nằm NGAY đầu chặng lùi, <1cm), mà không chạm
# tới giao lộ ở 4.1cm.
BACK_MIN_TRAVEL_CM = 3.0

# Cổng quãng đường cho chặng LÙI KHỎI KHU NHÀ MÁY — KHÁC chỗ lùi khỏi kệ.
# Mảng đen ngay đầu chặng lùi ở nhà máy VƯỢT ĐƯỢC bộ lọc giao lộ. Đo trên robot
# 04/08: ADC [458, 0, 113, 0, 600, 45] → 4 mắt đen đậm + 3 mắt đen sâu →
# la_giao_lo_that() = True. Nó chỉ bị loại nhờ cổng quãng đường (xuất hiện ở 0.9cm).
# Hạ cổng chung xuống 3.0 (để chữa hình học ở KỆ) làm biên tụt từ 4.1cm còn 2.1cm —
# robot lùi lệch một chút là mảng đó lọt, route đếm thừa một giao lộ và TOÀN BỘ
# chặng quay về sai. Đúng triệu chứng đội báo: "quay trở lại sau khi thả hàng đang
# đi sai hết".
# 5.0 là giá trị đã chạy đúng trước 04/08 — giữ nguyên cho chặng nhà máy.
BACK_MIN_TRAVEL_FACTORY_CM = 5.0

# Quãng TIẾN tối thiểu trước khi tin một tín hiệu giao lộ (đo bằng encoder).
# Cùng lý do như BACK_MIN_TRAVEL_CM, nhưng cho chiều TIẾN — và ca gây lỗi ở đây là
# TẤM IN KHU NHÀ MÁY, không phải chân kệ.
# Đo trên robot 03/08, robot vừa thả hàng ở Samsung và đang đi tiếp tới Hana:
#     ADC [ 56, 139,  73, 197, 171, 208]   ngưỡng 200
#     ADC [141, 119,  53, 148, 101, 131]   ← 6 mắt dưới 153, BỊ ĐẾM THÀNH GIAO LỘ
# Mọi mắt đọc 50-250: không mắt nào thấy nền trắng (~900), cũng không mắt nào đen
# sâu (~0). Đó là cả thanh nằm trên TẤM IN. Robot đếm nhầm nó thành giao lộ, dừng
# sớm, rồi thả sai nhà máy.
# KHÔNG ngưỡng nào tách được: tấm in có mắt đọc 53 (đen như vạch thật), còn ngã tư
# thật thì cả 6 mắt đọc 0 nên "phải có mắt sáng" cũng sai nốt.
# Quãng đường thì tách được: các hàng R0..R4 cách nhau ~40cm trên sa bàn, còn tấm
# in nằm ngay dưới chân robot lúc khởi hành. 10cm an toàn cho cả hai phía.
FORWARD_MIN_TRAVEL_CM = 10.0
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
EDGE_COST_START_GAP = 20     # Phụ phí đoạn ngang R0 — TRÁNH HẲN khoảng đứt ô xuất phát
# ⚠️ 3 → 20 ngày 03/08 vì tuyến qua đó KHÔNG CHẠY ĐƯỢC. Đo trên robot: đi giao
# foxconn (cùng hàng R0 với ô xuất phát), robot quay 180° tại kệ rồi đi thẳng qua ô
# xuất phát — nơi vạch line ĐỨT 245mm và còn in hình mascot đen. Cảm biến ra ngoài
# line, robot đi lung tung. Lạc ở đó thì rủi ro ra khỏi sa bàn = reset (−10đ).
#
# Giá phải trả, tính bằng route_cost tổng cho cả 4 nhà máy (đi + về):
#       phạt  3  →  107
#       phạt 20  →  131        tức +22% quãng đường
# Đắt, nhưng tuyến rẻ hơn thì không chạy được nên không phải là lựa chọn.
#
# Ở mức 20 bộ tìm đường tránh hẳn cạnh này; mức 10 vẫn còn chọn nó. Đặt lại về 3
# CHỈ SAU KHI navigate_intersections() vượt được khoảng đứt một cách tin cậy —
# hướng đúng là trôi theo QUÃNG ĐƯỜNG đo bằng encoder (~25-30cm) thay vì theo thời
# gian như LINE_GAP_COAST_TIME hiện nay, cùng cách đã chữa mọi hằng số thời gian
# khác trong ngày. Làm được thì lấy lại toàn bộ 22% đó.
#
# Lợi phụ: ở mức 20, tuyến tới foxconn mở đầu bằng "LÙI 1 giao lộ" thay vì "xoay
# phải hai lần" — bỏ luôn cú quay đầu 180° ngay trước mặt kệ khi đang cõng 2 kiện,
# vốn cũng chưa từng chạy thử.

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
# ⚠️ ĐÃ ĐO trên robot 04/08, không phải số ướm. Cùng một tư thế ở kệ:
#     kiện THẬT   : 26.9  29.5  29.9  40.3  44.7  57.9  64.7  86.5  96.2 %
#     ngăn TRỐNG  :  9.5  11.5  12.0  12.2 %   (camera đang đọc màu kệ)
# Ngưỡng cũ 0.08 nằm DƯỚI cả nền: ngăn trống vẫn vượt ngưỡng nên robot nhận một
# nhãn và tin là thật. 0.20 nằm giữa hai cụm, cách nền 1.7× mà vẫn còn biên dưới
# số đo thật thấp nhất (26.9%).
# ⚠️ 0.12 LÀ SỐ ĐÃ ĐO VÀ CÓ LÝ DO — ĐỪNG NÂNG. Xem CLAUDE.md mục "HAI THAY ĐỔI SAU
# PHẢI ĐI CÙNG NHAU" (a950c75). Decal hana nền TRẮNG nên dải amkor luôn ăn nhiều
# pixel hơn: trên kiện hana thật, amkor 47.0% còn hana chỉ 15.4%. Hana KHÔNG cần
# thắng về số pixel — màu đỏ là đặc trưng riêng, sạch hơn 20 lần (15.4% trên kiện
# hana so với 0.6-0.9% trên ba loại kia). Nó chỉ cần VƯỢT NGƯỠNG để cơ chế ưu tiên
# CHROMATIC_LABELS kích hoạt và chặn amkor.
# Nâng lên 0.20 là hana 15.4% không vượt ngưỡng → amkor thắng → HANA THÀNH AMKOR.
# Tôi đã làm đúng lỗi đó ngày 04/08 và người dùng báo "hana thành amkor" ngay sau.
# Ô TRỐNG đọc 9.5-12.2% nên 0.12 để lọt sát nút — ca đó nay do luật "hai càng không
# bao giờ cùng một nhãn" trong classify_pair chặn, KHÔNG phải do ngưỡng.
CONFIDENCE_THRESHOLD = 0.12
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
# ⚠️ HAI SỐ DƯỚI ĐÂY LÀ VÙNG ĐÃ CHỨNG MINH CHẤM ĐÚNG trên robot 04/08, không phải
# số ướm. Đường chạy thật với vùng RỘNG (520x291) cho amkor/amkor — mà mỗi cặp
# trên kệ LUÔN là hai nhà máy khác nhau, nên hai kết quả giống hệt tự nó là bằng
# chứng nền đã lấn át nhãn. Cùng khung hình đó, cắt hẹp lại còn 312x175 thì:
#     tầng 1:  hana_micron 26.9%   samsung 40.3%
#     tầng 2:  foxconn     86.5%   amkor   96.2%
# Kiện chỉ là khối 40mm trên pallet 90mm trong ngăn kệ 240mm — phần lớn vùng rộng
# là kệ và pallet, nên % pixel đúng màu bị pha loãng tới mức nhãn sai thắng.
# Suy ra từ chính vùng đó: x 168..480 và y 632..807 trên nửa khung 648x972.
ROI_HEIGHT = 0.18            # chiều cao vùng quét (tỉ lệ) ≈ 175px
ROI_MARGIN_X = 0.26          # cắt ngang mỗi bên của NỬA khung. 0.2 xén hụt cả 2 mép:
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

# Số mắt ĐEN ĐẬM LIỀN NHAU tối thiểu để tin "đã chạm line R0" khi rời ô xuất phát.
# Trước đây chỉ cần `sum(values) > 0` — nhận bất kỳ hình dạng nào, kể cả mắt CÁCH
# QUÃNG. Đo trên robot 04/08, nửa sân bên kia:
#     Chạm line R0! sensor=[1, 0, 1, 0, 0, 1]   ← chấp nhận sau đúng 1ms
# Ba mắt cách quãng, trên mặt tối om (ADC cao nhất 284; nền trắng nửa bên kia đọc
# 400-900). Robot căn giữa vào chỗ không có vạch rồi đi mò cả sân, và log báo
# "exit_start_zone OK".
# Vạch rộng 20mm trên thanh trải 47mm luôn cho một dãy LIỀN ≥2 mắt.
EXIT_START_LINE_EYES = 2
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
TURN_TIME = 0.90             # 0.5 (số của motor CŨ) chỉ quay được 45° trên JGA25-370.
                             # 0.95 → 0.90 ngày 03/08: người dùng báo xoay HƠI QUÁ
                             # một chút (~5°; ở 0.95 thì 1° ≈ 0.0106s).

# --- XOAY ĐO BẰNG ENCODER (tắt cho tới khi đo được vệt bánh) ---------------
# TURN_TIME có cùng điểm yếu với REVERSE_RECENTER_TIME: nó là hằng số THỜI GIAN
# nên góc quay đổi theo pin, ma sát sàn và tải trên càng. Tệ hơn, nó chỉ có MỘT
# giá trị cho CẢ HAI chiều, mà hệ số bù PWM hai chiều lại khác nhau — chỉnh khớp
# chiều này là lệch chiều kia, không có cách nào đúng cả hai.
#
# Encoder chữa được: xoay tại chỗ 90° thì MỖI bánh lăn một cung
#     cung = (π/2) × (vệt bánh / 2) = π × vệt bánh / 4
# Bộ đếm không đọc chiều quay, nhưng xoay tại chỗ hai bánh cùng sinh xung nên
# TỔNG xung = 2 × cung × ENCODER_PULSES_PER_CM. Không phụ thuộc pin hay tải, và
# tự đúng cho cả hai chiều.
#
# Cần ĐÚNG MỘT số đo nữa: WHEEL_TRACK_CM = khoảng cách giữa hai ĐIỂM TIẾP ĐẤT của
# 2 bánh dẫn động (đo bằng thước, tâm bánh tới tâm bánh). Để 0 = TẮT, dùng
# TURN_TIME như cũ. Đo xong đặt số vào đây rồi xác nhận bằng test_motion option 10.
WHEEL_TRACK_CM = 12.63       # ⚠️ ĐÂY LÀ SỐ HIỆU CHỈNH, KHÔNG PHẢI SỐ ĐO BẰNG THƯỚC.
# Thước đo được 20.0cm (tâm bánh → tâm bánh) nhưng chạy test_motion option 10 với
# số đó thì robot xoay 135°, tức QUÁ 45°. Robot quay NHIỀU hơn mô hình cung lăn dự
# đoán → bán kính quay thực nhỏ hơn nửa vệt bánh đo được. Hiệu chỉnh theo tỉ lệ:
#       20.0 × 90/135 = 13.33   → chạy lại ra 95°, chỉnh tiếp:
#       13.33 × 90/95 = 12.63   (1129 → 753 → 713 xung)
# ĐỪNG "sửa lại cho đúng thước" — 20.0 đã được thử và SAI. Số này là hằng số hiệu
# chỉnh của cả cụm (bánh + caster + mặt sàn), không phải một kích thước hình học.
#
# CÁCH CHỈNH TIẾP nếu vẫn chưa đúng 90° — nó vào công thức như HỆ SỐ TỈ LỆ THUẦN
# (xung cần = 2 × π × vệt/4 × xung_mỗi_cm) nên nhân thẳng theo góc đo được:
#       vệt mới = vệt cũ × 90 / góc_thực_tế
# Đo lại bằng test_motion option 10, CẢ HAI CHIỀU. Hai chiều lệch nhau nhiều thì
# mô hình một-hằng-số không đủ — nói ra, đừng chỉnh cho vừa lòng một chiều.
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
# File log RIÊNG cho các menu test phần cứng (test_smoke/motion/lift/vision).
# Trước 06/08 chúng chỉ in ra màn hình, nên mỗi lần cần chẩn đoán là phải chép tay
# hàng trăm dòng — và log thi đấu thì lại bị bộ test mô phỏng đổ rác vào. Tách hẳn
# hai file: robot_log.txt chỉ của main.py, test_log.txt của các bài test.
TEST_LOG_FILE = "test_log.txt"
WEB_PORT = 5000
DEBUG_MODE = True            # True = web debug (luyện tập); False = thi đấu
if os.environ.get("ROBOT_COMPETE") == "1":   # scripts/start.sh đặt cờ này
    DEBUG_MODE = False
