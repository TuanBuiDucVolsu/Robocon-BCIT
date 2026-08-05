# Bố cục kiện hàng tốt nhất — khi TỰ ĐẶT được (thi cấp trường, luyện tập)

> ⚠️ **Bản đầu của tài liệu này SAI.** Nó dựng trên giả định hai kiện cùng một cặp có
> thể CÙNG loại — khi đó robot thả một lần bằng cả hai càng và tiết kiệm rất nhiều.
> Thực tế **mỗi cặp luôn là hai loại KHÁC nhau**, nên toàn bộ phần tiết kiệm đó không
> tồn tại. Bản này viết lại theo ràng buộc đúng.

> ⛔ **RÀNG BUỘC DƯỚI ĐÂY CHỈ ĐÚNG KHI TỰ XẾP ĐƯỢC** (luyện tập, thi cấp trường).
> Vòng chính thức, BTC đặt **12 kiện NGẪU NHIÊN trên 3 giá** — nên **HAI Ô CÙNG MỘT
> TẦNG CÓ THỂ TRÙNG LOẠI**. Đừng suy ngược từ tài liệu này thành một luật trong code.
> Ngày 04/08 đã xảy ra: `classify_pair` bị cài luật "hai càng không bao giờ cùng một
> nhãn", và nó ÉP SAI một kiện đang nhận ĐÚNG. Đã gỡ.
> `main.py` vốn có sẵn nhánh "2 kiện cùng loại — giao 1 điểm duy nhất".

## Ràng buộc

Mỗi cặp (2 ô trên một tầng) là **hai nhà máy khác nhau**. 12 kiện, 4 nhà máy → mỗi
nhà máy **3 kiện**. 6 cặp, mỗi nhà máy xuất hiện đúng 3 lần → đó chính là **6 cạnh
của đồ thị đủ 4 đỉnh**, không có cách chia nào khác:

```
FOXCONN+AMKOR   FOXCONN+HANA   FOXCONN+SAMSUNG
AMKOR+HANA      AMKOR+SAMSUNG  HANA+SAMSUNG
```

Việc duy nhất còn tự do là **gán 6 cặp đó vào 6 tầng kệ**. Đã duyệt hết **720 cách**
bằng chính bộ tính chi phí của `main.py`.

## Bảng xếp — in ra, dán lên kệ

Robot lấy theo thứ tự **Kệ 3 → Kệ 2 → Kệ 1**, mỗi kệ **tầng 1 trước**.

| Thứ tự lấy | Kệ | Tầng | Hai ô |
|---|---|---|---|
| 1 | **Kệ 3** (hàng R0) | 1 | FOXCONN + AMKOR |
| 2 | **Kệ 3** | 2 | FOXCONN + HANA MICRON |
| 3 | **Kệ 2** (hàng R2) | 1 | FOXCONN + SAMSUNG |
| 4 | **Kệ 2** | 2 | AMKOR + HANA MICRON |
| 5 | **Kệ 1** (hàng R4) | 1 | HANA MICRON + SAMSUNG |
| 6 | **Kệ 1** | 2 | AMKOR + SAMSUNG |

Trái/phải trong mỗi cặp **không quan trọng** — robot tự chọn thứ tự giao rẻ hơn.

## Được bao nhiêu

| | Chi phí | Ước tính | Giao trong 240s | Điểm |
|---|---|---|---|---|
| **Bố cục này** | **198** | 381s | **8/12** | **160** |
| Xếp ngẫu nhiên | ~206 | 377s | 8/12 | 160 |
| Cách tệ nhất | 214 | 413s | 7/12 | 140 |

**Chỉ chênh ~20 điểm.** Vì mỗi lượt bốc đều buộc phải ghé **hai** nhà máy, cách xếp
không đổi được điều đó — nó chỉ rút ngắn quãng nối giữa chúng.

## Thứ thật sự chặn: thời gian, không phải cách xếp

Cần ~380s cho 12 kiện, chỉ có 240s. Độ nhạy theo từng pha:

| Đổi gì | Ước tính | Giao được | Điểm |
|---|---|---|---|
| nguyên trạng | 381s | 8/12 | 160 |
| chạy thẳng nhanh gấp 1.5 | 344s | 8/12 | 160 |
| chạy thẳng nhanh **gấp 2** | 324s | 9/12 | 180 |
| xoay nhanh gấp 2 | 355s | 8/12 | 160 |
| vào điểm cuối nhanh gấp 2 | 361s | 8/12 | 160 |
| **cả ba nhanh gấp 1.5** | 314s | 10/12 | 200 |
| **cả ba nhanh gấp 2** | 277s | **11/12** | **220** |

