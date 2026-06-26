# Hướng dẫn chạy test

Thư mục `tests/` có 2 nhóm test:

| Nhóm | File | Chạy ở đâu | Cần phần cứng? |
|------|------|-----------|----------------|
| **Unit test** (logic) | `test_logic.py` | PC hoặc Pi | ❌ Không |
| **Test phần cứng** (tương tác) | `test_motion.py`, `test_lift.py`, `test_vision.py` | Raspberry Pi 4 | ✅ Có |
| **Smoke tích hợp** | `test_smoke.py` | Pi + **sa bàn thật** | ✅ Có |

> Tất cả lệnh chạy từ **thư mục gốc repo** (`/home/mbw12345/Robocon-BCIT`), không phải trong `tests/`.

---

## A. Unit test — `test_logic.py` (chạy trên PC, không cần GPIO)

Kiểm tra logic route, cost, polarity cảm biến, phân loại màu, reset luyện tập, plan delivery… bằng mock. **44 test.**

```bash
cd /home/mbw12345/Robocon-BCIT

# Chạy toàn bộ unit test (gọn)
python3 -m unittest discover -s tests -q

# Chạy chi tiết từng test
python3 -m unittest tests.test_logic -v

# Chạy 1 nhóm test cụ thể
python3 -m unittest tests.test_logic.TestLineSensorPolarity -v
python3 -m unittest tests.test_logic.TestReturnRoute -v
python3 -m unittest tests.test_logic.TestVisionColorClassify -v   # phân loại màu HSV
```

Kết quả mong đợi: dòng cuối in `OK`. Nếu có `FAILED (...)` → đọc traceback để sửa.

> Các cảnh báo `PinFactoryFallback` / log `[WARNING]` là **bình thường** trên PC (không có GPIO) — test vẫn pass.

---

## B. Chuẩn bị trước khi test phần cứng (trên Pi)

```bash
# 1. SSH vào Pi (xem docs/SETUP_PI.md nếu chưa cài)
ssh pi@<hostname>

# 2. Vào repo + bật virtualenv (nếu đã tạo theo SETUP_PI.md)
cd ~/Robocon-BCIT
source ~/robot_env/bin/activate

# 3. Đảm bảo đã bật SPI + Camera (raspi-config) và cấp nguồn động cơ
```

> ⚠️ **An toàn:** kê robot lên đế (bánh không chạm đất) khi test động cơ lần đầu, tránh robot lao đi.

---

## C. Test phần cứng tương tác — chọn theo menu

Mỗi file mở menu; nhập số rồi Enter. Với `test_motion`/`test_lift`/`test_vision`:
**`0` = chạy tất cả**. `test_smoke` chỉ có `1`–`5` (không có `0`). Ctrl+C = thoát.

### `test_motion.py` — động cơ, dò line, điều hướng
```bash
python3 tests/test_motion.py
```
| # | Test | Dùng để |
|---|------|---------|
| 1 | Tiến/Lùi | Kiểm chiều quay động cơ |
| 2 | Xoay trái/phải | Kiểm 2 bánh ngược chiều |
| 3 | Các mức tốc độ | Xem PWM theo % |
| 4 | Đọc cảm biến dò line (digital) | Kiểm 6 mắt ra 0/1 |
| 5 | **Calibrate QTR-8A (raw ADC)** | Xem giá trị thô đen/trắng |
| 6 | Thoát ô start | `exit_start_zone()` |
| 7 | Bám line (chạy thực tế) | PD line-following |
| 8 | Cảm biến siêu âm | Đo khoảng cách HC-SR04 |
| 9 | Tiếp cận + lùi khỏi kệ | `approach_shelf` 2 pha |
| 10 | **Xoay 90° (calibrate `TURN_TIME`)** | Chỉnh thời gian xoay |
| 11 | `execute_route` (route config) | Chạy thử 1 route |
| 12 | Shared SPI: line + IR cùng lúc | Kiểm bus dùng chung |

### `test_lift.py` — cơ cấu nâng forklift
```bash
python3 tests/test_lift.py
```
| # | Test |
|---|------|
| 1 | Nâng/Hạ cơ bản |
| 2 | Các tầng kệ (1 và 2) |
| 3 | Cảm biến IR pallet trái/phải (calibrate `PALLET_THRESHOLD`) |
| 4 | Pickup/Dropoff tầng 1 |
| 5 | Pickup/Dropoff tầng 2 |
| 6 | Drop từng càng NV1 (left/right + stow) |
| 7 | Pickup NV2 (`require_both=False`) |
| 8 | `dropoff()` 2 kiện cùng nhà máy |

### `test_vision.py` — camera & nhận diện màu HSV
```bash
python3 tests/test_vision.py
```
| # | Test |
|---|------|
| 1 | Chụp ảnh camera |
| 2 | **Phân tích màu HSV (tinh chỉnh `COLOR_RANGES`)** |
| 3 | Nhận diện 1 lần |
| 4 | Nhận diện liên tục (5 lần) |
| 5 | Đánh giá độ ổn định (10 lần) |
| 6 | Nhận diện cặp 2 kiện (`classify_pair` — dùng trong NV1) |
| 7 | `classify_pair` liên tục 5 lần |

### `test_smoke.py` — tích hợp trên sa bàn thật
```bash
python3 tests/test_smoke.py
```
| # | Smoke |
|---|-------|
| 1 | Exit start + `ROUTE_START` → Kệ 3 |
| 2 | Pickup 1 lượt (approach + classify_pair + nâng) |
| 3 | Drop từng càng + raise_after_drop / stow |
| 4 | NV2 pickup (`require_both=False`) |
| 5 | Full rút gọn (1+2) |

---

## D. Công cụ calibrate riêng (ngoài menu test)

```bash
# Chốt LINE_BLACK_IS_HIGH + LINE_THRESHOLD cho QTR-8A
python3 -m tools.calibrate_line
```
Xem thêm: [../docs/SA_BAN.md](../docs/SA_BAN.md).

---

## E. Thứ tự khuyến nghị khi lên sân

1. `test_logic` (trên PC, trước khi mang đi) → đảm bảo logic xanh.
2. `tools.calibrate_line` → chốt polarity + ngưỡng line.
3. `test_motion` #5 #4 (cảm biến line) → #10 (`TURN_TIME`) → #7 (bám line) → #2 #3.
4. `test_lift` #3 (IR) → #1 #2 → #4..#8.
5. `test_vision` #2 (HSV) → #6 (cặp kiện).
6. `test_smoke` #1 → #2 → #3 → #5 → cuối cùng chạy full bằng **`bash scripts/practice.sh`**
   (luyện tập lặp: xong 1 lượt tự reset, nhấn nút chạy lại, Ctrl+C thoát).

> Các giá trị cần đo (TURN_TIME, LINE_KP/KD, LIFT_TIME_*, COLOR_RANGES…) cập nhật trong
> [../config.py](../config.py). Số giao lộ các `ROUTE_*` đã verify từ file in chuẩn — không cần đếm lại.

## F. Lưu ý

- Nếu một test phần cứng báo lỗi SPI/GPIO "đang bận", chạy lại — các test tự gọi
  `reset_mcp3008_bus()` khi thoát; hoặc reboot Pi.
- Đừng chạy test phần cứng khi `main.py`/systemd service đang chạy (tranh chấp GPIO):
  `sudo systemctl stop robot` trước khi test.
- Chế độ thi đấu (`ROBOT_COMPETE=1` trong `scripts/start.sh`) bỏ qua web debug — xem
  [../docs/SETUP_PI.md](../docs/SETUP_PI.md).
