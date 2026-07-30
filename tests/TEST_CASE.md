# Hướng dẫn chạy test

| Nhóm | File | Chạy ở đâu | Cần phần cứng |
|------|------|-----------|---------------|
| **Tự động** | `test_units.py`, `test_logic.py`, `test_match_sim.py` | PC hoặc Pi | ❌ |
| **Phần cứng** (menu tương tác) | `test_motion.py`, `test_lift.py`, `test_vision.py` | Pi | ✅ |
| **Smoke tích hợp** | `test_smoke.py` | Pi + **sa bàn thật** | ✅ |
| **Diễn tập thi đấu** | [DIEN_TAP.md](DIEN_TAP.md) | Pi + sa bàn + đồng hồ | ✅ |

> **Bắt đầu test từ đâu?** → [LO_TRINH_TEST.md](LO_TRINH_TEST.md): danh sách đánh số
> theo đúng thứ tự phải làm, từ chạy pytest trên PC đến diễn tập thi đấu. File dưới
> đây là tra cứu từng menu; file đó là lộ trình.

> File này kiểm **từng phần chạy đúng không**. [DIEN_TAP.md](DIEN_TAP.md) kiểm **có ăn
> được điểm trong 240 giây thật không** — gồm ngân sách thời gian, kịch bản xếp kiện
> xấu nhất, diễn tập reset/sự cố, pin tụt, ánh sáng sân.

> Chạy từ **thư mục gốc repo**, không phải trong `tests/`.

---

## A. Test tự động (PC, không cần GPIO)

```bash
python3 -m pytest tests/ -q          # tất cả — 197 test + 401 subtest
python3 -m unittest tests.test_logic -v
python3 -m unittest tests.test_match_sim -v
```

Kết quả mong đợi: `197 passed`. Cảnh báo `PinFactoryFallback` là **bình thường** trên PC.

### `test_units.py` — logic thuần từng module

Khoá lại các hàm nhỏ mà **sai thì mất điểm nhưng không báo lỗi**:

| Nhóm | Kiểm gì |
|---|---|
| `TestLiftTiming` | Bù lệch càng theo vị trí tuyệt đối; regression: 0→1→2 không cộng dồn bù, nâng lại sau khi thả đúng bằng lúc nâng lên |
| `TestPalletSensors` | Ngưỡng IR; đọc lỗi trả `None` chứ không phải `False` |
| `TestVerifyReleased` | Quyết định `packages_delivered` có tăng không — SPI lỗi ≠ đã thả |
| `TestShapeMatcherDecision` | ORB cần CẢ ngưỡng tuyệt đối VÀ cách biệt với kiện thứ nhì |
| `TestClassifyPair` | Gộp 2 nửa ảnh, retry, ORB bỏ qua ngưỡng HSV |
| `TestLineError` | Dấu sai số trái/phải, mất line giữ lỗi cũ, analog mượt hơn digital |

### `test_logic.py` — logic điều hướng & state machine

| Nhóm | Kiểm gì |
|---|---|
| `TestBoardMap` | Bản đồ khớp sa bàn in: cột kệ chỉ 3 giao lộ, R2 bị cấm, nhà máy đều ở cột giữa |
| `TestRouteReachesDestination` | **Mô phỏng lại từng route sinh ra** — 12 tuyến kệ→NM, 12 tuyến NM→kệ, 12 cặp NM, NV2, đều phải tới đúng chỗ đúng hướng |
| `TestMirroredHalf` | Nửa gương = ảnh gương chính xác của nửa chuẩn |
| `TestFactoryOrderPerHalf` | Thứ tự nhà máy đảo giữa 2 nửa; liên hợp luôn ở giữa |
| `TestBoardSideSwitch` | Công tắc gạt: ánh xạ 2 vị trí, đổi được qua config, đọc lỗi trả `None` |
| `TestApplyBoardSide` | Công tắc **thắng** config; hỏng thì rơi về config |
| `TestDetectSide` | Dò chiều trái/phải: thấy line/không/lỗi cảm biến/tắt tính năng |
| `TestMidMatchReset` | Reset giữa trận: về ô xuất phát, GIỮ tiến độ, không cộng giờ |
| `TestMotionAbort` | Motion bỏ dở ngay khi có yêu cầu reset (không chờ timeout) |
| `TestGotoHelper` | Route chạy dở → vị trí tính từ bước ĐÃ hoàn thành |
| `TestLineSensorPolarity` | `LINE_BLACK_IS_HIGH`; đọc lỗi không được thành "trên line" giả |
| `TestPlanDelivery` | Chọn thứ tự giao rẻ hơn |
| `TestMatchResume` | Lưu/đọc/xoá mốc trận để chạy nốt sau lỗi |
| `TestVisionColorClassify` | Ưu tiên màu chromatic hơn Amkor xám |

