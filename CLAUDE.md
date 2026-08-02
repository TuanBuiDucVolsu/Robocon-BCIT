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
- `exit_start_zone()`: tiến MÙ tới khi qua hết vùng in → tiến tiếp tới khi chạm line R0
  → căn giữa ngắn (nếu chạm giao lộ khi căn → dừng căn, **không** đếm giao lộ).
  ⚠️ Cửa sổ mù là BẮT BUỘC: ô xuất phát in hình **mascot mặt đen**, robot ngồi ngay
  trên đó (14/23 px đen) nên không có bước mù là nó "chạm line" ở mẫu đầu tiên rồi
  căn giữa trên mặt con mascot. Cửa sổ phải kết thúc trong **10.2→51.2cm** (hết
  mascot → trước giao lộ C0R0). Số đo: `docs/SA_BAN.md` mục 3c.
  Điểm kết thúc bám theo **hình in**, không theo đồng hồ: thấy đen rồi thấy SẠCH =
  vừa ra khỏi mascot (sau nó là 11.7cm sạch). Nhờ vậy đúng ở mọi tốc độ và mọi chỗ
  đặt trong ô 400x400mm. `EXIT_START_BLIND_TIME = 1.5` chỉ là **chặn trên**, dùng
  khi robot đặt ở chỗ không có hình in nào dưới cảm biến — an toàn tới 34cm/s.
  **cm/s thật CHƯA ĐO trên robot.**
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
vision/vision.py     — Nhận diện kiện hàng, classify_pair(LEVEL). _classify_frame():
                        thử ORB (shape_match.ShapeMatcher) trước, rơi về HSV màu nếu
                        ORB chưa có ảnh mẫu hoặc không đủ tự tin (không dùng AI model/
                        deep learning ở cả 2 phương pháp).
                        ⚠️ VÙNG QUÉT DỊCH THEO TẦNG (config.ROI_Y_CENTER) và bộ ảnh
                        mẫu chọn theo (tầng, ô) — main.py truyền current_tier, còn
                        classify_pair tự truyền "left"/"right". Xem mục "Nhận diện
                        kiện hàng" ở dưới, ĐỌC TRƯỚC KHI SỬA.
