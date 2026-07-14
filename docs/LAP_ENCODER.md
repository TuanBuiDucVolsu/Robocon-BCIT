# Hướng dẫn lắp encoder tốc độ bánh xe (MH Sensor Series)

Mục tiêu: đo được tốc độ quay thực tế của 2 bánh xe để chẩn đoán/calibrate
`PWM_COMPENSATION` (xe chạy lệch) bằng `test_motion.py` option **e**/**f**
thay vì dò tay hoàn toàn. Xem thêm mục D trong
[`../tests/DEBUG_DONG_CO.md`](../tests/DEBUG_DONG_CO.md).

> Lắp xong nhớ đọc lại [`PHAN_CUNG.md`](PHAN_CUNG.md) mục 4b để đối chiếu chân
> GPIO cuối cùng đã dùng.

---

## 1. Đồ nghề cần có

- 2x module **MH Sensor Series — Speed Sensor** (module khe quang, có khe hở
  chữ U, 3 chân VCC/GND/DO)
- 2x **đĩa mã hoá (encoder disc)** — đĩa nhựa/mica có các khe cắt xuyên tâm
  đều nhau (thường 20 khe có sẵn kèm module, hoặc tự in 3D/cắt bìa cứng nếu
  cần đường kính khác)
- Keo dán / ốc vặn để cố định đĩa vào trục bánh hoặc trục motor
- Dây jumper cái-cái (hoặc đực-cái tuỳ chân Pi dùng)
- Đồng hồ vạn năng (VOM) để đo điện áp DO nếu nghi ngờ sai mức logic

---

## 2. Lắp cơ khí — gắn đĩa mã hoá

Có 2 vị trí gắn, chọn 1:

| Gắn ở | Ưu điểm | Nhược điểm |
|-------|---------|------------|
| **Trục motor** (trước hộp giảm tốc 1:48) | Đĩa quay nhanh → nhiều xung/giây, đo mượt hơn ở tốc độ thấp | Số xung không phản ánh trực tiếp vòng quay bánh (phải nhân thêm tỉ số truyền nếu cần đổi ra tốc độ thật) |
| **Trục bánh xe** (sau hộp giảm tốc) | Xung tỉ lệ trực tiếp với tốc độ bánh, phản ánh đúng cái xe đang chạy lệch bao nhiêu | Bánh quay chậm hơn nhiều lần → ít xung/giây, cần đĩa nhiều khe hơn để đủ độ phân giải |

**Khuyến nghị: gắn ở trục bánh xe** — vì mục đích là so sánh **tốc độ bánh
thực tế**, không cần biết tốc độ motor trước hộp số. `test_motion` option f
chỉ so **tỉ lệ** xung trái/phải nên không cần đổi ra đơn vị vật lý, gắn ở đâu
cũng tính được miễn 2 bên gắn **giống nhau** (cùng vị trí, cùng số khe).

Các bước:
1. Đĩa mã hoá xuyên tâm với trục bánh, dán/vặn cố định — **không được trượt**
   khi quay (nếu trượt, số xung không phản ánh đúng tốc độ thật → calibrate sai).
2. Gắn module khe quang sao cho đĩa xuyên qua đúng khe chữ U, không chạm/cọ
   xát viền đĩa vào 2 cạnh khe khi quay (chỉnh khe hở ~1-2mm).
3. Quay tay thử bánh xe (robot kê lên đế, bánh không chạm đất) — quan sát đèn
   báo hiệu trên module (thường có LED nhấp nháy theo từng khe cắt qua) để
   xác nhận cơ khí ổn trước khi đấu dây vào Pi.

---

## 3. Đấu dây vào Raspberry Pi

```
Encoder TRÁI:                     Encoder PHẢI:
  VCC ──→ 3.3V (hoặc 5V*)           VCC ──→ 3.3V (hoặc 5V*)
  GND ──→ GND chung                GND ──→ GND chung
  DO  ──→ GPIO 26                  DO  ──→ GPIO 21
          (ENCODER_LEFT_PIN)               (ENCODER_RIGHT_PIN)
```

- `ENCODER_LEFT_PIN` / `ENCODER_RIGHT_PIN` khai báo trong `config.py` — đổi số
  ở đó nếu muốn dùng chân GPIO khác (còn nhiều chân trống, không còn bị giới
  hạn 16 cổng theo thể lệ mới).
- **\*Kiểm tra mức điện áp DO của module trước khi cắm**: nhiều module MH
  Sensor Series ra mức logic theo VCC cấp vào. Nếu cấp **5V** mà DO cũng ra
  **~5V** khi HIGH → **bắt buộc cầu phân áp** xuống 3.3V trước khi vào GPIO
  Pi (giống cách làm với ECHO của HC-SR04, xem `PHAN_CUNG.md` mục 3), nếu
  không sẽ hỏng chân GPIO. An toàn nhất: cấp VCC module bằng **3.3V** từ Pi
  luôn để DO cũng ra tối đa 3.3V, khỏi cần cầu phân áp.
- GND của 2 module phải nối **chung** với GND của Pi và toàn bộ hệ thống
  (không nối GND riêng).

---

## 4. Kiểm tra sau khi lắp

```bash
cd /home/mbw12345/Robocon-BCIT
python3 tests/test_motion.py
```

1. Chọn option **e** — đọc xung real-time khi robot tiến (kê bánh không chạm
   đất). Quan sát cả 2 dòng `trái=... phải=...` đều ra số > 0 và tăng dần khi
   tăng tốc độ (`SPEED_DEFAULT`).
   - Nếu 1 bên luôn ra **0** → kiểm tra lại bước 2-3 (đĩa lệch tâm/không
     xuyên đúng khe) và bước 3 (dây DO/GND, đúng chân GPIO trong `config.py`).
   - Nếu số xung **giật cục thất thường** dù bánh quay đều → đĩa bị trượt
     hoặc rung lắc, siết chặt lại cơ khí.
2. Chọn option **f** — calibrate: tiến 1s, đo xung 2 bánh, đề xuất giá trị
   `PWM_COMPENSATION` mới. Nhấn `y` để lưu nếu thấy hợp lý, lặp lại vài lần
   cho ổn định trước khi chốt.

---

## 5. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|-------------|-------------|----------|
| Cả 2 bên đều 0 xung | Sai chân GPIO trong `config.py`, hoặc chưa cấp nguồn module | Đo VOM chân DO khi quay tay bánh — phải dao động giữa mức thấp/cao |
| 1 bên 0 xung, bên kia bình thường | Đĩa lệch khỏi khe quang bên đó, hoặc đứt dây DO/GND bên đó | Kiểm tra lại khe hở đĩa-module, đo continuity dây |
| Xung ra liên tục dù bánh đứng yên | Đĩa/module rung do lỏng, hoặc nhiễu điện từ động cơ DC gần đó | Siết chặt cơ khí; tách dây tín hiệu xa dây động lực 12V |
| `test_motion` option f báo "không đọc được xung" | Encoder chưa gắn đúng hoặc `available=False` (không khởi tạo được `DigitalInputDevice`) | Chạy option **e** trước để xác nhận có xung ổn định rồi mới calibrate |
| Số xung 2 bên chênh cực lớn dù xe không lệch rõ bằng mắt | 2 đĩa không cùng số khe, hoặc gắn khác vị trí (1 bên trục motor, 1 bên trục bánh) | Đảm bảo 2 bên đối xứng — cùng loại đĩa, cùng vị trí gắn |
