# CLAUDE.md — Context cho Claude Code

## Tổng quan project

Robot tự động **Bảng O2** ("Khát vọng công nghệ"), Giải Robocon Bắc Ninh mở rộng 2026 — Tranh Cúp Foxconn.
Raspberry Pi 4. Phân loại và vận chuyển hàng hoá trên sa bàn 4000x2000mm trong 240 giây.
Thi đấu dự kiến **ngày 08-09/08/2026** tại phường Bắc Giang, tỉnh Bắc Ninh.

## Thể lệ — Quy định quan trọng (Phụ lục 01 + 03)

### Giới hạn robot
- Kích thước xuất phát: **≤ 400x400x400mm** (sau xuất phát có thể mở rộng)
- Bộ điều khiển: **1 vi xử lý duy nhất**, tổng cổng I/O **≤ 16 cổng**
- Động cơ: **≤ 12** (kể cả servo, máy nén khí tính 1 động cơ)
- Pin Bảng O2: **≤ 12V**, **≤ 5000mAh**
- Camera AI: **bắt buộc** cho Bảng O2, xử lý **cục bộ** (không Internet)
- Vật liệu: **không dùng kim loại** làm khung (trừ ốc vít, bu lông)
- Robot **tự động hoàn toàn** — sau khi kích hoạt không can thiệp

### Quy định thi đấu
- Thời gian: **240 giây** (4 phút)
- Reset: tối đa **5 lần**, mỗi lần **-10 điểm** (sẵn 50 điểm reset)
- Khi reset: đội viên **tay đặt** robot về ô xuất phát
- Khởi động sai trước hiệu lệnh → cảnh báo lần 1, lần 2 bị loại
- Robot rời sa bàn hoặc sang phần sân đối phương → bị reset
- Tương tác từ xa với robot tự động → **bị loại**

### Nhiệm vụ Bảng O2 — Điểm số
- **NV1**: Lấy kiện hàng từ kho hải quan, nhận diện bằng Camera AI, giao đúng nhà máy
  - 12 kiện × 20 điểm = **240 điểm** tối đa
- **NV2**: Lấy kiện hàng rời, giao nhà máy liên hợp — **30 điểm**
  - Chỉ thực hiện **sau khi hoàn thành 100% NV1**
- **Tổng tối đa: 270 điểm** (chưa trừ reset)

### Kích thước chuẩn (từ tài liệu thi công)
- Sa bàn: **4000 x 2000mm**, in hiflex, mặt trơn, chênh lệch ≤5mm
- Khu vực xuất phát: **400 x 400mm**
- Giá kệ: **240 x 120 x 240mm**, chân cao 25mm, 2 tầng, in 3D (đen)
- Pallet: **90 x 90 x 26mm**, in 3D (nâu)
- Khối hàng hoá: **40 x 40 x 40mm**, mút xốp, dán decal 6 mặt
- Kiện hàng = 1 pallet + 4 khối cùng loại (dán cùng hình)
- Khu vực nhà máy: **250 x 250mm** mỗi khu
- Tường bao check-in: dày 2cm, cao 5cm, khoảng trống 10cm 2 phía

## Bố trí sa bàn (phía xanh) — QUAN TRỌNG

```
    Col0 (kệ/trái)   Col1 (giữa)    Col2 (nhà máy/phải)
      │                  │               │
  R4 [Kệ1]──────────────┼──[Samsung]─────┤   Kệ 1 thẳng Samsung
      │                  │               │
  R3  │                  │──[Hana M.]─────┤
      │        ◉         │               │
  R2 [Kệ2]──────────────┼──[Liên hợp]────┤   Kệ 2 thẳng Robocon / Liên hợp
      │                  │               │
  R1  │                  │──[Amkor]───────┤
      │                  │               │
  R0 [Kệ3]──line──┃GAP┃──line──[Foxconn]  ← Line R0 đứt tại ô start
      │             ┃   ┃              │
      │          ←■Start┃              │   Robot quay mặt 9h (về Kệ 3)
      │             [Kệ4]             │   Kệ 4 THỤT XUỐNG dưới R0, bên phải Start
```

