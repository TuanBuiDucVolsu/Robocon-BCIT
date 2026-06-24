# Hướng dẫn lắp QTR-8A + MCP3008

## Bạn có 2 linh kiện cần nối với nhau

### Linh kiện 1: QTR-8A — Thanh cảm biến dò line

```
┌─────────────────────────────────────────────────┐
│  ●  ●  ●  ●  ●  ●  ●  ●                       │  ← 8 mắt LED hồng ngoại
│  1  2  3  4  5  6  7  8                         │
│                                                 │
│  [VCC] [GND] [1] [2] [3] [4] [5] [6] [7] [8]   │  ← 10 chân phía dưới
└─────────────────────────────────────────────────┘
```

- 8 mắt LED hồng ngoại, chiếu xuống mặt sàn
- Mỗi mắt xuất ra **1 dây tín hiệu analog** (điện áp thay đổi)
- Mắt chiếu vào **đen** (line) → điện áp **thấp** (~0V)
- Mắt chiếu vào **trắng** (nền) → điện áp **cao** (~3.3V)
- VCC = 5V, GND = mass

### Linh kiện 2: MCP3008 — Bộ chuyển đổi analog → số

```
        ┌────────────┐
  CH0 ──┤ 1       16 ├── VDD
  CH1 ──┤ 2       15 ├── VREF
  CH2 ──┤ 3       14 ├── AGND
  CH3 ──┤ 4       13 ├── CLK
  CH4 ──┤ 5       12 ├── DOUT
  CH5 ──┤ 6       11 ├── DIN
  CH6 ──┤ 7       10 ├── CS
  CH7 ──┤ 8        9 ├── DGND
        └────────────┘
```

- **8 kênh input** (CH0-CH7): nhận tín hiệu analog từ cảm biến
- **4 chân SPI** (CLK, DOUT, DIN, CS): giao tiếp với Raspberry Pi
- Chuyển điện áp analog (0-3.3V) thành số (0-1023) để Pi đọc được
- **Tại sao cần?** Raspberry Pi không có chân analog, chỉ có digital

## Tại sao chỉ dùng 6 mắt thay vì 8?

MCP3008 có 8 kênh. Nếu dùng hết 8 kênh cho QTR-8A thì không còn kênh nào cho 2 cảm biến IR pallet (trái + phải).

**Giải pháp:** Dùng 6 mắt giữa (mắt 1-6), bỏ 2 mắt ngoài cùng (mắt 7-8). Dành CH6 và CH7 cho 2 cảm biến IR pallet.

```
QTR-8A:  [1] [2] [3] [4] [5] [6] [7] [8]
          ↓   ↓   ↓   ↓   ↓   ↓   ✗   ✗    ← bỏ mắt 7, 8
         CH0 CH1 CH2 CH3 CH4 CH5
                                   CH6 → IR pallet trái
                                   CH7 → IR pallet phải
```

6 mắt vẫn dư sức bám line (nhiều robot thi đấu chỉ dùng 5 mắt).

## Cách nối dây — Từng bước

### Bước 1: Cắm MCP3008 lên breadboard

```
Cắm IC MCP3008 vào giữa breadboard (ngang rãnh chia).
Chú ý hướng: dấu chấm tròn trên IC = chân 1 (CH0).

  Breadboard:
  ─────────────────────
  │ CH0  1 ●│    │16 VDD  │
  │ CH1  2  │    │15 VREF │
  │ CH2  3  │    │14 AGND │
  │ CH3  4  │    │13 CLK  │
  │ CH4  5  │    │12 DOUT │
  │ CH5  6  │    │11 DIN  │
  │ CH6  7  │    │10 CS   │
  │ CH7  8  │    │ 9 DGND │
  ─────────────────────
```

### Bước 2: Nối nguồn cho MCP3008

| Chân MCP3008 | Nối vào | Ghi chú |
|:---:|---|---|
| 16 (VDD) | **3.3V** của Pi | ⚠️ KHÔNG dùng 5V! |
| 15 (VREF) | **3.3V** của Pi | Điện áp tham chiếu |
| 14 (AGND) | **GND** | Mass analog |
| 9 (DGND) | **GND** | Mass digital |

**⚠️ QUAN TRỌNG:** MCP3008 dùng **3.3V**, KHÔNG dùng 5V. Nối 5V sẽ hỏng IC hoặc hỏng Pi.

### Bước 3: Nối SPI từ MCP3008 → Raspberry Pi

| Chân MCP3008 | → Chân Pi | Tên SPI | Màu dây gợi ý |
|:---:|:---:|---|---|
| 13 (CLK) | GPIO 11 | SCLK (clock) | Vàng |
| 12 (DOUT) | GPIO 9 | MISO (data ra) | Xanh lá |
| 11 (DIN) | GPIO 10 | MOSI (data vào) | Xanh dương |
| 10 (CS) | GPIO 8 | CE0 (chip select) | Trắng |

```
MCP3008                    Raspberry Pi
  CLK  (13) ─── vàng ───→ GPIO 11 (SCLK)
  DOUT (12) ─── xanh lá → GPIO  9 (MISO)
  DIN  (11) ─── xanh ──→ GPIO 10 (MOSI)
  CS   (10) ─── trắng ─→ GPIO  8 (CE0)
```

### Bước 4: Nối QTR-8A → MCP3008

