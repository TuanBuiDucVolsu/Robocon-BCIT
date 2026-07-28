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

### ⚠️ Ảnh này chỉ là MỘT NỬA sân

Sa bàn 4000x2000 chia đôi thành **2 nửa 2000x2000**, ngăn bởi **bức tường giữa sân**
(cột dọc dày ở mép phải ảnh). Khu nhà máy in trên **cả 2 mặt tường** — đó là lý do
trong ảnh thấy ảnh nhà máy lặp lại ở cả hai bên tường, cùng thứ tự Samsung(trên) →
Foxconn(dưới): đó là **một bức tường 2 mặt**, mỗi đội nhìn thấy cùng cụm nhà máy từ
phía mình.

Ảnh bị kéo giãn không đều (1500x750 px cho vùng 2000x2000mm): thang ngang ≈1.49
mm/px, thang dọc ≈2.67 mm/px. Kiểm chứng: ô kệ trong ảnh 81x85 px → 120mm sâu x
227mm rộng ≈ giá kệ 240x120mm đặt quay mặt 240mm ra sân ✓.

**Nửa còn lại** — xem `docs/Sa bàn đầy đủ.png` (ảnh cả sân) thì rõ:

- Robot mascot của đội góc trên-phải vẽ **lộn ngược** → nửa kia là bản **QUAY 180°**
  của nửa này. Phép quay **bảo toàn chiều trái/phải** → đứng ở ô xuất phát quay mặt
  về phía kệ thì ở CẢ HAI nửa, các kệ còn lại đều nằm bên **tay phải** robot.
- Ô xuất phát, Kệ 4, vòng tròn ROBOCON, khoảng đứt line — đều đối xứng quay 180° ✓
- **NHƯNG cụm nhà máy in trên TƯỜNG thì không quay theo**: hai đội nhìn chung một tấm
  panel nên Samsung luôn ở một đầu tường, Foxconn ở đầu kia.

→ Khác biệt thật giữa 2 nửa là **THỨ TỰ NHÀ MÁY THEO HÀNG**, không phải chiều xoay:

| Trong hệ quy chiếu robot | Đội góc dưới-trái | Đội góc trên-phải |
|---|---|---|
| `config.FACTORY_AT_START_ROW` | `"foxconn"` | `"samsung"` |
| Cùng hàng ô xuất phát (R0) | Foxconn | **Samsung** |
| R1 | Amkor | Hana Micron |
| R2 | Liên hợp | Liên hợp |
| R3 | Hana Micron | Amkor |
| R4 (xa nhất) | Samsung | **Foxconn** |

**Robot KHÔNG tự dò được cái này** — qua cảm biến line hai nửa giống hệt nhau. Kiểm 5
giây bằng mắt: đứng ở ô xuất phát nhìn sang tường, cụm nhà máy **cùng hàng** ô xuất
phát là cụm nào. Đặt sai = giao Samsung vào Foxconn; IR vẫn báo thả thành công nên
log KHÔNG báo lỗi, chỉ mất sạch điểm.

Chiều trái/phải thì robot **tự dò** đầu trận (state `DETECT_SIDE`) để phòng bản in
sai — dò được nhờ một điểm bất đối xứng: tại giao lộ Kệ 3, đường line dọc cột kệ
**chỉ chạy về MỘT phía** (lên R2/R4), phía kia là mép sa bàn.

```
Robot đứng tại giao lộ Kệ 3, quay mặt về phía kệ:
   xoay phải 90° → tiến ~10-15cm → đọc cảm biến line → lùi lại → xoay về
      thấy line   → chiều CHUẨN (đúng bản in)
      không thấy  → chiều ngược → tự nạp lại bản đồ gương
```

Phải **tiến ra khỏi giao lộ** rồi mới đọc: ngay tại điểm giao, đường line cắt ngang
nằm dọc theo thanh cảm biến nên xoay kiểu gì mọi mắt cũng thấy đen.

Khoảng cách và số giao lộ **giống hệt** ở cả 2 nửa.

| Hằng số | Vai trò |
|---|---|
| `FACTORY_AT_START_ROW` | **Nửa sân — thứ tự nhà máy.** Phải đặt tay, kiểm bằng mắt |
| `BOARD_AUTO_DETECT` | Bật tự dò chiều trái/phải (mặc định `True`) |
| `BOARD_MIRRORED` | Dự phòng chiều trái/phải khi dò lỗi (bản in: cả 2 nửa `False`) |
| `PROBE_TRAVEL_TIME` | Giây tiến ra khỏi giao lộ khi dò — đo trên sân |

Kiểm tra tay: `python3 tests/test_motion.py` → option **13**.
Xem route đang dùng: `python3 -m tools.show_routes` (dòng đầu in rõ nửa nào).

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

## 3. Đường line THẬT SỰ có trên bản in (đo lại bằng quét pixel)

