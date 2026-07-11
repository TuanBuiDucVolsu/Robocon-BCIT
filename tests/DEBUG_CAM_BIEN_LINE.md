# Debug MCP3008 + QTR-8A — checklist tìm lỗi

Hướng dẫn tìm lỗi cảm biến dò line (QTR-8A) đọc qua MCP3008, đặc biệt khi
**đọc ra toàn 0** hoặc **toàn 1023**. Làm theo thứ tự từ trên xuống, **dừng ngay
khi tìm ra lỗi**.

> Lệnh chạy từ **thư mục gốc repo**, không phải trong `tests/`.

## Công cụ có sẵn

| Lệnh | Tầng | Mục đích |
|------|------|----------|
| `python3 -m tools.raw_spi_test` | SPI thô (spidev) | Đọc 8 channel, bỏ qua gpiozero |
| `python3 -m tools.raw_spi_test loopback` | SPI thô | Self-test SPI Pi (nối MOSI↔MISO) |
| `python3 tools/check_mcp3008.py` | gpiozero | Chẩn đoán chip + real-time che tay |
| `python3 -m tools.calibrate_line` | gpiozero | Chốt `LINE_BLACK_IS_HIGH` + `LINE_THRESHOLD` |

## Chân MCP3008 (DIP-16) — đối chiếu `config.py` / `docs/PHAN_CUNG.md`

```
        ┌────────────┐
  CH0 ──┤ 1       16 ├── VDD  (3.3V)
  CH1 ──┤ 2       15 ├── VREF (3.3V)
  CH2 ──┤ 3       14 ├── AGND (GND)
  CH3 ──┤ 4       13 ├── CLK  (GPIO 11)
  CH4 ──┤ 5       12 ├── DOUT (GPIO 9  = MISO)
  CH5 ──┤ 6       11 ├── DIN  (GPIO 10 = MOSI)
  CH6 ──┤ 7       10 ├── CS   (GPIO 8  = CE0)
  CH7 ──┤ 8        9 ├── DGND (GND)
        └────────────┘
```

- CH0–5 → QTR-8A (line) · CH6 → IR trái · CH7 → IR phải
- ⚠️ VDD **và** VREF đều **3.3V** (KHÔNG 5V). QTR-8A cấp VCC = 5V (nguồn riêng).

---

## LƯU Ý QUAN TRỌNG trước khi debug

- **Toàn 0 ≠ lỗi cảm biến.** All-0 trên cả 8 kênh = chip không convert/giao tiếp.
  Nếu chỉ QTR hỏng thì kênh hở sẽ **trôi nổi ~cao**, không phải 0 sạch.
- **Đèn IR sáng KHÔNG chứng minh MCP3008 chạy.** IR lấy nguồn 3.3V thẳng từ Pi,
  không qua MCP3008. Đèn sáng chỉ nghĩa là IR có điện.
- **Code trả 1023 khi lỗi đọc.** `Mcp3008Bus` trả `1.0` (=ADC 1023) và đặt
  `last_read_ok=False` khi SPI lỗi → "lỗi đọc" và "input floating thật" đều ra 1023.
  Vì vậy phải dùng `raw_spi_test` / `check_mcp3008` để phân biệt, đừng chỉ nhìn web debug.

---

## A. Phần mềm (nhanh, không tháo gì)

- [ ] **A1.** SPI đã bật: `ls /dev/spidev*` → phải thấy `/dev/spidev0.0`
      - Không thấy → `sudo raspi-config` → Interface → SPI → Enable → `sudo reboot`
- [ ] **A2.** `python3 -m tools.raw_spi_test`
      - Vẫn **toàn 0** → không phải lỗi phần mềm → sang **B**
      - **Toàn 1023** → input floating (chưa nối cảm biến) hoặc VREF>VDD → xem mục C1 + nối cảm biến
      - **Ra số hợp lệ** → chip OK → nhảy xuống **D**

## B. Loopback — tách "lỗi Pi" hay "lỗi chip" (bước quyết định)

- [ ] **B1.** Rút dây MISO khỏi chip (hoặc rút cả chip)
- [ ] **B2.** Nối jumper thẳng **GPIO 10 (chân vật lý 19) ↔ GPIO 9 (chân vật lý 21)**
- [ ] **B3.** `python3 -m tools.raw_spi_test loopback`

| Kết quả | Kết luận | Đi tiếp |
|---------|----------|---------|
| **SAI** (không vòng đúng byte) | Lỗi ở **Pi / chân GPIO 9–10** hoặc jumper chưa chắc | Kiểm tra lại jumper, GPIO |
| **OK** (nhận đúng byte) | Pi + MOSI/MISO **tốt** → lỗi **phía chip** | Cắm lại MISO → sang **C** |

## C. Đo phần cứng chip (VOM, que đen ở GND) — theo thứ tự nghi ngờ

- [ ] **C1.** **VREF (pin 15)** = **3.3V** ← nghi ngờ số 1 khi VDD OK mà vẫn all-0
- [ ] **C2.** **AGND (pin 14)** thông mạch (beep) về GND ← **hay quên nhất**
- [ ] **C3.** **DGND (pin 9)** thông mạch về GND
- [ ] **C4.** **MISO: chip pin 12 → GPIO 9** thông mạch (dây đứt = all-0 y hệt mất nguồn)
- [ ] **C5.** 3 dây còn lại: pin 13(CLK)→GPIO11 · pin 11(DIN)→GPIO10 · pin 10(CS)→GPIO8
- [ ] **C6.** VDD (pin 16) = 3.3V · chip không nóng (nóng = cắm ngược, xoay 180°)

**Test cô lập kèm theo:** đo điện áp tại **pin 7 (CH6)**, đưa/rút vật cản trước IR →
điện áp phải **đổi**. Có đổi mà chip vẫn đọc 0 → chắc chắn lỗi **VREF/AGND/MISO**.

## D. Chỉ làm khi A–C đã ra số hợp lệ (chip chạy tốt)

- [ ] **D1.** `python3 -m tools.calibrate_line` → đặt lên line đen rồi nền sáng → chốt
      `LINE_BLACK_IS_HIGH` + `LINE_THRESHOLD` vào `config.py`
- [ ] **D2.** `python3 tools/check_mcp3008.py` → mục [5] che tay, giá trị phải đổi
- [ ] **D3.** `python3 tests/test_motion.py` option **4** (digital) / **5** (raw ADC)
      hoặc web debug → xem line 6 mắt realtime

---

## Bảng tra nhanh triệu chứng → nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp (thứ tự) |
|-------------|--------------------------------|
| **Toàn 0** (cả 8 kênh) | 1. Cắm ngược chip (nóng) · 2. MISO pin 12 hở · 3. VREF pin 15 mất 3.3V · 4. AGND pin 14 hở · 5. Sai chân CLK/DIN/CS |
| **Toàn 1023** | 1. Chưa nối cảm biến (floating) · 2. VREF > VDD · 3. Lỗi đọc SPI (code trả 1023) |
| **Đọc được, không đổi khi che** | Cảm biến chưa có điện · dây OUT hở · QTR chưa chỉnh biến trở/độ cao |
| **Đọc được, robot dò line ngược** | Sai `LINE_BLACK_IS_HIGH` → chạy `calibrate_line` |
| **Đọc được, đếm giao lộ sai** | `LINE_THRESHOLD` / `INTERSECTION_THRESHOLD` chưa hợp → `calibrate_line` |

## Đường ngắn nhất khi bị all-0

`A2 → B → C1 → C2` — gần như chắc chắn lỗi lộ ra ở một trong bốn bước đó.
