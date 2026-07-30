# Lộ trình test — làm theo đúng thứ tự này

In tờ này ra, tick từng ô. **Không nhảy cóc**: mỗi giai đoạn là điều kiện cần của
giai đoạn sau. Nhảy cóc thì khi hỏng sẽ không biết hỏng ở đâu.

Ký hiệu: 🔒 = **chặn** các bước sau, không đạt thì dừng lại sửa · ⏱ = tốn nhiều thời gian

| Giai đoạn | Ở đâu | Robot | Mục tiêu |
|---|---|---|---|
| 0 | PC | — | Xanh trước khi mang đi |
| 1 | Bàn thợ | **kê lên đế** | Từng cơ cấu chạy đúng chiều |
| 2 | Bàn thợ | trên line thẳng | Cảm biến line 🔒 |
| 3 | Bàn thợ | kê lên đế | Cơ cấu nâng + IR |
| 4 | **Sa bàn (không cần robot)** | — | **Bản đồ** 🔒 |
| 5 | Sa bàn | chạy | Di chuyển từng đoạn |
| 6 | Sa bàn | đứng yên | Nhận diện |
| 7 | Sa bàn | chạy | Tích hợp |
| 8 | Sa bàn | chạy | Ngân sách 240s ⏱ |
| 9 | Sa bàn | chạy | Diễn tập thi đấu ⏱ |

---

## GIAI ĐOẠN 0 — Trên PC (10 phút, không rủi ro)

- [ ] **0.1** `python3 -m pytest tests/ -q` → phải **`176 passed`** 🔒
- [ ] **0.2** `python3 -m tools.show_routes > routes.txt` — **in ra giấy, mang theo**
- [ ] **0.3** `python3 -m tools.dry_run > kichban.txt` — **in ra giấy**, đây là kịch bản
      robot sẽ chạy, dùng để đối chiếu ở giai đoạn 4

---

## GIAI ĐOẠN 1 — Bàn thợ, robot KÊ LÊN ĐẾ (bánh không chạm đất)

> ⚠️ Không đặt robot xuống đất ở giai đoạn này. Sai chiều motor là robot lao đi.

- [ ] **1.1** `python3 tools/check_mcp3008.py` — SPI + 8 kênh sống 🔒
- [ ] **1.2** `test_motion` **d** — chạy từng bánh riêng.
      *Đạt:* bánh nào quay đúng chiều bánh đó. *Hỏng:* đảo dây motor, **không sửa code**
- [ ] **1.3** `test_motion` **1** → **2** → **3** — tiến/lùi/xoay/các mức tốc độ
- [ ] **1.4** `test_lift` **b** → **c** — từng càng nâng lên hạ xuống đúng chiều
- [ ] **1.5** `test_lift` **a** → chốt `PALLET_THRESHOLD` → `test_lift` **8** xác nhận
- [ ] **1.6** `test_motion` **8** — siêu âm đo đúng khoảng cách (đưa tay ra xa/gần)
- [ ] **1.7** `python3 -m tools.check_board_side` — **làm đủ 3 bước** trong tool:
      gạt công tắc → chỉ dòng NỬA SÂN đổi; bấm nút → chỉ dòng NÚT đổi.
      Cả hai cùng đổi = **cắm tráo chân**. Xong thì **dán nhãn 2 bên công tắc**
- [ ] **1.8** `test_vision` **1** (chụp được ảnh) → **8** (thứ tự kênh BGR/RGB) 🔒
      *Sai ở 8 thì mọi dải màu HSV sau này đều sai có hệ thống*

---

## GIAI ĐOẠN 2 — Cảm biến line 🔒

> Đây là gốc của mọi thứ liên quan đến di chuyển. Chưa xong bước này thì mọi lỗi
> bám line sau đó đều vô nghĩa để chẩn đoán.

- [ ] **2.1** `python3 -m tools.calibrate_line` trên line thật của sa bàn
      → chốt `LINE_BLACK_IS_HIGH` + `LINE_THRESHOLD` 🔒
- [ ] **2.2** `test_motion` **5** — rê robot qua line, xem ADC đổi đúng
- [ ] **2.3** `test_motion` **4** — digital ra 0/1 đúng, giữa line thì các mắt giữa = 1
- [ ] **2.4** `test_motion` **12** — line + IR đọc đồng thời không xung đột SPI

---

## GIAI ĐOẠN 3 — Cơ cấu nâng (kê lên đế)

- [ ] **3.1** `test_lift` **d** → gõ `find1` rồi `find2` — đo thật `LIFT_TIME_SHELF_1/2`
      bằng cách nâng từng xung 0.05s cho tới khi càng khít dưới pallet
- [ ] **3.2** `test_lift` **e** → thấy lệch thì sang **d** chỉnh `l+/l-` `r+/r-` → quay lại **e**.
      Lặp tới khi 2 càng ngang nhau
      *Mô hình bù vừa đổi sang vị trí tuyệt đối — số cũ của tầng 2 không còn đúng*