- Kệ 1-3: cạnh TRÁI, cách nhau 2 giao lộ (R4, R2, R0)
- Kệ 4: bên PHẢI Start, thụt XUỐNG dưới R0, cạnh Foxconn (kho hàng rời — NV2)
- Robot xuất phát: ô start trên R0, **quay mặt sang trái (9h)** về Kệ 3
- `exit_start_zone()`: tiến thẳng chạm line R0 → căn giữa ngắn (nếu chạm giao lộ khi căn → dừng căn, **không** đếm giao lộ)
- Sau đó `ROUTE_START_TO_SHELF_0` forward 1 giao lộ → Kệ 3
- Thứ tự lấy kệ: Kệ 3 (R0, gần nhất) → Kệ 2 (R2) → Kệ 1 (R4)
- 4 nhà máy xếp DỌC cạnh phải: Samsung(R4) → Hana(R3) → Amkor(R1) → Foxconn(R0)
- Nhà máy liên hợp: giữa sân (R2), chung 2 đội

## Cấu trúc code

```
main.py              — State machine: INIT → NAVIGATE → PICKUP → DELIVER → DROP → lặp 6 lượt → TASK2
config.py            — GPIO, route commands, HSV color ranges, timing, SHELVES_TASK1
control/mcp3008_bus.py — Bus SPI dùng chung MCP3008 (lock)
control/motion.py    — Di chuyển, bám line PD analog, siêu âm HC-SR04
control/lift.py      — 2 càng độc lập: PalletSensors (SPI), require_both, _verify_released
vision/vision.py     — Nhận diện màu HSV (không dùng AI model), classify_pair()
debug/server.py      — Flask web debug UI (MJPEG stream, line sensor, classify_pair)
scripts/             — install.sh, start.sh, robot.service (systemd auto-start)
docs/                — CAC_BUOC_HOAT_DONG.md, PHAN_CUNG.md, ...
tests/               — test_motion/lift/vision/smoke + test_logic (44 unit test)
```

## State machine (luồng chính)

```
NAVIGATE_TO_SHELF → PICKUP_PAIR (approach + classify_pair + pickup + retreat)
  → DELIVER_FIRST → DROP_FIRST
  → [DELIVER_SECOND → DROP_SECOND]  (bỏ qua nếu cùng nhà máy)
  → RETURN_TO_WAREHOUSE
  → lặp 6 lượt → TASK2 → DONE
```

