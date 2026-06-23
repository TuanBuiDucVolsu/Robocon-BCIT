# Danh sách phần cứng — Robot Bảng O2

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
| 10 | Càng forklift (2 thanh nâng) | 2 | Đang làm |
| 11 | Pin 18650 + đế | 1 bộ | ≤12V, ≤5000mAh |
| 12 | Breadboard | 1 | Kết nối tạm |

## Phần cứng CẦN MUA THÊM

| STT | Linh kiện | SL | Chức năng | Giá ước tính |
|-----|-----------|:--:|-----------|-------------|
| 1 | Cảm biến dò line 8 mắt I2C (PCF8574) | 1 | Bám line sa bàn | ~80-120k |
| 2 | HC-SR04 (siêu âm) | 1 | Đo khoảng cách đến kệ | ~15-25k |
| 3 | Cảm biến IR obstacle | 1 | Xác nhận pallet trên càng | ~10-15k |
| 4 | Nút bấm thường hở | 1 | Khởi động robot | ~3-5k |
| 5 | Điện trở 1kΩ | 1 | Cầu phân áp ECHO | ~1k |
| 6 | Điện trở 2kΩ | 1 | Cầu phân áp ECHO | ~1k |
| 7 | Dây nối dupont (đực-cái, cái-cái) | ~30 | Kết nối module | ~20-30k |

**Tổng ước tính: ~130-200k VND**

## Sơ đồ đấu nối GPIO

```
Raspberry Pi 4
 ┌─────────────────────────────────────────────────────────┐
 │                                                         │
 │  ── L298N #1 (bánh xe) ──                               │
 │  GPIO 17 → IN1 → Motor bánh TRÁI (tiến, PWM)           │
 │  GPIO 27 → IN2 → Motor bánh TRÁI (lùi)                 │
 │  GPIO 22 → IN3 → Motor bánh PHẢI (tiến, PWM)           │
 │  GPIO 23 → IN4 → Motor bánh PHẢI (lùi)                 │
 │                                                         │
 │  ── L298N #2 (cẩu forklift) ──                          │
 │  GPIO 24 → IN3 → Motor cẩu TRÁI (nâng)                 │
 │  GPIO 25 → IN4 → Motor cẩu TRÁI (hạ)                   │
 │  GPIO  5 → ENA → Motor cẩu PHẢI (enable)               │
 │  GPIO  6 → IN1 → Motor cẩu PHẢI (nâng)                 │
 │  GPIO 13 → IN2 → Motor cẩu PHẢI (hạ)                   │
 │                                                         │
 │  ── Cảm biến dò line (I2C) ──                           │
 │  GPIO  2 (SDA) → Module line 8 mắt PCF8574             │
 │  GPIO  3 (SCL) → Module line 8 mắt PCF8574             │
 │  Địa chỉ I2C: 0x20                                     │
 │                                                         │
 │  ── Cảm biến siêu âm HC-SR04 ──                         │
 │  GPIO 19 → TRIG                                         │
 │  GPIO 20 ← ECHO (qua cầu phân áp 1kΩ + 2kΩ!)          │
 │                                                         │
 │  ── Cảm biến IR pallet ──                               │
 │  GPIO 26 ← OUT (LOW = có pallet)                        │
 │                                                         │
 │  ── Nút khởi động ──                                    │
 │  GPIO 16 ← NÚT → GND (pull-up bên trong Pi)            │
 │                                                         │
 │  ── Camera ──                                           │
 │  CSI port → Camera OV5647 (không dùng GPIO)             │
 │                                                         │
 │  TỔNG: 15/16 GPIO — ĐẠT (dư 1 chân)                    │
 └─────────────────────────────────────────────────────────┘
```

## Sơ đồ nguồn điện