### `test_match_sim.py` — mô phỏng TRỌN trận

Chạy thật state machine của `main.py` với phần cứng giả lập, đồng thời mô phỏng robot
đi trên bản đồ. **So vị trí main.py tin tưởng với vị trí mô phỏng sau MỖI state** — lệch
một lần là fail.

| Kịch bản | Kiểm gì |
|---|---|
| Chạy sạch (20 seed) | Giao đủ **13/13 kiện** (12 NV1 + NV2) |
| 15% thao tác phần cứng lỗi | Vẫn kết thúc, không kẹt vòng lặp |
| 20% route mất line giữa chừng | Vị trí vẫn khớp thực tế |
| Nửa sân thứ tự nhà máy đảo | Vẫn 12/12 |
| Cấu hình chiều sai + probe đúng | Tự nạp lại bản đồ, vẫn 12/12 |
| **Reset giữa trận** | Về ô xuất phát, chạy tiếp, không lấy lại kiện đã lấy |
| **Kiện thứ 13 (NV2)** | Giao đủ 13/13; không làm NV2 khi NV1 chưa xong; thử lại khi nhấc hỏng; hết giờ thì bỏ |

---

## B. Chuẩn bị trước khi test phần cứng

```bash
ssh pi@<hostname>
cd ~/Robocon-BCIT && source ~/robot_env/bin/activate
sudo systemctl stop robot        # tránh tranh chấp GPIO
```

> ⚠️ Kê robot lên đế (bánh không chạm đất) khi test động cơ lần đầu.

---

## C. Test phần cứng — menu

`0` = chạy tất cả (bỏ qua các test cần nhập tay). Ctrl+C = thoát.

### `test_motion.py` — động cơ, dò line, điều hướng

| # | Test | Dùng để |
|---|---|---|
| 1 | Tiến/Lùi | Chiều quay động cơ |
| 2 | Xoay trái/phải | 2 bánh ngược chiều |
| 3 | Các mức tốc độ | PWM theo % |
| 4 | Đọc cảm biến line (digital) | 6 mắt ra 0/1 |
| 5 | **Calibrate QTR-8A (raw ADC)** | Giá trị thô đen/trắng |
| 6 | Thoát ô start | `exit_start_zone()` |
| 7 | Bám line thực tế | PD line-following |
| 8 | Cảm biến siêu âm | Đo khoảng cách |
| 9 | Tiếp cận + lùi khỏi kệ | `approach_shelf` 2 pha |
| 10 | **Xoay 90° — calibrate `TURN_TIME`** | ƯU TIÊN #1 |
| 11 | `execute_route` — 8 tuyến mẫu | Route do `navigation.plan()` tính ra |
| 12 | Shared SPI: line + IR | Bus dùng chung |
| 13 | **Tự dò nửa sân** | `probe_side_branch` tại giao lộ Kệ 3 |
| 14 | **Vượt khoảng đứt line** | Calibrate `LINE_GAP_COAST_TIME` |
| 15 | Lùi ra khỏi kệ (`back`) | Kiểm dấu PD khi lùi TRƯỚC khi tin dùng |
| 16 | **A/B đếm giao lộ: dừng vs chạy liền** | Đòn bẩy 240s lớn nhất — đo rồi mới bật |
| 17 | **Giới hạn tốc độ** | Đo trước khi tăng `SPEED_DEFAULT` — trượt giao lộ là lỗi im lặng |
| d | Chẩn đoán motor từng bánh | Bánh nào ngược chiều |
| e | Xung encoder real-time | Kiểm dây/kênh encoder |
| f | **Calibrate `PWM_COMPENSATION`** | Tự tính & lưu |

### `test_lift.py` — cơ cấu nâng

Menu **LẶP** (chọn xong về menu, không thoát). **Home lúc vào và sau mỗi option** —
càng không có limit switch nên `_current_level` chỉ khớp thực tế sau khi home; ngắt
giữa lúc càng đang lên mà không home thì lần nâng sau đội cữ cơ khí, kẹt motor.

