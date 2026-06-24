# Hướng dẫn thi công phần cứng — Robot Bảng O2

## Tổng quan hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│                    RASPBERRY PI 4                           │
│                                                             │
│  SPI bus ──→ MCP3008 (ADC 10-bit, 8 kênh)                  │
│              ├── CH0-CH5: QTR-8A dò line (6 mắt)           │
│              ├── CH6: IR pallet trái                        │
│              └── CH7: IR pallet phải                        │
│                                                             │
│  GPIO ──→ L298N #1 ──→ 2 motor bánh xe                     │
│  GPIO ──→ L298N #2 ──→ 2 motor cẩu (trái/phải độc lập)    │
│  GPIO ──→ HC-SR04  ──→ Đo khoảng cách phía trước           │
│  GPIO ──→ Nút bấm ──→ Khởi động robot                      │
│  CSI  ──→ Camera   ──→ Nhận diện kiện hàng                 │
└─────────────────────────────────────────────────────────────┘
```

**Tổng: 16/16 cổng GPIO — dùng hết, không dư.**

> **Line vs IR — độc lập chức năng, chung MCP3008:** QTR (CH0–5) và IR pallet (CH6–7) là hai nhóm cảm biến riêng (vị trí, nhiệm vụ, code). Chúng cùng nối vào **một chip MCP3008** vì Pi không đọc analog trực tiếp và tiết kiệm GPIO (SPI chỉ 4 chân cho 8 kênh analog). Chi tiết lắp từng bước: `docs/HUONG_DAN_LAP_QTR8A_MCP3008.md`

---

## 1. Cảm biến dò line — QTR-8A + MCP3008

### Tại sao cần MCP3008?

QTR-8A xuất tín hiệu **analog** (điện áp thay đổi theo mức phản xạ), nhưng Raspberry Pi **không có chân analog**. MCP3008 chuyển tín hiệu analog thành số (0-1023) qua giao tiếp SPI.

### Sơ đồ đấu nối

```
QTR-8A (8 mắt trên thanh, chỉ nối 6 mắt đầu — mắt 1→6)
  Mắt 1 ──→ MCP3008 CH0
  Mắt 2 ──→ MCP3008 CH1
  Mắt 3 ──→ MCP3008 CH2
  Mắt 4 ──→ MCP3008 CH3
  Mắt 5 ──→ MCP3008 CH4
  Mắt 6 ──→ MCP3008 CH5
  Mắt 7 ──→ (không nối — dành kênh CH6–7 cho IR pallet)
  Mắt 8 ──→ (không nối)
  VCC   ──→ 5V
  GND   ──→ GND

MCP3008 (ADC SPI)
  VDD   ──→ 3.3V
  VREF  ──→ 3.3V
  AGND  ──→ GND
  DGND  ──→ GND
  CLK   ──→ GPIO 11 (SCLK)
  DOUT  ──→ GPIO  9 (MISO)
  DIN   ──→ GPIO 10 (MOSI)
  CS    ──→ GPIO  8 (CE0)
  CH0-5 ──→ QTR-8A mắt 1-6
  CH6   ──→ IR pallet trái
  CH7   ──→ IR pallet phải
```

### Sơ đồ chân MCP3008 (DIP-16)

```
        ┌────────────┐
  CH0 ──┤ 1       16 ├── VDD (3.3V)
  CH1 ──┤ 2       15 ├── VREF (3.3V)
  CH2 ──┤ 3       14 ├── AGND (GND)
  CH3 ──┤ 4       13 ├── CLK  (GPIO 11)
  CH4 ──┤ 5       12 ├── DOUT (GPIO 9)
  CH5 ──┤ 6       11 ├── DIN  (GPIO 10)
  CH6 ──┤ 7       10 ├── CS   (GPIO 8)
  CH7 ──┤ 8        9 ├── DGND (GND)
        └────────────┘
