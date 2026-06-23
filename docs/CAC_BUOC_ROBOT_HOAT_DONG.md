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
  R0 [Kệ3]──■ Start ─────┼──[Foxconn]────┤
      │                  │               │
      │       [Kệ4]      │               │
```

## Biến theo dõi tiến độ

```python
self.pickup_count = 0          # Số lần đã nâng (0→6)
self.packages_delivered = 0    # Số kiện đã giao (0→12)
self.current_shelf = 0         # Kệ hiện tại (0=Kệ3, 1=Kệ2, 2=Kệ1)
self.current_tier = 1          # Tầng hiện tại (1=dưới, 2=trên)
self.carried_labels = [None, None]  # 2 label đang mang
self.delivery_queue = []       # Thứ tự giao [label_gần, label_xa]
```

## Cách robot cập nhật tiến độ

```
pickup_count tăng khi:    nâng thành công (cảm biến IR xác nhận)
packages_delivered tăng:  +2 nếu 2 kiện cùng nhà máy (giao 1 lần)
                          +1 mỗi lần giao nếu 2 kiện khác nhà máy
current_shelf/tier:       _advance_position() gọi sau mỗi lượt giao xong
NV1 hoàn thành khi:       packages_delivered >= 12
NV2 bắt đầu khi:          NV1 hoàn thành + còn giờ
Dừng (DONE) khi:           NV2 xong HOẶC hết giờ (< 10s an toàn)
```

---

## GIAI ĐOẠN 1: KHỞI ĐỘNG

### State: INIT → START

```
Robot đặt trong ô xuất phát 400×400mm
Quay mặt lên trên (hướng R0 → R4)
  │
  │ Trọng tài đếm ngược "3, 2, 1, BẮT ĐẦU"
  │ Đội nhấn nút (GPIO 16)
  ▼
Timer bắt đầu đếm 240 giây
Càng forklift reset về mặt sàn (level 0)
```

---

## GIAI ĐOẠN 2: NHIỆM VỤ 1 — LẶP 6 LƯỢT

### Lượt 1: Kệ 3 (R0), Tầng 1

#### Bước 1: Di chuyển đến kệ

```
State: NAVIGATE_TO_SHELF
pickup_count == 0 → lần đầu, dùng ROUTE_START_TO_SHELF_0

Robot (R0 giữa, hướng lên)
  │ ("left",)         → Xoay 90° sang trái (hướng về cạnh trái)
  │ ("forward", 1)    → Bám line, đếm 1 giao lộ → dừng trước Kệ 3
  ▼
Robot dừng tại giao lộ Kệ 3, hướng sang trái (vào kệ)
```

#### Bước 2: Quét nhận diện 2 kiện

```
State: SCAN_PAIR

Camera chụp 1 frame (640×480)
  ┌─────────────────────────┐
  │ [Kiện trái] [Kiện phải] │  ← 2 pallet cạnh nhau trên tầng 1
  └─────────────────────────┘
         ↓ chia đôi ảnh
  ┌───────────┐ ┌───────────┐
  │ Nửa trái  │ │ Nửa phải  │
  │ → HSV     │ │ → HSV     │
  │ 35% xanh  │ │ 28% vàng  │
  │ =samsung  │ │ =foxconn  │
  └───────────┘ └───────────┘

carried_labels = ["samsung", "foxconn"]
```

#### Bước 3: Lên kế hoạch giao hàng

```
_plan_delivery("samsung", "foxconn")

So sánh khoảng cách từ kệ hiện tại đến mỗi nhà máy:
  ROUTE_SHELF_TO_FACTORY["samsung"] → 2 giao lộ (cùng hàng, đi ngang)
  ROUTE_SHELF_TO_FACTORY["foxconn"] → 2 giao lộ (cùng hàng, đi ngang)
  → Bằng nhau → giữ thứ tự: samsung trước, foxconn sau

delivery_queue = ["samsung", "foxconn"]
```

#### Bước 4: Tiếp cận kệ + Nâng hàng

```
State: PICKUP_PAIR

