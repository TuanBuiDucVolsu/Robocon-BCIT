# Robot Tự Động Bảng O2 — Robocon Bắc Ninh Mở Rộng 2026

**Giải Robocon Bắc Ninh mở rộng 2026 — Tranh Cúp Foxconn**
Chủ đề: "Khát vọng công nghệ" | Thi đấu: **08-09/08/2026** | Phường Bắc Giang, tỉnh Bắc Ninh

Robot tự động phân loại và vận chuyển hàng hoá trên sa bàn 4000x2000mm trong 240 giây.
Nâng **2 kiện/lượt** — hoàn thành 12 kiện trong **6 lượt** nâng.
Nhận diện kiện hàng bằng **phân tích màu HSV** (không cần AI model).

## Thông số kỹ thuật

| Hạng mục | Thông số | Giới hạn thể lệ |
|----------|----------|:----------------:|
| Vi xử lý | Raspberry Pi 4 Model B | 1 bộ điều khiển |
| GPIO | 16 chân | **16/16** |
| Động cơ | 4 (2 bánh xe + 2 cẩu) | **4/12** |
| Pin | ≤ 12V, ≤ 5000mAh | ≤ 12V, ≤ 5000mAh |
| Kích thước xuất phát | ≤ 400x400x400mm | ≤ 400x400x400mm |
| Camera AI | Camera CSI + OpenCV HSV | Bắt buộc (bảng O2) |
| Khung | Không kim loại (trừ ốc vít) | Theo thể lệ |

## Nhiệm vụ

- **NV1**: Lấy 12 kiện hàng từ 3 kho hải quan, nhận diện bằng Camera AI, giao đúng nhà máy (12 x 20 = **240 điểm**)
- **NV2**: Lấy kiện hàng rời, giao nhà máy liên hợp — **30 điểm** (chỉ sau khi hoàn thành 100% NV1)
- **Tổng tối đa: 270 điểm** | Reset: tối đa 5 lần, mỗi lần -10 điểm

## Cấu trúc project

```
Robocon-BCIT/
├── main.py                # State machine: INIT → NAVIGATE → PICKUP → DELIVER → DROP → lặp
├── config.py              # GPIO, route, HSV, timing — tất cả hằng số tinh chỉnh
├── requirements.txt       # Thư viện Python
│
├── control/               # Điều khiển phần cứng
│   ├── mcp3008_bus.py     #   Bus SPI dùng chung MCP3008 (lock)
│   ├── motion.py          #   Di chuyển + bám line PD analog + siêu âm HC-SR04
│   └── lift.py            #   Nâng/hạ 2 càng độc lập + cảm biến IR pallet (SPI)
│
├── vision/                # Nhận diện hình ảnh
│   └── vision.py          #   Camera CSI + phân tích màu HSV + classify_pair()
│
├── debug/                 # Giao diện web debug (Flask)
│   ├── server.py          #   Flask server + API (di chuyển, nâng/hạ, camera, cảm biến)
│   ├── templates/         #   HTML
│   └── static/            #   CSS + JS
│
├── tests/                 # Test từng module
│   ├── test_motion.py     #   Motor, line sensor, siêu âm, route, exit start
│   ├── test_lift.py       #   Nâng/hạ, IR pallet, drop từng càng, NV2
│   ├── test_vision.py     #   Camera, HSV, classify_pair
│   ├── test_smoke.py      #   Smoke test tích hợp trên sa bàn
│   └── test_logic.py      #   Unit test logic (chạy trên PC, không cần GPIO)
│
├── scripts/               # Triển khai
│   ├── install.sh         #   Cài systemd service tự khởi động
│   ├── start.sh           #   Script khởi chạy (ROBOT_COMPETE=1)
│   └── robot.service      #   Systemd unit file
│
└── docs/                  # Tài liệu
    ├── HUONG_DAN_CAI_DAT_LAN_DAU.md    # Cài đặt Pi lần đầu (14 bước)
    ├── HUONG_DAN_SSH_WIFI.md           # SSH + WiFi + debug không dây
    ├── HUONG_DAN_PHAN_CUNG.md          # Sơ đồ đấu nối phần cứng
    ├── HUONG_DAN_LAP_QTR8A_MCP3008.md  # Lắp QTR-8A + MCP3008 chi tiết
    ├── CAC_BUOC_ROBOT_HOAT_DONG.md     # Luồng state machine chi tiết
    ├── Thể lệ.pdf                      # Thể lệ giải đấu
    ├── Hướng dẫn thi công.pdf          # Hướng dẫn thi công đạo cụ
    ├── Hình dán khối bảng O2.pdf       # File in decal kiện hàng
    └── Sa bàn.jpg                      # Sơ đồ sa bàn
```

## Cài đặt nhanh

