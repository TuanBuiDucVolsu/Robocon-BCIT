# CLAUDE.md — Context cho Claude Code

## Tổng quan project

Robot tự động **Bảng O2** ("Khát vọng công nghệ"), Giải Robocon Bắc Ninh mở rộng 2026 — Tranh Cúp Foxconn.
Raspberry Pi 4. Phân loại và vận chuyển hàng hoá trên sa bàn 4000x2000mm trong 240 giây.
Thi đấu dự kiến **ngày 08-09/08/2026** tại phường Bắc Giang, tỉnh Bắc Ninh.

## Thể lệ — Quy định quan trọng (Phụ lục 01 + 03)

### Giới hạn robot
- Kích thước xuất phát: **≤ 400x400x400mm** (sau xuất phát có thể mở rộng)
- Bộ điều khiển: **1 vi xử lý duy nhất** (BTC đã bỏ giới hạn số cổng I/O — không còn ≤16 cổng)
- Động cơ: **≤ 12** (kể cả servo, máy nén khí tính 1 động cơ)
- Pin Bảng O2: **≤ 12V**, **≤ 5000mAh**
- Camera AI: **bắt buộc** cho Bảng O2, xử lý **cục bộ** (không Internet)
- Vật liệu: **không dùng kim loại** làm khung (trừ ốc vít, bu lông)
- Robot **tự động hoàn toàn** — sau khi kích hoạt không can thiệp

### Quy định thi đấu
- Thời gian: **240 giây** (4 phút)
- Reset: tối đa **5 lần**, mỗi lần **-10 điểm** (sẵn 50 điểm reset)
- Khi reset: đội viên **tay đặt** robot về ô xuất phát
  → thao tác trên robot là **BẤM NÚT 2 LẦN**: lần 1 = dừng ngay (`_on_reset_button`),
  đặt robot xong rồi lần 2 = chạy tiếp (`_wait_for_placement`). Không có lần 2 thì
  robot đứng yên — trước đây 1 lần bấm là nó tự chạy sau ~4.5s, tiến trong lúc còn
  đang bê. Đồng hồ trận KHÔNG dừng trong lúc chờ.
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

Chỉ vẽ line THẬT SỰ có trên bản in (đã đo bằng quét pixel — xem docs/SA_BAN.md mục 3):

```
      C0 (cột kệ)          C1 (cột giữa)        khu nhà máy
        │                       │                    │
  R4 [Kệ1]─────────────────────┼───────────────[Samsung]
        │                       │
  R3    │                       ├───────────────[Hana Micron]
        │      ( vòng tròn      │
  R2 [Kệ2]····  ROBOCON  ······┼───────────────[Liên hợp]   ← R2 ĐỨT ~560mm
        │       line đứt )      │
  R1    │                       ├───────────────[Amkor]
        │                       │
  R0 [Kệ3]────┈┈┈start┈┈┈──────┼───────────────[Foxconn]    ← R0 đứt ~245mm (ô start)
                                │
                             [Kệ4]   (kho hàng rời — NV2, dưới R0 trên cột C1)
```

- **R1/R3 KHÔNG kéo tới cột kệ** → cột kệ chỉ có 3 giao lộ (R4/R2/R0), Kệ↔Kệ = **1 giao lộ**
- **Line ngang dừng ở mép khu nhà máy** → giữa các nhà máy KHÔNG có line nối dọc,
  đi nhà máy → nhà máy phải vòng về cột C1
- **Kệ 4** nằm trên cột C1, ngay dưới R0 (bên phải ô start, cạnh Foxconn — kho hàng rời NV2)
- Robot xuất phát: ô start trên R0, **quay mặt sang trái (9h)** về Kệ 3
- `exit_start_zone()`: tiến thẳng chạm line R0 → căn giữa ngắn (nếu chạm giao lộ khi căn → dừng căn, **không** đếm giao lộ)
- Sau đó `navigation.plan(START_POSE, "SHELF0")` = tiến 1 giao lộ + advance → Kệ 3
- Thứ tự lấy kệ: Kệ 3 (R0, gần nhất) → Kệ 2 (R2) → Kệ 1 (R4)
- 4 nhà máy xếp DỌC cạnh phải: Samsung(R4) → Hana(R3) → Amkor(R1) → Foxconn(R0)
- Nhà máy liên hợp: giữa sân (R2), chung 2 đội

