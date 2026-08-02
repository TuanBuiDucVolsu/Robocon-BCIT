# Nghiệm thu — ĐẠT / CHƯA ĐẠT bằng số

In tờ này, cầm theo **thước lá** và **ke vuông**. Mỗi bước có tiêu chí bằng SỐ, không
phải "thấy có vẻ ổn".

> **Nguyên tắc bao trùm: một lần đúng KHÔNG phải là đạt.**
> Trận đấu có 6 lượt lấy hàng và 5 lần reset. Cơ cấu nào chỉ đúng 1/3 lần thì trong
> trận nó sai 2/3 lần. **Mọi bước dưới đây phải lặp 3 lần liên tiếp cùng kết quả.**
> Lần 2 hỏng thì tiêu chí CHƯA ĐẠT, không phải "chắc do xui".

> ⚠️ Ba thay đổi ngày 02/08 **chưa chạy trên robot lần nào**: bám line khi tiến sát
> kệ (`_forward_guided`), cửa sổ mù lúc xuất phát (`EXIT_START_BLIND_TIME`), dừng có
> giảm tốc (`stop_gently`). Vòng A–C dưới đây chính là để nghiệm thu chúng.

---

## VÒNG A — Số nền. Không có A thì mọi thứ sau đều là đoán

Sàn phẳng, có thể chưa cần sa bàn. Khoảng 30 phút.

### A1 · Xoay 90° hai chiều — `test_motion` **2**

Đặt ke vuông trên sàn, dán băng dính đánh dấu hướng đầu robot trước và sau.

| | |
|---|---|
| **ĐẠT** | Mỗi chiều **90° ± 5°**, VÀ chênh lệch giữa hai chiều **≤ 3°** |
| **CHƯA ĐẠT** | Lệch > 5°, hoặc hai chiều chênh nhau > 3° |
| **Sửa** | Lệch đều cả hai chiều → chỉnh `TURN_TIME`. **Hai chiều chênh nhau thì `TURN_TIME` không cứu được** — chỉ có một hằng số cho cả hai chiều, phải sửa `PWM_COMPENSATION_*_REV` |

Vì sao ±5°: chặng giữa hai giao lộ dài 66–100cm. Lệch 5° trên 66cm là trôi ngang
5.8cm, mà thanh cảm biến chỉ rộng ~60mm — quá 5° là robot ra khỏi vạch trước khi PD
kịp kéo lại. **Chênh lệch giữa hai chiều quan trọng hơn trị tuyệt đối.**

### A2 · Bù PWM — `test_motion` **f**, rồi đo tay

Chạy `f` để ghi `PWM_COMPENSATION`. Sau đó dán vạch thẳng 2m trên sàn, cho robot
chạy dọc theo, đo độ trôi ngang ở cuối.

| | Tiến | Lùi |
|---|---|---|
| **ĐẠT** | trôi ngang **≤ 2cm / 2m** | **≤ 2cm / 2m** |
| **CHƯA ĐẠT** | > 2cm | > 2cm |
| **Sửa** | chạy lại `f` | **`f` KHÔNG ghi hệ số chiều lùi** — sửa tay `PWM_COMPENSATION_REV` / `PWM_COMPENSATION_LEFT_REV`, mỗi lần 0.01 |

2cm/2m ≈ 0.6°. Chiều lùi bắt buộc phải đạt: **mọi tuyến giao hàng đều mở đầu bằng
`LÙI 1 giao lộ`** — khoảng 28 lần mỗi trận.

### A3 · Đo cm/s — `test_motion` **1**

Cho tiến đúng **1.0 giây** ở tốc độ 50, đo bằng thước. Lặp **3 lần**.

| | |
|---|---|
| **ĐẠT** | Trung bình nằm trong **15–40 cm/s**, VÀ 3 lần chênh nhau **≤ 10%** |
| **CHƯA ĐẠT** | Ngoài dải → sai giả định thiết kế. Chênh > 10% → pin yếu hoặc motor lệch |

**Ghi lại con số này.** Nó chốt hai thứ đang treo:
- `EXIT_START_BLIND_TIME` = **45 ÷ (cm/s)**, nhưng **không quá 1.5**
- đối chiếu `--forward` của `tools.dry_run` (đang để 2.5s/giao lộ — chỉ là placeholder)

### A4 · Lùi bám line — `test_motion` **15**

| | |
|---|---|
| **ĐẠT** | Đi hết chặng, biên độ lắc ngang **≤ ±2cm** và **không tăng dần**, dừng đúng giao lộ |
| **CHƯA ĐẠT** | Lắc tăng dần, hoặc văng khỏi vạch, hoặc không tới giao lộ |
| **Sửa** | Lắc tăng dần = dấu hiệu kinh điển của **sai dấu hiệu chỉnh khi lùi**. Trôi lệch một bên đều đều = `PWM_COMPENSATION_REV` |

