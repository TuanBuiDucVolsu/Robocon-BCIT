# Cách robot hoạt động — Chi tiết từng bước

## Tổng quan

Robot hoàn thành 2 nhiệm vụ trong 240 giây:
- **NV1**: 12 kiện hàng từ 3 kệ → 4 nhà máy (6 lượt × 2 kiện)
- **NV2**: 1 kiện từ kệ 4 → nhà máy liên hợp (chỉ sau 100% NV1)

## Bố trí sa bàn

```
    Col0 (kệ/trái)   Col1 (giữa)    Col2 (nhà máy/phải)
      │                  │               │
  R4 [Kệ1]───────────────┼──[Samsung]────┤
      │                  │               │
  R3  │                  │──[Hana M.]────┤
      │        ◉         │               │
  R2 [Kệ2]───────────────┼──[Liên hợp]───┤
      │                  │               │
  R1  │                  │──[Amkor]──────┤
      │                  │               │
  R0 [Kệ3]──line──┃GAP┃──line──[Foxconn]
      │             ┃   ┃              │
      │          ←■Start┃              │   Robot hướng 9h (về Kệ 3)
      │             [Kệ4]             │
```

## Biến theo dõi tiến độ

```python
self.pickup_count = 0               # Số lần đã nâng (0→6)
self.packages_delivered = 0         # Số kiện đã giao (0→12)
self.current_shelf = 0              # Kệ hiện tại (0=Kệ3, 1=Kệ2, 2=Kệ1)
self.current_tier = 1               # Tầng hiện tại (1=dưới, 2=trên)
self.carried_labels = [None, None]  # [label_trái, label_phải] trên càng
self.delivery_queue = []            # Thứ tự giao [label1, label2]
self._last_delivered_label = None   # Nhà máy vừa giao — get_return_route + DELIVER_SECOND
self._tier_retries = 0              # Số lần đã thử lại tầng kệ hiện tại
self._start_route_done = False      # Đã chạy THÀNH CÔNG ROUTE_START_TO_SHELF_0 chưa
```

## Cách robot cập nhật tiến độ

```
pickup_count tăng khi:    nâng thành công (IR xác nhận — NV1 cần **cả 2** IR)
packages_delivered tăng:  **chỉ khi IR xác nhận đã thả**
                          +2 nếu 2 kiện cùng nhà máy (dropoff() thành công)
                          +1 mỗi lần giao nếu 2 kiện khác nhà máy (dropoff_left/right thành công)
                          Không tăng nếu SPI/ADC lỗi hoặc IR vẫn thấy pallet
current_shelf/tier:       _advance_position() sau khi bỏ tầng hoặc sau RETURN
NV1 hoàn thành khi:       packages_delivered >= 12
NV2 bắt đầu khi:          NV1 hoàn thành + còn giờ
Dừng (DONE) khi:           NV2 xong HOẶC hết giờ (< 10s an toàn) HOẶC hết kệ
```

---

## Route quay về kho (`config.py`)

```python
get_return_route(from_factory, target_shelf)
  = ROUTE_FACTORY_TO_SHELF[factory]      # nhà máy → cột kệ (cùng hàng)
  + _vertical_on_shelf_column(from, to)    # dọc cột kệ nếu khác hàng
```

| Map | Giá trị |
|-----|---------|
| `FACTORY_BOARD_ROW` | samsung=R4, hana=R3, amkor=R1, foxconn=R0 |
| `SHELF_BOARD_ROW` | Kệ3(0)=R0, Kệ2(1)=R2, Kệ1(2)=R4 |

- **Xuống hàng** (vd. R4→R0): `right → forward N → left`
- **Lên hàng** (vd. R0→R4): `left → forward N → right`
- `_plan_delivery()` dùng `_return_cost()` — chọn thứ tự giao có return ngắn hơn
- `_between_route(a,b)` fallback `(b,a)` nếu thiếu key trực tiếp

**Calibrate bắt buộc trên sa bàn** — số `forward N` là ước lượng.

---

## GIAI ĐOẠN 1: KHỞI ĐỘNG

### State: INIT → START