| # | Test |
|---|---|
| 1 | **Diễn tập TRỌN 1 lượt giao** — pickup → thả càng 1 → nâng lại → thả càng 2 → gập, đếm điểm theo đúng quy tắc `packages_delivered` của main.py |
| 2 | Chạy hết dải hành trình SÀN → T1 → SÀN → T2 → SÀN |
| 3 | Pickup/Dropoff (**chọn tầng 1 hoặc 2** — gộp option 4 cũ) |
| 5 | Thả từng càng NV1 (**luôn nâng lại/gập, giống main.py**) |
| 6 | Pickup NV2 (`require_both=False`) |
| 7 | `dropoff()` 2 kiện cùng nhà máy |
| 8 | IR real-time |
| 9 | **`home_to_floor`** — chạy đầu mỗi trận, phải hạ hết cỡ từ tầng 2. So `LIFT_HOME_DURATION` với **`min_home_duration()`** (đã tính `LIFT_*_LOWER_EXTRA`), không phải với `LIFT_TIME_SHELF_2` suông |
| a | Scan 8 channel MCP3008 (chốt `PALLET_THRESHOLD`) |
| b | **Càng TRÁI riêng** — nâng + hạ (càng phải đứng yên) |
| c | **Càng PHẢI riêng** — nâng + hạ (càng trái đứng yên) |
| e | **So sánh 2 càng cùng tầng** — nâng riêng từng bên rồi giữ nguyên để so độ cao |
| d | **Calibrate độ cao + bù lệch** (lưu `config.py`). `find1/find2` chạy **MỘT càng** do người chọn rồi **trừ lại `LIFT_*_EXTRA`** trước khi lưu mốc gốc — chạy cả 2 càng cùng số giây thì 2 bên dừng ở 2 độ cao khác nhau, không biết đang canh theo bên nào |
| h | Home lại giữa phiên |

> b/c/e dùng ĐÚNG thời gian đã bù (`_move_duration`) chứ không bật GPIO thô — nên cái
> quan sát được chính là cái xảy ra trong trận. Trước đây b/c bật chân trực tiếp với
> thời gian tự đặt và **phần hạ bị comment mất**, chỉ kiểm được dây chứ không kiểm
> được calibrate.

### `test_vision.py` — camera & nhận diện

| # | Test |
|---|---|
| 1 | Chụp ảnh |
| 2 | **Phân tích HSV** (tinh chỉnh `COLOR_RANGES`) |
| 3-5 | Nhận diện 1 lần / 5 lần / độ ổn định 10 lần |
| 6 | `classify_pair` — cặp 2 kiện (dùng trong NV1) |
| 7 | `classify_pair` liên tục 5 lần |
| 8 | **Thứ tự kênh BGR/RGB** — chạy TRƯỚC khi tinh chỉnh màu |
| 9 | So khớp ORB với ảnh mẫu (chẩn đoán template) |
| l | **Ánh xạ TRÁI/PHẢI ảnh ↔ càng robot** — lỗi im lặng, phải kiểm bằng 2 kiện khác loại |

### `test_smoke.py` — tích hợp trên sa bàn thật

Dùng đúng `navigation.plan()` như thi đấu. Fail ở bước nào thì dừng ngay tại đó.

| # | Smoke | Đi qua |
|---|---|---|
| 1 | Xuất phát → dò nửa sân → Kệ 3 | `exit_start_zone` + `DETECT_SIDE` + route |
| 2 | Pickup 1 lượt | approach → `classify_pair` → nâng → lùi |
| 3 | Thả từng càng + nâng lại/gập | Khớp đúng hành vi `main.py` |
| 4 | NV2 pickup | `require_both=False` |
| 5 | **★ MỘT LƯỢT ĐẦY ĐỦ** | pickup → giao NM1 → giao NM2 → quay về lấy tầng 2 |
| 6 | Chặn chạy mù `approach_shelf` | Bỏ vật chắn ra, robot phải dừng sớm |
| 7 | **NHIỆM VỤ 2 đầy đủ** | nhà máy → Kệ 4 → nhấc → liên hợp → thả |

> **Smoke 5 là kịch bản quan trọng nhất.** Nó là chỗ duy nhất chạy đủ cả 3 loại tuyến
> vừa viết lại (kệ→NM, NM→NM, NM→kệ) — cũng đúng là nhóm mà bảng route cũ sai 9/12.

---

## D. Công cụ ngoài menu test