```

### Tại sao chỉ dùng 6 mắt thay vì 8?

MCP3008 chỉ có **8 kênh analog** (CH0–CH7). Cần **2 kênh cho IR pallet** (CH6, CH7) → còn **6 kênh** cho QTR → bỏ mắt 7 và 8 (ngoài cùng). 6 mắt giữa vẫn đủ bám line PD.

**Lưu ý:** Đây là giới hạn **kênh ADC**, không phải thiếu GPIO — dù 6 hay 8 mắt QTR thì SPI vẫn chỉ tốn 4 chân GPIO.

### Cách đọc (trong code)

- `control/mcp3008_bus.py` — bus SPI chung (Motion + Lift)
- `control/motion.py` — `LineSensor` đọc CH0–CH5
- Ngưỡng `LINE_THRESHOLD` trong `config.py` (mặc định 500)
- Bám line dùng **weighted average analog** (`compute_line_error_analog`), giao lộ vẫn dùng digital (≥5/6 mắt active)

---

## 2. Cảm biến IR pallet — 2 cái qua MCP3008

### Tại sao cần 2 cảm biến IR?

Robot có **2 càng độc lập** (trái/phải), mỗi càng mang 1 pallet. Cần biết **từng bên** có pallet hay không để:
- Xác nhận nâng thành công (cả 2 hoặc chỉ 1)
- Xác nhận thả đúng bên khi giao 2 nhà máy khác nhau

### Đấu nối

```
IR obstacle sensor TRÁI:
  VCC ──→ 3.3V
  GND ──→ GND
  OUT ──→ MCP3008 CH6

IR obstacle sensor PHẢI:
  VCC ──→ 3.3V
  GND ──→ GND
  OUT ──→ MCP3008 CH7
```

### Cách đọc

Code đọc qua `control/mcp3008_bus.py` (bus SPI dùng chung + lock) → `control/lift.py` (`PalletSensors`):

- Giá trị ADC **0–1023** từ MCP3008 CH6/CH7
- Ngưỡng `PALLET_THRESHOLD` trong `config.py` (mặc định 500)
- Giá trị **thấp** (< ngưỡng) = có pallet (IR phản xạ mạnh)
- Giá trị **cao** (≥ ngưỡng) = không có pallet
- NV1: cần **cả 2 IR** (`require_both=True`); NV2 kho rời: **1 IR** đủ
- SPI/ADC lỗi → pickup/drop **không** coi thành công

### Vị trí lắp

```
     ══════════════════  ← Càng trái
        [IR trái]↑       ← Gắn trên mặt càng trái, hướng lên
        [HC-SR04] →      ← Giữa 2 càng
        [IR phải]↑       ← Gắn trên mặt càng phải, hướng lên
     ══════════════════  ← Càng phải
```

---

## 3. Cảm biến siêu âm HC-SR04

### Chức năng

Đo khoảng cách phía trước robot → dừng chính xác trước kệ hàng (cách 4cm).

### Đấu nối

```
HC-SR04:
  VCC  ──→ 5V
  TRIG ──→ GPIO 19
  ECHO ──→ qua CẦU PHÂN ÁP ──→ GPIO 20
  GND  ──→ GND

⚠️ BẮT BUỘC: Cầu phân áp cho ECHO (5V → 3.3V)

  ECHO ──┬── R1 (1kΩ) ──→ GPIO 20
         │
         └── R2 (2kΩ) ──→ GND

  Vout = 5V × 2kΩ/(1kΩ+2kΩ) = 3.33V → an toàn cho Pi

  ⚠️ KHÔNG NỐI TRỰC TIẾP ECHO VÀO GPIO — SẼ HỎNG Pi!
```

### Vị trí lắp

Gắn giữa 2 càng forklift, mặt phát sóng hướng thẳng ra trước, cao ~2-3cm so với sàn.

---

## 4. Động cơ bánh xe — L298N #1

### Đấu nối

```
L298N #1:
  12V (VCC motor) ──→ Pin trực tiếp (≤12V)
  5V (logic)      ──→ XH-M401 output 5V
  GND             ──→ GND chung

  IN1 ←── GPIO 17  →  Motor TRÁI tiến (có PWM điều tốc)
  IN2 ←── GPIO 27  →  Motor TRÁI lùi
  IN3 ←── GPIO 22  →  Motor PHẢI tiến (có PWM điều tốc)
  IN4 ←── GPIO 23  →  Motor PHẢI lùi

  OUT1/OUT2 ──→ Motor bánh TRÁI
  OUT3/OUT4 ──→ Motor bánh PHẢI
