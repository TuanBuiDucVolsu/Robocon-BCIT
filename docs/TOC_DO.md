# Tối ưu tốc độ hoàn thành bài thi

Mục tiêu: giảm thời gian hoàn thành NV1 + NV2 từ **~180-185s** (trạng thái hiện tại,
đã có tiếp cận 2 pha #1, chưa calibrate timing) xuống **~135-145s** sau khi calibrate
fast-profile — dư biên an toàn cho retry và sai số trên sa bàn thật.

> **Nguyên tắc:** chỉ tối ưu nơi tốn nhiều thời gian nhất. Mọi giá trị bên dưới là
> ĐIỂM KHỞI ĐẦU — phải calibrate trên sa bàn rồi mới chốt. Tăng tốc mà mất line /
> trượt kệ thì chậm hơn vì phải retry.

---

## 1. Phân bổ thời gian — biết tiền đi đâu trước khi cắt

NV1 = 6 lượt nâng × 2 kiện = 12 kiện giao 4 nhà máy. NV2 = 1 kiện kho hàng rời → liên hợp.
Quy đổi sa bàn (đo từ file in chuẩn): ô lưới ~330mm (dọc) đến ~1000mm (ngang C0→C1).

| Hạng mục | Số lần | Hiện tại | Sau fast-profile | Ưu tiên |
|----------|:------:|:--------:|:----------------:|:---:|
| Bám line qua giao lộ | ~50 đoạn | ~60s | ~42s | 🔴 |
| Tiếp cận + lùi kệ (2 pha ✅) | 6+6 | ~34s | ~28s | 🔴 |
| Hạ/giao 12 kiện | 12 | ~25s | ~22s | 🟡 |
| Nâng 6 lượt | 6 | ~20s | ~16s | 🟡 |
| Xoay 90° | ~24 | ~19s | ~13s | 🟢 |
| Quét camera + exit + misc | — | ~10s | ~7s | 🟢 |
| **NV1 cộng dồn** | | **~168s** | **~128s** | |
| NV2 (kho hàng rời → liên hợp) | +1 | ~15s | ~12s | |
| **TỔNG (NV1+NV2)** | | **~183s** | **~140s** | |

| | Thời gian | Biên an toàn / 240s |
|---|:---:|:---:|
| **Hiện tại** (chưa calibrate timing) | **~180–185s** | ~55–60s |
| **Sau fast-profile** (calibrate xong) | **~135–145s** | ~95–105s |

**~61% thời gian ở 2 hạng mục đầu** (bám line + tiếp cận kệ). Đừng phí công tối ưu xoay/camera.

> ⚠️ **Biến số lớn nhất chưa đo:** tốc độ tịnh tiến thật của robot (giả định ~0.4 m/s ở
> 70% PWM). Sau khi bấm giờ 1 lượt thật bằng `test_smoke.py` option 5, thay đơn giá thật
> vào bảng để ra số chính xác (±5s thay vì ±20s).

---

## 2. Sáu tối ưu xếp theo lợi ích / rủi ro

| # | Tối ưu | Tiết kiệm | Rủi ro | Loại | Trạng thái |
|:-:|--------|:---------:|:------:|------|:----------:|
| 1 | Tiếp cận kệ 2 pha (nhanh → chậm) | ~14s | Thấp | Code | ✅ Đã làm |
| 2 | Tăng tốc bám line + calibrate PD | ~15-20s | Trung bình | Config | ⏳ Calibrate |
| 3 | Nâng/hạ càng SONG SONG khi di chuyển | ~10s | Trung bình | Code | ⏳ Chưa |
| 4 | Giảm khoảng cách lùi kệ | ~10s | Thấp | Config | ⏳ Calibrate |
| 5 | Calibrate xoay + tăng tốc xoay | ~4s | Thấp | Config | ⏳ Calibrate |
| 6 | Giảm delay verify/retry thừa | ~3s | Thấp | Config | ⏳ Calibrate |
| | **Tổng tiềm năng** | **~55s** | | | |

> **Đã áp dụng vào code (ngoài bảng):** động cơ bánh PWM **cả 2 chiều** (lùi/xoay đúng
> tốc độ, xoay cân tâm) + siêu âm lấy **median 3 mẫu** trong approach/retreat (chống
> nhiễu HC-SR04, giảm dừng sai → giảm retry tầng).

---

## 3. Tối ưu #1 — Tiếp cận kệ 2 pha (lợi ích lớn nhất, rủi ro thấp) ✅ ĐÃ IMPLEMENT

> Đã áp dụng vào `config.py` + `control/motion.py`. Phần dưới giữ lại để tham khảo +
> hướng dẫn calibrate. Còn lại chỉ cần đo `APPROACH_FAST/SLOW_SPEED` trên sa bàn.

### Vấn đề
`approach_shelf()` hiện tiến **tốc độ cố định 30%** từ 20cm xuống 4cm. Chậm toàn bộ
quãng đường dù đoạn xa không cần chính xác.

### Giải pháp
Đi **nhanh** (60%) đến khi còn ~10cm, rồi **chậm** (25%) để dừng chính xác ở 4cm.
Đoạn xa nhanh gấp đôi, đoạn gần vẫn chính xác.

### Config thêm vào `config.py`

```python
# Tiếp cận kệ 2 pha
APPROACH_FAST_SPEED = 60     # Tốc độ pha xa (nhanh)
APPROACH_SLOW_SPEED = 25     # Tốc độ pha gần (chính xác)
APPROACH_SLOW_DISTANCE = 10  # cm — dưới mức này chuyển sang chậm
```

### Sửa `control/motion.py` — `approach_shelf()`

```python
def approach_shelf(self, target_cm: float = config.APPROACH_DISTANCE) -> bool:
    if self._distance_sensor is None:
        logger.error("Không có cảm biến siêu âm — không thể tiếp cận kệ an toàn")
        return False

    logger.info("Tiếp cận kệ 2 pha — mục tiêu %.1fcm", target_cm)
    start = time.time()

    while time.time() - start < config.APPROACH_TIMEOUT:
        dist = self.get_distance()
        if dist <= target_cm:
            self.stop()
            logger.info("Đã đến vị trí kệ — %.1fcm", dist)
            return True
        # Pha xa: nhanh; pha gần: chậm để dừng chính xác
        speed = (config.APPROACH_SLOW_SPEED if dist <= config.APPROACH_SLOW_DISTANCE
                 else config.APPROACH_FAST_SPEED)
        self.forward(speed)
        time.sleep(0.02)

    self.stop()
    logger.warning("Timeout tiếp cận kệ sau %.1fs!", config.APPROACH_TIMEOUT)
    return False
```

> **Calibrate:** test_motion option 9. Đảm bảo robot KHÔNG vọt quá 4cm (đâm kệ) khi
> chuyển pha. Nếu vọt → giảm `APPROACH_SLOW_SPEED` hoặc tăng `APPROACH_SLOW_DISTANCE`.

---

## 4. Tối ưu #2 — Tăng tốc bám line (lợi ích lớn nhất tổng thể)

### Vấn đề
`SPEED_DEFAULT = 70`. Bám line chiếm 34% thời gian → tăng tốc ở đây lời nhất.
Nhưng nhanh quá → dao động, mất line, đếm sai giao lộ.

### Lộ trình calibrate an toàn (test_motion option 7)

```python
# Bước 1: giữ nguyên KP/KD, tăng dần tốc độ
SPEED_DEFAULT = 75   # rồi 80, 85... dừng khi bắt đầu dao động

# Bước 2: khi dao động, tăng KD để dập rung
LINE_KD = 6.0        # rồi 7, 8...

# Bước 3: nếu vào cua trượt line, tăng KP
LINE_KP = 17.0
```

### Giá trị khởi đầu đề xuất

```python
SPEED_DEFAULT = 82   # từ 70
LINE_KP = 16.0       # từ 15.0
LINE_KD = 6.5        # từ 5.0
```

> **Quan trọng:** giao lộ nhận diện bằng `INTERSECTION_THRESHOLD = 5` mắt. Nhanh quá
> có thể "nhảy" qua giao lộ mà không đủ 5 mắt thấy đồng thời → đếm thiếu → sai cả route.
> Test kỹ option 7 trên đoạn có nhiều giao lộ trước khi tăng cao.

---

## 5. Tối ưu #3 — Nâng/hạ càng SONG SONG khi di chuyển

### Vấn đề
Motor cẩu (GPIO 24/25, 5/6/13) và motor bánh (GPIO 17/27/22/23) **độc lập hoàn toàn**.
Hiện code chạy tuần tự: di chuyển xong → mới nâng. Lãng phí.

### Cơ hội
- **Sau pickup:** robot rời kệ với càng đang cao. Khi bám line đến nhà máy, **hạ dần
  càng về tư thế giao** trong lúc đang chạy → tiết kiệm thời gian hạ tại chỗ.
- **Trước pickup tầng 2:** nâng càng lên `approach_level` (tầng 1) **trong lúc** đang
  tiếp cận kệ, thay vì sau khi dừng.

### Cách làm an toàn (đơn giản nhất, ít rủi ro)
Chỉ overlap ở đoạn **đi thẳng** (không trong lúc xoay/đua line gắt). Ví dụ chèn lệnh
nâng KHÔNG chặn (non-blocking) ở đầu `_handle_deliver_first` khi route bắt đầu bằng
đoạn forward dài.

> ⚠️ Đây là tối ưu rủi ro trung bình — chỉ làm SAU khi #1, #2, #4 đã ổn định và đã đo
> thực tế là cơ cấu nâng không làm lệch trọng tâm khi đang chạy. Nếu càng rung khi di
> chuyển làm rơi pallet thì BỎ tối ưu này.

---

## 6. Tối ưu #4 — Giảm khoảng cách lùi kệ

### Vấn đề
`RETREAT_DISTANCE = 15cm`. Robot chỉ cần lùi đủ xa để xoay không chạm kệ — thường
**10cm là đủ** tuỳ bán kính xoay.

### Config

```python
RETREAT_DISTANCE = 10.0   # từ 15.0 — đo bán kính xoay thực tế
```

> **Calibrate:** test_motion option 9 rồi option 10 (xoay) — đảm bảo khi xoay ở 10cm,
> đuôi/càng robot KHÔNG quệt kệ. Nếu quệt → tăng lại.

---

## 7. Tối ưu #5 — Xoay nhanh và chính xác

### Vấn đề
`TURN_TIME = 0.6s`, `SPEED_TURN = 55`. ~24 lần xoay = ~15s. Xoay không đủ 90° → lệch
line → phải recover (rất tốn thời gian).

### Hướng
1. **Calibrate `TURN_TIME` cực chính xác** (test_motion option 10) — đây là ưu tiên
   số 1, vì xoay sai gây mất line dây chuyền.
2. Có thể tăng `SPEED_TURN` lên 60-65 để xoay nhanh hơn, rồi giảm `TURN_TIME` tương ứng.

```python
SPEED_TURN = 62      # từ 55
TURN_TIME = 0.5      # đo lại sau khi đổi SPEED_TURN
```

> Xoay nhanh tiết kiệm ít (~4s) nhưng xoay **chính xác** tiết kiệm rất nhiều gián tiếp
> (không phải recover line). Ưu tiên chính xác hơn nhanh.

---

## 8. Tối ưu #6 — Giảm delay/retry thừa

```python
PICKUP_VERIFY_DELAY = 0.2    # từ 0.3 — nếu IR phản hồi nhanh
SCAN_RETRY_DELAY = 0.05      # từ 0.1
MAX_PAIR_SCAN_ATTEMPTS = 2   # giữ nguyên — đừng giảm, ảnh hưởng độ chính xác
```

> Đừng giảm `MAX_TIER_RETRIES` hay `PICKUP_MAX_RETRIES` — đó là lưới an toàn, mất nhiều
> điểm hơn là tiết kiệm vài giây.

---

## 9. "Fast profile" — khối config dán sẵn (sau khi calibrate)

```python
# ===== FAST PROFILE — chỉ áp dụng SAU khi đã calibrate từng giá trị =====
# Bám line
SPEED_DEFAULT = 82
LINE_KP = 16.0
LINE_KD = 6.5

# Xoay
SPEED_TURN = 62
TURN_TIME = 0.5          # PHẢI đo lại sau khi đổi SPEED_TURN

# Tiếp cận kệ 2 pha
APPROACH_FAST_SPEED = 60
APPROACH_SLOW_SPEED = 25
APPROACH_SLOW_DISTANCE = 10
APPROACH_DISTANCE = 4.0
RETREAT_DISTANCE = 10.0

# Delay
PICKUP_VERIFY_DELAY = 0.2
SCAN_RETRY_DELAY = 0.05
```

**Ước tính sau tối ưu:** ~180-185s (hiện tại) → **~135-145s** (sau fast-profile),
dư ~95-105s biên an toàn / 240s. Xem bảng phân bổ chi tiết ở mục 1.

---

## 10. Tối ưu chiến lược (không cần code, chỉ bố trí)

| Ý tưởng | Lợi ích |
|---------|---------|
| **Đặt camera góc rộng hơn** để quét 2 kiện rõ ngay khi vừa tới kệ | Bớt retry scan |
| **Calibrate HSV tại sân thi** (ánh sáng khác phòng tập) | Bớt scan fail → bớt retry tầng |
| **Bánh xe bám tốt** (cao su, không trượt) | PD ổn định ở tốc độ cao |
| **Trọng tâm thấp + cân** | Tăng tốc/xoay không lật, không trượt |
| **Pin đầy mỗi trận** | Motor đủ lực ở tốc độ cao, không sụt PWM |

---

## 11. Thứ tự triển khai (làm theo đúng thứ tự này)

1. ✅ **Calibrate `TURN_TIME`** chính xác trước (option 10) — nền tảng mọi thứ
2. ✅ **Tối ưu #1** (approach 2 pha) — lời nhất, rủi ro thấp, làm trước
3. ✅ **Tối ưu #4** (giảm retreat) — đổi 1 số, test nhanh
4. ✅ **Tối ưu #2** (tăng tốc line) — calibrate từ từ, đây là phần khó nhất
5. ✅ **Tối ưu #6** (giảm delay) — đổi vài số
6. ⚠️ **Tối ưu #3** (overlap nâng/hạ) — CHỈ làm cuối, sau khi mọi thứ ổn định
7. 🏁 Chạy full `test_smoke.py` option 5, đo thời gian thực, lặp lại calibrate

> **Quy tắc vàng:** đổi MỘT thứ → test → đo → chốt → mới đổi thứ tiếp theo. Đừng đổi
> nhiều tham số cùng lúc, sẽ không biết cái nào gây lỗi.