```bash
python3 -m tools.show_routes         # in cả 40+ tuyến để đối chiếu tay trên sa bàn
python3 -m tools.estimate_time       # ngân sách 240s: kịch bản xếp kiện xấu nhất/đẹp nhất
python3 -m tools.check_board_side    # công tắc nửa sân + nút start (chống cắm tráo chân)
python3 -m tools.calibrate_line      # chốt LINE_BLACK_IS_HIGH + LINE_THRESHOLD
python3 -m tools.calibrate_vision    # chốt COLOR_RANGES
python3 -m tools.capture_templates   # chụp ảnh mẫu ORB (nhận diện CHÍNH)
python3 tools/check_mcp3008.py       # chẩn đoán MCP3008
python3 -m tools.raw_spi_test        # đọc SPI thô khi nghi gpiozero
python3 -m tools.test_right_wheel    # cô lập lỗi bánh chạy mãi sau stop()
```

> Line đọc toàn 0/1023 hoặc dò ngược → [DEBUG_CAM_BIEN_LINE.md](DEBUG_CAM_BIEN_LINE.md)
> Bánh chạy mãi / ngược / lệch → [DEBUG_DONG_CO.md](DEBUG_DONG_CO.md)

---

## E. Thứ tự khi lên sân

**0. Trước khi đi:** `python3 -m pytest tests/ -q` trên PC → phải `197 passed`.

**1. Bản đồ — làm TRƯỚC, mọi thứ khác dựa lên nó**
```bash
python3 -m tools.show_routes
```
Cầm ra sa bàn **đếm tay từng đoạn**. Sai thì sửa `navigation.EDGES`, **không sửa route lẻ**.
Bản đồ hiện tại suy ra từ ảnh in, **chưa đo thực địa**.

**2. Nửa sân** — `tools.check_board_side` (3 bước, có bước chống cắm tráo chân), gạt công
tắc theo kết quả bốc thăm, dán nhãn.

**3. Cảm biến line** — `tools.calibrate_line` → `test_motion` #5 #4.

**4. Động cơ** — `test_motion` #10 (`TURN_TIME`) → #f (`PWM_COMPENSATION`) → #7 → #14 → #15.

**4b. Tăng tốc (ĐÒN BẨY LỚN NHẤT cho 240s)** — `SPEED_DEFAULT` đang để 50 (mức bring-up).
Tăng từng nấc +10 theo quy trình trong `config.py`, mỗi nấc chạy lại #7 và #11 xem có
trượt giao lộ không. Riêng việc này gỡ ~80s. Xong rồi chạy #16 để cân nhắc bật
`CONTINUOUS_INTERSECTIONS`.

**5. Nâng hạ** — `test_lift` #a → #8 → **#b #c (từng càng riêng)** → **#e (so 2 càng)** → **#1 (diễn tập trọn lượt giao)**
→ #d (calibrate, chỉnh `l+/l-` `r+/r-` cho tới khi #e thấy bằng nhau) → #9 → #1..#7.
> ⚠️ Mô hình bù lệch đã đổi sang **vị trí tuyệt đối** — số cũ của tầng 2 không còn đúng.

**6. Nhận diện** — `test_vision` #8 (BGR) → `tools.capture_templates` → #9 (ORB) → #2 (HSV
dự phòng) → #6 → **#l (ánh xạ trái/phải)**.

**7. Tích hợp** — `test_smoke` #1 → #6 → #2 → #3 → **#5 (một lượt đầy đủ)** → #7 (NV2).

**8. Chạy trọn trận** — `bash scripts/practice.sh` (lặp, nhấn nút mỗi lượt, Ctrl+C thoát).

**9. Diễn tập thi đấu** — [DIEN_TAP.md](DIEN_TAP.md): ngân sách thời gian, kịch bản kiện
xấu nhất, reset, sự cố, pin, ánh sáng. **Đây mới là bước quyết định có ăn được điểm không.**

---

## F. Lưu ý

- Lỗi SPI/GPIO "đang bận" → chạy lại (test tự gọi `reset_mcp3008_bus()` khi thoát) hoặc reboot.
- Đừng test khi `main.py`/systemd đang chạy: `sudo systemctl stop robot`.
- Giá trị calibrate cập nhật trong [../config.py](../config.py).
- Số giao lộ **KHÔNG còn khai báo trong config** — nằm ở bản đồ `navigation.py`,
  xem [../docs/SA_BAN.md](../docs/SA_BAN.md).