```
Robot đặt trong ô xuất phát 400×400mm
Quay mặt SANG TRÁI — hướng 9h, về phía Kệ 3 (KHÔNG hướng lên)
  │
  │ Trọng tài đếm ngược "3, 2, 1, BẮT ĐẦU"
  │ Đội nhấn nút (GPIO 16)
  ▼
Timer bắt đầu đếm 240 giây
Càng forklift reset về mặt sàn (level 0)
exit_start_zone() — tiến thẳng chạm line R0, căn giữa line (không đếm giao lộ)
  Nếu chạm giao lộ khi căn → dừng căn; giao lộ do ROUTE_START đếm
```

---

## GIAI ĐOẠN 2: NHIỆM VỤ 1 — LẶP 6 LƯỢT

### Lượt 1: Kệ 3 (R0), Tầng 1

#### Bước 1: Di chuyển đến kệ

```
State: START → exit_start_zone()
  Tiến thẳng (hướng 9h) → chạm line R0 → căn giữa line (tối đa EXIT_START_ALIGN_TIME)

State: NAVIGATE_TO_SHELF
not _start_route_done → _run_route(ROUTE_START_TO_SHELF_0)
  Chỉ đánh dấu _start_route_done=True khi CHẠY THÀNH CÔNG (không phải dựa vào
  pickup_count) — nếu route này fail và bị bỏ tầng (tier tăng lên 2 nhưng vẫn ở
  kệ 0), lần sau vẫn thử lại đúng route này thay vì nhầm "đã ở kệ, chỉ cần pass"
  Fail (mất line / timeout) → _retry_or_skip_tier("navigate")
_start_route_done, tier 2 → tại chỗ
_start_route_done, tier 1 → _run_route(ROUTE_BETWEEN_SHELVES); fail → retry/skip tầng

Robot (trong ô start, đã chạm line R0, hướng 9h)
  │ ("forward", 1)    → Bám line sang trái, 1 giao lộ → dừng tại Kệ 3
  ▼
Robot dừng trước Kệ 3, hướng sang trái (vào kệ)
```

#### Bước 2–4: Tiếp cận + Quét + Nâng (PICKUP_PAIR)

```
State: PICKUP_PAIR

── _approach_shelf("PICKUP_PAIR") ── (tiếp cận 2 pha)
Robot tiến NHANH (APPROACH_FAST_SPEED) ở xa → CHẬM (APPROACH_SLOW_SPEED) khi gần
  Robot ════►  [Kệ]
  HC-SR04 (median 3 mẫu): 20cm... 15cm...│10cm chuyển chậm│... 5cm... 4cm → DỪNG!
  Timeout (>APPROACH_TIMEOUT) → _retry_or_skip_tier("approach")

── classify_pair() ── (quét SAU khi tiếp cận — góc nhìn chính xác hơn)
Camera chụp 1 frame (640×480)
  ┌─────────────────────────┐
  │ [Kiện trái] [Kiện phải] │
  └─────────────────────────┘
         ↓ chia đôi ảnh → HSV
  carried_labels = ["samsung", "foxconn"]

  Nếu không nhận diện đủ 2 kiện:
    → thử lại MAX_PAIR_SCAN_ATTEMPTS lần
    → vẫn fail → _retreat_from_shelf() → _retry_or_skip_tier("scan")

── _plan_delivery() ──
So sánh tổng route cost (forward + turn × ROUTE_TURN_COST + return về kệ):
  cost_left_first  = shelf→left + between(left,right) + return(right)
  cost_right_first = shelf→right + between(right,left) + return(left)
  → chọn thứ tự giao tổng cost thấp hơn (gồm cả chi phí quay về đúng hàng)
delivery_queue = ["samsung", "foxconn"]   # ví dụ

── lift.pickup(shelf_level=1, require_both=True) ──
Nâng CẢ 2 càng đồng bộ, retry tối đa PICKUP_MAX_RETRIES lần
  read_status() → (trái, phải, đọc_ok)
  NV1: cần đọc_ok=True VÀ cả 2 IR = LOW (có pallet) → ✅
  SPI/ADC lỗi (đọc_ok=False) → không coi là thành công
  Fail → _retry_or_skip_tier("pickup")

pickup_count: 0 → 1

── _retreat_from_shelf("PICKUP_PAIR") ──
Lùi đến khi siêu âm ≥ 15cm (timeout → log cảnh báo, vẫn tiếp tục)
```