```

### Lưu ý

- **PWM** trên IN1 và IN3 để điều chỉnh tốc độ (0-100%)
- IN2 và IN4 chỉ dùng digital (bật/tắt) cho chiều lùi
- Jumper ENA/ENB trên L298N giữ nguyên (enable mặc định)

---

## 5. Động cơ cẩu forklift — L298N #2

### 2 càng HOẠT ĐỘNG ĐỘC LẬP

```
L298N #2:
  12V (VCC motor) ──→ Pin trực tiếp
  5V (logic)      ──→ XH-M401 output 5V
  GND             ──→ GND chung

  Càng TRÁI:
    IN3 ←── GPIO 24  →  Nâng trái
    IN4 ←── GPIO 25  →  Hạ trái
    OUT3/OUT4 ──→ Motor cẩu TRÁI

  Càng PHẢI:
    ENA ←── GPIO  5  →  Enable phải (bật/tắt)
    IN1 ←── GPIO  6  →  Nâng phải
    IN2 ←── GPIO 13  →  Hạ phải
    OUT1/OUT2 ──→ Motor cẩu PHẢI
```

### Tại sao ENA riêng cho cẩu phải?

Cẩu trái dùng trực tiếp IN3/IN4 (jumper ENB giữ nguyên = luôn enable).
Cẩu phải dùng ENA để bật/tắt riêng — phần mềm cần enable trước khi nâng/hạ.

---

## 6. Nút khởi động

```
GPIO 16 ──── [ NÚT BẤM ] ──── GND
              (thường hở)

- Code đã bật pull-up bên trong Pi
- Chưa nhấn = HIGH, nhấn xuống = LOW → robot bắt đầu
```

---

## 7. Camera CSI

```
Camera OV5647 ──→ cổng CSI trên Pi (cáp flat)
- Không dùng GPIO
- Hướng thẳng ra trước, ngang tầm kệ hàng
- Dùng để nhận diện màu kiện hàng (xanh/vàng/xám/đỏ)
```

---

## 8. Nguồn điện

```
Pin 18650 (≤12V, ≤5000mAh theo thể lệ)
  │
  ├──→ L298N #1 VCC motor (12V trực tiếp)
  ├──→ L298N #2 VCC motor (12V trực tiếp)
  │
  └──→ XH-M401 (hạ áp → 5V)
       ├──→ Raspberry Pi 4 (5V qua micro-USB hoặc GPIO pin 5V)
       ├──→ L298N #1 logic VCC (5V)
       ├──→ L298N #2 logic VCC (5V)
       ├──→ HC-SR04 VCC (5V)
       └──→ QTR-8A VCC (5V)

3.3V (từ Pi):
  ├──→ MCP3008 VDD + VREF (3.3V)
  └──→ 2x IR pallet VCC (3.3V)