- [ ] **3.3** `test_lift` **9** — nâng lên tầng 2 rồi home. *Đạt:* cả 2 càng chạm đáy hẳn
- [ ] **3.4** `test_lift` **3** → **4** — pickup/dropoff tầng 1 và 2, IR xác nhận
- [ ] **3.5** `test_lift` **5** — thả từng càng, nâng lại / gập càng
- [ ] **3.6** `test_lift` **6** — pickup NV2 (chỉ cần 1 IR)

---

## GIAI ĐOẠN 4 — BẢN ĐỒ 🔒 (quan trọng nhất, KHÔNG cần robot)

> Bản đồ line hiện tại **suy ra từ ảnh in, chưa ai đo thực địa**. Mọi route đều dựa
> lên nó. Chưa xác nhận bước này mà cho robot chạy route thì hỏng cũng không biết
> do bản đồ sai hay do robot chạy sai.

- [ ] **4.1** Cầm `routes.txt` (bước 0.2), **đi bộ dọc từng đoạn trên sa bàn**, đếm tay
      số giao lộ. Đối chiếu 3 điểm dễ sai nhất:
  - Kệ ↔ kệ có đúng **1** giao lộ không (R1/R3 có cắt cột kệ không)?
  - Đi từ kệ sang cột giữa có đúng **1** giao lộ không?
  - Hàng R2 (hàng Kệ 2) có **đứt** ở vòng tròn ROBOCON không?
- [ ] **4.2** Đo khoảng đứt ở ô xuất phát (~245mm?) và ở vòng tròn (~560mm?)
- [ ] **4.3** Lệch chỗ nào → sửa `navigation.NODES` / `EDGES` → chạy lại **0.1** và **0.2**
      *Sửa BẢN ĐỒ, tuyệt đối không sửa từng route lẻ*
- [ ] **4.4** Cầm `kichban.txt` (bước 0.3) đi bộ trọn kịch bản một lượt cho chắc

---

## GIAI ĐOẠN 5 — Di chuyển trên sa bàn

- [ ] **5.1** `test_motion` **7** — bám line thẳng, không lắc
- [ ] **5.2** `test_motion` **f** — calibrate `PWM_COMPENSATION` bằng encoder (tự lưu)
- [ ] **5.3** Chốt `SPEED_TURN` **trước**, rồi `test_motion` **10** — calibrate `TURN_TIME`
      *Đổi `SPEED_TURN` sau khi calibrate sẽ làm `TURN_TIME` sai trở lại*
- [ ] **5.4** `test_motion` **6** — thoát ô xuất phát, chạm line R0
- [ ] **5.5** `test_motion` **14** — vượt khoảng đứt ô xuất phát → chốt `LINE_GAP_COAST_TIME`
- [ ] **5.6** `test_motion` **13** — dò nửa sân. *Đạt:* kết quả khớp bản in (nửa CHUẨN)
- [ ] **5.7** `test_motion` **15** — lùi ra khỏi kệ.
      *Đạt:* robot lùi thẳng, KHÔNG ngoáy đuôi tăng dần. Ngoáy = dấu PD khi lùi sai 🔒
- [ ] **5.8** `test_motion` **11** — chạy lần lượt **cả 8 tuyến mẫu**, tuyến nào cũng
      phải dừng đúng chỗ. Đây là lần đầu bản đồ được robot kiểm chứng

---

## GIAI ĐOẠN 6 — Nhận diện (làm TẠI SÂN, dưới ánh sáng thi đấu)

> Ảnh mẫu chụp ở phòng lab thường không dùng được ở sân.

- [ ] **6.1** `python3 -m tools.capture_templates` — chụp lại 4 ảnh mẫu ORB
- [ ] **6.2** `test_vision` **9** — *Đạt:* kiện đúng ≥6 inlier VÀ cách kiện thứ nhì ≥2 lần
- [ ] **6.3** `python3 -m tools.calibrate_vision` → `test_vision` **2** — HSV dự phòng
- [ ] **6.4** `test_vision` **6** → **7** — `classify_pair` ổn định
- [ ] **6.5** `test_vision` **l** — ánh xạ TRÁI/PHẢI 🔒
      *Đặt 2 kiện KHÁC LOẠI, robot đọc đúng bên. Lật trái/phải = cả 2 kiện đi nhầm
      nhà máy mà log vẫn báo OK — không cảm biến nào phát hiện được*

---

## GIAI ĐOẠN 7 — Tích hợp (smoke)

Chạy `python3 tests/test_smoke.py`, theo đúng thứ tự:

- [ ] **7.1** smoke **1** — xuất phát → dò nửa sân → vào Kệ 3
- [ ] **7.2** smoke **6** — chặn chạy mù (dọn trống phía trước, robot phải dừng sớm)
- [ ] **7.3** smoke **2** — pickup 1 lượt
- [ ] **7.4** smoke **3** — thả từng càng
- [ ] **7.5** smoke **5** ★ — **MỘT LƯỢT ĐẦY ĐỦ**: pickup → giao 2 nhà máy → quay về
      lấy tầng 2. Đây là lần đầu cả 3 loại tuyến chạy liền mạch