```
Pin 18650 (≤12V, ≤5000mAh)
  │
  ├──→ XH-M401 (hạ áp) ──→ 5V
  │      ├──→ Raspberry Pi 4 (5V micro-USB hoặc GPIO 5V)
  │      ├──→ L298N #1 logic VCC (5V)
  │      ├──→ L298N #2 logic VCC (5V)
  │      ├──→ HC-SR04 VCC (5V)
  │      └──→ Line sensor VCC (có thể 3.3V hoặc 5V tuỳ module)
  │
  └──→ L298N VCC motor (điện áp pin trực tiếp)
       ├──→ Motor bánh trái
       ├──→ Motor bánh phải
       ├──→ Motor cẩu trái
       └──→ Motor cẩu phải

3.3V (từ Pi):
  ├──→ Cảm biến IR pallet VCC
  └──→ Line sensor VCC (nếu module dùng 3.3V)

GND chung: tất cả module, Pi, L298N, cảm biến
```

## Cầu phân áp HC-SR04 ECHO (BẮT BUỘC)

```
HC-SR04 ECHO (5V) ──┬── R1 (1kΩ) ──→ GPIO 20 (3.3V safe)
                     │
                     └── R2 (2kΩ) ──→ GND

Công thức: Vout = 5V × 2kΩ / (1kΩ + 2kΩ) = 3.33V → an toàn cho Pi

⚠️ KHÔNG NỐI TRỰC TIẾP ECHO → GPIO! Sẽ hỏng chân GPIO của Pi.
```

## Vị trí lắp đặt cảm biến trên robot

```
Nhìn từ trên xuống:

     ══════════════════  ← Càng trái
        [HC-SR04] →      ← Giữa 2 càng, mặt phát sóng hướng ra trước
     ══════════════════  ← Càng phải
        [IR pallet]↑     ← Mặt trên càng, hướng lên (phát hiện pallet)

     ┌──────────────────┐
     │  [Camera]  →     │  ← Giữa thân, hướng ra trước, ngang tầm kệ
     │   RPi 4          │
     │  [NÚT BẤM]  ●   │  ← Mặt trên, dễ bấm bằng tay
     │                  │
     │  [Line 8 mắt] ↓ │  ← Dưới gầm, sát mặt sàn (~3-5mm)
     ├──────────────────┤
     │ (bánh trái)(bánh phải) │  ← Bánh sau chủ động
     │    (caster)(caster)    │  ← Bánh trước đa hướng
     └──────────────────┘


Nhìn từ bên cạnh:

     Kệ hàng          Càng
     ┌──────┐    ══════════════
     │Pallet│    ║  [HC-SR04]   ← cao ~2-3cm so với sàn
     │      │    ║  [IR] ↑      ← trên mặt càng
     └──────┘    ══════════════
     ◄─4cm──►    ← khoảng cách dừng (APPROACH_DISTANCE)
```

## Bảng tổng hợp GPIO

| Chân | Chức năng | Loại | Module |
|:----:|-----------|------|--------|
| 2 | I2C SDA | Input | Line sensor |
| 3 | I2C SCL | Output | Line sensor |
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
| 26 | IR pallet sensor | Input (pull-up) | Cảm biến IR |
| 27 | IN2 bánh trái (lùi) | Output | L298N #1 |

**Tổng: 15 chân / Giới hạn: 16 chân — ĐẠT (dư 1 chân)**

## Lưu ý thi công

1. **GND chung**: tất cả module phải nối chung GND với Pi
2. **Cầu phân áp**: BẮT BUỘC cho HC-SR04 ECHO (5V→3.3V)
3. **Line sensor**: gắn dưới gầm, sát sàn 3-5mm, ngang tâm robot
4. **HC-SR04**: gắn giữa 2 càng, cao ~2-3cm, hướng thẳng ra trước
5. **IR pallet**: gắn trên mặt càng, hướng lên, vị trí pallet sẽ đè lên
6. **Camera**: hướng thẳng ra trước, ngang tầm nhìn kệ hàng
7. **Nút bấm**: vị trí dễ bấm, nối GPIO 16 ↔ GND
8. **Pin**: ≤12V, ≤5000mAh (quy định thể lệ Bảng O2)
9. **Khung robot**: ≤400x400x400mm khi xuất phát, không dùng kim loại (trừ ốc vít)