GND: TẤT CẢ module nối chung GND với nhau và với Pi
```

---

## Bảng tổng hợp 16 chân GPIO

| Chân | Chức năng | Hướng | Module |
|:----:|-----------|:-----:|--------|
| 8 | SPI CE0 (chip select MCP3008) | Output | MCP3008 |
| 9 | SPI MISO (data từ MCP3008) | Input | MCP3008 |
| 10 | SPI MOSI (data đến MCP3008) | Output | MCP3008 |
| 11 | SPI SCLK (clock) | Output | MCP3008 |
| 5 | ENA cẩu phải | Output | L298N #2 |
| 6 | IN1 cẩu phải (nâng) | Output | L298N #2 |
| 13 | IN2 cẩu phải (hạ) | Output | L298N #2 |
| 16 | Nút khởi động | Input | Nút bấm |
| 17 | IN1 bánh trái (tiến, PWM) | Output | L298N #1 |
| 19 | HC-SR04 TRIG | Output | Siêu âm |
| 20 | HC-SR04 ECHO | Input | Siêu âm |
| 22 | IN3 bánh phải (tiến, PWM) | Output | L298N #1 |
| 23 | IN4 bánh phải (lùi) | Output | L298N #1 |
| 24 | IN3 cẩu trái (nâng) | Output | L298N #2 |
| 25 | IN4 cẩu trái (hạ) | Output | L298N #2 |
| 27 | IN2 bánh trái (lùi) | Output | L298N #1 |

**Tổng: 16/16 — đúng giới hạn thể lệ, không dư chân nào.**

---

## Bố trí trên robot

```
Nhìn từ trên xuống:

     ══════════════════  ← Càng trái + [IR trái trên mặt càng]
        [HC-SR04] →      ← Giữa 2 càng, hướng ra trước
     ══════════════════  ← Càng phải + [IR phải trên mặt càng]

     ┌──────────────────┐
     │  [Camera]  →     │  ← Giữa thân, hướng ra trước
     │   RPi 4          │
     │  [MCP3008]       │  ← Trên breadboard
     │  [L298N #1]      │
     │  [L298N #2]      │
     │  [NÚT BẤM] ●    │  ← Mặt trên, dễ bấm
     │  [QTR-8A] ↓↓↓↓↓↓│  ← Dưới gầm, sát sàn 3-5mm
     ├──────────────────┤
     │ (motor T)(motor P)│  ← Bánh sau chủ động
     │  (caster)(caster) │  ← Bánh trước đa hướng
     └──────────────────┘
```

---

## Checklist trước khi chạy

- [ ] GND chung tất cả module
- [ ] XH-M401 output đúng 5V (đo bằng VOM)
- [ ] Cầu phân áp HC-SR04 ECHO (1kΩ + 2kΩ)
- [ ] MCP3008 VDD/VREF = 3.3V (KHÔNG dùng 5V)
- [ ] QTR-8A sát sàn 3-5mm
- [ ] Camera cáp flat cắm chặt
- [ ] Bật SPI: `sudo raspi-config` → Interface → SPI → Enable → reboot
- [ ] (Tuỳ chọn) `sudo usermod -aG spi $USER` nếu lỗi quyền đọc SPI
- [ ] Test line digital: `python3 tests/test_motion.py` option **4**
- [ ] Calibrate QTR raw ADC: `python3 tests/test_motion.py` option **5** → chỉnh `LINE_THRESHOLD`
- [ ] Test IR pallet: `python3 tests/test_lift.py` option **3** → chỉnh `PALLET_THRESHOLD`
- [ ] Debug web (DEBUG_MODE=True, chạy `python3 main.py` trực tiếp): line 6 mắt + ADC, IR tại `:5000`
- [ ] Thi đấu / systemd: `scripts/start.sh` đặt `ROBOT_COMPETE=1` → state machine (không mở web)
- [ ] Robot ≤ 400×400×400mm khi xuất phát, **quay mặt sang trái (9h)** trong ô start
- [ ] Test exit start: `python3 tests/test_motion.py` option **6**
- [ ] Pin ≤ 12V, ≤ 5000mAh


## Sau khi nối xong — Kiểm tra

### 1. Bật SPI trên Pi

```bash
sudo raspi-config
# → Interface Options → SPI → Enable
sudo reboot
```

### 2. Kiểm tra SPI hoạt động

```bash
ls /dev/spidev*
# Phải thấy: /dev/spidev0.0  /dev/spidev0.1
```

### 3. Test bằng code

```bash
cd ~/Robocon-BCIT
python3 tests/test_motion.py
# Option 4: đọc line digital (0/1)
# Option 5: calibrate raw ADC — đặt QTR lên đen/trắng, chỉnh LINE_THRESHOLD trong config.py

python3 tests/test_lift.py
# Option 3: IR trái/phải + ADC — đặt/bỏ pallet, chỉnh PALLET_THRESHOLD trong config.py
```