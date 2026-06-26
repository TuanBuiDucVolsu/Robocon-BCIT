# Lưới sa bàn O2 — đối chiếu từ file in chuẩn

> Nguồn: **file in Hiflex chính thức** `Mo rong BN 2026 O2 2m x 4m I Hiflex.pdf`
> (Google Drive trong Phụ lục 04 thể lệ). Đây là bản in thật, **đúng tỉ lệ** —
> không phải sơ đồ minh hoạ trong file Thể lệ.pdf.
>
> Sơ đồ chú thích: [sa_ban.png](sa_ban.png)

## 1. Đường màu đen = đường line

- **Nền sa bàn: sáng** (xám-trắng ~176/255)
- **Line: đen** (<80/255) → robot dò **line đen trên nền sáng**.
- Vòng tròn "ROBOCON Bắc Ninh", ảnh nhà máy, ô vuông xám (kệ/start), mascot
  **không phải line**.
- Sân **đối xứng quay 180°**: đội xanh (góc dưới-trái) và đội đỏ (góc trên-phải).

## 2. Lưới đo được (toạ độ % theo nửa sân của 1 đội)

**3 cột dọc:**

| Cột | x (%) | Vai trò |
|-----|-------|---------|
| C0  | ~12.5% | Cột kệ (kho hải quan), nối 3 kệ |
| C1  | ~37.5% | Cột trung chuyển; Kệ4 treo ngay dưới R0 |
| C2  | ~50%   | Sống giữa — cột nhà máy (chia đôi sân) |

**5 hàng ngang** (2 hàng kề nhau = **1 giao lộ**):

| Hàng | y (%) | Kệ (C0) | Nhà máy (C2) |
|------|-------|---------|--------------|
| R4 | ~17% | Kệ 1 | Samsung |
| R3 | ~33% | — | Hana Micron |
| R2 | ~50% | Kệ 2 | Liên hợp (NV2) |
| R1 | ~67% | — | Amkor |
| R0 | ~83% | Kệ 3 | Foxconn |

- Kệ chỉ có ở **R4 / R2 / R0** trên C0 (cách nhau 2 hàng).
- Nhà máy có ở **cả 5 hàng** trên C2.
- **Ô xuất phát**: ~x24% (giữa C0–C1) trên R0, robot quay mặt 9h về Kệ 3.
- **Kệ 4** (kho hàng rời, NV2): trên C1, ngay **dưới** R0.

## 3. Kết quả đối chiếu số giao lộ trong `config.py`

Đã verify bằng cách trace lưới in chuẩn — **toàn bộ khớp**:

| Route | Kết quả |
|-------|---------|
| `ROUTE_BETWEEN_FACTORIES` (6 cặp xuôi) | ✅ = hiệu số hàng (1,2,3,4) — đúng |
| `ROUTE_BETWEEN_SHELVES` (forward 2) | ✅ kệ cách 2 hàng |
| `ROUTE_SHELF_TO_FACTORY` (forward 2 ngang C0→C2) | ✅ qua C1 = 2 giao lộ |
| `ROUTE_START_TO_SHELF_0` (forward 1) | ✅ start→Kệ3 dọc R0 = 1 giao lộ |
| `ROUTE_FACTORY_TO_LOOSE` / `ROUTE_LOOSE_TO_JOINT` | ✅ Kệ4 dưới R0 tại C1 |

## 4. Cái gì lưới chuẩn **không** quyết định — vẫn phải calibrate trên sân

Số giao lộ đã chốt. Những thứ sau là **timing/cảm biến**, đo trên sân thật:

- `TURN_TIME` — thời gian xoay 90° (xem [TOC_DO.md](TOC_DO.md)).
- `LINE_KP` / `LINE_KD`, `LINE_THRESHOLD`, `INTERSECTION_THRESHOLD`.
- **⚠️ Cực kỳ lưu ý cảm biến QTR-8A:** sa bàn là **line đen / nền sáng** (khớp giả
  định config). Nhưng nhiều module QTR-8A đọc bề mặt **đen ra giá trị CAO** (ngược).
  **Đã làm sẵn cơ chế xử lý:** chạy trên Pi:

  ```bash
  python3 -m tools.calibrate_line
  ```

  Tool đo line đen vs nền sáng rồi gợi ý `LINE_BLACK_IS_HIGH` (True/False) và
  `LINE_THRESHOLD`. Chỉ cần đặt `LINE_BLACK_IS_HIGH` trong [config.py](../config.py)
  — code **tự đảo tín hiệu tại nguồn**, không phải sửa gì khác. Bỏ qua bước này mà
  cảm biến đọc ngược → robot dò line ngược hoàn toàn.