vision/shape_match.py — ShapeMatcher: ORB + BFMatcher (Lowe's ratio test) + RANSAC
                        homography (đếm inlier) so với ảnh mẫu, chia theo (tầng, ô):
                        vision/templates/t{1,2}_{left,right}/*.png — 16 tấm.
                        Nạp xong CHUẨN HOÁ kích thước trong từng bộ (lý do ở dưới).
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
tests/               — test_motion/lift/vision/smoke + test_logic/units/match_sim/tools
                        (219 unit test). config_editor.save_config: ghi hằng số vào
                        config.py cho 2 menu calibrate, TỪ CHỐI khi regex không khớp
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
  giao lộ. Vào bằng lệnh `("advance",)`, ra bằng `forward 1`. **`advance` KHÔNG bò tới
  sát chân kệ**: ở kệ/nhà máy thì siêu âm dừng nó trước, tại `APPROACH_SLOW_DISTANCE`
  (20cm), rồi `approach_shelf()` canh nốt về `APPROACH_DISTANCE` (11.9cm). "Hết line"
  chỉ là nhánh dự phòng khi không có gì để siêu âm nhìn.
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

### Chiều trái/phải — state `DETECT_SIDE` ⚠️ ĐANG TẮT (`BOARD_AUTO_DETECT = False`)

**Bước tự dò đã tắt (178c4e8). Đừng bật lại nếu chưa đọc hết mục này.**

1. **THỪA.** Công tắc gạt đã cho robot biết nó ở NỬA NÀO — đó cũng là thông tin duy
   nhất bước dò moi ra được. Mà chiều trái/phải KHÔNG đổi theo nửa (cả hai đều
   `False`), nên bước dò đang đo một HẰNG SỐ, không phải biến.
2. **NÓ LÀM HỎNG LỆNH NGAY SAU.** `probe_side_branch()` chạy hở hoàn toàn rồi tin
   mình về đúng chỗ cũ, mà `TURN_TIME` mới xác nhận chiều TRÁI và bù PWM chiều LÙI
   thì chưa calibrate. Đo trên robot: smoke option 1 dừng ngay tại giao lộ vì
   `advance_to_end()` kế đó không tìm thấy line.
3. **ĐOÁN SAI THÌ MẤT CẢ TRẬN.** Dò xong nó gọi `set_mirrored()` — báo nhầm GƯƠNG là
   lật toàn bộ bản đồ, mọi lệnh xoay đảo chiều tới hết trận. Đã thấy nó lúc báo
   CHUẨN lúc báo GƯƠNG.
4. Tốn 2-4s đầu trận.

Thứ nó bảo vệ chỉ là giả thuyết "bản in sai chiều" — kiểm bằng mắt 5 giây trên sân.
Route giờ đi thẳng: `START → SHELF0` = `tiến 1 giao lộ → vào điểm cuối`.

Cơ chế vẫn còn trong code và bật lại được; `tests/test_match_sim.py::TestAutoDetectSide`
tự ép cờ `True` trong phạm vi test để vẫn kiểm được nó.

Mô tả cơ chế (khi bật): theo bản in thì cả 2 nửa cùng chiều (`BOARD_MIRRORED=False`)
vì phép quay 180° bảo toàn tay thuận. Robot tự kiểm chứng để phòng bản in sai. Sau
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
- `config.BOARD_AUTO_DETECT` — **hiện `False`**; tắt thì dùng thẳng `config.BOARD_MIRRORED`
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
  chậm (`APPROACH_SLOW_SPEED`) khi gần → dừng ở `APPROACH_DISTANCE`.
  ⚠️ **PHỤ THUỘC CHẤT LƯỢNG BÁM LINE nhiều hơn tưởng.** Robot đứng LỆCH LINE thì
  chùm siêu âm dội vào mặt khác và đọc sai — đã gặp thật: robot húc kệ vì được đặt
  hơi lệch, đặt lại đúng line thì chạy sạch. Lúc thi đấu robot tới kệ bằng bám line,
  nên nếu bám line để nó dừng hơi lệch thì cùng lỗi đó xảy ra giữa trận, mà lúc ấy
  không có tay ai đỡ.
- **`_forward_guided()` — tiến sát kệ CÓ LÁI, không chạy mù** (6fc3e39).
  `approach_shelf()` và `creep_until()` trước đây gọi `forward()` suốt quãng ~10cm
  cuối. Robot không đi thẳng tuyệt đối nên nó lệch dần → càng vào khe pallet lệch,
  không luồn hết → **IR không báo có hàng** → cả chu trình bốc hàng hỏng. Đây là mắt
  xích ĐẦU của chuỗi đó; hạ `INSERT_MIN_DISTANCE` hay tăng `LIFT_PICKUP_RAISE_TIME`
  chỉ là chữa mắt xích CUỐI.
  Còn thấy line thì `follow_line()`, mất line thì rơi về `forward()` — đúng hành vi
  cũ, nên an toàn kể cả khi vạch line không kéo tới tận chân kệ. **Đo trên bản in
  thì nó có kéo tới:** vạch dài **35.4cm** từ giao lộ C0 tới sát chân kệ (hở 1mm),
  giống hệt ở cả 3 kệ — robot chờ ở 11.9cm và bò tới 2.2cm nên nằm gọn giữa vạch
  suốt cả quãng. Số đo + cách đo lại: `docs/SA_BAN.md` mục 3b. Cờ giao lộ của
  `follow_line()` bị **bỏ qua** ở đây: sát kệ thì nền kệ có thể làm mọi mắt thấy đen,
  mà ta chỉ cần phần LÁI chứ không đếm giao lộ.
  ⚠️ **CHƯA XÁC NHẬN TRÊN ROBOT** — mới có unit test. Chạy `test_smoke` option 2.
  ⚠️ `APPROACH_SLOW_SPEED` nằm sát VÙNG CHẾT của JGA25-370 qua L298N — dải dùng được
  rất hẹp: 25 thì robot chỉ nhích từng tí (chậm hơn ngưỡng 0.83cm/s của cơ chế chống
  húc kệ → bị dừng oan giữa đường và báo nhầm "càng đã chạm kệ"), 40 thì vọt quá đà.
  **32 đã xác nhận chạy sạch trên robot** (test_motion #9). Nếu thay motor, đổi pin
  hay đổi mặt sàn thì đo lại — đây là số bám vào phần cứng cụ thể, không phải hằng
  số vật lý.
  **Chặn chạy mù**: nếu sau `APPROACH_BLIND_TIMEOUT` chưa lần nào thấy vật trong
  `APPROACH_DETECT_DISTANCE` → dừng + trả `False` (trước đây chạy hết 5s ở 60% tốc độ
  = lao ra khỏi sa bàn / sang sân đối phương khi mất echo).
- **Dừng có giảm tốc (`Motion.stop_gently`)**: `stop()` đặt cả 4 chân PWM về 0, mà
  EN của L298N nối cứng mức cao nên hai đầu motor cùng bị kéo xuống đất — đó là
  **PHANH ĐỘNG**, không phải thả trôi. Phanh gấp ngay trước kệ sinh mô-men giật,
  hai bánh không phanh giống hệt nhau, cộng 2 bánh caster tự xoay → robot **lệch
  vài độ tại chỗ**. Vài độ đó đủ làm càng không luồn thẳng vào khe pallet, mà bước
  đó không còn line để tự sửa. Dùng ở 3 chỗ tư thế quyết định bước sau: cuối
  `approach_shelf()`, cuối `creep_until()` (càng đang TRONG khe pallet — phanh gấp
  là giật cả pallet), cuối `advance_to_end()`. Kèm `STOP_SETTLE_TIME` đứng yên một
  nhịp cho khung xe hết chòng chành.
  ⚠️ Giảm dần thì robot **trôi thêm** so với phanh gấp. Đo lại `APPROACH_DISTANCE`;
  nếu dừng sát kệ hơn trước thì **hạ `STOP_RAMP_TIME`**, đừng vội đổi
  `APPROACH_DISTANCE` (khoảng cách đó còn ràng buộc với vị trí khe pallet).
  Đặt `STOP_RAMP_TIME = 0` là quay về đúng hành vi cũ.
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
  `turn_left/right()` cũng lấy hệ số theo ĐÚNG CHIỀU từng bánh (`*_LEFT_REV` cho bánh
  trái lùi…) — `TURN_TIME` chỉ có MỘT hằng số cho cả 2 chiều nên hệ số lệch là một
  chiều xoay quá, chiều kia thiếu, không cách nào chỉnh cho khớp cả hai.
- **Kẹp tốc độ giữ ĐỘ CHÊNH 2 bánh** (`Motion._fit_to_range`): độ chênh mới tạo ra
  góc lái, nên khi `base + correction > 100` phải trượt CẢ HAI bánh xuống, không kẹp
  riêng. Kẹp riêng ở `SPEED_DEFAULT=80` làm mất 25% lực lái đúng lúc sai số lớn nhất
  ((120,40)→(100,40) chênh 60 thay vì 80). Ở tốc độ 50 chưa vượt dải nên **lỗi này
  chỉ hiện ra khi TĂNG tốc độ** — đúng đòn tối ưu số 1 của ngân sách 240s.
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
| `tests/test_logic.py` | 118 unit test — **an toàn chạy cả trên Pi** (tự ép pin factory giả, xem dưới): bản đồ + mô phỏng route tới đúng chỗ + polarity + phân loại màu + reset + resume |
| `tests/test_units.py` | 82 unit test — **an toàn chạy cả trên Pi**: bám line, lift, ShapeMatcher, classify_pair |
| `tests/test_match_sim.py` | Mô phỏng TRỌN trận với phần cứng giả lập: **13/13 kiện** (12 NV1 + hàng rời NV2), reset giữa trận, lỗi phần cứng, mất line giữa route — kiểm vị trí main.py tin tưởng có khớp vị trí thật không |
| `tests/test_tools.py` | 19 unit test — PC (regex của `measure_phases` phải khớp chuỗi log CÓ THẬT trong source + round-trip; `dry_run` chạy hết được và mọi bước đi đều có line thật) |
| `tools/show_routes.py` | In toàn bộ route sinh ra để đối chiếu tay trên sa bàn |
| `tools/dry_run.py` | **Chạy khô trọn trận** — in từng bước robot sẽ đi kèm mốc giây. Cầm đi bộ trên sa bàn để đối chiếu tay |
| `tools/measure_phases.py` | Đọc `robot_log.txt` → 6 tham số cho `estimate_time` + dự báo điểm. Chạy sau mỗi lượt `practice.sh` |
| `tools/estimate_time.py` | "Worst case giao được mấy kiện trong 240s" — nạp số đo từ `measure_phases` |
| `tools/sim_ui.py` | Xuất trang HTML **mô phỏng robot chạy** — phát lại các bước state machine thật sinh ra, đổi tốc độ ngay trên trang |
| `tests/NGHIEM_THU.md` | **Tiêu chí ĐẠT/CHƯA ĐẠT bằng SỐ** cho vòng A(số nền)→B(cơ cấu)→C(ghép nối)→D(ngân sách). Mọi bước phải lặp **3 lần** mới tính đạt. Có bảng ghi số |
| `tests/LO_TRINH_TEST.md` | **Lộ trình test đánh số theo thứ tự phải làm** — bắt đầu từ đây |
| `tests/DIEN_TAP.md` | 9 bài diễn tập sát thi đấu: ngân sách 240s, kiện xấu nhất, reset, pin, ánh sáng |
| `tests/test_motion.py` | 17 option (1-17) + `d/e/f` — motor, line, route, dò nửa sân, lùi, giới hạn tốc độ |
| `tests/test_lift.py` | Menu LẶP, **home đầu phiên + sau mỗi option** (không limit switch → `_current_level` chỉ đúng sau khi home). Option **1 = diễn tập trọn 1 lượt giao** như main.py; còn lại: nâng/hạ, IR, home, từng càng riêng, so 2 càng, calibrate |
| `tests/test_vision.py` | 9 option + `l` — camera, BGR, ORB, HSV, classify_pair, ánh xạ trái/phải |
| `tests/test_smoke.py` | Smoke tích hợp trên sa bàn. **HỎI nửa sân đầu phiên** (`_ask_board_side`) — đặt sai thứ tự nhà máy là lỗi KHÔNG có tín hiệu báo |

### ⚠️ Script nào chạm phần cứng THẬT

Chạy nhầm trên Pi là **robot cử động thật** — kê bánh khỏi mặt bàn hoặc ngắt nguồn
động lực L298N trước khi chạy nhóm dưới.

| Chạy được ở đâu | Script |
|---|---|
| **PC và Pi — không chạm GPIO** | `test_logic`, `test_units`, `test_tools`, `test_match_sim`, `tools/show_routes`, `tools/dry_run`, `tools/measure_phases`, `tools/estimate_time`, `tools/sim_ui` |
| **CHỈ trên Pi — điều khiển thật** | `test_motion` (chạy bánh), `test_lift` (nâng càng), `test_vision` (camera), `test_smoke`, `tools/measure_pickup` (nâng càng, bánh KHÔNG chạy), `tools/calibrate_line`, `tools/capture_templates`, `tools/check_board_side` |

`test_units.py` / `test_logic.py` **tự ép pin factory giả** ngay đầu file, TRƯỚC khi
import `control.*`:

```python
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
os.environ.setdefault("GPIOZERO_MOCK_PIN_CLASS", "mockpwmpin")
```

Không có 2 dòng này thì chạy trên Pi là **bánh xe quay thật**: `TestFollowLine._drive()`
chỉ giả lập ĐẦU VÀO cảm biến (`read_line_sensor_raw`), rồi gọi `follow_line()` thật để
đọc ngược duty cycle 4 chân motor — chân ra là `PWMOutputDevice` thật. Mà `follow_line()`
không dừng motor sau khi chạy, nên bánh quay tới tận `cleanup()`.

- `mockpwmpin` là **bắt buộc** — `MockPin` thường không hỗ trợ PWM, thiếu nó là 14 test
  lỗi `PinPWMUnsupported`.
- **KHÔNG chuyển 2 dòng này sang `tests/__init__.py`.** `test_motion.py` và `test_lift.py`
  đều có `from tests.config_editor import save_config` → chúng cũng bị ép sang chân giả
  và sẽ **im lặng không điều khiển gì**: bấm menu, log chạy bình thường, robot đứng yên.
- `setdefault` để các script cần phần cứng thật vẫn đặt đè được.
- Dấu hiệu nhận biết đang chạy bằng chân giả: bộ test xong trong ~4.5s thay vì ~31s.

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

Hai tầng: **ORB (hình dạng) trước, HSV (màu) dự phòng** — `_classify_frame()`.
4 loại hình dán trên khối 40x40x40mm (dán 6 mặt, cố định):
- **Samsung (01)**: chip xanh dương
- **Foxconn (02)**: chip vàng đồng — loại DUY NHẤT phủ màu kín mặt
- **Amkor (03)**: khối nhôm Al xám
- **Hana Micron (04)**: QR code + **ngoặc đỏ ở GÓC**
- Camera: **1296x972** (xem `config.CAMERA_RESOLUTION`, đừng hạ lại — lý do dưới)
- Nâng 2 kiện → chia ảnh trái/phải → `classify_pair(level)`

### ⚠️ VÙNG QUÉT DỊCH THEO TẦNG (`config.ROI_Y_CENTER`)

Camera gắn CỐ ĐỊNH vào thân robot nên tầng 1 và tầng 2 rơi vào 2 độ cao khác nhau
trong khung. Kệ lúc thi đấu có hàng ở CẢ HAI tầng, nên một khung cắt giữa cố định
sẽ ôm 2 loại kiện cùng lúc: HSV trộn màu 2 kiện, ORB so vùng 2 decal với ảnh mẫu
1 decal. Đo trên robot (640x480 lúc đó): kiện tầng 2 ở y 75..215, tầng 1 ở y
300..430, mà ROI cũ là y 96..384 — vắt ngang cả hai, 164px còn lại là sàn nhà.

`main.py` truyền `self.current_tier` xuống. **Mọi công cụ soi ROI phải truyền tầng**
(`calibrate_vision`, `capture_templates`, `test_vision`, `test_smoke`, web debug) —
soi nhầm vùng thì calibrate xong vẫn nhận sai.

### ⚠️ ẢNH MẪU ORB CHIA THEO (TẦNG, Ô) — 16 tấm

```
vision/templates/t2_left/{label}.png    t2_right/   t1_left/   t1_right/
```

Đo trên robot: khớp ĐÚNG tổ hợp được **65-229 inlier**, khớp lệch tổ hợp chỉ **0-6**.
Camera đặt giữa nên kiện ô TRÁI nhìn từ sườn phải, ô PHẢI nhìn từ sườn trái, hai
tầng lại hai góc chúc — bốn tổ hợp là bốn phối cảnh, một ảnh mẫu không phủ nổi.
Thiếu tổ hợp nào thì tổ hợp đó không có ORB (log cảnh báo rõ).

**Chuẩn hoá kích thước trong cùng một bộ** (`ShapeMatcher._load_dir`): bốn ảnh mẫu
của cùng một ô đều chứa CÙNG phần pallet + khung kệ, mà nền đó có trong MỌI vùng
quét — tấm nào cắt rộng hơn thì ăn thêm inlier miễn phí, nên **tấm cắt SẠCH nhất
lại thiệt nhất**. Đo ở t2_left: samsung (296px) thua sát nút amkor (395px) ngay
trên ô đang đặt samsung; cắt về cùng cỡ thì cách biệt lên 11.1x. Lệch cỡ quá
`MAX_TEMPLATE_SIZE_SPREAD` thì cảnh báo chụp lại — **dán dấu lên pallet** rồi đặt
cả 4 loại đúng vào dấu đó khi chụp.

**Vì sao 1296x972 chứ không phải 640x480:** kiện tầng 1 nằm xa camera nên ở 640x480
ảnh mẫu tầng 1 chỉ 178x130 với 130-220 keypoint, và kiện THẬT ở đó chỉ đạt 9 inlier
— bằng đúng mức ô TRỐNG ở tầng 2 (10 inlier), không ngưỡng nào tách được. Ở độ phân
giải mới thành ~290x220 với 321-706 kp. Giá: `classify_pair` 360ms → 585ms, cả trận
≈ +1.4s. `ORB_FEATURES` nâng 500 → 900 vì ROI 520x364 chạm đúng trần 500.

### ⚠️ ORB RẤT NHẠY VỚI VỊ TRÍ ĐẶT KIỆN — đừng tin nó một mình

Cùng ô, cùng loại, hai lần đo cách nhau vài phút: **230 inlier so với 15**. Nguyên
nhân thuộc về bản chất phương pháp: RANSAC homography giả định vật thể PHẲNG, mà
kiện là khối lập phương và ảnh mẫu ôm cả mặt trước lẫn mặt trên — đổi góc nhìn là
không homography nào khớp được cả hai mặt.

Thi đấu thì BTC đặt kiện NGẪU NHIÊN, nên **ORB sẽ thường xuyên bỏ cuộc**. Điều đó
chấp nhận được: nó không nhận SAI, chỉ im lặng, nhờ cơ chế 2 điều kiện
(`MIN_INLIERS` + `MARGIN_RATIO`). Đừng nới `MARGIN_RATIO` để ép nó lên tiếng.

### HSV — dự phòng, và điểm yếu đã biết

- **Ưu tiên màu chromatic hơn Amkor (xám)**: `_classify_by_color` chọn nhãn
  chromatic (`CHROMATIC_LABELS`) nếu đạt ngưỡng, KỂ CẢ khi Amkor đếm nhiều pixel
  hơn. Cần vậy vì **3/4 decal có nền TRẮNG** (samsung chip xanh trên trắng, hana QR
  đỏ trên trắng, amkor chữ Al trên trắng xám) — "vô sắc và sáng" không phải đặc
  trưng riêng của amkor.
- **Dải V của amkor bị siết bằng tay** (130..230, không dùng số tool đề xuất): dải
  gốc phủ luôn khung kệ đen và mặt bàn trắng nên KỆ TRỐNG khớp 41.6%, tự nó vượt
  `CONFIDENCE_THRESHOLD`. Siết còn kệ trống 14.8% / có amkor 68.9%.
- ⚠️ **HAI THAY ĐỔI SAU PHẢI ĐI CÙNG NHAU** (a950c75) — sửa hai lỗi ngược chiều của
  cùng một nguyên nhân là 3/4 decal nền trắng. Đổi một cái mà quên cái kia là hỏng:
  - **Sàn S của samsung 52 → 90.** Decal "Al Aluminum" có nền xanh xám nhạt, rơi
    đúng dải hue samsung — trên kiện amkor thật, dải samsung ăn 31.1% còn dải amkor
    chỉ 18.5%, tức HSV gọi amkor thành samsung. Chip xanh samsung là màu IN ĐẬM còn
    ánh xanh trên nhôm thì nhạt: S>=52 cho 33.3%/16.7% (2.0x), S>=90 cho 23.4%/5.7%
    (4.1x). Đừng nâng quá 110 — samsung thật tụt còn 20.3%, hết dư địa khi tối đi.
  - **`CONFIDENCE_THRESHOLD` 0.20 → 0.12.** Decal hana nền trắng nên dải amkor luôn
    ăn nhiều pixel hơn (trên kiện hana: amkor 47.0% mà hana 15.4%). Hana không cần
    thắng về SỐ pixel — màu đỏ là đặc trưng RIÊNG, sạch hơn hẳn: 15.4% trên kiện
    hana so với 0.6-0.9% trên 3 loại kia, chênh >20 lần. Nó chỉ cần vượt ngưỡng để
    cơ chế ưu tiên `CHROMATIC_LABELS` kích hoạt và chặn amkor.
  - Hạ ngưỡng MỘT MÌNH sẽ hỏng: samsung 31.1% trên kiện amkor sẽ thắng ở ô đó.
  - ĐÃ THỬ VÀ LOẠI: nâng sàn S của dải amkor cho nó nhả nền trắng của hana. Phải
    lên S>=30 mới thắng (12.6% so với 9.3%) nhưng lúc đó chính amkor tụt dưới ngưỡng
    — chữa ô này thì mất khả năng nhận amkor.
  - Hệ quả phụ đáng biết: với ngưỡng 0.12, kết quả ORB chắc chắn luôn có conf
    >= SHAPE_MIN_INLIERS/40 = 0.15, tức luôn cao hơn mọi kết quả HSV chưa đạt ngưỡng.
- **Kết quả sau 2 bản vá trên**, bố cục đúng kiểu thi đấu (tầng 2 hai khối, tầng 1
  bốn khối 2x2) — lần đầu CẢ HAI đường đều đúng CẢ 4 ô:
      T2 trái hana ORB 100% / HSV 26.9%  |  T2 phải samsung ORB 100% / HSV 39.9%
      T1 trái amkor ORB 100% / HSV 53.6% |  T1 phải foxconn ORB 100% / HSV 66.6%
  Ghi nhận thêm: 16 ảnh mẫu chụp bằng MỘT khối vẫn khớp tốt với kiện đủ 2-4 khối.
- ĐÃ SỬA (0e8107d): vạch xanh tím của sa bàn từng lọt vào 60px đáy ROI tầng 1 và
  rơi đúng dải hue samsung — trên kiện hana, samsung ăn 12.3% chỉ nhờ dải đó và
  vượt mặt hana. Thu `ROI_HEIGHT` 0.375→0.30 và dịch `ROI_Y_CENTER[1]` 0.76→0.74
  là hết: samsung giả còn 5.4-7.7%, ORB tự quyết đúng tăng từ 2/4 lên 3/4 ô.
  **Đo lại 2 hằng số này nếu đổi độ phân giải, góc camera hay khoảng cách dừng** —
  chúng là toạ độ pixel quy ra phần trăm, không phải hằng số vật lý.
- Chốt dải bằng `python3 -m tools.calibrate_vision` (hỏi tầng, chạy riêng từng tầng;
  `COLOR_RANGES` hiện chỉ có MỘT bộ dùng chung cho cả 2 tầng).

## Quy tắc quan trọng

- Bản đồ line trong `navigation.py` đo từ file in chuẩn — vẫn phải **đếm lại tay trên
  sa bàn thật** trước khi chạy (in bằng `python3 -m tools.show_routes`)
- `TURN_TIME = 0.5s` (fast-profile, CHƯA calibrate thật) cần đo lại trên robot thật
- `LIFT_TIME_SHELF_1/2` cần calibrate riêng cho từng càng; `LIFT_*_EXTRA` là bù theo
  **vị trí tuyệt đối** (thời gian từ sàn lên tầng n), không phải bù mỗi lần chạy
- **`HOME_AT_INIT = False`** — robot KHÔNG tự hạ càng lúc INIT nữa. ⚠️ **ĐỘI PHẢI TỰ
  HẠ CÀNG VỀ SÀN TRƯỚC KHI BẤM NÚT.** Không có limit switch nên robot không kiểm
  chứng được, nó chỉ tin `_current_level = 0`; quên hạ càng thì mọi phép tính tầng
  sau đó lệch và KHÔNG có tín hiệu báo — cùng loại lỗi im lặng với công tắc gạt nửa
  sân. `main.py` in khối cảnh báo 6 dòng mỗi lần khởi động.
  Lưu ý 4 giây đó **không** ăn vào 240s (nó chạy TRƯỚC lúc chờ nút); tắt đi là để đỡ
  bào mòn dây curoa, vì mỗi lần khởi động là 4s motor ghì đáy ở 100% duty.
  Bật lại bằng `HOME_AT_INIT = True` nếu muốn robot tự lo.
- `LIFT_HOME_DURATION` phải **≥ `Lift.min_home_duration()`** = `LIFT_TIME_SHELF_2` **+**
  `LIFT_*_LOWER_EXTRA` lớn hơn trong 2 bên (hiện 4.2s). So với `LIFT_TIME_SHELF_2`
  suông là SAI ngưỡng — thấy "đạt" mà càng vẫn còn hở. `home_to_floor()` tự kẹp lên
  ngưỡng thật + ghi WARNING, nên không còn hạ thiếu âm thầm được
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
  dụng khác) dễ gây nhận nhầm — nên nhận diện đi HAI TẦNG: ORB (hình dạng) trước,
  HSV (màu) dự phòng. Đo thật cho thấy hai đường bù trừ nhau đúng chỗ: ô nào ORB
  bỏ cuộc thì HSV đỡ, ô nào HSV nhầm thì ORB đỡ. **Đừng bỏ đường nào.**
- **Tới sân thi phải chụp lại CẢ 16 ảnh mẫu** (`tools.capture_templates`, 4 tổ hợp
  × 4 loại) và **calibrate lại HSV** (`tools.calibrate_vision`, từng tầng). Ảnh mẫu
  gắn chặt với khoảng cách dừng, góc camera và ánh sáng — đổi sân là phải làm lại,
  không mang bộ cũ đi dùng được. Tính khoảng 30-45 phút, đưa vào kế hoạch ngày thi.
- ORB **rất nhạy với vị trí đặt kiện** (đo được 230 inlier so với 15 ở cùng ô, cùng
  loại) vì RANSAC homography giả định vật PHẲNG mà kiện là khối lập phương. BTC đặt
  kiện ngẫu nhiên nên ORB sẽ hay bỏ cuộc — chấp nhận được, vì nó im lặng chứ không
  nhận sai. **Đừng nới `SHAPE_MARGIN_RATIO` để ép nó lên tiếng.**
