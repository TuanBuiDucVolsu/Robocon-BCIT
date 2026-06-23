# Robot Tự Động Bảng O2 — Robocon Bắc Ninh Mở Rộng 2026

Robot tự động (autonomous state machine) phân loại và vận chuyển hàng hoá trên sa bàn.
Nâng **2 kiện/lượt** — hoàn thành 12 kiện trong **6 lượt** nâng.
Nhận diện kiện hàng bằng **phân tích màu HSV** (không cần AI model).

## Thư viện sử dụng

| Thư viện | Mục đích | Ghi chú |
|----------|----------|---------|
| `gpiozero` + `lgpio` | Điều khiển GPIO (động cơ, nút bấm, cảm biến) | Tương thích RPi OS Bullseye & Bookworm |
| `picamera2` | Camera CSI trên RPi 4 | Thay thế picamera (deprecated) |
| `smbus2` | Đọc cảm biến dò line qua I2C | Cần bật I2C trong raspi-config |
| `numpy` + `opencv` | Phân tích màu HSV nhận diện kiện hàng | Không cần model AI |
| `flask` | Giao diện web debug khi luyện tập | Chỉ dùng khi DEBUG_MODE = True |

## Cấu trúc project

```
Robocon-BCIT/
├── main.py                # Điểm khởi chạy — state machine (nâng 2 kiện/lượt)
├── config.py              # Hằng số cấu hình (GPIO, tốc độ, kệ hàng, màu HSV)
├── requirements.txt       # Danh sách thư viện Python
│
├── control/               # Điều khiển phần cứng
│   ├── __init__.py
│   ├── motion.py          #   Di chuyển + bám line + cảm biến siêu âm
│   └── lift.py            #   Nâng/hạ càng forklift + cảm biến IR pallet
│
├── vision/                # Nhận diện hình ảnh
│   ├── __init__.py
│   └── vision.py          #   Camera + phân tích màu HSV
│
├── debug/                 # Giao diện web debug (Flask)
│   ├── __init__.py
│   ├── server.py          #   Flask server + API endpoints
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── style.css
│       └── app.js
│
├── tests/                 # Script test từng module
│   ├── test_motion.py     #   Test động cơ, line sensor, siêu âm, tiếp cận kệ
│   ├── test_lift.py       #   Test nâng/hạ + cảm biến IR pallet
│   └── test_vision.py     #   Test camera & nhận diện màu HSV
│
├── scripts/               # Script triển khai
│   ├── install.sh         #   Cài service tự khởi động
│   ├── start.sh           #   Script khởi chạy (gọi bởi systemd)
│   └── robot.service      #   Systemd unit file
│
└── docs/                  # Tài liệu
    ├── PLAN.md
    ├── Sa bàn.jpg
    └── Hình dán khối bảng O2.pdf
```

## Cài đặt

### Bước 1: Cài gói hệ thống qua apt (BẮT BUỘC chạy trước)

```bash
sudo apt update
sudo apt install -y python3-lgpio python3-gpiozero \
    python3-picamera2 python3-libcamera \
    python3-opencv python3-numpy i2c-tools
```

### Bước 2: Bật I2C và Camera

```bash
sudo raspi-config
# -> Interface Options -> I2C    -> Enable
# -> Interface Options -> Camera -> Enable
sudo reboot
```

### Bước 3: Kiểm tra I2C nhận module dò line

```bash
sudo i2cdetect -y 1
# Phải thấy địa chỉ 0x20 (hoặc địa chỉ module của đội)
```

### Bước 4: Cài thêm thư viện qua pip

```bash
python3 -m venv --system-site-packages ~/robot_env
source ~/robot_env/bin/activate
pip install -r requirements.txt
```

## Hệ thống cảm biến

### Sơ đồ bố trí trên robot

```
         Nhìn từ trên xuống:

         ══════════════════  ← Càng trái
            [HC-SR04] →      ← Siêu âm: giữa 2 càng, hướng ra trước
         ══════════════════  ← Càng phải
            [IR pallet]↑     ← IR: mặt trên càng, hướng lên (phát hiện pallet)

         ┌──────────────────┐
         │  [Camera]  →     │  ← Camera CSI: giữa thân, hướng ra trước
         │   Raspberry Pi   │
         │  [Line sensor]↓  │  ← Dò line 8 mắt: dưới gầm robot
         ├──────────────────┤
         │ (bánh trái)(bánh phải) │
         └──────────────────┘
```