> Chi tiết đầy đủ từng bước: xem `docs/HUONG_DAN_CAI_DAT_LAN_DAU.md`

### 1. Cài thư viện hệ thống (bắt buộc chạy trước pip)

```bash
sudo apt update
sudo apt install -y python3-lgpio python3-gpiozero python3-spidev \
    python3-picamera2 python3-libcamera \
    python3-opencv python3-numpy
```

### 2. Bật SPI + Camera

```bash
sudo raspi-config
# → Interface Options → SPI    → Enable
# → Interface Options → Camera → Enable
sudo reboot
```

### 3. Clone code + cài thư viện pip

```bash
cd ~
git clone https://github.com/TÊN_TÀI_KHOẢN/Robocon-BCIT.git
cd Robocon-BCIT

python3 -m venv --system-site-packages ~/robot_env
source ~/robot_env/bin/activate
pip install -r requirements.txt
```

### 4. Kiểm tra

```bash
ls /dev/spidev*                          # Phải thấy spidev0.0 và spidev0.1
python3 -m unittest tests.test_logic -v  # Unit test logic — 31 test, chạy trên PC
```

## Cách chạy

### Chế độ debug (luyện tập — điều khiển qua web)

```bash
source ~/robot_env/bin/activate
python3 main.py
# Mở trình duyệt: http://<IP-của-Pi>:5000
```

`DEBUG_MODE = True` trong config.py → Flask web UI khởi động thay state machine.

Giao diện web:
- **Di chuyển**: nhấn giữ nút hoặc phím W/A/S/D, thanh trượt tốc độ
- **Camera**: xem trực tiếp MJPEG stream, nhấn nút nhận diện kiện hàng
- **Nâng/hạ**: nâng/hạ từng tầng, pickup/dropoff, reset
- **Cảm biến dò line**: 6 mắt QTR-8A + ADC raw, độ lệch, phát hiện giao lộ
- **IR pallet**: trái/phải realtime qua MCP3008 CH6–7

> Không cần nối màn hình vào Pi — SSH + web debug qua WiFi. Xem `docs/HUONG_DAN_SSH_WIFI.md`

### Chế độ thi đấu (tự động)

```bash
# Cách 1: sửa DEBUG_MODE = False trong config.py
python3 main.py

# Cách 2: qua systemd (giống ngày thi)
sudo bash scripts/install.sh
sudo systemctl start robot
# start.sh đặt ROBOT_COMPETE=1 → luôn chạy state machine
```

Robot chờ nhấn nút (GPIO 16) → chạy tự động 240 giây → dừng.

### Test từng module

```bash
python3 tests/test_motion.py    # 1-12: motor, line, siêu âm, route, exit start
python3 tests/test_lift.py      # 1-8: nâng/hạ, IR, drop từng càng, NV2
python3 tests/test_vision.py    # 1-7: camera, HSV, classify_pair
python3 tests/test_smoke.py     # Smoke test tích hợp trên sa bàn
python3 -m unittest tests.test_logic -v   # Unit test logic — chạy trên PC
```

### Quản lý systemd service

```bash
sudo systemctl status robot      # Xem trạng thái
sudo systemctl stop robot        # Dừng robot
sudo systemctl restart robot     # Khởi động lại
sudo systemctl disable robot     # Tắt tự khởi động
journalctl -u robot -f           # Log realtime
cat robot_log.txt                # Log file
```

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
  R0 [Kệ3]──line──┃GAP┃──line──[Foxconn]  ← Line R0 đứt quãng tại ô start
      │             ┃   ┃              │
      │          ←■Start┃              │   Robot quay mặt 9h (về Kệ 3)
      │             [Kệ4]             │   Kệ 4 thụt xuống, bên phải Start
```

- Kệ 1-3: cạnh TRÁI, cách nhau 2 giao lộ (R0, R2, R4)
- Kệ 4: bên PHẢI Start, thụt xuống dưới R0 (kho hàng rời — NV2)
- Robot xuất phát: ô start trên R0, quay mặt sang trái (9h) về Kệ 3
- Thứ tự lấy kệ: Kệ 3 (gần Start) → Kệ 2 → Kệ 1

## Phần cứng

### Sơ đồ bố trí trên robot

```
     ══════════════════  ← Càng trái + [IR trái]↑ (MCP3008 CH6)
        [HC-SR04] →      ← Siêu âm: giữa 2 càng, hướng ra trước
     ══════════════════  ← Càng phải + [IR phải]↑ (MCP3008 CH7)
     [QTR-8A 6 mắt] ↓   ← Dưới gầm, dò line analog qua MCP3008 CH0-5

     ┌──────────────────┐
     │  [Camera]  →     │  ← Camera CSI: giữa thân, hướng ra trước
     │   Raspberry Pi   │
     │  [MCP3008]       │
     │  [L298N x2]      │
     │  [XH-M401]       │  ← Hạ áp 12V → 5V cho Pi
     ├──────────────────┤
     │ (bánh trái)(bánh phải) │
     └──────────────────┘