| Chân QTR-8A | → Chân MCP3008 | Kênh |
|:---:|:---:|---|
| Mắt 1 | CH0 (chân 1) | Dò line |
| Mắt 2 | CH1 (chân 2) | Dò line |
| Mắt 3 | CH2 (chân 3) | Dò line |
| Mắt 4 | CH3 (chân 4) | Dò line |
| Mắt 5 | CH4 (chân 5) | Dò line |
| Mắt 6 | CH5 (chân 6) | Dò line |
| VCC | **5V** của Pi | QTR-8A cần 5V |
| GND | **GND** | Mass chung |

```
QTR-8A                     MCP3008
  Mắt 1 ─── dây ──→ CH0 (chân 1)
  Mắt 2 ─── dây ──→ CH1 (chân 2)
  Mắt 3 ─── dây ──→ CH2 (chân 3)
  Mắt 4 ─── dây ──→ CH3 (chân 4)
  Mắt 5 ─── dây ──→ CH4 (chân 5)
  Mắt 6 ─── dây ──→ CH5 (chân 6)
  VCC ───── dây ──→ 5V (Pi)
  GND ───── dây ──→ GND (chung)
```

**Mắt 7 và 8 của QTR-8A:** KHÔNG nối. Để trống.

### Bước 5: Nối 2 cảm biến IR pallet → MCP3008

| Cảm biến IR | → Chân MCP3008 | Kênh |
|---|:---:|---|
| IR càng **trái** (OUT) | CH6 (chân 7) | Pallet trái |
| IR càng **phải** (OUT) | CH7 (chân 8) | Pallet phải |
| IR VCC (cả 2) | **3.3V** | |
| IR GND (cả 2) | **GND** | |

```
IR trái (OUT) ─── dây ──→ CH6 (chân 7)
IR phải (OUT) ─── dây ──→ CH7 (chân 8)
```

## Sơ đồ tổng (nhìn 1 lần là hiểu)

```
                    3.3V ────┬──────────────────────┐
                             │                      │
                    5V ──────┼──── QTR-8A VCC       │
                             │                      │
  ┌──────────────────────────┼──────────────────────┼─────────────────┐
  │ Raspberry Pi             │                      │                 │
  │                          │     ┌────────────┐   │                 │
  │  GPIO 11 (SCLK) ────────┼───→ │13 CLK   16├───┘ (3.3V VDD)      │
  │  GPIO  9 (MISO) ←───────┼──── │12 DOUT  15├─── 3.3V (VREF)      │
  │  GPIO 10 (MOSI) ────────┼───→ │11 DIN   14├─── GND  (AGND)      │
  │  GPIO  8 (CE0)  ────────┼───→ │10 CS     9├─── GND  (DGND)      │
  │                          │     │           │                      │
  │                          │     │ 1  CH0 ←──┼─── QTR-8A mắt 1     │
  │                          │     │ 2  CH1 ←──┼─── QTR-8A mắt 2     │
  │                          │     │ 3  CH2 ←──┼─── QTR-8A mắt 3     │
  │                          │     │ 4  CH3 ←──┼─── QTR-8A mắt 4     │
  │                          │     │ 5  CH4 ←──┼─── QTR-8A mắt 5     │
  │                          │     │ 6  CH5 ←──┼─── QTR-8A mắt 6     │
  │                          │     │ 7  CH6 ←──┼─── IR pallet trái   │
  │                          │     │ 8  CH7 ←──┼─── IR pallet phải   │
  │                          │     │  MCP3008  │                      │
  │                          │     └────────────┘                     │
  │                          │                                        │
  │  GND ────────────────────┼── QTR-8A GND ── IR GND ── MCP GND     │
  └──────────────────────────┼────────────────────────────────────────┘
                             │
                    3.3V ────┘── IR VCC (cả 2 cái)
```

## Sai lầm thường gặp

| Sai | Hậu quả | Cách sửa |
|-----|---------|----------|
| Nối VDD MCP3008 vào 5V | Hỏng MCP3008 hoặc hỏng GPIO Pi | Dùng **3.3V** |
| Nối nhầm MOSI ↔ MISO | Không đọc được dữ liệu | MOSI = Pi→MCP (chân 11), MISO = MCP→Pi (chân 12) |
| Quên nối AGND hoặc DGND | Đọc giá trị lung tung | Nối **cả 2** chân GND (chân 9 và 14) |
| Cắm MCP3008 ngược | Không hoạt động | Dấu chấm tròn = chân 1 (CH0), ở góc trái trên |
| Quên bật SPI trong raspi-config | Code báo lỗi | `sudo raspi-config` → SPI → Enable → reboot |
| Nối mắt 7-8 QTR-8A vào CH6-7 | Mất kênh IR pallet | CH6-7 dành cho IR pallet, mắt 7-8 để trống |

## Tóm tắt nhanh — 6 dây từ Pi → MCP3008

```
Pi GPIO  8 ──→ MCP chân 10 (CS)
Pi GPIO  9 ←── MCP chân 12 (DOUT/MISO)
Pi GPIO 10 ──→ MCP chân 11 (DIN/MOSI)
Pi GPIO 11 ──→ MCP chân 13 (CLK)
Pi 3.3V    ──→ MCP chân 16 (VDD) + chân 15 (VREF)
Pi GND     ──→ MCP chân 9 (DGND) + chân 14 (AGND)
```

Thêm 6 dây từ QTR-8A mắt 1-6 → MCP CH0-CH5, 2 dây IR → CH6-CH7. **Tổng: ~16 dây.**