#### Bước 5: Di chuyển đến nhà máy 1 (Samsung)

```
State: DELIVER_FIRST
label = delivery_queue[0] = "samsung"
_run_route(ROUTE_SHELF_TO_FACTORY["samsung"])
  Fail → log cảnh báo "Navigation lệch — vẫn thử hạ hàng"
```

#### Bước 6: Đặt hàng tại Samsung (2 kiện khác nhà máy)

```
State: DROP_FIRST
label = "samsung" → _last_delivered_label = "samsung"
same_factory = False (samsung ≠ foxconn)

_approach_shelf("DROP_FIRST ...")  ← timeout vẫn thử hạ
_drop_single_side("left")  ← dropoff_left() + raise_after_drop("left")
  Chỉ packages_delivered += 1 nếu IR xác nhận càng trái đã rời pallet
_retreat_from_shelf("DROP_FIRST ...")

delivery_queue: pop → ["foxconn"]
packages_delivered: 0 → 1 (nếu IR OK)
→ DELIVER_SECOND
```

**Nếu 2 kiện cùng nhà máy:** dùng `dropoff()` hạ cả 2 càng; `packages_delivered += 2` **chỉ khi** `_verify_released()` thấy cả 2 IR đã rời; bỏ qua DELIVER_SECOND.

#### Bước 7: Di chuyển đến nhà máy 2 (Foxconn)

```
State: DELIVER_SECOND
prev_label = _last_delivered_label   ← nhà máy vừa giao ở DROP_FIRST
label = delivery_queue[0] = "foxconn"
route = _between_route(prev_label, label)   ← fallback chiều ngược nếu thiếu key
_run_route(route) — fail → log cảnh báo, vẫn thử DROP_SECOND
  Ví dụ: ("forward", 4) xuống R4→R0
(Không cần go_to_level — càng phải vẫn giữ kiện ở cao)
```

#### Bước 8: Đặt hàng tại Foxconn

```
State: DROP_SECOND
label = "foxconn" → _last_delivered_label = "foxconn"

_approach_shelf("DROP_SECOND ...")
dropoff_right()    ← thả kiện foxconn; IR xác nhận càng phải đã rời
stow_forks("right") ← hạ càng trái (còn ở cao) về sàn → cả 2 càng level 0
_retreat_from_shelf("DROP_SECOND ...")

packages_delivered: 1 → 2 (nếu IR OK)
→ RETURN_TO_WAREHOUSE
```

#### Bước 9: Quay về kệ

```
State: RETURN_TO_WAREHOUSE
target_shelf = _next_pickup_shelf()   ← kệ pickup tiếp (trước _advance_position)
route = get_return_route(_last_delivered_label, target_shelf)
  = ROUTE_FACTORY_TO_SHELF[factory] + đoạn dọc cột kệ (nếu khác hàng)
  Ví dụ: samsung (R4) → Kệ 3 (R0): base + right→forward 4→left
        foxconn (R0) → Kệ 3 (R0): chỉ base (cùng hàng)
_run_route(route) — fail → log, vẫn advance

_advance_position() → current_tier: 1 → 2 (cùng kệ)
→ NAVIGATE_TO_SHELF (tier 2 → tại chỗ, robot đã ở đúng hàng R0)
```

---

### Lượt 2: Kệ 3 (R0), Tầng 2

```
NAVIGATE_TO_SHELF: current_tier == 2 → TẠI CHỖ
PICKUP_PAIR: approach → scan → pickup tầng 2 (LIFT_TIME_SHELF_2 = 1.5s)
→ DELIVER → DROP → RETURN

_advance_position():
  current_tier: 2 → 1
  current_shelf: 0 → 1 (chuyển sang Kệ 2)
```

---

### Lượt 3–6: Tương tự