- [ ] **7.6** smoke **7** — NV2 đầy đủ (Kệ 4 → liên hợp)

---

## GIAI ĐOẠN 8 — Ngân sách 240 giây ⏱

> Đến đây robot chạy đúng rồi. Câu hỏi còn lại là **có kịp giờ không**.

- [ ] **8.1** `bash scripts/practice.sh` — chạy **1 lượt trọn vẹn**, xem bảng
      *Thời gian từng chặng* cuối log
- [ ] **8.2** `python3 -m tools.measure_phases` — ra 7 số đo thật + dự báo điểm
- [ ] **8.3a** `test_motion` **17** — **đo giới hạn tốc độ TRƯỚC khi tăng**.
      Bài này đo tần số đọc cảm biến thật + tốc độ thật, rồi tính mỗi lần đọc robot
      đi được bao nhiêu mm và có bao nhiêu lần đọc rơi trên vạch giao lộ.
      **Dưới 3 lần đọc/vạch là robot sẽ bay qua giao lộ mà không thấy** — lỗi này
      không hiện ra khi chạy thử vài mét, nó hiện ra giữa trận
- [ ] **8.3b** **TĂNG TỐC** — đòn bẩy lớn nhất (~80s). `SPEED_DEFAULT` đang để 50
      (mức bring-up; motor cũ chạy 82). Tăng **từng nấc +10**, KHÔNG vượt mức mà
      **8.3a** báo an toàn. Mỗi nấc kiểm đủ 3 thứ:
  - **5.1** bám line — có dao động/lắc không
  - **5.8** đếm giao lộ — **đếm tay đối chiếu**, thiếu 1 cái là dừng lại
  - Vị trí dừng ở giao lộ — có vọt quá không (vọt thì lần xoay sau lệch chỗ)
- [ ] **8.3c** Chốt tốc độ xong mới chỉnh `LINE_KP` / `LINE_KD` cho hết dao động
- [ ] **8.3d** Nếu có đổi `SPEED_TURN` → **calibrate lại `TURN_TIME`** (bước 5.3)
- [ ] **8.4** `test_motion` **16** — A/B đếm giao lộ dừng vs chạy liền.
      Đếm tay đúng cả 2 lần → mới đặt `CONTINUOUS_INTERSECTIONS = True` (~34s)
- [ ] **8.5** Chạy lại **8.1 → 8.2**, xem dự báo kịch bản **TỆ NHẤT** được mấy kiện
- [ ] **8.5b** Chạy lại **smoke 5** (một lượt đầy đủ) ở tốc độ mới — tăng tốc xong
      mà chưa chạy lại trọn một lượt thì chưa biết có còn đúng không
- [ ] **8.5c** `python3 -m tools.sim_ui --speed 80` — xem trước robot dừng ở kiện
      thứ mấy khi hết 240s
- [ ] **8.6** Còn thiếu giờ → tối ưu tiếp theo thứ tự: `TURN_TIME` → thời gian nâng/hạ
      → thời gian tiếp cận siêu âm

**Mốc tham chiếu** (nếu làm hết): tệ nhất ~12/13 kiện = 240đ, đẹp nhất 13/13 = 270đ.
NV1 phải xong trước giây ~216 thì mới với được NV2.

---

## GIAI ĐOẠN 9 — Diễn tập thi đấu ⏱

Theo [DIEN_TAP.md](DIEN_TAP.md), 9 bài. Ba bài bắt buộc không được bỏ:

- [ ] **9.1** DT-2 — chạy với **kịch bản xếp kiện XẤU NHẤT** (có bảng cụ thể trong file)
- [ ] **9.2** DT-3 ★ — **diễn tập RESET**: bấm nút giữa trận, đặt tay robot về ô xuất
      phát, robot phải chạy tiếp và **giữ nguyên tiến độ**
- [ ] **9.3** DT-7 — gạt công tắc sang **nửa sân đối diện**, chạy lại 8.1 và 9.1
- [ ] **9.4** Các bài còn lại: DT-4 (sự cố), DT-5 (pin tụt), DT-6 (ánh sáng), DT-8
      (bấm nút đúng hiệu lệnh), DT-9 (dừng khẩn cấp)
- [ ] **9.5** Checklist ngày thi đấu (cuối DIEN_TAP.md)

---

## Nếu chỉ có ít thời gian

Làm đúng 6 bước này, bỏ hết phần còn lại:

1. **2.1** calibrate line
2. **4.1** đếm giao lộ tay trên sa bàn
3. **1.7** công tắc nửa sân + dán nhãn
4. **6.5** kiểm trái/phải camera
5. **7.5** smoke 5 — một lượt đầy đủ
6. **8.3** tăng `SPEED_DEFAULT`

Năm cái đầu là những chỗ sai mà **không có tín hiệu báo lỗi nào**; cái cuối là thứ
quyết định được mấy kiện trong 240 giây.