── approach_shelf() ──
Robot tiến chậm (30%) + siêu âm đo liên tục
  Robot ════►  [Kệ]
  HC-SR04 đo: 20cm... 15cm... 10cm... 5cm... 4cm → DỪNG!
  Càng đã luồn vào dưới 2 pallet

── lift.pickup(shelf_level=1) ──
Lần 1:
  Hạ càng xuống level 0 (dưới pallet)     ← go_to_level(0)
  Chờ 0.2s
  Nâng càng lên level 1 (nhấc pallet)     ← go_to_level(1), chạy motor 0.8s
  Chờ 0.3s (PICKUP_VERIFY_DELAY)
  Kiểm tra cảm biến IR:
    IR = LOW → CÓ pallet → ✅ Thành công!
    IR = HIGH → KHÔNG có → ⚠️ Thử lại (tối đa 2 lần)

pickup_count: 0 → 1

── retreat_from_shelf() ──
Robot lùi + siêu âm đo liên tục
  [Kệ]  ◄════ Robot
  HC-SR04 đo: 4cm... 8cm... 12cm... 15cm → DỪNG!
  Đủ xa để xoay mà không va kệ
```

#### Bước 5: Di chuyển đến nhà máy 1 (Samsung)

```
State: DELIVER_FIRST

label = delivery_queue[0] = "samsung"
route = ROUTE_SHELF_TO_FACTORY["samsung"]

Robot (tại Kệ 3, R0, hướng trái)
  │ ("right",)         → Xoay 90° sang phải (hướng lên)
  │ ("right",)         → Xoay 90° sang phải (hướng sang phải)
  │ ("forward", 2)     → Bám line, qua 2 giao lộ → đến Samsung (R4)
  ▼
Robot dừng trước Samsung
```

#### Bước 6: Đặt hàng tại Samsung

```
State: DROP_FIRST

── approach_shelf() ──
Tiến chậm vào khu nhà máy Samsung (250×250mm)
Siêu âm đo đến tường/vạch nhà máy → dừng ở 4cm

── lift.dropoff() ──
Hạ càng từ level 1 xuống level 0 (chậm, DROP_SPEED)
Pallet + 4 khối hàng đặt xuống mặt sàn
Kiểm tra IR: HIGH (không còn pallet) → ✅ Đã hạ thành công

── retreat_from_shelf() ──
Lùi ra 15cm

── Cập nhật tiến độ ──
delivery_queue: ["samsung", "foxconn"] → pop → ["foxconn"]
carried_labels[0] == carried_labels[1]? → "samsung" ≠ "foxconn" → KHÁC
packages_delivered: 0 → 1
delivery_queue còn → chuyển sang DELIVER_SECOND
```

#### Bước 7: Di chuyển đến nhà máy 2 (Foxconn)

```
State: DELIVER_SECOND

label = delivery_queue[0] = "foxconn"
prev_label = "samsung" (vừa giao)
route = ROUTE_BETWEEN_FACTORIES[("samsung", "foxconn")]

── lift.go_to_level(1) ──
NÂNG LẠI CÀNG để giữ kiện Foxconn (đã hạ Samsung, kiện Foxconn vẫn trên càng)

Robot (tại Samsung R4, hướng phải)
  │ ("forward", 4)     → Bám line xuống 4 giao lộ: R4→R3→R2→R1→R0
  ▼
Robot dừng trước Foxconn (R0)
```

#### Bước 8: Đặt hàng tại Foxconn

```
State: DROP_SECOND

approach_shelf() → tiến vào Foxconn
lift.dropoff() → hạ càng, đặt pallet xuống
retreat_from_shelf() → lùi ra

── Cập nhật tiến độ ──
delivery_queue: ["foxconn"] → pop → []
packages_delivered: 1 → 2
Chưa đủ 12 + còn giờ → RETURN_TO_WAREHOUSE
```

#### Bước 9: Quay về kệ

```
State: RETURN_TO_WAREHOUSE

last_label = "foxconn" (nhà máy cuối cùng đã giao)
route = ROUTE_FACTORY_TO_SHELF["foxconn"]