| Lượt | pickup_count | current_shelf | current_tier | packages_delivered |
|------|:-----------:|:------------:|:------------:|:-----------------:|
| 1 | 0→1 | 0 (Kệ3) | 1 | 0→2 |
| 2 | 1→2 | 0 (Kệ3) | 2 | 2→4 |
| 3 | 2→3 | 1 (Kệ2) | 1 | 4→6 |
| 4 | 3→4 | 1 (Kệ2) | 2 | 6→8 |
| 5 | 4→5 | 2 (Kệ1) | 1 | 8→10 |
| 6 | 5→6 | 2 (Kệ1) | 2 | 10→12 ✅ |

**Khi packages_delivered >= 12 → NV1 HOÀN THÀNH → chuyển NV2**

---

## GIAI ĐOẠN 3: NHIỆM VỤ 2 — KHO HÀNG RỜI

### Bước 1: Nhà máy cuối → Kệ 4

```
State: TASK2_NAVIGATE_TO_LOOSE
route = ROUTE_FACTORY_TO_LOOSE[_last_delivered_label]
  (nhà máy cuối cùng vừa giao kiện NV1)
_run_route(route) — fail → DONE (bỏ NV2)
```

### Bước 2: Nâng hàng rời

```
State: TASK2_PICKUP
_approach_shelf("TASK2_PICKUP") — fail → DONE
lift.pickup(shelf_level=1, require_both=False)
_retreat_from_shelf("TASK2_PICKUP")
  NV2: chỉ cần 1 IR thấy pallet (kho hàng rời — 1 kiện)
Nâng thất bại → DONE (bỏ qua NV2)
```

### Bước 3: Kệ 4 → Nhà máy liên hợp

```
State: TASK2_NAVIGATE_TO_JOINT
_run_route(ROUTE_LOOSE_TO_JOINT) — fail → DONE
```

### Bước 4: Đặt hàng

```
State: TASK2_DROP
_approach_shelf("TASK2_DROP") → lift.dropoff() → _retreat_from_shelf("TASK2_DROP")
  Log "NHIỆM VỤ 2 HOÀN THÀNH" chỉ khi IR xác nhận đã thả
  Drop fail → log lỗi, vẫn chuyển DONE
→ DONE ✅
```

---

## GIAI ĐOẠN 4: KẾT THÚC

```
State: DONE
motion.stop() → ghi log → cleanup GPIO + camera
Robot đứng yên chờ trọng tài kết thúc trận
```

---

## SƠ ĐỒ TỔNG LUỒNG HOẠT ĐỘNG

```
INIT (chờ nút) ──→ START (reset càng, exit_start_zone → chạm line R0)
  │
  ▼
┌─────────────── LẶP 6 LƯỢT (tối đa 3 kệ × 2 tầng) ─────┐
│                                                         │
│  NAVIGATE_TO_SHELF                                      │
│    ├ Lần đầu: _run_route(ROUTE_START_TO_SHELF_0)        │
│    ├ Tầng 2: tại chỗ                                   │
│    └ Kệ tiếp: _run_route(ROUTE_BETWEEN_SHELVES)         │
│    navigate fail → _retry_or_skip_tier("navigate") → NAVIGATE_TO_SHELF │
│    (hết kệ → DONE hoặc NV2 nếu đủ 12 kiện)             │
│                     │                                   │
│  PICKUP_PAIR ◄──────┘                                   │
│    _approach_shelf() ── 2 pha (nhanh→chậm), siêu âm dừng 4cm │
│    classify_pair()  ── HSV trái/phải (sau tiếp cận)   │
│    _plan_delivery() ── tối ưu thứ tự giao (cost gồm return về kệ) │
│    lift.pickup(require_both=True) ── NV1: cả 2 IR phải thấy pallet │
│    _retreat_from_shelf() ── siêu âm lùi 15cm            │
│         │                                               │
│     thành công │  scan/nâng/approach fail               │
│         │      └── _retry_or_skip_tier()                │
│         │            ├ retry (MAX_TIER_RETRIES)         │
│         │            └ skip → tầng/kệ tiếp              │
│         │                                               │
│  DELIVER_FIRST → DROP_FIRST                             │
│    _run_route() — fail vẫn thử hạ                       │
│    Cùng NM: dropoff() (+2 kiện nếu IR xác nhận)        │
│    Khác NM: _drop_single_side() (+1 kiện nếu IR OK)     │
│         │                                               │
│    ┌────┴────┐                                          │
│  Cùng NM   Khác NM                                      │
│    │          │                                         │
│    │    DELIVER_SECOND (_between_route từ _last_delivered_label) │
│    │    DROP_SECOND: dropoff + stow_forks (+1 nếu IR OK) │
│    └────┬─────┘                                         │
│         │                                               │
│    ┌────┴──────────────────┐                            │
│  >=12 kiện            <12 + còn giờ                     │
│    │                       │                            │
│    │               RETURN_TO_WAREHOUSE                  │
│    │                 get_return_route(factory, target)   │
│    │                 fail → log, vẫn _advance_position() │
│    │                 _advance_position()                │
│    │                       └────→ (lặp lại)             │
└────┼────────────────────────────────────────────────────┘
     │
     ▼
  NV1 HOÀN THÀNH (12/12)
     │
  TASK2_NAVIGATE_TO_LOOSE (_run_route) → TASK2_PICKUP (require_both=False)
     → TASK2_NAVIGATE_TO_JOINT → TASK2_DROP (chỉ log hoàn thành nếu IR OK)
     navigate/approach NV2 fail → DONE
     │
     ▼
   DONE
```