---

## VÒNG B — Từng cơ cấu. Khoảng 30 phút

### B1 · Độ cao càng — `test_lift` **d** rồi **e**

Đo bằng thước từ sàn lên mặt trên càng, ở cả hai tầng.

| | |
|---|---|
| **ĐẠT** | Hai càng chênh nhau **≤ 3mm** ở cả tầng 1 và tầng 2; mũi càng vào khe pallet **không chạm mép trên/dưới** |
| **CHƯA ĐẠT** | Chênh > 3mm, hoặc càng tì vào mép khe |
| **Sửa** | `LIFT_*_EXTRA` (bù theo vị trí tuyệt đối, không phải bù mỗi lần chạy) |

Khe pallet trên khối 90×90×26mm rất hẹp. Chênh 3mm là một càng vào được, càng kia tì.

### B2 · Nhấc pallet đặt tay — `test_lift` **3**

**Tự tay** luồn càng vào khe pallet, rồi cho nâng. Bước này **tách** lift+IR ra khỏi
việc luồn, để biết hỏng nằm ở đâu.

| | |
|---|---|
| **ĐẠT** | **Cả 2 IR** báo CÓ, `confirm_pickup` trả True, pallet rời mặt kệ, **3/3 lần** |
| **CHƯA ĐẠT** | Một IR không báo → ngưỡng IR hoặc vị trí cảm biến. Cả hai không báo → SPI/ADC |

**B2 chưa đạt thì đừng chạy C2** — sẽ không phân biệt được "luồn sai" với "IR sai".

### B3 · Khoảng dừng trước kệ — `test_motion` **9** 🔑

**Đây là bước bắt lỗi trôi thêm của `stop_gently`.** Chạy **5 lần**, mỗi lần đo bằng
thước từ mặt cảm biến siêu âm tới mặt trước kệ.

| | |
|---|---|
| **ĐẠT** | Trung bình **11.9 ± 1.0 cm**, VÀ độ tản (max − min) **≤ 1.0 cm** |
| **CHƯA ĐẠT — dừng sát hơn 10.9cm** | `stop_gently` trôi thêm. **Hạ `STOP_RAMP_TIME`** 0.12 → 0.08 → 0.04, chạy lại. **KHÔNG đổi `APPROACH_DISTANCE`** — số đó ràng buộc với vị trí khe pallet |
| **CHƯA ĐẠT — tản > 1.0cm** | Siêu âm nhiễu, hoặc robot đứng không vuông góc với kệ |
| **CHƯA ĐẠT — robot lệch góc sau khi dừng** | Đặt `STOP_RAMP_TIME = 0` thử lại: vẫn lệch thì do phanh động, hết lệch thì do chính cái ramp |

**Ghi lại khoảng cách trung bình.** Nếu nó lệch quá **1cm** so với lúc chụp ảnh mẫu
thì phải làm B4.

### B4 · Nhận diện — `test_vision` **9**

Chỉ bắt buộc khi B3 cho khoảng cách khác trước > 1cm — camera đóng khung khác đi thì
16 ảnh mẫu ORB và `ROI_Y_CENTER` không còn đúng.

| | |
|---|---|
| **ĐẠT** | **Cả 4 ô** đúng nhãn; nhãn đúng thắng nhãn nhì **≥ 1.5×**; HSV ≥ `CONFIDENCE_THRESHOLD` (0.08) |
| **CHƯA ĐẠT** | Sai 1 ô, hoặc thắng < 1.5× (thắng sát nút = đổi ánh sáng là lật) |
| **Sửa** | Chụp lại 16 ảnh mẫu (`tools.capture_templates`) + `tools.calibrate_vision` từng tầng. ~30–45 phút |

---

## VÒNG C — Ghép nối. Khoảng 40 phút

Chạy `test_smoke`, **chọn đúng nửa sân** ở câu hỏi đầu phiên.

### C1 · Xuất phát → Kệ 3 — smoke **1**

| | |
|---|---|
| **ĐẠT** | Log `Advance: đã tới gần mục tiêu (1x.x cm)` + ✅, robot dừng cách kệ **20 ± 3 cm**, **3/3 lần** |
| **CHƯA ĐẠT** — `không thấy line trong 0.80s đầu` | Cửa sổ mù kết thúc sai chỗ, hoặc robot đặt lệch trong ô 400×400 |
| **CHƯA ĐẠT** — `gặp giao lộ` | Đã vượt qua C0R0 khi còn mù → `EXIT_START_BLIND_TIME` quá dài |
| **CHƯA ĐẠT** — dừng ngay trên hình mascot | Cửa sổ mù quá ngắn, hoặc cơ chế thoát sớm không kích hoạt |
| **CHƯA ĐẠT** — dừng cách kệ > 25cm | Siêu âm bắt phải vật khác |

