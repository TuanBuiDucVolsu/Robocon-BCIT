# Diễn tập — test sát điều kiện thi đấu

`TEST_CASE.md` kiểm **từng module hoạt động đúng không**. File này kiểm **có ăn được
điểm trong 240 giây thật không** — hai chuyện khác nhau.

Mọi thứ dưới đây chạy trên **sa bàn thật**, robot chạy **trọn trận**, có bấm đồng hồ.

```bash
bash scripts/practice.sh        # chế độ luyện tập: 1 lượt → nhấn nút → lặp
```

---

## Vì sao test theo module không đủ

| Chuyện chỉ xuất hiện trong trận thật | Test module có bắt được không |
|---|---|
| Có kịp 240s không | ❌ |
| BTC xếp kiện ngẫu nhiên — kịch bản xấu tốn **2.17 lần** kịch bản đẹp | ❌ |
| Trọng tài cho reset giữa trận (5 lần, −10đ/lần) | ❌ |
| Pin tụt sau vài trận → `TURN_TIME`, `LIFT_TIME_*` lệch dần | ❌ |
| Ánh sáng sân đấu khác phòng lab | ❌ |
| Robot lỗi giữa trận → systemd restart → chạy nốt giờ còn lại | ❌ |

---

## DT-1. Ngân sách thời gian — làm ĐẦU TIÊN

Không có số này thì mọi tối ưu đều là đoán.

```bash
bash scripts/practice.sh        # chạy 1 lượt đầy đủ, bấm đồng hồ đối chiếu
```

Cuối lượt, log in bảng **Thời gian từng chặng**:

```
--- Thời gian từng chặng ---
  DELIVER_FIRST              62.3s  31.2%  (6 lần, TB 10.4s)
  RETURN_TO_WAREHOUSE        48.1s  24.1%  (6 lần, TB 8.0s)
  PICKUP_PAIR                35.0s  17.5%  (6 lần, TB 5.8s)
  ...
  Trung bình 16.6s/kiện — nhịp này giao đủ 12 kiện mất 199s
```

Lấy số đo thật đó nạp vào bộ ước tính để suy ra **kịch bản xấu nhất**:

```bash
python3 -m tools.estimate_time --forward 2.5 --turn 1.2 --lift 5.1 \
                               --approach 3.0 --advance 2.0 --scan 1.0
```

> ⚠️ **Với các số ước lượng mặc định, kết quả hiện tại là KHÔNG KỊP**: kịch bản đẹp
> ~251s, kịch bản xấu ~467s, trong khi giới hạn là 240s. Các số này là **phỏng đoán**
> — phải đo thật rồi chạy lại. Nếu đo thật vẫn không kịp thì phải chọn chiến lược
> (xem DT-2), chứ không thể vừa giao đủ 12 kiện vừa làm NV2.

**Đạt khi:** kịch bản **xấu nhất** < 230s (240 trừ `SAFETY_MARGIN`).

**Chặng nào ăn nhiều giây nhất thì tối ưu chặng đó trước.** Độ nhạy đã đo:

| Cải thiện | Tiết kiệm (kịch bản xấu) |
|---|---|
| Giao lộ 2.5s → 1.5s | −66s |
| Xoay 1.2s → 0.6s | −46s |
| Nâng/hạ 5.1s → 3.0s | −38s |
| Tiếp cận+lùi 3.0s → 1.5s | −35s |
| Advance 2.0s → 1.0s | −17s |

Đòn bẩy lớn nhất là **giây/giao lộ** — hiện robot **dừng hẳn ở mỗi giao lộ** rồi tăng
tốc lại (`follow_line` gọi `stop()`, sau đó `_escape_intersection` chạy mù 0.3s). Một
lượt đi qua 10–13 giao lộ, nên chỉ riêng việc dừng/tăng tốc đã ăn rất nhiều.

---

## DT-2. Kịch bản xếp kiện XẤU NHẤT

Chạy thử với kiện xếp ngẫu nhiên rồi kết luận "kịp giờ" là tự lừa mình — chênh lệch
giữa kịch bản đẹp và xấu là **2.17 lần**.

Xếp kiện đúng bảng này rồi chạy trọn trận:

| Kệ | Tầng | Kiện trái | Kiện phải |
|---|---|---|---|
| Kệ 3 (R0) | 1 | Amkor | Hana Micron |
| Kệ 3 (R0) | 2 | Amkor | Hana Micron |
| Kệ 2 (R2) | 1 | Amkor | Hana Micron |
| Kệ 2 (R2) | 2 | Amkor | Hana Micron |
| Kệ 1 (R4) | 1 | Foxconn | Amkor |
| Kệ 1 (R4) | 2 | Foxconn | Amkor |

