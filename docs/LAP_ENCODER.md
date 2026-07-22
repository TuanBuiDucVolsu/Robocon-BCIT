# Hướng dẫn lắp encoder tốc độ bánh xe (JGA25-370)

Mục tiêu: đo tốc độ quay thực tế của 2 bánh để chẩn đoán/calibrate
`PWM_COMPENSATION` (xe chạy lệch) bằng `test_motion.py` option **e**/**f**
thay vì dò tay hoàn toàn. Xem thêm mục D trong
[`../tests/DEBUG_DONG_CO.md`](../tests/DEBUG_DONG_CO.md).

> Lắp xong nhớ đọc lại [`PHAN_CUNG.md`](PHAN_CUNG.md) mục 4b để đối chiếu chân
> GPIO cuối cùng đã dùng.

**Encoder đã TÍCH HỢP sẵn trong motor JGA25-370** — không cần gắn đĩa mã hoá,
không cần canh khe quang. Đây là ưu điểm lớn so với module khe quang rời: hết
hẳn nhóm lỗi đĩa trượt / đĩa lệch khe / rung đĩa.

---

## 1. Đồ nghề cần có

- 2x motor **JGA25-370 12V có encoder** (kèm gá bắt + bánh xe 65mm)
- Dây jumper cái-cái (hoặc đực-cái tuỳ chân Pi dùng)
- Đồng hồ vạn năng (VOM) để đo mức điện áp chân encoder trước khi cắm

---

## 2. Nhận biết 6 dây của JGA25-370

Motor ra **6 dây**, chia 2 nhóm:

| Nhóm | Số dây | Chức năng | Nối tới |
|------|:------:|-----------|---------|
| **Nguồn motor** | 2 (dây TO) | Cấp 12V quay motor | L298N `OUT1/OUT2` (trái), `OUT3/OUT4` (phải) |
| **Encoder** | 4 (dây nhỏ) | VCC, GND, C1, C2 | Pi (xem mục 3) |

> ⚠️ **Bảng màu dây khác nhau theo lô sản xuất** — KHÔNG suy đoán theo màu.
> Hỏi shop bảng màu, hoặc đo bằng VOM. Cắm nhầm VCC/C1 có thể hỏng encoder.
> Dấu hiệu phân biệt chắc chắn nhất: 2 dây **to hơn hẳn** là nguồn motor.

---

## 3. Đấu dây vào Raspberry Pi

Code chỉ dùng **MỘT kênh** (C1) mỗi bánh — đếm xung, không đọc chiều quay
(chiều đã biết từ lệnh motor). Dây **C2 để trống**.

```
Encoder TRÁI:                     Encoder PHẢI:
  VCC ──→ 3.3V Pi                   VCC ──→ 3.3V Pi
  GND ──→ GND chung                 GND ──→ GND chung
  C1  ──→ GPIO 26                   C1  ──→ GPIO 21
          (ENCODER_LEFT_PIN)                (ENCODER_RIGHT_PIN)
  C2  ──→ (không nối)               C2  ──→ (không nối)
```

- **Cấp encoder VCC = 3.3V** (KHÔNG phải 5V): xung ra sẽ ≤3.3V, an toàn cho
  GPIO Pi, khỏi cần cầu phân áp. Motor vẫn ăn **12V riêng** qua L298N —
  hai đường nguồn này độc lập nhau.
- Nếu buộc phải cấp encoder 5V thì **bắt buộc cầu phân áp** C1 xuống 3.3V
  trước khi vào GPIO (giống ECHO của HC-SR04, xem `PHAN_CUNG.md` mục 3).
- GND encoder phải nối **chung** với GND của Pi và toàn hệ thống.
- `ENCODER_LEFT_PIN` / `ENCODER_RIGHT_PIN` khai trong `config.py` — đổi số ở đó
  nếu muốn dùng chân khác (BTC đã bỏ giới hạn số cổng I/O, còn nhiều chân trống).

---

## 4. Kiểm tra sau khi lắp

```bash
cd /home/mbw12345/Robocon-BCIT
python3 tests/test_motion.py
```

1. Chọn option **e** — đọc xung real-time khi robot tiến (kê bánh không chạm
   đất). Cả 2 dòng `trái=... phải=...` phải ra số > 0 và tăng khi tăng tốc độ.
   - 1 bên luôn **0** → sai chân C1, đứt dây, hoặc chưa cấp nguồn encoder bên đó.
   - Cả 2 đều **0** → kiểm tra `ENCODER_LEFT_PIN`/`ENCODER_RIGHT_PIN` trong
     `config.py`, và đo VOM chân C1 khi quay tay bánh (phải dao động mức cao/thấp).
2. Chọn option **f** — calibrate: tiến 1s, đo xung 2 bánh, đề xuất
   `PWM_COMPENSATION` mới. Nhấn `y` để lưu, lặp vài lần cho ổn định rồi chốt.

---

## 5. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|-------------|-------------|----------|
| Cả 2 bên 0 xung | Sai chân GPIO trong `config.py`, hoặc chưa cấp nguồn encoder | Đo VOM chân C1 khi quay tay bánh — phải dao động cao/thấp |
| 1 bên 0 xung | Đứt dây C1/GND bên đó, hoặc cắm nhầm C2 | Đo continuity; xác nhận đúng dây C1 theo bảng màu của shop |
| Số xung giật thất thường dù bánh quay đều | Nhiễu điện từ từ dây động lực 12V, hoặc gpiozero rớt xung ở tần số cao | Tách dây tín hiệu xa dây động lực; nếu vẫn giật thì chuyển encoder sang `pigpio` |
| Số xung 2 bên chênh cực lớn dù xe không lệch rõ | 2 motor khác tỉ số hộp số/PPR (mua khác lô) | Đảm bảo 2 motor **cùng model, cùng lô** |
| Encoder nóng / không ra xung sau khi cắm | Cắm nhầm VCC vào dây motor, hoặc cấp 12V vào encoder | Ngắt điện ngay, đối chiếu lại bảng màu dây với shop |

---

## 6. Ghi chú về độ phân giải

JGA25-370 cho xung **dày hơn nhiều** so với đĩa khe quang 20 khe — thực tế
khoảng vài trăm đến hơn 1000 xung/giây mỗi bánh tuỳ tốc độ. Hệ quả:

- **Tốt:** `ENCODER_SAMPLE_TIME = 0.2s` cho hàng trăm xung/mẫu → calibrate
  `PWM_COMPENSATION` chính xác hơn hẳn (đĩa 20 khe chỉ được ~11 xung/mẫu).
- **Cần lưu ý:** callback `gpiozero` có thể **rớt xung** ở tần số này. Chấp nhận
  được vì option **f** chỉ so **tỉ lệ** trái/phải (2 bên rớt tương đương), không
  cần số tuyệt đối. Chỉ khi nào cần đo quãng đường thật (odometry) mới bắt buộc
  chuyển sang `pigpio`.

> Số xung/vòng chính xác = **PPR × tỉ số hộp số**. Hỏi shop 2 thông số này nếu
> sau này cần đổi xung → quãng đường (mm). Hiện code **không** cần: điều hướng
> dựa vào bám line + đếm giao lộ, không dùng odometry.
