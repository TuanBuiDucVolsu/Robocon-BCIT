# Bố cục kiện hàng "dễ nhất" — dùng khi TỰ ĐẶT được (thi cấp trường, luyện tập)

> ⚠️ **Chỉ dùng khi được tự xếp.** Thi chính thức thì **BTC xếp NGẪU NHIÊN** — bố cục
> này không mang ra đó được. Nó để chứng minh luồng chạy thông và lấy điểm ở vòng
> mà mình chủ động xếp.

## Bảng xếp — in ra, dán lên kệ

Robot lấy hàng theo đúng thứ tự này: **Kệ 3 → Kệ 2 → Kệ 1**, mỗi kệ **tầng 1 trước, tầng 2 sau**.

| Thứ tự lấy | Kệ | Tầng | Ô TRÁI | Ô PHẢI |
|---|---|---|---|---|
| 1 | **Kệ 3** (hàng R0) | 1 | FOXCONN | FOXCONN |
| 2 | **Kệ 3** | 2 | FOXCONN | FOXCONN |
| 3 | **Kệ 2** (hàng R2) | 1 | AMKOR | AMKOR |
| 4 | **Kệ 2** | 2 | HANA MICRON | HANA MICRON |
| 5 | **Kệ 1** (hàng R4) | 1 | SAMSUNG | SAMSUNG |
| 6 | **Kệ 1** | 2 | SAMSUNG | SAMSUNG |

Tổng: Foxconn 4 · Samsung 4 · Amkor 2 · Hana Micron 2 = **12 kiện**.

## Vì sao bố cục này

**Đòn bẩy 1 — hai kiện cùng cặp CÙNG LOẠI.** Robot thả **một lần bằng cả hai càng**
(`drop_both`), bỏ hẳn chặng giao thứ hai và bước nâng lại càng. Sáu lượt bốc chỉ còn
**sáu** chặng giao thay vì tối đa mười hai.

**Đòn bẩy 2 — nhà máy CÙNG HÀNG với kệ.** Kệ 3 ở R0 cùng hàng **Foxconn**; Kệ 1 ở R4
cùng hàng **Samsung**. Hai tuyến đó ngắn nhất trong toàn bộ bản đồ. Kệ 2 ở R2 thì
Amkor (R1) và Hana (R3) đều chỉ cách một hàng.

## Chênh lệch đo được (`tools.dry_run`)

| | Bố cục này | Trộn đều (mặc định) |
|---|---|---|
| Số bước | **133** | 190 |
| Ước tính | **264s** | 377s |
| Giao được trong 240s | **12/12** | 8/12 |
| **Điểm NV1** | **240** | 160 |
| Lệnh xoay | 34 | 42 |

Chênh **80 điểm**, chỉ do cách xếp — không đụng một dòng code nào.

Xem từng bước:
```bash
python3 -m tools.dry_run --scenario "foxconn,foxconn foxconn,foxconn amkor,amkor hana_micron,hana_micron samsung,samsung samsung,samsung"
```

## Nó cũng giải luôn bài toán xếp chồng ở nhà máy

Mỗi nhà máy nhận **số CHẴN** kiện, mà robot thả hai kiện **cạnh nhau** trong một lần
hạ càng. Nên:

| Nhà máy | Nhận | Số HÀNG kiện phải xếp | Chiều sâu cần |
|---|---|---|---|
| Foxconn, Samsung | 4 | **2 hàng** (2 lần thả × 2 kiện) | 2 × 9 = **18cm** |
| Amkor, Hana | 2 | **1 hàng** | 9cm |

Khu nhà máy sâu **25cm** → vừa thoải mái. Còn bố cục trộn đều thì có nhà máy phải
xếp **3 hàng = 27cm > 25cm**, không lọt.

⚠️ Vẫn cần **lùi điểm dừng ~10cm cho lần thả THỨ HAI** ở Foxconn và Samsung, không
thì kiện mới đè lên kiện cũ. Đây là việc chưa làm — xem phần cuối.

## Thứ tự việc robot làm (để đứng ngoài đối chiếu)

```
xuất phát → Kệ 3 T1 → giao Foxconn (thả 2 càng) → về Kệ 3
          → Kệ 3 T2 → giao Foxconn              → về Kệ 2
          → Kệ 2 T1 → giao Amkor                → về Kệ 2
          → Kệ 2 T2 → giao Hana Micron          → về Kệ 1
          → Kệ 1 T1 → giao Samsung              → về Kệ 1
          → Kệ 1 T2 → giao Samsung              → NV2
```

## Trước khi chạy — 3 việc bắt buộc

1. **Gạt công tắc nửa sân đúng.** Bảng trên viết cho nửa sân có Foxconn cùng hàng ô
   xuất phát. Nửa kia thì **đảo Foxconn ↔ Samsung** trong bảng. Kiểm bằng mắt: đứng ở
   ô xuất phát nhìn sang tường, khu ngang tầm mình là khu nào.
2. **Hạ càng về sàn bằng tay** (`HOME_AT_INIT = False`).
3. **Đặt robot đúng dấu đã dán** trong ô xuất phát 400×400mm.

## Còn thiếu gì để chạy được bố cục này

| | Trạng thái |
|---|---|
| Lùi điểm dừng cho lần thả thứ 2 cùng nhà máy | ❌ **chưa làm** — cần đo siêu âm có thấy kiện đã thả không |
| `test_smoke` option 5 chạy trọn 3/3 lần | ❌ chưa |
| `test_smoke` option 8 chạy trọn 3/3 lần | ⚠️ đã mượt 1 lần |
| Nhận diện 4/4 ô | ✅ đã đạt (chụp lại ảnh mẫu nếu đổi sân/ánh sáng) |