> ⚠️ Mục này thay cho bảng "toàn bộ khớp" trước đây. Bảng cũ đếm **hàng/cột trên
> lưới**, nhưng robot chỉ đếm được **giao lộ mà cảm biến thật sự thấy** — tức là chỗ
> có 2 đường line CẮT nhau. Hai thứ này khác nhau ở đúng những chỗ quan trọng nhất.

Cách đo lại (chạy được trên PC, không cần Pi):

```bash
python3 -c "
import cv2, numpy as np
g = cv2.cvtColor(cv2.imread('docs/sa_ban.png'), cv2.COLOR_BGR2GRAY)
d = g < 100
print('cột có line:', [x for x in range(g.shape[1]) if d[:,x].sum() > 400])
print('hàng có line:', [y for y in range(g.shape[0]) if d[y].sum() > 400])"
```

**Kết quả đo (ảnh 1500x750):**

| Đường | Toạ độ | Phạm vi | Ý nghĩa |
|-------|--------|---------|---------|
| Cột kệ **C0** | x≈340 | y 128→620 liền mạch | nối Kệ1–Kệ2–Kệ3 |
| Cột giữa **C1** | x≈1022 | y 128→705 | nối cả 5 hàng + thò xuống Kệ 4 |
| Hàng **R4** | y≈128 | x 89→**1195** | Kệ 1 → khu Samsung |
| Hàng **R3** | y≈250 | x **1016**→1185 | **chỉ từ C1** sang Hana |
| Hàng **R2** | y≈375 | x 89→**491**, **872**→1277 | **ĐỨT ~560mm** ở vòng tròn ROBOCON |
| Hàng **R1** | y≈495 | x **1016**→1186 | **chỉ từ C1** sang Amkor |
| Hàng **R0** | y≈620 | x 89→615, 782→1208 | **ĐỨT ~245mm** ở ô xuất phát |

**4 hệ quả bắt buộc phải theo:**

1. **R1 và R3 không kéo tới cột kệ** → trên cột kệ chỉ có **3 giao lộ** (R4/R2/R0).
   Kệ ↔ kệ = **1 giao lộ**, không phải 2.
2. **Line ngang dừng ở mép khu nhà máy**, không cắt sống giữa sân → **giữa các khu
   nhà máy KHÔNG có line nối dọc**. Giao kiện thứ 2 phải quay về cột C1 rồi đi dọc C1.
3. **Khu nhà máy / kệ / Kệ 4 là ĐIỂM CUỐI của line, không phải giao lộ** → không đếm
   được bằng `("forward", N)`. Dùng lệnh `("advance",)` (bám line tới hết line) rồi
   `approach_shelf()` canh nốt bằng siêu âm.
4. **Hàng R2 bị vòng tròn ROBOCON cắt đứt 560mm** → cấm đi thẳng Kệ 2 ↔ cột giữa;
   robot phải vòng qua R4 hoặc R0. Khoảng đứt 245mm ở ô xuất phát thì vượt được
   (xem `config.LINE_GAP_COAST_TIME`) nhưng bị tính thêm chi phí để ưu tiên tuyến sạch.

Bản đồ này được khai báo **một chỗ duy nhất**: `navigation.NODES` / `EDGES` /
`TERMINALS`. Route không còn viết tay — xem mục 5.

## 5. Xem và kiểm tra route

```bash
python3 -m tools.show_routes                  # in cả 40+ tuyến
python3 -m tools.show_routes SHELF1 F_samsung # in 1 tuyến
python3 -m unittest tests.test_logic -v       # mô phỏng: route có tới đúng chỗ không
```

Nếu một tuyến không khớp sa bàn thật → **sửa bản đồ trong `navigation.py`**, đừng sửa
từng route: mọi route đều được tính lại từ bản đồ đó.

## 4. Cái gì bản đồ **không** quyết định — vẫn phải calibrate trên sân

Số giao lộ suy ra từ bản đồ. Những thứ sau là **timing/cảm biến**, đo trên sân thật:

- `TURN_TIME` — thời gian xoay 90° (xem [TOC_DO.md](TOC_DO.md)).
- `LINE_KP` / `LINE_KD`, `LINE_THRESHOLD`, `INTERSECTION_THRESHOLD`.
- `LINE_GAP_COAST_TIME` — thời gian trôi thẳng khi mất line, phải đủ để vượt khoảng
  đứt 245mm ở ô xuất phát nhưng không quá dài (lạc thật mà vẫn chạy tiếp).
- **Bẫy giao lộ giả ở vòng tròn ROBOCON:** 2 cung ellipse dày cắt ngang hàng R2 tại
  x≈491 và x≈872. Nếu robot có lý do đi qua đó, ≥4/6 mắt sẽ thấy đen và báo giao lộ
  giả. Bản đồ đã cấm đoạn này, nhưng cần xác nhận trên sân là robot không bao giờ
  chạm vào.
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
