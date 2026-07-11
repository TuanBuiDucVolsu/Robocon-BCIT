# Debug động cơ bánh xe + L298N — checklist tìm lỗi

Hướng dẫn tìm lỗi 2 motor bánh xe (qua L298N #1): bánh chạy mãi không dừng,
quay ngược chiều, một bánh không quay, xe chạy lệch. Làm từ trên xuống, **dừng
ngay khi tìm ra lỗi**.

> Lệnh chạy từ **thư mục gốc repo**, không phải trong `tests/`.

## Công cụ có sẵn

| Lệnh | Mục đích |
|------|----------|
| `python3 tests/test_motion.py` → option **1** | Tiến/lùi cơ bản |
| `python3 tests/test_motion.py` → option **d** | Chạy từng bánh riêng — tìm bánh ngược chiều |
| `python3 -m tools.test_right_wheel` | Cô lập lỗi "bánh chạy mãi sau stop()" — chạy 1 bánh → stop → giữ để đo VOM |

## Chân điều khiển motor bánh (từ `config.py` / `docs/PHAN_CUNG.md`)

| Biến config | GPIO | Chân vật lý Pi | Chức năng | L298N #1 |
|-------------|:----:|:--------------:|-----------|----------|
| `IN1_XE_T` | 17 | 11 | Bánh **trái** tiến (PWM) | IN1 → OUT1/2 |
| `IN2_XE_T` | 27 | 13 | Bánh **trái** lùi (PWM) | IN2 → OUT1/2 |
| `IN1_XE_P` | 23 | 16 | Bánh **phải** tiến (PWM) | IN3 → OUT3/4 |
| `IN2_XE_P` | 22 | 15 | Bánh **phải** lùi (PWM) | IN4 → OUT3/4 |

- **PWM cả 2 chiều**: cả chân tiến và lùi đều là `PWMOutputDevice` → điều tốc được cả tiến lẫn lùi.
- Jumper **ENA/ENB** trên L298N #1 giữ nguyên (enable mặc định); tốc độ điều bằng PWM trên chân IN.
- Nguồn: 12V vào VCC motor, **5V (XH-M401) vào logic**, **GND chung với Pi** (bắt buộc).

---

## Bảng tra nhanh triệu chứng → nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Mục |
|-------------|------------------------|:---:|
| Bánh **chạy mãi**, `stop()` không tắt (chỉ 1 bánh) | GND logic lỏng · ENB floating · L298N kênh đó chết | **A** |
| Bánh quay **ngược chiều** khi lệnh "tiến" | Đảo dây, swap 2 chân IN trong config | **B** |
| **Một bánh không quay** | Dây motor/OUT hở · ENA/ENB kênh đó · motor hỏng | **C** |
| Xe **chạy lệch** dù cả 2 quay | Chênh tốc độ bánh → `PWM_COMPENSATION` | **D** |
| Cả 2 bánh **không quay gì** | Mất nguồn 12V motor · GND · logic 5V | **C** |

---

## A. Bánh chạy mãi, stop() không tắt (chỉ 1 bánh)

> Code bánh trái/phải **đối xứng hệt nhau**. Nếu chỉ 1 bánh kẹt → gần như chắc chắn
> lỗi **phần cứng kênh đó của L298N**, không phải phần mềm. Nhưng phải đo để chốt.

- [ ] **A1.** Xác nhận thời điểm: chạy `test_motion` option 1.
      - Không quay lúc khởi động, chỉ kẹt **sau** khi kích tiến/lùi → đúng dạng này.
- [ ] **A2.** Cô lập bằng VOM: `python3 -m tools.test_right_wheel`
      (bánh phải; sửa script đổi sang `_left_*` nếu là bánh trái).
      Sau khi thấy "ĐÃ STOP", đo (que đen ở GND), so với GND:

| Đo | Chân | Kỳ vọng |
|----|------|---------|
| IN1_XE_P (GPIO 23) | vật lý 16 | ~0V |
| IN2_XE_P (GPIO 22) | vật lý 15 | ~0V |

- [ ] **A3.** Đọc kết quả:

| Đo được | Kết luận | Đi tiếp |
|---------|----------|---------|
| Chân IN vẫn **~3.3V** sau stop | Lỗi **phần mềm/gpiozero** | Báo lại để sửa `stop()` |
| Cả 2 IN **~0V** mà bánh **vẫn quay** | Lỗi **phần cứng** L298N/OUT | A4→A7 |

- [ ] **A4. GND chung** Pi ↔ L298N #1: đo continuity. Thiếu/lỏng → chân IN "thấp"
      không được nhận đúng sau khi đã kích. ← **hay gặp nhất**
- [ ] **A5. Jumper ENB** (kênh phải) trên L298N #1: phải cắm chắc. Floating → thất thường.
- [ ] **A6. Test chéo:** cắm motor phải sang **OUT1/OUT2** (kênh trái). Nếu giờ dừng
      bình thường → xác nhận **kênh phải L298N chết** → **thay L298N #1**.
- [ ] **A7.** Dây OUT3/OUT4 chạm nguồn 12V? Đo chập với đường 12V.

## B. Bánh quay ngược chiều khi lệnh "tiến"

- [ ] **B1.** `test_motion` option **d** — chạy từng bánh, quan sát chiều quay.
- [ ] **B2.** Sửa (chọn 1 trong 2, không cần cả hai):
      - **Phần mềm:** swap 2 chân trong `config.py` — bánh trái `IN1_XE_T ↔ IN2_XE_T`,
        bánh phải `IN1_XE_P ↔ IN2_XE_P`.
      - **Phần cứng:** đảo 2 dây motor tại OUT của L298N.

## C. Một/cả hai bánh không quay

- [ ] **C1.** Đo nguồn: 12V vào VCC motor L298N, 5V vào chân logic, GND chung.
- [ ] **C2.** `test_motion` option **d** — bánh không quay là bánh nào.
- [ ] **C3.** Đo continuity dây motor → OUT của L298N.
- [ ] **C4.** Jumper ENA/ENB kênh đó còn cắm không.
- [ ] **C5.** Test chéo motor sang kênh còn lại (loại trừ motor hỏng vs L298N hỏng).

## D. Xe chạy lệch dù cả 2 bánh quay

- [ ] **D1.** Cho chạy thẳng (`test_motion` option 1), quan sát lệch bên nào.
- [ ] **D2.** Chỉnh `PWM_COMPENSATION` trong `config.py` (hiện 0.95 — hệ số nhân tốc
      độ bánh **phải**). Bánh phải nhanh hơn → giảm; chậm hơn → tăng (tối đa 1.0).
- [ ] **D3.** Kiểm cơ khí: bánh lỏng, ma sát lệch, caster kẹt — không phải lúc nào cũng do PWM.

---

## Đường ngắn nhất khi "bánh chạy mãi sau stop"

`A1 → A2 (đo VOM) → A3`. Nếu IN đã 0V mà bánh vẫn quay → `A4 (GND) → A6 (test chéo)`.
