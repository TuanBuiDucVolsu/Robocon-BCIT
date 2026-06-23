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
  R0 [Kệ3]──■ Start ────┼──[Foxconn]─────┤   Kệ 3 thẳng Start / Foxconn
      │                  │               │
      │       [Kệ4]     │               │   Kệ 4 THỤT XUỐNG dưới R0, bên phải Start
```

- Kệ 1-3: cạnh TRÁI, cách nhau 2 giao lộ (R4, R2, R0)
- Kệ 4: bên PHẢI Start, thụt XUỐNG dưới R0, cạnh Foxconn (kho hàng rời — NV2)
- Robot xuất phát: R0 giữa (Start), quay mặt lên trên
- Thứ tự lấy kệ: Kệ 3 (R0, gần nhất) → Kệ 2 (R2) → Kệ 1 (R4)
- 4 nhà máy xếp DỌC cạnh phải: Samsung(R4) → Hana(R3) → Amkor(R1) → Foxconn(R0)
- Nhà máy liên hợp: giữa sân (R2), chung 2 đội

## Cấu trúc code

```
main.py              — State machine: INIT → SCAN → PICKUP → DELIVER → DROP → lặp 6 lượt → TASK2
config.py            — GPIO, route commands, HSV color ranges, timing, kích thước
control/motion.py    — Di chuyển, bám line PD, siêu âm HC-SR04, execute_route(), line recovery
control/lift.py      — Nâng/hạ forklift, cảm biến IR xác nhận pallet, retry
vision/vision.py     — Nhận diện màu HSV (không dùng AI model), classify_pair()
debug/server.py      — Flask web debug UI (MJPEG stream, line sensor, classify_pair)
scripts/             — install.sh, start.sh, robot.service (systemd auto-start)
```

## Điều hướng (Navigation)

Dùng route commands: `("forward", N)`, `("left",)`, `("right",)`.
Các route định nghĩa trong `config.py`:
- `ROUTE_START_TO_SHELF_0` — Start → Kệ 3 (rẽ trái + tiến 1)
- `ROUTE_BETWEEN_SHELVES` — Kệ → kệ tiếp (tiến 2 giao lộ)
- `ROUTE_SHELF_TO_FACTORY[label]` — Kệ → nhà máy (quay phải 2 lần + đi ngang + rẽ nếu cần)
- `ROUTE_FACTORY_TO_SHELF[label]` — Nhà máy → về kệ
- `ROUTE_BETWEEN_FACTORIES[(a,b)]` — Giữa 2 nhà máy (12 cặp đầy đủ cả 2 chiều)
- `ROUTE_FACTORY_TO_LOOSE[label]` — Nhà máy → Kệ 4 (thụt dưới R0)
- `ROUTE_LOOSE_TO_JOINT` — Kệ 4 → nhà máy liên hợp (R2)

Kệ thẳng hàng nhà máy → Samsung/Foxconn chỉ cần đi ngang (không rẽ lên/xuống).

## Phần cứng

- Raspberry Pi 4 Model B
- 2 DC motor bánh xe (giảm tốc 1:48) + 2 bánh caster
- 2 DC motor cẩu forklift (dây curoa + con lăn trượt dọc trụ nhôm)
- 2 thanh nâng (nâng 2 pallet cùng lúc)
- Camera CSI (OV5647) — nhận diện HSV
- Cảm biến dò line 8 mắt qua I2C (PCF8574, addr 0x20)
- HC-SR04 siêu âm (GPIO 19 TRIG, 20 ECHO) — tiếp cận kệ chính xác
- Cảm biến IR pallet (GPIO 26) — xác nhận nâng thành công
- Nút khởi động (GPIO 16)
- L298N x2 + XH-M401 hạ áp
- Tổng: **15/16 GPIO**, **4/12 động cơ** — ĐẠT

## Nhận diện kiện hàng

Phân tích màu HSV (OpenCV), không cần model AI.
4 loại hình dán trên khối 40x40x40mm (dán 6 mặt, cố định):
- **Samsung (01)**: chip xanh dương — H=90-130, S>60, V>40
- **Foxconn (02)**: chip vàng đồng — H=15-40, S>60, V>80
- **Amkor (03)**: khối nhôm Al xám — S<40 (saturation thấp)
- **Hana Micron (04)**: QR code viền đỏ — H=0-10 hoặc 160-179
- Nâng 2 kiện → chia ảnh trái/phải → `classify_pair()`
- Camera resolution: 640x480

## Quy tắc quan trọng

- Số giao lộ trong route là ƯỚC LƯỢNG — đội phải đo thực tế trên sa bàn
- `TURN_TIME = 0.6s` cần calibrate trên robot thật
- `DEBUG_MODE = False` khi thi đấu
- Không có network call khi thi đấu
- Chân ECHO HC-SR04 phải qua cầu phân áp 1kΩ+2kΩ (5V→3.3V)
- Robot phải **≤ 400x400x400mm** khi xuất phát
- Khung robot **không dùng kim loại** (trừ ốc vít)
- Pin **≤ 12V, ≤ 5000mAh**
- Ánh sáng thi đấu **không đảm bảo ổn định** — cần calibrate HSV tại sân