## Cấu trúc code

```
main.py              — State machine: INIT → NAVIGATE → PICKUP → DELIVER → DROP → lặp 6 lượt → TASK2
navigation.py        — BẢN ĐỒ sa bàn (node giao lộ + cạnh line thật) + Dijkstra sinh
                        route theo (vị trí, hướng). Thay toàn bộ bảng ROUTE_* tĩnh cũ
config.py            — GPIO, HSV color ranges, timing, SHELVES_TASK1, chi phí tìm đường
control/mcp3008_bus.py — Bus SPI dùng chung MCP3008 (lock)
control/motion.py    — Di chuyển, bám line PD analog, siêu âm HC-SR04
control/lift.py      — 2 càng độc lập: PalletSensors (SPI), require_both, _verify_released
vision/vision.py     — Nhận diện kiện hàng, classify_pair(). _classify_frame(): thử
                        ORB (shape_match.ShapeMatcher) trước, rơi về HSV màu nếu ORB
                        chưa có ảnh mẫu hoặc không đủ tự tin (không dùng AI model/deep
                        learning ở cả 2 phương pháp)
vision/shape_match.py — ShapeMatcher: ORB + BFMatcher (Lowe's ratio test) + RANSAC
                        homography (đếm inlier) so với ảnh mẫu vision/templates/*.png.
                        Bền với nền lạ (tường, dây điện...) hơn HSV vì so HÌNH DẠNG,
                        không chỉ màu — xem lịch sử debug HSV bị nền "ăn" ở dưới.
                        Ảnh mẫu tạo bằng `python3 -m tools.capture_templates` (ảnh
                        chụp THẬT, KHÔNG dùng ảnh PDF thể lệ — vector sạch khác nhiều
                        ảnh chụp thật, so khớp kém chính xác hơn).
                        ⚠️ Ảnh mẫu phải là MỘT kiện, cắt sát decal: thi đấu dùng
                        `classify_pair()` = chia đôi khung, so từng nửa 1 kiện. Mẫu
                        chụp cả 2 kiện + kệ + pallet thì phần khớp được lại rơi vào
                        NỀN DÙNG CHUNG (giống hệt ở cả 4 mẫu) → không mẫu nào trội,
                        MARGIN_RATIO chặn lại, ORB im lặng rơi hết về HSV.
                        Kiểm bằng `tests/test_vision.py` option 9 (in inlier từng
                        nửa khung + lý do bị loại)
                        HSV màu (_classify_by_color, dự phòng): điểm có trọng số tâm ROI
                        (_center_weight_map, config.CENTER_WEIGHT_SIGMA) để nền kệ/pallet
                        ở rìa ảnh hưởng ít hơn — TRỪ Hana (ngoặc đỏ ở góc,
                        config.NO_CENTER_WEIGHT_LABELS) vẫn đếm đều như cũ
debug/server.py      — Flask web debug UI (MJPEG stream, line sensor, classify_pair)
scripts/             — install.sh, start.sh, robot.service (systemd auto-start)
docs/                — CAC_BUOC_HOAT_DONG.md, PHAN_CUNG.md, ...
tests/               — test_motion/lift/vision/smoke + test_logic (45 unit test)
```

## State machine (luồng chính)

```
START (exit_start_zone) → DETECT_SIDE (tự dò nửa sân, ~2-4s)
NAVIGATE_TO_SHELF → PICKUP_PAIR (approach + classify_pair + pickup + retreat)
  → DELIVER_FIRST → DROP_FIRST
  → [DELIVER_SECOND → DROP_SECOND]  (bỏ qua nếu cùng nhà máy)
  → RETURN_TO_WAREHOUSE
  → lặp 6 lượt → TASK2 → DONE
```

- **Không còn state SCAN_PAIR riêng** — quét camera nằm trong PICKUP_PAIR, sau `_approach_shelf()`
- **`self.pose = (vị trí, hướng)`** — nguồn sự thật duy nhất về robot đang ở đâu. Mọi
  state gọi `_goto(terminal)`; route được TÍNH ra, không tra bảng.