```

### Sơ đồ đấu nối

```
MCP3008 (ADC SPI):             HC-SR04 (siêu âm):
  VDD  → 3.3V                   VCC  → 5V
  VREF → 3.3V                   TRIG → GPIO 19
  CLK  → GPIO 11 (SCLK)         ECHO → GPIO 20 (qua cầu
  DOUT → GPIO  9 (MISO)                 phân áp 1kΩ + 2kΩ)
  DIN  → GPIO 10 (MOSI)         GND  → GND
  CS   → GPIO  8 (CE0)
  CH0-5 → QTR-8A 6 mắt        Nút khởi động:
  CH6   → IR càng trái          GPIO 16 ── [NÚT] ── GND
  CH7   → IR càng phải

Nguồn:                         Cầu phân áp cho ECHO:
  Pin 12V ─┬→ L298N #1          ECHO ──┬── R1 (1kΩ) → GPIO 20
           ├→ L298N #2                 └── R2 (2kΩ) → GND
           └→ XH-M401 (5.1V) → Pi USB-C
```

> Chi tiết: xem `docs/HUONG_DAN_PHAN_CUNG.md`

### Bảng GPIO

| Chân | Chức năng | Module |
|:----:|-----------|--------|
| 8 | SPI CE0 (MCP3008) | mcp3008_bus.py |
| 9 | SPI MISO | mcp3008_bus.py |
| 10 | SPI MOSI | mcp3008_bus.py |
| 11 | SPI SCLK | mcp3008_bus.py |
| 5 | ENA cẩu phải | lift.py |
| 6 | IN1 cẩu phải (nâng) | lift.py |
| 13 | IN2 cẩu phải (hạ) | lift.py |
| 16 | Nút khởi động | main.py |
| 17 | IN1 bánh trái (tiến, PWM) | motion.py |
| 19 | HC-SR04 TRIG | motion.py |
| 20 | HC-SR04 ECHO | motion.py |
| 22 | IN1 bánh phải (tiến, PWM) | motion.py |
| 23 | IN2 bánh phải (lùi) | motion.py |
| 24 | IN3 cẩu trái (nâng) | lift.py |
| 25 | IN4 cẩu trái (hạ) | lift.py |
| 27 | IN2 bánh trái (lùi) | motion.py |

**16/16 GPIO** — vừa đúng giới hạn thể lệ

## Nhận diện kiện hàng (HSV Color)

Camera chụp ảnh → chia trái/phải → phân tích màu HSV → nhận diện:

| Kiện | Màu chủ đạo | Dải HSV |
|------|-------------|---------|
| 01 Samsung | Xanh dương | H=90-130, S>60, V>40 |
| 02 Foxconn | Vàng đồng | H=15-40, S>60, V>80 |
| 03 Amkor | Xám bạc | S<40 (saturation thấp) |
| 04 Hana Micron | Đỏ/hồng | H=0-10 hoặc H=160-179 |

Tinh chỉnh ngưỡng: `python3 tests/test_vision.py` option 2

## State Machine

```
INIT (chờ nút) → START (reset càng, exit_start_zone → chạm line R0)
  │
  ├── NAVIGATE_TO_SHELF → PICKUP_PAIR
  │     _plan_delivery() — tối ưu thứ tự giao (cost gồm return về kệ)
  │     → DELIVER_FIRST → DROP_FIRST
  │     → DELIVER_SECOND → DROP_SECOND (nếu 2 kiện khác nhà máy)
  │     → RETURN_TO_WAREHOUSE (get_return_route → đúng hàng kệ)
  │     → lặp 6 lượt (3 kệ × 2 tầng)
  │
  ├── TASK2: nhà máy cuối → Kệ 4 → pickup → nhà máy liên hợp → drop
  │
  └── DONE