### C2 · Bốc hàng — smoke **2** 🔑 **BÀI QUAN TRỌNG NHẤT**

Ngồi ngang tầm mắt với bánh xe. **Nhìn kỹ 10cm cuối.**

| | |
|---|---|
| **ĐẠT** | **Cả 2 bánh quay đều suốt** quãng luồn; cả 2 IR báo CÓ; IR báo khi còn **cách kệ > 3.0cm**; `classify_pair` đúng cả 2 ô; **3/3 lần** |
| **CHƯA ĐẠT** 🔴 — **một bánh đứng hẳn, robot xoay quanh nó** | Đúng cái đã tính trước: `LINE_KP = 16` chỉnh cho tốc độ 50, chạy ở 32% thì sai số line > 0.44 là bánh trong tụt dưới vùng chết. **Phải kẹp `LINE_KP` trước khi chạy tiếp** |
| **CHƯA ĐẠT** — `đã tới 2.x cm (chặn 2.2cm) mà IR chưa báo` | Càng vẫn không vào khe. Xem lại B1 (độ cao) và B3 (khoảng dừng) |
| **CHƯA ĐẠT** — chỉ **1 IR** báo | Lệch NGANG, không phải lệch góc. Kiểm khoảng cách 2 càng so với 2 khe |
| **CHƯA ĐẠT** — IR chỉ báo ở **2.2–2.5cm** | Về mặt số là đạt nhưng **biên an toàn bằng 0**. Coi như chưa đạt |
| **CHƯA ĐẠT** — nhấc lên thì chạm kệ | `LIFT_PICKUP_RAISE_TIME` quá lớn, hoặc dừng quá sát |

Sau khi C2 **đạt**: đo lại `INSERT_MIN_DISTANCE` (2.2) và `LIFT_PICKUP_RAISE_TIME`
(0.3). Hai số đó đang bị **nới ra để bù cho việc đi lệch** — lệch chữa xong thì giữ
nguyên chúng là để robot chạy sát kệ hơn mức cần thiết.

### C3 · Thả hàng — smoke **3**

| | |
|---|---|
| **ĐẠT** | Cả 2 lần thả đều có IR xác nhận đã RỜI càng; sau kiện 1 càng được **nâng lại ngang càng kia** (chênh ≤ 3mm); sau kiện 2 cả hai càng về sàn |
| **CHƯA ĐẠT** | IR vẫn thấy pallet sau khi thả → pallet chưa rời. Càng không nâng lại → sẽ cạ sàn khi chạy tiếp |

### C4 · Vòng khép kín — smoke **5**

| | |
|---|---|
| **ĐẠT** | Không có bước ❌ nào; kiện tới **đúng** nhà máy (kiểm bằng mắt, không tin log); cuối bài robot đứng **vuông góc** trước Kệ 3, lệch ngang ≤ 3cm |
| **CHƯA ĐẠT** — sai nhà máy | **Chọn sai nửa sân.** Log vẫn xanh — đây là lỗi duy nhất không có tín hiệu báo |
| **CHƯA ĐẠT** — về tới Kệ 3 nhưng lệch | Tích luỹ sai số xoay/lùi → quay lại A1, A2 |

---

## VÒNG D — Chỉ sau khi C4 đạt 3/3

```bash
bash scripts/practice.sh
python3 -m tools.measure_phases
```

| | |
|---|---|
| **ĐẠT** | Dự báo **worst case ≥ 8/12 kiện** trong 240s |
| **CHƯA ĐẠT** | < 8 kiện → chặng ăn nhiều giây nhất là chạy thẳng (~35%), tăng `SPEED_DEFAULT` (đang 50, mức bring-up) theo quy trình trong `config.py` |

Đọc theo **điểm**, không theo "kịp / không kịp": hết giờ vẫn giữ điểm kiện đã giao.

---

## Bảng ghi số — điền vào rồi báo lại

| Mục | Giá trị đo | Hằng số liên quan |
|---|---|---|
| A1 xoay trái / phải | ______° / ______° | `TURN_TIME` |
| A2 trôi tiến / lùi (2m) | ______cm / ______cm | `PWM_COMPENSATION*` |
| A3 tốc độ ở 50% | ______ cm/s | → `EXIT_START_BLIND_TIME` = 45 ÷ ____ = ______ |
| B1 chênh 2 càng T1 / T2 | ______mm / ______mm | `LIFT_*_EXTRA` |
| B3 khoảng dừng TB / tản | ______cm / ______cm | `APPROACH_DISTANCE`, `STOP_RAMP_TIME` |
| C2 khoảng cách khi IR báo | ______cm | `INSERT_MIN_DISTANCE` |