Robot (tại Foxconn R0, hướng phải)
  │ ("left",)          → Xoay 90° sang trái (hướng sang trái)
  │ ("forward", 2)     → Bám line qua 2 giao lộ → về cột kệ
  ▼
Robot dừng tại vị trí Kệ 3

── _advance_position() ──
current_tier: 1 → 2 (cùng kệ, chuyển tầng 2)
→ NAVIGATE_TO_SHELF
```

---

### Lượt 2: Kệ 3 (R0), Tầng 2

```
State: NAVIGATE_TO_SHELF
current_tier == 2 → TẠI CHỖ, không di chuyển (cùng kệ)

→ SCAN_PAIR → quét 2 kiện tầng 2
→ PICKUP_PAIR → nâng tầng 2 (lift_time = 1.5s thay vì 0.8s)
→ DELIVER_FIRST → giao nhà máy gần
→ DROP_FIRST → hạ hàng
→ DELIVER_SECOND → giao nhà máy xa (nếu khác)
→ DROP_SECOND → hạ hàng
→ RETURN_TO_WAREHOUSE

── _advance_position() ──
current_tier: 2 → 1
current_shelf: 0 → 1 (chuyển sang Kệ 2)
```

---

### Lượt 3: Kệ 2 (R2), Tầng 1

```
State: NAVIGATE_TO_SHELF
current_tier == 1 + không phải lần đầu → dùng ROUTE_BETWEEN_SHELVES

Robot (tại cột kệ, R0)
  │ ("forward", 2)     → Bám line lên 2 giao lộ: R0→R1→R2
  ▼
Robot dừng tại Kệ 2 (R2)

→ SCAN_PAIR → PICKUP_PAIR → DELIVER → DROP → RETURN
```

---

### Lượt 4-6: Tương tự

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

last_label = carried_labels cuối cùng (VD: "samsung")
route = ROUTE_FACTORY_TO_LOOSE["samsung"]

Robot (tại Samsung R4)
  │ ("forward", 4)     → Xuống R4→R3→R2→R1→R0
  │ ("forward", 1)     → Xuống thêm 1 (Kệ 4 thụt dưới R0)
  │ ("left",)          → Rẽ trái
  │ ("forward", 1)     → Tiến đến Kệ 4
  ▼
Robot dừng trước Kệ 4

Nếu last_label = "foxconn" (gần nhất):
  │ ("forward", 1)     → Xuống 1
  │ ("left",)          → Rẽ trái
  │ ("forward", 1)     → Đến Kệ 4
  ▼
Chỉ mất ~5s (Foxconn cạnh Kệ 4)
```

### Bước 2: Nâng hàng rời

```
State: TASK2_PICKUP

approach_shelf() → tiến vào Kệ 4 (siêu âm)
lift.pickup(shelf_level=1) → nâng pallet (1 pallet, 4 khối khác loại)
  → Kiểm tra IR: có pallet → ✅
  → Nếu thất bại → DONE (bỏ qua NV2)
retreat_from_shelf() → lùi ra
```

### Bước 3: Kệ 4 → Nhà máy liên hợp

```
State: TASK2_NAVIGATE_TO_JOINT

route = ROUTE_LOOSE_TO_JOINT

Robot (tại Kệ 4, dưới R0)
  │ ("right",)         → Quay ra (hướng sang phải)
  │ ("forward", 1)     → Đến cột nhà máy
  │ ("left",)          → Rẽ trái (hướng lên)
  │ ("forward", 3)     → Lên 3 giao lộ → R2 (nhà máy liên hợp)
  ▼
Robot dừng trước nhà máy liên hợp
```

### Bước 4: Đặt hàng

```
State: TASK2_DROP

approach_shelf() → tiến vào nhà máy liên hợp
lift.dropoff() → hạ pallet xuống
retreat_from_shelf() → lùi ra

→ DONE ✅
```

---

## GIAI ĐOẠN 4: KẾT THÚC

```
State: DONE

motion.stop()          → Dừng tất cả động cơ
Ghi log:
  "Thời gian: 144.2 giây"
  "Kiện hàng đã giao: 12/12 (trong 6 lượt nâng)"
motion.cleanup()       → Đóng GPIO động cơ
lift.cleanup()         → Đóng GPIO cẩu + IR sensor
vision.cleanup()       → Đóng camera
start_button.close()   → Đóng GPIO nút

Robot đứng yên chờ trọng tài kết thúc trận
```