---

## CƠ CHẾ AN TOÀN

| Tình huống | Xử lý |
|-----------|-------|
| Sắp hết giờ (<10s) | `is_time_safe()` check sau mỗi state → DONE |
| Không tìm thấy line khi exit start | Retry `MAX_TIER_RETRIES + 1` lần (như các lỗi navigation khác); hết retry → kiểm tra hướng 9h, GAP line, `EXIT_START_TIMEOUT` → DONE |
| Navigation fail (mất line / timeout giao lộ) | `execute_route()` → `False`; đến kệ fail → `_retry_or_skip_tier("navigate")` → **NAVIGATE_TO_SHELF**; giao hàng fail → log, vẫn thử hạ; NV2 fail → DONE |
| Route rỗng (thiếu config) | Log warning, coi navigation fail |
| Tiếp cận kệ timeout (PICKUP) | `_retry_or_skip_tier("approach")` |
| Tiếp cận kệ timeout (DROP) | Log cảnh báo, vẫn thử hạ hàng |
| Scan fail (confidence thấp) | Retry MAX_PAIR_SCAN_ATTEMPTS → _retry_or_skip_tier |
| Nâng thất bại (IR không thấy pallet) | Retry PICKUP_MAX_RETRIES → _retry_or_skip_tier |
| SPI/ADC lỗi khi đọc IR (`last_read_ok=False`) | pickup/drop **không** coi thành công; log lỗi |
| Hết retry tầng kệ | Bỏ qua tầng, _advance_position(), sang tầng/kệ tiếp |
| Hết kệ (current_shelf >= 3) | DONE hoặc NV2 nếu đủ 12 kiện |
| Hạ xong nhưng IR vẫn thấy pallet | Không tăng packages_delivered; log cảnh báo "có thể kẹt" |
| Drop thất bại (IR/SPI) | Không tăng packages_delivered; robot vẫn chuyển state tiếp |
| Mất line (6 sensor = 0) | `_recover_line()` quét trái/phải tìm lại |
| Bám line timeout (>15s) | `navigate_intersections()` → False → propagate lên state machine |
| Chạm giao lộ khi căn line (exit start) | Dừng căn (`break`); **không** đếm giao lộ — ROUTE_START đếm |
| Siêu âm timeout (>5s) | `_approach_shelf` / `_retreat_from_shelf` log cảnh báo |
| Ctrl+C / SIGTERM | `_emergency_stop()` → tắt tất cả motor |
| Camera nhận diện thất bại | **Không** gán label mặc định — retry hoặc bỏ tầng |
| NV2 drop thất bại | Log lỗi, vẫn DONE (không log hoàn thành) |
| NV2 navigate fail | DONE (bỏ NV2) |
| NV2 nâng thất bại | Bỏ qua NV2 → DONE |
