# Danh sách phần cứng — Robot Bảng O2

> Chi tiết lắp QTR-8A + MCP3008: xem `docs/HUONG_DAN_LAP_QTR8A_MCP3008.md` và `docs/HUONG_DAN_PHAN_CUNG.md`

## Phần cứng đã có

| STT | Linh kiện | SL | Ghi chú |
|-----|-----------|:--:|---------|
| 1 | Raspberry Pi 4 Model B | 1 | Bộ điều khiển chính |
| 2 | Camera module CSI (OV5647) | 1 | Nhận diện kiện hàng HSV |
| 3 | Mạch L298N | 2 | #1 cho bánh xe, #2 cho cẩu |
| 4 | Mạch hạ áp XH-M401 | 1 | Hạ áp pin → 5V |
| 5 | DC motor giảm tốc 1:48 (bánh xe) | 2 | Bánh sau chủ động |
| 6 | DC motor cẩu (dây curoa) | 2 | Nâng/hạ forklift |
| 7 | Bánh xe xanh (bánh sau) | 2 | Chủ động |
| 8 | Bánh caster (bánh trước) | 2 | Đa hướng |
| 9 | Trụ nhôm định hình + curoa + con lăn | 2 bộ | Khung cẩu |
| 10 | Càng forklift (2 thanh nâng **độc lập**) | 2 | Mỗi càng 1 motor — thả riêng từng pallet |
| 11 | Pin 18650 + đế | 1 bộ | ≤12V, ≤5000mAh |
| 12 | Breadboard | 1 | Kết nối tạm |

## Phần cứng CẦN MUA THÊM

| STT | Linh kiện | SL | Chức năng | Giá ước tính |
|-----|-----------|:--:|-----------|-------------|
| 1 | QTR-8A (line sensor analog) | 1 | Dò line 6 mắt (CH0–5) | ~150-250k |
| 2 | MCP3008 (ADC SPI 8 kênh) | 1 | Đọc QTR + 2 IR pallet | ~15-25k |
| 3 | Cảm biến IR obstacle | **2** | Xác nhận pallet trái + phải (CH6–7) | ~20-30k |
| 4 | HC-SR04 (siêu âm) | 1 | Đo khoảng cách đến kệ | ~15-25k |
| 5 | Nút bấm thường hở | 1 | Khởi động robot | ~3-5k |
| 6 | Điện trở 1kΩ + 2kΩ | 1+1 | Cầu phân áp ECHO | ~2k |
| 7 | Dây nối dupont | ~30 | Kết nối module | ~20-30k |

**Tổng ước tính: ~220-360k VND**

## Sơ đồ đấu nối GPIO

```
Raspberry Pi 4
 ┌─────────────────────────────────────────────────────────┐
 │  ── L298N #1 (bánh xe) ──                               │
 │  GPIO 17/27/22/23 → Motor bánh trái/phải               │
 │                                                         │
 │  ── L298N #2 (cẩu forklift) ──                          │
 │  GPIO 24/25/5/6/13 → Motor cẩu trái/phải              │
 │                                                         │
 │  ── SPI → MCP3008 (ADC) ──                              │
 │  GPIO  8 (CE0), 9 (MISO), 10 (MOSI), 11 (SCLK)         │
 │    CH0-5 → QTR-8A 6 mắt                                │
 │    CH6   → IR pallet trái                               │
 │    CH7   → IR pallet phải                               │
 │                                                         │
 │  ── HC-SR04 ── GPIO 19 TRIG, 20 ECHO (cầu phân áp)     │
 │  ── Nút ── GPIO 16 ↔ GND                               │
 │  ── Camera CSI (không dùng GPIO)                        │
 │                                                         │
 │  TỔNG: 16/16 GPIO — vừa đúng giới hạn thể lệ           │
 └─────────────────────────────────────────────────────────┘
```

## Bảng tổng hợp GPIO

| Chân | Chức năng | Loại | Module |
|:----:|-----------|------|--------|
| 8 | SPI CE0 | SPI | MCP3008 |
| 9 | SPI MISO | SPI | MCP3008 |
| 10 | SPI MOSI | SPI | MCP3008 |
| 11 | SPI SCLK | SPI | MCP3008 |
| 5 | ENA cẩu phải | Output | L298N #2 |
| 6 | IN1 cẩu phải (nâng) | Output | L298N #2 |
| 13 | IN2 cẩu phải (hạ) | Output | L298N #2 |
| 16 | Nút khởi động | Input (pull-up) | Nút bấm |
| 17 | IN1 bánh trái (tiến, PWM) | Output PWM | L298N #1 |
| 19 | HC-SR04 TRIG | Output | Siêu âm |
| 20 | HC-SR04 ECHO | Input | Siêu âm (qua phân áp) |
| 22 | IN3 bánh phải (tiến, PWM) | Output PWM | L298N #1 |
| 23 | IN4 bánh phải (lùi) | Output | L298N #1 |
| 24 | IN3 cẩu trái (nâng) | Output | L298N #2 |
| 25 | IN4 cẩu trái (hạ) | Output | L298N #2 |
| 27 | IN2 bánh trái (lùi) | Output | L298N #1 |

## Cơ cấu cẩu + cảm biến

```
Motor trái/phải → 2 càng độc lập
  IR trái  → MCP3008 CH6
  IR phải  → MCP3008 CH7
QTR-8A (6 mắt) → MCP3008 CH0–CH5

Code: control/mcp3008_bus.py (bus SPI dùng chung + lock)
      control/motion.py (line), control/lift.py (IR pallet)
```

## Lưu ý thi công

1. **GND chung** cho tất cả module
2. **MCP3008 VDD/VREF = 3.3V** (không 5V)
3. **QTR-8A VCC = 5V**, gắn sát sàn 3–5mm
4. **Bật SPI**: `sudo raspi-config` → SPI → Enable
5. **Calibrate**: `python3 tests/test_motion.py` option 5 (LINE_THRESHOLD), `test_lift.py` option 3 (PALLET_THRESHOLD)
6. **Cầu phân áp** bắt buộc cho HC-SR04 ECHO
7. Pin ≤12V, ≤5000mAh; khung ≤400×400×400mm khi xuất phát