---

## SƠ ĐỒ TỔNG LUỒNG HOẠT ĐỘNG

```
INIT (chờ nút) ──→ START (reset càng, bắt đầu timer)
  │
  ▼
┌─────────────── LẶP 6 LƯỢT ───────────────────┐
│                                              │
│  NAVIGATE_TO_SHELF                           │
│    ├ Lần đầu: ROUTE_START_TO_SHELF_0         │
│    ├ Tầng 2: tại chỗ (không di chuyển)       │
│    └ Kệ tiếp: ROUTE_BETWEEN_SHELVES          │
│                     │                        │
│  SCAN_PAIR ←────────┘                        │
│    Camera chia trái/phải → HSV → 2 label     │
│    _plan_delivery() → sắp gần trước xa sau   │
│                     │                        │
│  PICKUP_PAIR ◄──────┘                        │
│    approach_shelf() ── siêu âm dừng ở 4cm    │
│    lift.pickup()    ── nâng + IR xác nhận    │
│    retreat_from_shelf() ── siêu âm lùi 15cm  │
│         │       │                            │
│     thành công  thất bại → bỏ qua, kệ tiếp   │
│         │                                    │
│  DELIVER_FIRST                               │
│    execute_route(SHELF_TO_FACTORY[label1])   │
│         │                                    │
│  DROP_FIRST                                  │
│    approach + dropoff + retreat              │
│    packages_delivered += (2-cùng, 1-khác)    |
│         │                                    │
│    ┌────┴────┐                               │
│  Cùng NM   Khác NM                           │
│    │          │                              │
│    │    DELIVER_SECOND                       │
│    │      lift.go_to_level(1) ← giữ kiện 2   │
│    │      execute_route(BETWEEN_FACTORIES)   │
│    │          │                              │
│    │    DROP_SECOND                          │
│    │      approach + dropoff + retreat       │
│    │      packages_delivered += 1            │
│    │          │                              │
│    └────┬─────┘                              │
│         │                                    │
│    ┌────┴──────────────────┐                 │
│  >=12 kiện            <12 kiện + còn giờ     │
│    │                       │                 │
│    │               RETURN_TO_WAREHOUSE       │
│    │                 ROUTE_FACTORY_TO_SHELF  │
│    │                 _advance_position()     │
│    │                       │                 │
│    │                       └────→ (lặp lại)  │
│    │                                         │
└────┼─────────────────────────────────────────┘
     │
     ▼
  NV1 HOÀN THÀNH (12/12)
     │
  TASK2_NAVIGATE_TO_LOOSE
     ROUTE_FACTORY_TO_LOOSE[last_label]
     │
  TASK2_PICKUP
     approach + pickup + retreat
     │
  TASK2_NAVIGATE_TO_JOINT
     ROUTE_LOOSE_TO_JOINT
     │
  TASK2_DROP
     approach + dropoff + retreat
     │
     ▼
   DONE ── dừng motor, ghi log, cleanup GPIO
```

---

## CƠ CHẾ AN TOÀN

| Tình huống | Xử lý |
|-----------|-------|
| Sắp hết giờ (<10s) | `is_time_safe()` check sau mỗi state → DONE |
| Nâng thất bại (IR không thấy pallet) | Retry 2 lần, nếu vẫn thất bại → bỏ qua, kệ tiếp |
| Hạ xong nhưng IR vẫn thấy pallet | Log cảnh báo "có thể kẹt" |
| Mất line (8 sensor = 0) | `_recover_line()` quét trái/phải tìm lại |
| Bám line timeout (>15s) | Dừng, log lỗi |
| Siêu âm timeout (>5s) | Dừng, log cảnh báo |
| Ctrl+C / SIGTERM | `_emergency_stop()` → tắt tất cả motor |
| Camera nhận diện thất bại | Fallback gán label mặc định |
| NV2 nâng thất bại | Bỏ qua NV2 → DONE |