```

**Thời gian dự kiến: ~180–185s hiện tại → ~135–145s sau calibrate / 240s giới hạn**
(chi tiết phân bổ: `docs/TOI_UU_TOC_DO.md` mục 1)

### Điều hướng quan trọng

| API | Mục đích |
|-----|----------|
| `get_return_route(factory, target_shelf)` | Quay về đúng hàng R0/R2/R4 trước pickup tầng 2 |
| `_between_route(a, b)` | Route giữa 2 NM; fallback chiều ngược |
| `_plan_delivery()` | Chọn thứ tự giao: shelf→NM1→NM2 + **return** |

Scenario calibrate bắt buộc: **Kệ3 T1 → foxconn → samsung → return → Kệ3 T2**

### Xử lý lỗi

| Tình huống | Hành vi |
|-----------|---------|
| Navigate đến kệ fail | `_retry_or_skip_tier("navigate")` → **NAVIGATE_TO_SHELF** |
| Approach kệ timeout (PICKUP) | `_retry_or_skip_tier("approach")` |
| Không có HC-SR04 | approach/retreat → `False` |
| Scan fail (confidence thấp) | Retry → bỏ tầng |
| IR không thấy pallet | Retry → bỏ tầng |
| SPI/ADC lỗi | pickup/drop không coi thành công |
| Navigate giao hàng fail | Log cảnh báo, vẫn thử hạ |
| Return route fail | Log cảnh báo, vẫn advance |
| NV2 fail | Chuyển DONE |
| NV2 drop fail | Log lỗi, vẫn DONE (không log hoàn thành) |
| Sắp hết giờ (<10s) | DONE |

## Tinh chỉnh tham số

Các giá trị cần đo thực nghiệm trên sa bàn, cập nhật trong `config.py`:

| Tham số | Mô tả | Cách đo |
|---------|-------|---------|
| `TURN_TIME` | Thời gian xoay 90° | test_motion option 10 |
| `LIFT_TIME_SHELF_1/2` | Thời gian nâng càng | Đo stopwatch từng càng |
| `PWM_COMPENSATION` | Bù lệch tốc độ bánh | Cho chạy thẳng, chỉnh đến khi không lệch |
| `LINE_KP`, `LINE_KD` | Hệ số PD bám line | Thử trên sa bàn |
| `LINE_BLACK_IS_HIGH`, `LINE_THRESHOLD` | Polarity + ngưỡng QTR-8A | `python3 -m tools.calibrate_line` |
| `EXIT_START_*` | Thoát ô start | test_motion option 6 |
| `ROUTE_*` | Số giao lộ các route | ✅ đã verify từ file in chuẩn — xem `docs/SA_BAN_O2_LUOI.md` |
| `get_return_route` / đoạn dọc | Return về đúng hàng kệ | Test scenario foxconn→samsung → Kệ3 T2 |
| `COLOR_RANGES` | Dải màu HSV | test_vision option 2 |
| `PALLET_THRESHOLD` | Ngưỡng IR pallet | test_lift option 3 |
| `APPROACH_FAST/SLOW_SPEED`, `APPROACH_SLOW_DISTANCE` | Tiếp cận kệ 2 pha | test_motion option 9 — đảm bảo không vọt quá 4cm |

> **Tiếp cận 2 pha + PWM cả 2 chiều:** `approach_shelf()` đi nhanh ở xa, chậm khi gần
> (siêu âm lấy median 3 mẫu chống nhiễu). Động cơ bánh PWM cả tiến lẫn lùi → lùi/xoay
> đúng tốc độ. Xem chi tiết tối ưu: `docs/TOI_UU_TOC_DO.md`.

## Tài liệu

| File | Nội dung |
|------|----------|
| `docs/HUONG_DAN_CAI_DAT_LAN_DAU.md` | Cài đặt Pi lần đầu (flash OS → chạy robot, 14 bước) |
| `docs/HUONG_DAN_SSH_WIFI.md` | SSH + WiFi + debug web không dây + hotspot điện thoại |
| `docs/HUONG_DAN_PHAN_CUNG.md` | Sơ đồ đấu nối phần cứng chi tiết + checklist |
| `docs/HUONG_DAN_LAP_QTR8A_MCP3008.md` | Lắp QTR-8A + MCP3008 từng bước |
| `docs/CAC_BUOC_ROBOT_HOAT_DONG.md` | Luồng state machine chi tiết (từng state, biến theo dõi) |
| `docs/TOI_UU_TOC_DO.md` | Phân tích thời gian + 6 tối ưu tốc độ + fast profile config |
| `docs/SA_BAN_O2_LUOI.md` | Lưới sa bàn O2 đối chiếu từ file in chuẩn + verify số giao lộ |

## Lưu ý quan trọng

1. **Trước thi đấu**: `DEBUG_MODE = False` hoặc chạy qua systemd (`ROBOT_COMPETE=1`)
2. **Không có network call** trong vòng lặp — tất cả chạy offline
3. Chân ECHO HC-SR04 **bắt buộc** qua cầu phân áp 1kΩ+2kΩ (5V→3.3V)
4. **Đặt robot hướng 9h** trong ô start — ô start không có line (GAP R0)
5. NV1 cần **cả 2 IR**; NV2 chỉ cần **1 IR**; `packages_delivered` chỉ tăng khi IR xác nhận
6. Ánh sáng thi đấu **không ổn định** — calibrate HSV tại sân trước trận
7. Chạy test_motion **6** (exit start) → **10–11** (xoay 90°, route) trước full
8. Smoke test: `test_smoke.py` option **5** — đặc biệt scenario return sau 2 NM khác nhau
9. File log: `robot_log.txt`; systemd log: `journalctl -u robot -f`