### Sơ đồ đấu nối

```
HC-SR04 (siêu âm):             Cảm biến IR (pallet):
  VCC  → 5V                      VCC → 3.3V
  TRIG → GPIO 19                 GND → GND
  ECHO → GPIO 20 (qua cầu       OUT → GPIO 26
          phân áp 1kΩ + 2kΩ)
  GND  → GND                   Nút khởi động:
                                  GPIO 16 ── [NÚT] ── GND
Cầu phân áp cho ECHO (bảo vệ GPIO):
  ECHO ──┬── R1 (1kΩ) ──→ GPIO 20
         └── R2 (2kΩ) ──→ GND
```

### Cách robot tìm và tiếp cận kệ

```
① Bám line → đếm giao lộ → dừng tại giao lộ kệ
② approach_shelf(): tiến chậm 30% + đo siêu âm liên tục
③ Khi khoảng cách ≤ 4cm → dừng chính xác trước kệ
④ Nâng càng → cảm biến IR xác nhận có pallet
⑤ retreat_from_shelf(): lùi + đo siêu âm
⑥ Khi khoảng cách ≥ 15cm → dừng, đủ xa để xoay/bám line tiếp
```

## Nhận diện kiện hàng (HSV Color)

Không cần train model AI. Camera chụp ảnh → phân tích màu HSV → nhận diện:

| Kiện | Hình ảnh | Màu chủ đạo | Dải HSV |
|------|----------|-------------|---------|
| 01 — Samsung | Chip xanh dương | Xanh dương | H=90-130, S>60, V>40 |
| 02 — Foxconn | Chip vàng đồng | Vàng | H=15-40, S>60, V>80 |
| 03 — Amkor | Khối nhôm Al | Xám bạc | S<50 (saturation thấp) |
| 04 — Hana Micron | QR code viền đỏ | Đỏ/hồng | H=0-10 hoặc H=160-179 |

Khi nâng 2 kiện cùng lúc, camera chia ảnh **trái/phải** để nhận diện riêng từng kiện.

Tinh chỉnh ngưỡng HSV:
```bash
python3 tests/test_vision.py   # Chọn option 2: "Phân tích màu HSV"
```

## Nút khởi động vật lý

### Cài đặt tự khởi động khi bật Pi

```bash
sudo bash scripts/install.sh
```

Sau khi cài:
1. **Bật Pi** → service tự chạy `main.py` → robot ở trạng thái **INIT** (chờ nút)
2. **Nhấn nút** → robot bắt đầu chương trình tự động (240 giây)
3. Kết thúc → robot dừng, chờ reset

Lệnh quản lý service:
```bash
sudo systemctl status robot      # Xem trạng thái
sudo systemctl stop robot        # Dừng robot
sudo systemctl restart robot     # Khởi động lại
sudo systemctl disable robot     # Tắt tự khởi động
journalctl -u robot -f           # Xem log realtime
```

## Cách chạy thủ công

### Chế độ thi đấu (tự động)
```bash
# Đảm bảo DEBUG_MODE = False trong config.py
python3 main.py
```

### Chế độ debug (luyện tập)
```bash
# Đặt DEBUG_MODE = True trong config.py
python3 main.py
# Mở trình duyệt: http://<IP-của-Pi>:5000
```

Giao diện debug bao gồm:
- **Di chuyển**: nhấn giữ nút hoặc phím W/A/S/D, thanh trượt tốc độ
- **Camera**: xem trực tiếp (MJPEG stream), nhấn nút nhận diện kiện hàng
- **Nâng/hạ**: nâng/hạ từng tầng, pickup/dropoff, reset
- **Cảm biến dò line**: hiển thị 8 mắt real-time, độ lệch, phát hiện giao lộ

### Test từng module
```bash
python3 tests/test_motion.py   # Test động cơ, line sensor, siêu âm, tiếp cận kệ
python3 tests/test_lift.py     # Test nâng/hạ + cảm biến IR pallet
python3 tests/test_vision.py   # Test camera & nhận diện màu HSV
```

## Bảng GPIO sử dụng