> Tự tính lại nếu đổi bản đồ hoặc nửa sân: các cặp này là kết quả duyệt toàn bộ tổ hợp
> bằng `navigation.route_cost` — chạy lại phần tính trong `tools/estimate_time.py`.

Chạy **cả 2 kịch bản** để biết biên trên và biên dưới:
- **Xấu nhất** — bảng trên
- **Đẹp nhất** — Kệ 3 cả 4 kiện Foxconn, Kệ 2 và Kệ 1 cả 8 kiện Samsung

**Đạt khi:** kịch bản xấu vẫn giao được ≥ 8 kiện trong 240s (160 điểm). Giao đủ 12 kiện
ở kịch bản xấu là mục tiêu lý tưởng, không phải điều kiện tối thiểu.

---

## DT-3. Diễn tập RESET giữa trận ★

Luật cho **5 lần reset**, mỗi lần **−10 điểm**, đội viên **đặt tay** robot về ô xuất
phát. Đây là tình huống chắc chắn xảy ra, không phải ngoại lệ.

**Quy trình:**
1. Chạy `practice.sh`, để robot chạy tới giữa trận (đang giao hàng hoặc đang về kho)
2. **Bấm nút khởi động** → robot phải **dừng ngay** (không chờ hết timeout)
3. Nhấc robot đặt về ô xuất phát, đúng tư thế thi đấu
4. Robot tự chạy tiếp

**Đạt khi:**
- Robot dừng trong **dưới 1 giây** kể từ lúc bấm nút
- Log in khối `RESET lần N` kèm tiến độ giữ nguyên
- Càng được hạ về sàn trước khi xuất phát lại
- Robot xuất phát lại đúng như đầu trận và **đi tiếp đúng kệ/tầng đang dang dở** —
  không quay về lấy lại kiện đã lấy
- **Đồng hồ trận KHÔNG được cộng thêm giây nào**

**Làm thêm:** reset đúng lúc robot **đang mang 2 kiện** — kiện rơi ra thì đó là kiện
mất, robot phải đi tiếp chứ không được treo.

> Trước khi có cơ chế này, bấm nút giữa trận không có tác dụng gì: robot vẫn tưởng
> mình đang ở nhà máy và lái tiếp từ ô xuất phát → chạy loạn. Đã có test tự động
> (`test_match_sim.TestMidMatchReset`) nhưng **phải diễn tập tay** vì phần "dừng trong
> 1 giây" phụ thuộc phần cứng.

---

## DT-4. Diễn tập SỰ CỐ — robot lỗi giữa trận

Chế độ thi đấu (`ROBOT_COMPETE=1`) có systemd `Restart=on-failure`: lỗi → thoát mã 1 →
khởi động lại → đọc `MATCH_STATE_FILE` để chạy **nốt thời gian còn lại**.

**Quy trình:**
1. Chạy chế độ thi đấu: `sudo systemctl start robot`
2. Giữa trận: `sudo pkill -9 -f main.py`
3. Đợi systemd khởi động lại (RestartSec=2)
4. Đặt robot về ô xuất phát, bấm nút

**Đạt khi:** log in `KHÔI PHỤC sau lỗi — đồng hồ gốc, còn ~Ns` với **N < 240 trừ số
giây đã trôi**. Nếu in đúng 240s là cơ chế resume hỏng.

> ⚠️ Khác DT-3: sau restart thì **tiến độ mất** (robot lấy lại từ Kệ 3). Kiện đã lấy
> khỏi kệ không còn ở đó → pickup fail → bỏ tầng → mất thời gian. Vì vậy **reset bằng
> nút (DT-3) luôn tốt hơn** để robot crash; chỉ dùng restart khi robot thật sự treo.

---

## DT-5. Pin tụt

Motor chậm dần khi pin yếu → `TURN_TIME` xoay thiếu góc, `LIFT_TIME_*` nâng thiếu tầng.
Calibrate lúc pin đầy rồi thi đấu lúc pin 60% là sai hết.

**Quy trình:** sạc đầy → chạy **4 trận liên tiếp** không sạc → sau mỗi trận chạy
`test_motion` #10 (xoay 90°) và `test_lift` #e (so 2 càng), ghi lại.

**Đạt khi:** sau 4 trận, góc xoay lệch < 10° và 2 càng vẫn ngang nhau.
Không đạt → sạc giữa các trận, hoặc hạ `SPEED_*` để bớt nhạy với điện áp.

---