- **`_plan_delivery()`**: so sánh `_delivery_cost(a,b)` = pose→NM1 + NM1→NM2 + NM2→kệ kế tiếp
- **`_retry_or_skip_tier()`**: scan/nâng/**navigate/approach** fail → retry MAX_TIER_RETRIES lần trước khi bỏ tầng
- **`_goto()` / `_approach_shelf()` / `_approach_for_drop()` / `_retreat_from_shelf()`**:
  wrapper kiểm tra kết quả navigation & siêu âm

### Xử lý lỗi navigation / tiếp cận

| Tình huống | Hành vi |
|-----------|---------|
| `execute_route()` / `navigate_intersections()` fail (mất line, timeout) | Trả `False`; log lỗi |
| `exit_start_zone()` fail (START) | Retry `MAX_TIER_RETRIES + 1` lần tại chỗ; hết retry → `DONE` |
| Dò nửa sân fail (không tới được giao lộ / cảm biến lỗi) | Giữ `config.BOARD_MIRRORED`, chạy tiếp |
| Navigate đến kệ fail | `_retry_or_skip_tier("navigate")` → **NAVIGATE_TO_SHELF** |
| `approach_shelf()` timeout ở PICKUP | `_retry_or_skip_tier("approach")` |
| Navigate DELIVER fail | Log ERROR, cập nhật pose = đích, **vẫn thử hạ** (tiết kiệm thời gian) |
| Tiếp cận điểm THẢ fail | `_approach_for_drop()` thử lại 1 lần rồi mới đành thả tại chỗ |
| Navigate RETURN fail | Log ERROR, vẫn `_advance_position()` |
| Navigate NV2 fail | Chuyển `DONE` (bỏ NV2) |
| Không có HC-SR04 | `approach_shelf()` / `retreat_from_shelf()` → `False` (không tiến mù) |
| Siêu âm mất echo khi tiếp cận | Dừng sau `APPROACH_BLIND_TIMEOUT` (không chạy mù ra khỏi sa bàn) |
| Route rỗng | **Thành công** — robot đã ở đích (vd lấy tầng 2 cùng kệ) |

## Điều hướng (`navigation.py`)

Bản đồ khai báo MỘT chỗ; route tính bằng Dijkstra trên trạng thái `(vị trí, hướng)`.

```python
route, pose_moi = navigation.plan(robot.pose, "F_samsung")
cost            = navigation.route_cost(pose, goal)     # so sánh thứ tự giao
```

- **Node giao lộ**: `C0R0/C0R2/C0R4` (cột kệ — CHỈ 3 giao lộ vì R1/R3 không kéo tới
  cột kệ) và `C1R0..C1R4` (cột giữa — đủ 5 hàng).
- **Điểm cuối (terminal)**: kệ, khu nhà máy, Kệ 4 — là CUỐI đường line, không phải
  giao lộ. Vào bằng lệnh `("advance",)` (bám line tới hết line), ra bằng `forward 1`.
- **Cạnh bị cấm**: `C0R2 ↔ C1R2` — hàng R2 đứt ~560mm ở vòng tròn ROBOCON.
- **Cạnh bị phạt**: `C0R0 ↔ C1R0` (+`EDGE_COST_START_GAP`) — đứt ~245mm ở ô xuất phát.
- Xem/kiểm tra: `python3 -m tools.show_routes`; test mô phỏng trong `tests/test_logic.py`.

### ⚠️ Nửa sân — THỨ TỰ NHÀ MÁY BỊ ĐẢO (`config.FACTORY_AT_START_ROW`)

Sa bàn chia đôi bởi **bức tường** giữa sân (`docs/Sa bàn đầy đủ.png`). Hai nửa là bản
**quay 180°** của nhau (mascot đội đỏ vẽ lộn ngược) → **chiều trái/phải GIỐNG NHAU**.

Nhưng cụm nhà máy in trên **tường** thì không quay theo — hai đội nhìn chung một tấm
panel. Nên trong hệ quy chiếu của chính robot, **thứ tự nhà máy theo hàng bị ĐẢO**:

| Trong hệ quy chiếu robot | Đội góc dưới-trái | Đội góc trên-phải |
|---|---|---|
| `FACTORY_AT_START_ROW` | `"foxconn"` | `"samsung"` |
| Cùng hàng ô xuất phát (R0) | Foxconn | Samsung |
| R1 | Amkor | Hana Micron |
| R2 (liên hợp) | Liên hợp | Liên hợp |
| R3 | Hana Micron | Amkor |
| R4 (xa nhất) | Samsung | Foxconn |

**Robot KHÔNG tự dò được cái này** — qua cảm biến line hai nửa giống hệt nhau; nhà máy
nào ở hàng nào chỉ người mới đọc được. **Đặt sai = giao Samsung vào Foxconn, IR vẫn
báo thả OK nên log không hề báo lỗi — mất sạch điểm.** Đây là thao tác duy nhất trong
hệ thống mà sai thì không có tín hiệu báo lỗi nào.

**→ Chọn bằng CÔNG TẮC GẠT trên GPIO 12** (`control/board_switch.py`), không sửa file:

| | |
|---|---|
| Đấu dây | chân giữa → GND, một cực → GPIO 12, cực kia để trống |
| Nối GND (LOW) | `config.BOARD_SIDE_SWITCH_CLOSED` (mặc định `"samsung"`) |
| Thả nổi (HIGH) | nửa còn lại (`"foxconn"`) |
| Đọc lúc nào | khi khởi tạo, trước khi chờ nút, và **ngay sau khi bấm nút** (chốt) |
| Không đọc được | rơi về `config.FACTORY_AT_START_ROW`, log ghi rõ nguồn |
| Kiểm đấu dây + nhãn | `python3 -m tools.check_board_side` (gạt qua lại, giá trị đổi ngay) |
| Kiểm trước khi vào sân | web debug `/api/board_side` |

Lý do dùng công tắc thay vì hằng số: trạng thái **nhìn thấy được bằng mắt, không cần
cấp nguồn**. Dán nhãn 2 bên, bốc thăm xong gạt một cái, cả đội liếc là kiểm chéo được.

`main._apply_board_side()` in một khối cảnh báo 6 dòng mỗi lần đọc — không thể bỏ sót
trong log. `navigation.set_factory_order(label)` đổi được giữa lúc chạy.

### Chiều trái/phải — robot tự dò (state `DETECT_SIDE`)

Theo bản in thì cả 2 nửa cùng chiều (`BOARD_MIRRORED=False`) vì phép quay 180° bảo
toàn tay thuận. Robot vẫn tự kiểm chứng để phòng bản in sai. Đầu trận, sau
`exit_start_zone()`, state
`DETECT_SIDE` đi tới giao lộ Kệ 3 (`navigation.PROBE_NODE`) rồi
`Motion.probe_side_branch("right")`: xoay phải 90°, tiến `PROBE_TRAVEL_TIME` giây ra
khỏi vùng 2 line cắt nhau, đọc cảm biến, lùi về và xoay lại.

| Kết quả dò | Nghĩa | Hành động |
|---|---|---|
| **CÓ** nhánh line bên phải | chiều chuẩn (đúng bản in) | giữ bản đồ |
| **KHÔNG** có | chiều ngược | `set_mirrored(True)`, nạp lại bản đồ |
| Cảm biến lỗi (`None`) | không kết luận | giữ `config.BOARD_MIRRORED` làm dự phòng |

Việc dò này **chỉ kiểm chiều trái/phải**, KHÔNG biết được thứ tự nhà máy.

Dò được vì đường line dọc cột kệ **chỉ chạy về một phía** từ Kệ 3 (lên R2/R4), phía
kia là mép sa bàn. Tốn ~2-4s đầu trận. Phải tiến ra khỏi giao lộ mới đọc được: ngay
tại điểm giao, line cắt ngang nằm dọc thanh cảm biến nên xoay kiểu gì cũng thấy đen.

- Dò **1 lần/trận** (`Robot._side_detected`): sau reset, state machine quay lại
  START → DETECT_SIDE nhưng sa bàn không đổi, dò lại chỉ tốn thêm 2-4s mỗi lần để ra
  đúng kết quả cũ. Dò lỗi cảm biến (`None`) thì KHÔNG chốt — lần reset sau vẫn thử lại.
- `config.BOARD_AUTO_DETECT` — tắt thì dùng thẳng `config.BOARD_MIRRORED`
- `navigation.set_board(mirrored=…, factory_at_start_row=…)` dựng lại CHÍNH BẢN ĐỒ,
  không đảo từng lệnh → tìm đường, `apply()`, log hướng tự đúng theo
- `main.py` in `navigation.board_summary()` lúc khởi động và sau khi dò
- Kiểm tra tay: `tests/test_motion.py` option **13**

> ⚠️ **Không viết route bằng tay nữa.** Bảng `ROUTE_*` cũ trong config đã bị xoá: mỗi
> bảng ngầm giả định một hướng robot khác nhau và ngầm giả định robot luôn xuất phát
> từ đúng một kệ → 9/12 tuyến kệ→nhà máy và toàn bộ tuyến quay về kho đi sai chỗ.
> Sai bản đồ thì sửa `NODES`/`EDGES`/`TERMINALS`, không sửa route lẻ.

## Motion — điều khiển động cơ & tiếp cận

- **PWM cả 2 chiều**: chân tiến (IN1/IN3) và lùi (IN2/IN4) đều là `PWMOutputDevice`.
  `backward()` / phần lùi của `turn_left/right()` chạy ĐÚNG tốc độ (không full speed) →
  retreat êm, không giật pallet; xoay cân tâm → calibrate `TURN_TIME` chính xác hơn.
- **`approach_shelf()` 2 pha**: nhanh (`APPROACH_FAST_SPEED`) khi > `APPROACH_SLOW_DISTANCE`,
  chậm (`APPROACH_SLOW_SPEED`) khi gần → dừng chính xác ở `APPROACH_DISTANCE` (4cm).
  **Chặn chạy mù**: nếu sau `APPROACH_BLIND_TIMEOUT` chưa lần nào thấy vật trong
  `APPROACH_DETECT_DISTANCE` → dừng + trả `False` (trước đây chạy hết 5s ở 60% tốc độ
  = lao ra khỏi sa bàn / sang sân đối phương khi mất echo).
- **`advance_to_end()`**: bám line tới HẾT line — dùng cho đoạn cuối vào kệ / khu nhà
  máy / Kệ 4 (những chỗ đó không phải giao lộ nên không đếm bằng `forward` được).
- **Vượt khoảng đứt**: mất line thì trôi thẳng `LINE_GAP_COAST_TIME` giây rồi mới quét
  tìm lại — sa bàn có khoảng đứt thật 245mm ở ô xuất phát.
- **Siêu âm median**: `approach_shelf` / `retreat_from_shelf` dùng `get_distance(samples=3)`
  (median) chống nhiễu HC-SR04 → tránh dừng sai gây retry tầng.
- **Polarity QTR-8A**: `LineSensor.read_raw()` chuẩn hoá để **0.0 = trên line** bất kể
  loại cảm biến. Cờ `config.LINE_BLACK_IS_HIGH` (hiện đặt True) tự đảo tín hiệu tại
  nguồn nếu QTR đọc đen ra giá trị cao → không phải sửa logic phía dưới. Chốt cờ +
  `LINE_THRESHOLD` bằng `python3 -m tools.calibrate_line` (chạy trên Pi).
- **Bù PWM**: `follow_line()` dùng ĐÚNG cùng `PWM_COMPENSATION`/`PWM_COMPENSATION_LEFT`
  như `forward()` — nếu lệch nhau thì đi thẳng và bám line sẽ khác nhau sau calibrate.
- **Bản đồ line**: đã đo lại bằng quét pixel file in chuẩn (docs/SA_BAN.md mục 3).
- **`back_to_intersection()` — lùi ra khỏi kệ**: rút khỏi điểm cuối bằng cách LÙI
  thay vì xoay 180° rồi tiến. Bỏ được **28/70 lần xoay** mỗi trận (~32s) — xoay là
  chi phí cố định lớn nhất. Bộ tìm đường tự chọn: chặng kế đi vuông góc thì lùi,
  đi thẳng tiếp thì vẫn quay đầu (`config.EDGE_COST_REVERSE` để cân).
  ⚠️ KHÔNG lùi ra khỏi ô xuất phát được (`navigation.NO_REVERSE_TERMINALS`) — chỗ đó
  là khoảng ĐỨT 245mm, không có line để bám.
  ⚠️ **Khi lùi phải ĐẢO DẤU hiệu chỉnh PD.** Thanh cảm biến ở đầu xe, lùi thì thành
  đuôi; ma trận trạng thái `(y, θ)` có `det = v·k` nên `k` phải cùng dấu vận tốc.
  Giữ nguyên dấu = robot ngoáy đuôi tăng dần rồi văng khỏi line. Kiểm trên robot
  thật bằng `tests/test_motion.py` option **15** TRƯỚC khi tin dùng.

## Test

| Script | Mục đích |
|--------|----------|
| `tests/test_logic.py` | 100 unit test — PC, không GPIO (bản đồ + mô phỏng route tới đúng chỗ + polarity + phân loại màu + reset + resume) |
| `tests/test_units.py` | 43 unit test — PC (bám line, lift, ShapeMatcher, classify_pair) |
| `tests/test_match_sim.py` | Mô phỏng TRỌN trận với phần cứng giả lập: 12/12 kiện, lỗi phần cứng, mất line giữa route — kiểm vị trí main.py tin tưởng có khớp vị trí thật không |
| `tests/test_tools.py` | 17 unit test — PC (regex của `measure_phases` phải khớp chuỗi log CÓ THẬT trong source + round-trip; `dry_run` chạy hết được và mọi bước đi đều có line thật) |
| `tools/show_routes.py` | In toàn bộ route sinh ra để đối chiếu tay trên sa bàn |
| `tools/dry_run.py` | **Chạy khô trọn trận** — in từng bước robot sẽ đi kèm mốc giây. Cầm đi bộ trên sa bàn để đối chiếu tay |
| `tools/measure_phases.py` | Đọc `robot_log.txt` → 6 tham số cho `estimate_time` + dự báo điểm. Chạy sau mỗi lượt `practice.sh` |
| `tools/estimate_time.py` | "Worst case giao được mấy kiện trong 240s" — nạp số đo từ `measure_phases` |
| `tests/test_motion.py` | 12 option (1-12) + `d` chẩn đoán — motor, line, route, exit start |
| `tests/test_lift.py` | 8 option (1-8) + `a-d` calibrate/độc lập — nâng/hạ, IR, drop từng càng, NV2 |
| `tests/test_vision.py` | 7 option — camera, HSV, classify_pair |
| `tests/test_smoke.py` | Smoke tích hợp trên sa bàn |

Scenario calibrate quan trọng: **Kệ3 T1 → giao foxconn → samsung → return → Kệ3 T2**

### Ngân sách 240 giây — đo, đừng đoán

BTC xếp kiện NGẪU NHIÊN mỗi trận và chi phí giữa kịch bản đẹp nhất/xấu nhất chênh
hơn 2 lần. Chạy thử trúng kịch bản nhẹ rồi kết luận "kịp giờ" là tự lừa mình.

```
bash scripts/practice.sh          # 1 lượt thật trên sa bàn
python3 -m tools.measure_phases   # log → 6 tham số + dự báo cả 2 biên
```

`measure_phases` ghép mốc thời gian trong `robot_log.txt` (chính xác hơn đồng hồ bấm
tay), lấy **trung vị** và **loại** các chặng chạy hỏng, rồi đếm riêng phần phụ trội
(retry, mất line, reset) — thứ mà `estimate_time` KHÔNG mô hình hoá, nên trận thật
luôn chậm hơn dự báo đúng bằng phần đó.

Đọc kết quả theo **điểm**, không theo "kịp/không kịp": hết giờ vẫn giữ điểm kiện đã
giao, nên câu hỏi đúng là *worst case được bao nhiêu điểm*. Chặng ăn nhiều giây nhất
là **chạy thẳng (~35%)** → ưu tiên tăng `SPEED_DEFAULT` (đang để 50 mức bring-up)
theo quy trình ở `config.py`, rồi mới tới `LIFT_TIME_SHELF_2`.

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

## Lệnh route

`execute_route(route) → bool`. Lệnh hợp lệ:

| Lệnh | Ý nghĩa |
|------|---------|
| `("forward", N)` | Bám line qua **N giao lộ** (`navigate_intersections`) |
| `("left",)` / `("right",)` | Xoay 90° tại chỗ (`TURN_TIME`) |
| `("back", N)` | **LÙI** qua N giao lộ, vẫn bám line, KHÔNG quay đầu — rút khỏi kệ/nhà máy |
| `("advance",)` | Bám line tới **HẾT line** — vào kệ / khu nhà máy / Kệ 4 |
| route rỗng `[]` | Đã ở đích → trả `True`, không chạy motor |

Route do `navigation.plan(pose, goal)` sinh — xem mục "Điều hướng (`navigation.py`)".

## Phần cứng

- Raspberry Pi 4 Model B
- 2 DC motor bánh xe **JGA25-370 12V/170rpm có encoder** + bánh 65mm + 2 bánh caster
  (170rpm không tải ≈ 578mm/s; qua L298N sụt ~2V + có tải → thực tế thấp hơn)
- 2 DC motor cẩu forklift **độc lập** (dây curoa + con lăn) — thả riêng từng càng
- 2 thanh nâng (nâng 2 pallet cùng lúc, thả riêng khi giao 2 NM khác nhau)
- Camera CSI (OV5647) — nhận diện HSV
- QTR-8A dò line 6 mắt (analog) qua MCP3008 SPI (CH0-CH5)
- 2 cảm biến IR pallet (trái/phải) qua MCP3008 SPI (CH6+CH7)
- MCP3008 ADC 10-bit SPI: GPIO 8(CE0), 9(MISO), 10(MOSI), 11(SCLK)
- HC-SR04 siêu âm (GPIO 19 TRIG, 20 ECHO) — tiếp cận kệ chính xác
- 2 encoder tốc độ bánh xe (JGA25-370 tích hợp, kênh C1 → GPIO 26 trái / 21 phải) — đo lệch
  tốc độ 2 bánh, dùng cho `test_motion.py` option e/f (không tham gia bám line
  thời gian thực, vẫn dùng `PWM_COMPENSATION` open-loop)
- Nút khởi động (GPIO 16)
- Công tắc gạt chọn nửa sân (GPIO 12) — quyết định thứ tự nhà máy, dán nhãn 2 bên
- L298N x2 + XH-M401 hạ áp
- Tổng: **19 GPIO đang dùng** (không còn bị giới hạn số cổng — có thể mở rộng thêm), **4/12 động cơ** — ĐẠT

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

- Bản đồ line trong `navigation.py` đo từ file in chuẩn — vẫn phải **đếm lại tay trên
  sa bàn thật** trước khi chạy (in bằng `python3 -m tools.show_routes`)
- `TURN_TIME = 0.5s` (fast-profile, CHƯA calibrate thật) cần đo lại trên robot thật
- `LIFT_TIME_SHELF_1/2` cần calibrate riêng cho từng càng; `LIFT_*_EXTRA` là bù theo
  **vị trí tuyệt đối** (thời gian từ sàn lên tầng n), không phải bù mỗi lần chạy
- `LIFT_HOME_DURATION` phải **> `LIFT_TIME_SHELF_2`**, nếu không home không chạm đáy
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
- Ánh sáng thi đấu **không đảm bảo ổn định**, nền xung quanh (kệ/pallet/tường/vật
  dụng khác) dễ gây nhận nhầm nếu chỉ dựa vào màu — nhận diện CHÍNH đã chuyển sang
  ORB (so hình dạng, bền với nền lạ hơn); chụp ảnh mẫu thật tại sân trước khi thi
  bằng `python3 -m tools.capture_templates`. HSV (`tools.calibrate_vision`) vẫn cần
  calibrate làm dự phòng khi ORB không đủ tự tin.