| Chân GPIO | Chức năng                      | Module              |
|-----------|--------------------------------|---------------------|
| 17        | IN1_XE_T (trái tiến, PWM)     | control/motion.py   |
| 27        | IN2_XE_T (trái lùi)           | control/motion.py   |
| 22        | IN1_XE_P (phải tiến, PWM)     | control/motion.py   |
| 23        | IN2_XE_P (phải lùi)           | control/motion.py   |
| 24        | IN3_CAU_T (cẩu trái nâng)     | control/lift.py     |
| 25        | IN4_CAU_T (cẩu trái hạ)       | control/lift.py     |
| 5         | ENA_CAU_P (enable cẩu phải)   | control/lift.py     |
| 6         | IN1_CAU_P (cẩu phải nâng)     | control/lift.py     |
| 13        | IN2_CAU_P (cẩu phải hạ)       | control/lift.py     |
| 16        | START_BUTTON (nút khởi động)   | main.py             |
| 26        | PALLET_SENSOR (IR pallet)      | control/lift.py     |
| 19        | ULTRASONIC_TRIG (siêu âm)     | control/motion.py   |
| 20        | ULTRASONIC_ECHO (siêu âm)     | control/motion.py   |
| 2         | I2C SDA (line sensor)          | control/motion.py   |
| 3         | I2C SCL (line sensor)          | control/motion.py   |

**Tổng: 15 chân GPIO** (giới hạn thể lệ: 16 chân) — **ĐẠT** (dư 1 chân)

## Bảng động cơ sử dụng

| STT | Động cơ            | Chức năng          |
|-----|--------------------|--------------------|
| 1   | DC motor trái      | Bánh xe trái       |
| 2   | DC motor phải      | Bánh xe phải       |
| 3   | DC motor cẩu trái  | Nâng/hạ càng trái  |
| 4   | DC motor cẩu phải  | Nâng/hạ càng phải  |

**Tổng: 4 động cơ** (giới hạn thể lệ: 12 động cơ) — **ĐẠT**

## Bố trí sa bàn (phía xanh)

```
    Col0 (kệ/trái)   Col1 (giữa)    Col2 (nhà máy/phải)
      │                  │               │
  R4 [Kệ1]──────────────┼──[Samsung]─────┤   ← Kệ 1 thẳng Samsung
      │                  │               │
  R3  │                  │──[Hana M.]─────┤
      │        ◉         │               │
  R2 [Kệ2]──────────────┼──[Liên hợp]────┤   ← Kệ 2 thẳng Robocon / Liên hợp
      │                  │               │
  R1  │                  │──[Amkor]───────┤
      │                  │               │
  R0 [Kệ3]──■ Start ────┼──[Foxconn]─────┤   ← Kệ 3 thẳng Start / Foxconn
      │                  │               │
      │       [Kệ4]     │               │   ← Kệ 4 thụt xuống, bên phải Start
```

- Kệ 1-3: cạnh TRÁI, cách nhau 2 giao lộ (R0, R2, R4)
- Kệ 4: bên PHẢI Start, thụt xuống dưới R0 (kho hàng rời — NV2)
- Robot xuất phát tại Start (R0 giữa), quay mặt lên trên

### Giá kệ

```
240 x 120 x 240mm, chân cao 25mm, 2 tầng
  ┌─────────────────────┐
  │ [Pallet A][Pallet B] │  ← Tầng 2 (trên)
  │ [Pallet C][Pallet D] │  ← Tầng 1 (dưới)
  └─────────────────────┘
  Mỗi tầng: 2 pallet cạnh nhau → nâng cùng lúc

Tổng: 4 kệ
  Kệ 1-3 (kho hải quan): 3 kệ × 4 pallet = 12 kiện → Nhiệm vụ 1
  Kệ 4   (kho hàng rời): 1 pallet (4 khối khác loại) → Nhiệm vụ 2
```

## State Machine — Nâng 2 kiện/lượt (6 lượt)

```
INIT → START →
  ┌─→ NAVIGATE_TO_SHELF (execute_route + rẽ hướng tại giao lộ)
  │   SCAN_PAIR (camera chia trái/phải, phân tích HSV)
  │   PICKUP_PAIR:
  │     approach_shelf() — tiến + siêu âm dừng ở 4cm
  │     lift.pickup() — nâng + IR xác nhận pallet
  │     retreat_from_shelf() — lùi + siêu âm dừng ở 15cm
  │   DELIVER_FIRST → DROP_FIRST (giao nhà máy gần trước)
  │   DELIVER_SECOND → DROP_SECOND (giao nhà máy xa)  ← bỏ qua nếu cùng nhà máy
  │   RETURN_TO_WAREHOUSE
  └── (lặp 6 lượt)
  → TASK2 (nhà máy cuối → Kệ 4 → nhà máy liên hợp)
  → DONE
```