## DT-6. Ánh sáng sân đấu

CLAUDE.md đã ghi: ánh sáng thi đấu **không đảm bảo ổn định**.

**Quy trình:** tại sân, dưới đúng ánh sáng thi đấu:
```bash
python3 -m tools.capture_templates    # chụp LẠI ảnh mẫu ORB
python3 tests/test_vision.py          # #9 (ORB) → #2 (HSV) → #6 → #l
```

**Đạt khi:** `#9` cho kiện đúng ≥ 6 inlier và cách kiện thứ nhì ≥ 2 lần; `#l` báo
ánh xạ trái/phải ĐÚNG.

> Ảnh mẫu chụp ở phòng lab thường không dùng được ở sân. Đây là việc **bắt buộc làm
> tại sân**, không làm trước được.

---

## DT-7. Nửa sân đối diện

Chạy lại **toàn bộ** DT-1 và DT-2 sau khi gạt công tắc sang nửa kia.

```bash
python3 -m tools.check_board_side     # xác nhận đã gạt đúng
python3 -m tools.show_routes          # route đổi theo, đối chiếu lại với sa bàn
```

**Đạt khi:** thời gian và số kiện giao được ở 2 nửa **xấp xỉ nhau**. Lệch nhiều =
bản đồ một nửa chưa đúng.

---

## DT-8. Bấm nút đúng hiệu lệnh

Luật: khởi động **trước** hiệu lệnh → cảnh báo lần 1, **lần 2 bị loại**.

Robot chỉ chạy khi bấm nút, nên rủi ro nằm ở người. Diễn tập: một người hô "BẮT ĐẦU",
người bấm nút chỉ được chạm nút **sau** tiếng hô. Làm 5 lần.

> Lưu ý: từ sau lần bấm đầu, **nút chuyển thành nút RESET**. Chạm nhầm giữa trận =
> mất 10 điểm. Nhắc cả đội không tì tay lên robot.

---

## DT-9. Dừng khẩn cấp

Robot lao ra khỏi sa bàn hoặc sang sân đối phương → phải dừng được ngay bằng tay.

**Quy trình:**
1. Chạy `practice.sh`, để robot đang chạy giữa chừng
2. `Ctrl+C` ở terminal (hoặc `sudo systemctl stop robot` ở chế độ thi đấu)

**Đạt khi:**
- Cả 4 motor (2 bánh + 2 càng) **dừng ngay**, không có bánh nào quay tiếp
- Càng không rơi tự do
- Log in `DỪNG KHẨN CẤP`
- File `/tmp/robot_match_state` **bị xoá** (dừng chủ động ≠ sự cố, lần chạy sau
  phải là trận mới với đủ 240s chứ không resume trận cũ)

> Nếu bánh vẫn quay sau khi dừng → xem [DEBUG_DONG_CO.md](DEBUG_DONG_CO.md), đây là
> lỗi phần cứng L298N đã từng gặp (có sẵn `tools.test_right_wheel` để cô lập).

---

## Checklist ngày thi đấu

**Trước khi vào sân**
- [ ] `python3 -m pytest tests/ -q` → `187 passed`
- [ ] Pin đầy, đo điện áp
- [ ] Robot lọt khuôn 400×400×400mm

**Sau khi bốc thăm biết nửa sân**
- [ ] Gạt công tắc nửa sân, `python3 -m tools.check_board_side` xác nhận
- [ ] Đứng ở ô xuất phát nhìn sang tường: cụm nhà máy **cùng hàng** đúng như công tắc
- [ ] `python3 -m tools.show_routes` — liếc lại tuyến đầu tiên

**Tại sân, trước trận**
- [ ] Chụp lại ảnh mẫu ORB dưới ánh sáng sân (DT-6)
- [ ] `test_motion` #10 xác nhận góc xoay còn đúng với mức pin hiện tại
- [ ] `test_lift` #e xác nhận 2 càng còn ngang nhau
- [ ] Chạy 1 lượt `practice.sh` xác nhận toàn tuyến

**Ngay trước hiệu lệnh**
- [ ] Robot đúng ô xuất phát, đúng hướng
- [ ] Đọc log: dòng `NỬA SÂN: ... = FOXCONN/SAMSUNG` đúng chưa
- [ ] Không ai tì tay lên nút
- [ ] Phân công sẵn người bấm nút reset khi trọng tài cho phép

**Trong trận**
- [ ] Robot lệch/kẹt → xin reset → bấm nút → đặt về ô xuất phát (đừng chờ nó tự thoát)
- [ ] Đếm số lần reset, tối đa 5