- **Không còn state SCAN_PAIR riêng** — quét camera nằm trong PICKUP_PAIR, sau `_approach_shelf()`
- **`_last_delivered_label`**: route DELIVER_SECOND, NV2, và điểm xuất phát `get_return_route()`
- **`get_return_route(factory, target_shelf)`**: quay về đúng hàng kệ (R0/R2/R4) trước pickup tầng 2
- **`_plan_delivery()`**: so sánh route cost = shelf→NM1 + BETWEEN + **return về kệ** (`_return_cost`)
- **`_between_route(a,b)`**: tra `ROUTE_BETWEEN_FACTORIES`; fallback chiều `(b,a)` nếu thiếu key
- **`_retry_or_skip_tier()`**: scan/nâng/**navigate/approach** fail → retry MAX_TIER_RETRIES lần trước khi bỏ tầng
- **`_run_route()` / `_approach_shelf()` / `_retreat_from_shelf()`**: wrapper kiểm tra kết quả navigation & siêu âm

### Xử lý lỗi navigation / tiếp cận

| Tình huống | Hành vi |
|-----------|---------|
| `execute_route()` / `navigate_intersections()` fail (mất line, timeout) | Trả `False`; log lỗi |
| Navigate đến kệ fail | `_retry_or_skip_tier("navigate")` → **NAVIGATE_TO_SHELF** |
| `approach_shelf()` timeout ở PICKUP | `_retry_or_skip_tier("approach")` |
| Navigate DELIVER fail | Log cảnh báo, **vẫn thử hạ** (tiết kiệm thời gian) |
| Navigate RETURN fail | Log cảnh báo, vẫn `_advance_position()` |
| Navigate NV2 fail | Chuyển `DONE` (bỏ NV2) |
| Không có HC-SR04 | `approach_shelf()` / `retreat_from_shelf()` → `False` (không tiến mù) |
| Route rỗng | Log warning, coi là fail |

## Route quay về kho (`get_return_route`)

```python
get_return_route(from_factory, target_shelf)
  = ROUTE_FACTORY_TO_SHELF[factory]     # nhà máy → cột kệ cùng hàng
  + _vertical_on_shelf_column(from, to) # dọc cột kệ nếu khác hàng
```

- `FACTORY_BOARD_ROW`: samsung=R4, hana=R3, amkor=R1, foxconn=R0
- `SHELF_BOARD_ROW`: Kệ3=0→R0, Kệ2=1→R2, Kệ1=2→R4
- **Xuống hàng** (R4→R0): `right → forward N → left`
- **Lên hàng** (R0→R4): `left → forward N → right`
- `target_shelf` = `_next_pickup_shelf()` **trước** `_advance_position()`
- Tầng 2 cùng kệ: sau return robot đã ở đúng hàng → `NAVIGATE_TO_SHELF` tại chỗ

## Motion — điều khiển động cơ & tiếp cận

- **PWM cả 2 chiều**: chân tiến (IN1/IN3) và lùi (IN2/IN4) đều là `PWMOutputDevice`.
  `backward()` / phần lùi của `turn_left/right()` chạy ĐÚNG tốc độ (không full speed) →
  retreat êm, không giật pallet; xoay cân tâm → calibrate `TURN_TIME` chính xác hơn.
- **`approach_shelf()` 2 pha**: nhanh (`APPROACH_FAST_SPEED`) khi > `APPROACH_SLOW_DISTANCE`,
  chậm (`APPROACH_SLOW_SPEED`) khi gần → dừng chính xác ở `APPROACH_DISTANCE` (4cm).
- **Siêu âm median**: `approach_shelf` / `retreat_from_shelf` dùng `get_distance(samples=3)`
  (median) chống nhiễu HC-SR04 → tránh dừng sai gây retry tầng.
- **Polarity QTR-8A**: `LineSensor.read_raw()` chuẩn hoá để **0.0 = trên line** bất kể
  loại cảm biến. Cờ `config.LINE_BLACK_IS_HIGH` (mặc định False) tự đảo tín hiệu tại
  nguồn nếu QTR đọc đen ra giá trị cao → không phải sửa logic phía dưới. Chốt cờ +
  `LINE_THRESHOLD` bằng `python3 -m tools.calibrate_line` (chạy trên Pi).
- **Số giao lộ các `ROUTE_*`**: ✅ đã đối chiếu file in sa bàn chuẩn (docs/SA_BAN.md).

## Test

| Script | Mục đích |
|--------|----------|
| `tests/test_logic.py` | 44 unit test — PC, không GPIO (logic + polarity + phân loại màu + reset + resume) |
| `tests/test_motion.py` | 12 option — motor, line, route, exit start |
| `tests/test_lift.py` | 8 option — nâng/hạ, IR, drop từng càng, NV2 |
| `tests/test_vision.py` | 7 option — camera, HSV, classify_pair |
| `tests/test_smoke.py` | Smoke tích hợp trên sa bàn |

Scenario calibrate quan trọng: **Kệ3 T1 → giao foxconn → samsung → return → Kệ3 T2**

## Lift API (càng độc lập + 2 IR qua SPI)

| Method | Mục đích |
|--------|----------|
| `pickup(level, require_both=True)` | NV1 — nâng 2 càng, cần **cả 2 IR**; NV2 dùng `require_both=False` |
| `dropoff()` | Hạ cả 2 càng; `_verify_released()` xác nhận cả 2 đã rời |
| `dropoff_left()` / `dropoff_right()` | Thả 1 kiện + IR xác nhận bên đó |
| `raise_after_drop(side)` | Sau DROP_FIRST — nâng lại càng vừa thả |
| `stow_forks(side)` | Sau DROP_SECOND — hạ càng còn lại về sàn |
| `go_to_level(n)` | Nâng/hạ cả 2 càng đồng bộ (debug/test) |
| `pallet.read_status()` | `(trái, phải, đọc_ok)` — đọc lỗi → `đọc_ok=False` |
| `pallet.has_left/right/any/both()` | Wrapper trên `read_status()`; trả `None` nếu đọc lỗi |

**main.py:** `_drop_single_side()` gọi dropoff + raise_after_drop; `packages_delivered` chỉ tăng khi IR xác nhận drop thành công.

## Điều hướng (Navigation)

Dùng route commands: `("forward", N)`, `("left",)`, `("right",)`.
`execute_route(route) → bool` — `False` nếu route rỗng hoặc `navigate_intersections()` không tìm đủ giao lộ.
Các route định nghĩa trong `config.py`:
- `ROUTE_START_TO_SHELF_0` — sau exit start (đã chạm line) → forward 1 giao lộ → Kệ 3
- `ROUTE_BETWEEN_SHELVES` — Kệ → kệ tiếp (tiến 2 giao lộ)
- `ROUTE_SHELF_TO_FACTORY[label]` — Kệ → nhà máy (quay phải 2 lần + đi ngang + rẽ nếu cần)
- `ROUTE_FACTORY_TO_SHELF[label]` — Đoạn cơ bản: nhà máy → cột kệ (cùng hàng NM)
- `get_return_route(factory, target_shelf)` — Ghép base + đoạn dọc đúng hàng kệ đích
- `ROUTE_BETWEEN_FACTORIES[(a,b)]` — Giữa 2 nhà máy (12 cặp 2 chiều; `_between_route` fallback)
- `ROUTE_FACTORY_TO_LOOSE[label]` — Nhà máy → Kệ 4 (thụt dưới R0)
- `ROUTE_LOOSE_TO_JOINT` — Kệ 4 → nhà máy liên hợp (R2)

Kệ thẳng hàng nhà máy → Samsung/Foxconn chỉ cần đi ngang (không rẽ lên/xuống).

## Phần cứng

- Raspberry Pi 4 Model B
- 2 DC motor bánh xe (giảm tốc 1:48) + 2 bánh caster
- 2 DC motor cẩu forklift **độc lập** (dây curoa + con lăn) — thả riêng từng càng
- 2 thanh nâng (nâng 2 pallet cùng lúc, thả riêng khi giao 2 NM khác nhau)
- Camera CSI (OV5647) — nhận diện HSV
- QTR-8A dò line 6 mắt (analog) qua MCP3008 SPI (CH0-CH5)
- 2 cảm biến IR pallet (trái/phải) qua MCP3008 SPI (CH6+CH7)
- MCP3008 ADC 10-bit SPI: GPIO 8(CE0), 9(MISO), 10(MOSI), 11(SCLK)
- HC-SR04 siêu âm (GPIO 19 TRIG, 20 ECHO) — tiếp cận kệ chính xác
- Nút khởi động (GPIO 16)
- L298N x2 + XH-M401 hạ áp
- Tổng: **16/16 GPIO** (vừa đúng giới hạn), **4/12 động cơ** — ĐẠT

## Nhận diện kiện hàng

Phân tích màu HSV (OpenCV), không cần model AI.
4 loại hình dán trên khối 40x40x40mm (dán 6 mặt, cố định):
- **Samsung (01)**: chip xanh dương — H=90-130, S>60, V>40
- **Foxconn (02)**: chip vàng đồng — H=15-40, S>60, V>80
- **Amkor (03)**: khối nhôm Al xám — S<40 (saturation thấp)
- **Hana Micron (04)**: QR code + **ngoặc đỏ ở GÓC** — H=0-10 hoặc 160-179
- Nâng 2 kiện → chia ảnh trái/phải → `classify_pair()`
- Camera resolution: 640x480
- **Ưu tiên màu sắc nét hơn Amkor (xám)**: `_classify_by_color` chọn màu chromatic
  (`CHROMATIC_LABELS`) nếu đạt ngưỡng, KỂ CẢ khi Amkor đếm nhiều pixel hơn → nền
  trắng/xám không "ăn" mất Samsung/Hana. ROI cắt giữa theo `ROI_MARGIN` (giảm nếu
  Hana hay bị nhầm Amkor vì ngoặc đỏ nằm ở góc). Giá trị HSV/ROI vẫn cần chốt bằng
  camera thật (test_vision #2/#6).

## Quy tắc quan trọng

- Số giao lộ trong route là ƯỚC LƯỢNG — đội phải đo thực tế trên sa bàn
- `TURN_TIME = 0.6s` cần calibrate trên robot thật
- `LIFT_TIME_SHELF_1/2` cần calibrate riêng cho từng càng
- **3 chế độ chạy** (`main()`):
  - `ROBOT_LOOP=1` (`scripts/practice.sh`) → **luyện tập lặp**: `run_practice_loop()` chạy
    state machine → `_reset_for_new_run()` → chờ nút → lặp; KHÔNG dọn phần cứng giữa lượt;
    Ctrl+C thoát. Ưu tiên trước cả DEBUG_MODE.
  - `DEBUG_MODE=True` (mặc định) → web debug (điều khiển tay).
  - thi đấu: `ROBOT_COMPETE=1` (systemd `start.sh`) ép DEBUG_MODE=False → `run()` chạy 1 trận
    rồi `_shutdown()` thoát hẳn.
- `run()` = 1 trận; `run_practice_loop()` = nhiều lượt. Cả 2 dùng chung `_run_state_machine()`
  (không cleanup) + `_shutdown()` (cleanup 1 lần khi thoát).
- **Khôi phục sau lỗi (thi đấu):** exception giữa trận → `run()` dừng an toàn, thoát **mã 1**
  → systemd `Restart=on-failure` (RestartSec=2, StartLimitIntervalSec=0) khởi động lại → về
  INIT chờ nút. Mốc bắt đầu trận lưu ở `MATCH_STATE_FILE` (`/tmp`) nên lần chạy lại dùng
  **đồng hồ gốc** → chạy nốt thời gian còn lại (`_load_match_resume`/`_persist_match_start`/
  `_clear_match_state`). Xong sạch hoặc dừng tay (signal) → xoá file → thoát mã 0 (không restart).
- Không có network call khi thi đấu
- Vision fail → retry hoặc bỏ tầng, **không** gán label mặc định
- NV1 pickup cần **cả 2 IR**; NV2 chỉ cần **1 IR**
- `packages_delivered` chỉ tăng khi IR xác nhận drop thành công (SPI/ADC lỗi → không đếm)
- `Mcp3008Bus` singleton — Motion + Lift dùng chung lock SPI; `last_read_ok=False` khi SPI/ADC lỗi
- Bám line dùng weighted average analog (`compute_line_error_analog`)
- đọc lỗi khi đọc IR → pickup/drop không coi thành công
- `MAX_TIER_RETRIES`, `MAX_PAIR_SCAN_ATTEMPTS` tinh chỉnh theo điều kiện sa bàn
- Chân ECHO HC-SR04 phải qua cầu phân áp 1kΩ+2kΩ (5V→3.3V)
- Robot phải **≤ 400x400x400mm** khi xuất phát
- Khung robot **không dùng kim loại** (trừ ốc vít)
- Pin **≤ 12V, ≤ 5000mAh**
- Ánh sáng thi đấu **không đảm bảo ổn định** — cần calibrate HSV tại sân