### Thứ tự lấy kệ: Kệ 3 (gần Start) → Kệ 2 → Kệ 1

| Lượt | Kệ | Tầng | Route đi | Route giao |
|------|----|------|----------|------------|
| 1 | Kệ 3 (R0) | T1 | Start → rẽ trái → Kệ 3 | Quay phải 2 lần → đi ngang sang nhà máy |
| 2 | Kệ 3 (R0) | T2 | Tại chỗ | Quay phải 2 lần → đi ngang |
| 3 | Kệ 2 (R2) | T1 | Tiến 2 giao lộ lên | Quay phải 2 lần → đi ngang |
| 4 | Kệ 2 (R2) | T2 | Tại chỗ | Quay phải 2 lần → đi ngang |
| 5 | Kệ 1 (R4) | T1 | Tiến 2 giao lộ lên | Quay phải 2 lần → đi ngang |
| 6 | Kệ 1 (R4) | T2 | Tại chỗ → xong NV1 | NV2: nhà máy cuối → Kệ 4 → Liên hợp |

**Tối ưu:** Kệ thẳng hàng nhà máy → Samsung/Foxconn chỉ cần đi ngang (không rẽ lên/xuống).
Nếu 2 kiện cùng nhà máy → giao 1 điểm duy nhất.

**Thời gian dự kiến: ~90-140 giây (NV1) + ~20-30 giây (NV2) = ~120-170 giây**
**Giới hạn trận đấu: 240 giây**

## Tinh chỉnh tham số

Các giá trị cần đo thực nghiệm trên sa bàn và cập nhật trong `config.py`:

| Tham số | Mô tả | Cách đo |
|---------|-------|---------|
| `APPROACH_DISTANCE` | Khoảng cách dừng trước kệ (cm) | Đo khi càng vừa luồn vào dưới pallet |
| `RETREAT_DISTANCE` | Khoảng cách lùi ra sau nâng/hạ (cm) | Đo khi robot đủ xa để xoay |
| `LIFT_TIME_SHELF_1/2` | Thời gian nâng càng cho từng tầng kệ | Đo bằng stopwatch |
| `PWM_COMPENSATION` | Hệ số bù lệch tốc độ bánh phải | Cho chạy thẳng, chỉnh đến khi không lệch |
| `LINE_KP`, `LINE_KD` | Hệ số PD bám line | Thử trên sa bàn, tăng/giảm đến khi mượt |
| `SPEED_DEFAULT/SLOW` | Tốc độ di chuyển | Cân bằng giữa nhanh và ổn định |
| `NAV_START_TO_SHELF_0` | Giao lộ từ xuất phát đến kệ 1 | Đếm trên sa bàn |
| `NAV_BETWEEN_SHELVES` | Giao lộ giữa 2 kệ liên tiếp | Đếm trên sa bàn |
| `NAV_WAREHOUSE_TO_*` | Giao lộ từ kho đến từng nhà máy | Đếm trên sa bàn |
| `FACTORY_DISTANCE` | Khoảng cách giữa các nhà máy | Đếm trên sa bàn |
| `COLOR_RANGES` | Dải màu HSV cho từng kiện | Chạy test_vision.py option 2 |

## Lưu ý quan trọng

1. **Trước khi thi đấu**: đảm bảo `DEBUG_MODE = False` trong `config.py`
2. **Không có network call** nào trong vòng lặp chính — tất cả chạy offline
3. File log được ghi tại `robot_log.txt` để debug sau mỗi lượt chạy
4. Cảm biến dò line cần dùng module **I2C** (PCF8574) để tiết kiệm chân GPIO
5. Chân ECHO của HC-SR04 **bắt buộc** dùng cầu phân áp (1kΩ + 2kΩ) để bảo vệ GPIO 3.3V
6. Chạy `test_motion.py` option 6-7 để kiểm tra siêu âm + tiếp cận kệ trước khi chạy full