Đổi **một** pha thì gần như không nhúc nhích — chặn nằm ở **tổng quãng đường**, phải
kéo cả ba cùng lúc. Và ngay cả nhanh gấp đôi cũng **chưa đủ 12/12**.

⚠️ Mấy con số trên tính từ tham số MẶC ĐỊNH của `tools.dry_run` (2.5s mỗi giao lộ,
1.2s mỗi lần xoay) — đó là **số đặt tạm, chưa ai đo**. Lấy số thật:

```bash
bash scripts/practice.sh && python3 -m tools.measure_phases
```

Trước khi có số thật thì đọc bảng trên theo **tỉ lệ**, đừng theo trị tuyệt đối.

## Vậy nên làm gì

1. **Xếp theo bảng trên** — miễn phí, được ~20 điểm.
2. **Đo ngân sách thật** (`practice.sh` + `measure_phases`) trước khi tối ưu tiếp.
3. **Nâng `SPEED_DEFAULT`** (đang 50, mức bring-up) theo quy trình ở `NGHIEM_THU`
   — đo giới hạn bằng `test_motion` option 17 trước, không nâng bừa.
4. **Bật đếm giao lộ CHẠY LIỀN** (`test_motion` option 16, A/B) — đòn phần mềm mà
   mô hình trên chưa tính tới.
5. Hết 240s vẫn **giữ điểm kiện đã giao**, nên câu hỏi đúng là *"worst case được bao
   nhiêu điểm"*, không phải *"có kịp không"*.

## Xếp chồng ở nhà máy

Mỗi nhà máy nhận **3 kiện**, và vì mỗi cặp hai loại khác nhau nên robot **luôn thả
từng kiện một** — 3 lần thả riêng, tức **3 hàng** nối đuôi nhau:

```
3 × 9cm = 27cm  >  25cm chiều sâu khu nhà máy
```

**Không lọt.** Cần một trong hai:
- Lùi điểm dừng ~9-10cm cho mỗi lần thả sau, và chấp nhận kiện thứ 3 nhô ra ~2cm;
- Hoặc thả so le trái/phải — robot có 2 càng ở 2 vị trí ngang khác nhau, nên chọn
  càng nào để thả sẽ quyết định kiện nằm cột trái hay cột phải. Hai cột × 2 hàng
  đủ chỗ cho 3 kiện trong 18cm.

Cách thứ hai gọn hơn nhưng cần `main.py` chọn càng theo **số kiện đã có ở nhà máy
đó**, chứ không theo càng nào đang giữ nhãn. Chưa làm.

**Phải đo trước khi chọn cách nào** — 3 phút:

```bash
python3 -m tools.check_sees_dropped_package
```

Đặt 1 kiện đầy đủ dưới sàn trước mũi robot ~15cm, phía sau nó trống ≥60cm. Công cụ
đọc **có kiện**, rồi bảo bạn **bỏ kiện ra** và đọc lại cùng chỗ. **Chênh lệch giữa
hai lần** mới là bằng chứng — đọc một lần không phân biệt được "thấy kiện" với "thấy
thứ gì đó phía sau kiện".

| Kết quả | Hệ quả |
|---|---|
| **CÓ thấy** | Robot tự dừng trước kiện cũ, không cần đếm — nhưng khoảng hở mặc định ~14cm quá lớn cho khu 25cm, phải siết riêng cho lúc thả |
| **KHÔNG thấy** | Robot đâm vào kiện cũ. Bắt buộc đếm kiện từng nhà máy; siêu âm vô dụng ở việc này |

Nghi trước khi đo: pallet cao 26mm + khối 40mm = ~66mm, có thể **thấp hơn chùm
sóng**; và mút xốp **hút âm**, phản xạ rất kém. Nhưng đó là suy luận, không phải số.

## Trước khi chạy — 3 việc bắt buộc

1. **Gạt công tắc nửa sân đúng.** Bảng trên không phụ thuộc nửa sân (mọi cặp đều có
   mặt cả 4 nhà máy), nhưng gạt sai vẫn làm robot giao nhầm chỗ mà log không báo.
2. **Hạ càng về sàn bằng tay** (`HOME_AT_INIT = False`).
3. **Đặt robot đúng dấu đã dán** trong ô xuất phát 400×400mm.
