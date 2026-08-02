# Nghiệm thu — ĐẠT / CHƯA ĐẠT bằng số

In tờ này, cầm theo **thước lá** và **ke vuông**. Mỗi bước có tiêu chí bằng SỐ, không
phải "thấy có vẻ ổn".

> **Nguyên tắc bao trùm: một lần đúng KHÔNG phải là đạt.**
> Trận đấu có 6 lượt lấy hàng và 5 lần reset. Cơ cấu nào chỉ đúng 1/3 lần thì trong
> trận nó sai 2/3 lần. **Mọi bước dưới đây phải lặp 3 lần liên tiếp cùng kết quả.**
> Lần 2 hỏng thì tiêu chí CHƯA ĐẠT, không phải "chắc do xui".

> ⚠️ Ba thay đổi ngày 02/08 **chưa chạy trên robot lần nào**: bám line khi tiến sát
> kệ (`_forward_guided`), cửa sổ mù lúc xuất phát (`EXIT_START_BLIND_TIME`), dừng có
> giảm tốc (`stop_gently`). Vòng A–C dưới đây chính là để nghiệm thu chúng.

---

## VÒNG A — Số nền. Không có A thì mọi thứ sau đều là đoán

Sàn phẳng, có thể chưa cần sa bàn. Khoảng 30 phút.

### A1 · Xoay 90° hai chiều — `test_motion` **2**

Đặt ke vuông trên sàn, dán băng dính đánh dấu hướng đầu robot trước và sau.

| | |
|---|---|
| **ĐẠT** | Mỗi chiều **90° ± 5°**, VÀ chênh lệch giữa hai chiều **≤ 3°** |
| **CHƯA ĐẠT** | Lệch > 5°, hoặc hai chiều chênh nhau > 3° |
| **Sửa** | Lệch đều cả hai chiều → chỉnh `TURN_TIME`. **Hai chiều chênh nhau thì `TURN_TIME` không cứu được** — chỉ có một hằng số cho cả hai chiều, phải sửa `PWM_COMPENSATION_*_REV` |

Vì sao ±5°: chặng giữa hai giao lộ dài 66–100cm. Lệch 5° trên 66cm là trôi ngang
5.8cm, mà thanh cảm biến chỉ rộng ~60mm — quá 5° là robot ra khỏi vạch trước khi PD
kịp kéo lại. **Chênh lệch giữa hai chiều quan trọng hơn trị tuyệt đối.**

### A2 · Bù PWM CẢ 2 CHIỀU — `test_motion` **f** 🔑

⚠️ **ĐO BẰNG THƯỚC MỚI LÀ CHÍNH, encoder chỉ để tham khảo.** Đo trên robot 02/08:
tỉ lệ xung 2 bánh tản **±5%** và tổng xung tản **±10%** giữa 3 lượt **cùng cấu hình**
— nhiễu LỚN HƠN thứ cần đo (lệch 2 bánh thường 2-5%). Nguyên nhân: encoder
JGA25-370 xung rất dày, callback gpiozero rớt xung và 2 bên rớt không như nhau.
Vòng chỉnh theo encoder đã dao động thật: 3.8% → 7.9% → 9.0%.

Encoder (`f` → **t**/**l**) chỉ dùng để **thấy nhanh bên nào nhanh hơn**; nếu nó báo
"TỈ LỆ TẢN ... PHÉP ĐO KHÔNG DÙNG ĐƯỢC" thì bỏ qua, xuống thẳng phép đo thước.

**Phép đo quyết định:** hạ robot xuống, dán vạch thẳng 2m, chạy dọc theo, đo trôi ngang:

| | Tiến | Lùi |
|---|---|---|
| **ĐẠT** | ≤ **2cm / 2m** | ≤ **2cm / 2m** |
| **Sửa** | xem bảng chiều ngay dưới | |

**⚠️ CHIỀU CHỈNH — dễ nhầm, nhầm là càng chỉnh càng lệch.** Bánh nhanh hơn nằm ở
PHÍA NGOÀI vòng cua, nên robot cong về phía bánh CHẬM:

| Robot cong về | Bánh nhanh hơn | Hạ hệ số của bánh đó |
|---|---|---|
| **TRÁI** | **PHẢI** | tiến: `PWM_COMPENSATION` · lùi: `PWM_COMPENSATION_REV` |
| **PHẢI** | **TRÁI** | tiến: `PWM_COMPENSATION_LEFT` · lùi: `PWM_COMPENSATION_LEFT_REV` |

Mỗi lần 0.02, đo lại, lặp tới khi ≤2cm/2m.

2cm/2m ≈ 0.6°. **Chiều lùi bắt buộc phải đạt** — mọi tuyến giao hàng đều mở đầu
bằng `LÙI 1 giao lộ`, khoảng 28 lần mỗi trận.

⚠️ **Đây là bài đang chặn nhiều thứ nhất.** Lùi không thẳng thì robot tới giao lộ
trong tư thế CHÉO — đo được trên robot: cùng một bước lùi, hai lần chạy cho
`[0,0,1,1,1,1]` và `[1,0,1,1,1,0]` (mắt 1 trắng kẹp giữa hai mắt đen, tức nằm
chéo). Xoay từ tư thế chéo thì văng khỏi line, và **kết quả đổi theo từng lần** —
loại lỗi không thể gỡ bằng cách chỉnh hằng số nào khác.

### A3 · Đo cm/s — `test_motion` **1**

Cho tiến đúng **1.0 giây** ở tốc độ 50, đo bằng thước. Lặp **3 lần**.

| | |
|---|---|
| **ĐẠT** | Trung bình nằm trong **15–40 cm/s**, VÀ 3 lần chênh nhau **≤ 10%** |
| **CHƯA ĐẠT** | Ngoài dải → sai giả định thiết kế. Chênh > 10% → pin yếu hoặc motor lệch |

**Ghi lại con số này.** Nó chốt hai thứ đang treo:
- `EXIT_START_BLIND_TIME` = **45 ÷ (cm/s)**, nhưng **không quá 1.5**
- đối chiếu `--forward` của `tools.dry_run` (đang để 2.5s/giao lộ — chỉ là placeholder)

### A4 · Lùi bám line — `test_motion` **15**

| | |
|---|---|
| **ĐẠT** | Đi hết chặng, biên độ lắc ngang **≤ ±2cm** và **không tăng dần**, dừng đúng giao lộ |
| **CHƯA ĐẠT** | Lắc tăng dần, hoặc văng khỏi vạch, hoặc không tới giao lộ |
| **Sửa** | Lắc tăng dần = dấu hiệu kinh điển của **sai dấu hiệu chỉnh khi lùi**. Trôi lệch một bên đều đều = `PWM_COMPENSATION_REV` |

### A5 · Rút khỏi kệ → xoay → bám line — `test_motion` **18** 🔑

**Mở đầu của MỌI tuyến giao hàng.** Đặt robot sát kệ, quay mặt vào kệ.

Bài này xâu **3 thứ chưa thứ nào được xác nhận**, và sai số của chúng **cộng dồn**
trước khi tới bước bám line — chạy rời từng cái thì mỗi cái "có vẻ ổn" mà ghép lại
vẫn trượt:

| Bước | Dựa vào | Tình trạng |
|---|---|---|
| lùi tới giao lộ | `PWM_COMPENSATION_REV` | ❌ chưa calibrate bao giờ |
| tiến bù | `REVERSE_RECENTER_TIME` = 1.3s | ★ đã chỉnh tay |
| xoay | `TURN_TIME` | ⚠️ mới xác nhận chiều TRÁI |

| | |
|---|---|
| **ĐẠT [1/3]** | Lùi thẳng, lắc ngang ≤ ±2cm và **không tăng dần**; sau khi tiến bù, **trục bánh nằm trên vạch ngang, lệch ≤ 2cm** |
| **ĐẠT [2/3]** | Sau khi xoay, **≥ 1 mắt** thấy line |
| **ĐẠT [3/3]** | Tới đủ số giao lộ, không mất line giữa chừng, robot đi **giữa vạch** chứ không men mép. **3/3 lần** |
| **CHƯA ĐẠT** — lắc tăng dần khi lùi | Dấu đảo hiệu chỉnh khi lùi SAI |
| **CHƯA ĐẠT** — lùi trôi lệch đều một bên | `PWM_COMPENSATION_REV` |
| **CHƯA ĐẠT** — xoay xong không mắt nào thấy line | Chạy option **10** riêng cho chiều đó: đúng 90° thì lỗi ở `REVERSE_RECENTER_TIME`, sai 90° thì lỗi ở `TURN_TIME` |
| **CHƯA ĐẠT** — mất line ngay sau khi xoay | Sai số 3 bước cộng dồn quá lớn — quay lại A1 và option 15 tách riêng |

Ghi lại **giây/giao lộ** ở bước [3/3] để đối chiếu `--forward` của `tools.dry_run`.

Option **15** chỉ chạy bước 1 và đọc cảm biến một lần sau khi xoay — dùng nó khi cần
soi riêng phần lùi. Option **18** mới là bài nghiệm thu.

---

## VÒNG B — Từng cơ cấu. Khoảng 30 phút

### B1 · Độ cao càng — `test_lift` **d** rồi **e**

Đo bằng thước từ sàn lên mặt trên càng, ở cả hai tầng.

| | |
|---|---|
| **ĐẠT** | Hai càng chênh nhau **≤ 3mm** ở cả tầng 1 và tầng 2; mũi càng vào khe pallet **không chạm mép trên/dưới** |
| **CHƯA ĐẠT** | Chênh > 3mm, hoặc càng tì vào mép khe |
| **Sửa** | `LIFT_*_EXTRA` (bù theo vị trí tuyệt đối, không phải bù mỗi lần chạy) |

Khe pallet trên khối 90×90×26mm rất hẹp. Chênh 3mm là một càng vào được, càng kia tì.

### B2 · Nhấc pallet đặt tay — `test_lift` **3**

**Tự tay** luồn càng vào khe pallet, rồi cho nâng. Bước này **tách** lift+IR ra khỏi
việc luồn, để biết hỏng nằm ở đâu.

| | |
|---|---|
| **ĐẠT** | **Cả 2 IR** báo CÓ, `confirm_pickup` trả True, pallet rời mặt kệ, **3/3 lần** |
| **CHƯA ĐẠT** | Một IR không báo → ngưỡng IR hoặc vị trí cảm biến. Cả hai không báo → SPI/ADC |

**B2 chưa đạt thì đừng chạy C2** — sẽ không phân biệt được "luồn sai" với "IR sai".

### B0 · Độ ổn định của cảm biến siêu âm — `tools.check_sonar_jitter` 🔑

**Làm TRƯỚC B3, và làm lại mỗi khi thay/lắp lại cảm biến.**

```bash
python3 -m tools.check_sonar_jitter
```

Robot ĐỨNG YÊN, mặt phẳng trước mặt ~12-15cm. Mọi dao động đọc được đều là **nhiễu**.

| Độ lệch chuẩn | Kết luận |
|---|---|
| **≤ 0.3cm**, không mẫu nào kịch trần | ✅ dừng trước kệ sẽ lặp lại được |
| ≤ 0.8cm | ⚠ tạm được, vẫn phải bù bằng `APPROACH_STOP_MARGIN` |
| **> 0.8cm** | ❌ không hằng số nào bù được cho cảm biến nhảy |
| có mẫu **kịch trần 100cm** | ❌ mất tiếng vọng — kiểm góc đặt, mặt phản xạ, dây ECHO |

Dùng để **so hai cảm biến bằng số**: chạy với cảm biến cũ, ghi độ lệch chuẩn; thay
cảm biến mới, đặt lại đúng khoảng cách đó, chạy lại, so.

⚠️ **Thay cảm biến thì phải đo lại toàn bộ nhóm khoảng cách** — chúng tính từ MẶT
CẢM BIẾN: `APPROACH_DISTANCE`, `RETREAT_DISTANCE`, `INSERT_MIN_DISTANCE`,
`ADVANCE_HARD_STOP_CM`. Lắp lệch vài cm là cả nhóm sai theo.
⚠️ Chân ECHO phải qua **cầu phân áp 1kΩ+2kΩ** (5V→3.3V). Nối thẳng là hỏng GPIO.

### B3 · Khoảng dừng trước kệ — `test_motion` **9** 🔑

**Đây là bước bắt lỗi trôi thêm của `stop_gently`.** Chạy **5 lần**.

**KHÔNG cần thước** — `approach_shelf()` tự đo lại sau khi robot đứng hẳn và in ra:

```
Đã đến vị trí kệ — lúc quyết định báo 13.9cm, ĐO LẠI khi đứng yên 11.8cm
(trôi thêm 2.1cm). Mốc 11.9 + bù 2.0. → bù ĐÚNG
```

Đo lại khi ĐỨNG YÊN mới là khoảng cách thật: độ trễ ~90ms của siêu âm chỉ tồn tại
lúc robot đang chạy, đứng yên thì hàng đợi đầy toàn giá trị hiện tại. Dòng cuối nói
thẳng phải nâng hay hạ `APPROACH_STOP_MARGIN` bao nhiêu cm.

| | |
|---|---|
| **ĐẠT** | Trung bình **13.9 ± 1.0 cm** (= `APPROACH_DISTANCE` 11.9 + `APPROACH_STOP_MARGIN` 2.0), VÀ độ tản (max − min) **≤ 1.0 cm** |
| **CHƯA ĐẠT — dừng sát hơn 10.9cm** | `stop_gently` trôi thêm. **Hạ `STOP_RAMP_TIME`** 0.12 → 0.08 → 0.04, chạy lại. **KHÔNG đổi `APPROACH_DISTANCE`** — số đó ràng buộc với vị trí khe pallet |
| **CHƯA ĐẠT — tản > 1.0cm** | Siêu âm nhiễu, hoặc robot đứng không vuông góc với kệ. **Nới `APPROACH_STOP_MARGIN` thêm nửa độ tản** — dừng sớm không mất gì vì `creep_until` bò tiếp tới khi IR báo; dừng muộn là càng chui gầm kệ |
| **CHƯA ĐẠT — robot lệch góc sau khi dừng** | Đặt `STOP_RAMP_TIME = 0` thử lại: vẫn lệch thì do phanh động, hết lệch thì do chính cái ramp |

**Ghi lại khoảng cách trung bình.** Nếu nó lệch quá **1cm** so với lúc chụp ảnh mẫu
thì phải làm B4.

### B4 · Nhận diện — `test_vision` **9**

Chỉ bắt buộc khi B3 cho khoảng cách khác trước > 1cm — camera đóng khung khác đi thì
16 ảnh mẫu ORB và `ROI_Y_CENTER` không còn đúng.

| | |
|---|---|
| **ĐẠT** | **Cả 4 ô** đúng nhãn; nhãn đúng thắng nhãn nhì **≥ 1.5×**; HSV ≥ `CONFIDENCE_THRESHOLD` (0.08) |
| **CHƯA ĐẠT** | Sai 1 ô, hoặc thắng < 1.5× (thắng sát nút = đổi ánh sáng là lật) |
| **Sửa** | Chụp lại 16 ảnh mẫu (`tools.capture_templates`) + `tools.calibrate_vision` từng tầng. ~30–45 phút |

---

## VÒNG C — Ghép nối. Khoảng 40 phút

Chạy `test_smoke`, **chọn đúng nửa sân** ở câu hỏi đầu phiên.

### C1 · Xuất phát → Kệ 3 — smoke **1**

| | |
|---|---|
| **ĐẠT** | Log `Advance: đã tới gần mục tiêu (1x.x cm)` + ✅, robot dừng cách kệ **20 ± 3 cm**, **3/3 lần** |
| **CHƯA ĐẠT** — `không thấy line trong 0.80s đầu` | Cửa sổ mù kết thúc sai chỗ, hoặc robot đặt lệch trong ô 400×400 |
| **CHƯA ĐẠT** — `gặp giao lộ` | Đã vượt qua C0R0 khi còn mù → `EXIT_START_BLIND_TIME` quá dài |
| **CHƯA ĐẠT** — dừng ngay trên hình mascot | Cửa sổ mù quá ngắn, hoặc cơ chế thoát sớm không kích hoạt |
| **CHƯA ĐẠT** — dừng cách kệ > 25cm | Siêu âm bắt phải vật khác |

### C1b · Đường dài, KHÔNG bốc hàng — smoke **8** 🔑

Xuất phát → trước Kệ 3 → lùi ra → **Samsung**. Chạy **trước C2**.

Vì sao xen vào đây: bốc hàng hỏng thì mọi bài có pickup đều dừng tại đó, và phần
điều hướng phía sau **không bao giờ được chạy** — mà đó mới là chỗ dùng những hằng
số chưa ai đo. Bài này tách hẳn đường đi ra khỏi lift và camera.

Kệ 3 → Samsung là tuyến **đắt nhất** trong 12 tuyến kệ→nhà máy: `LÙI 1 giao lộ →
xoay phải → tiến 2 giao lộ → xoay phải → tiến 1 → vào điểm cuối`. Hai lần xoay
**phải** và một lần **lùi** — đúng ba thứ chưa xác nhận, sai số cộng dồn.

| | |
|---|---|
| **ĐẠT** | Cả 5 bước ✅; robot đứng ở **đúng khu Samsung**, **quay mặt vào** nhà máy, lệch ngang so với tâm khu **≤ 3cm**; **3/3 lần** |
| **CHƯA ĐẠT** — sai nhà máy | **Chọn sai nửa sân.** Không có tín hiệu nào báo — chỉ kiểm được bằng mắt |
| **CHƯA ĐẠT** — đúng nhà máy nhưng lệch > 3cm | Tích luỹ sai số xoay/lùi → quay lại A5 (option 18) |
| **CHƯA ĐẠT** — gãy ở bước lùi | option **15** / **18** của `test_motion` |
| **CHƯA ĐẠT** — gãy ở bước xoay | option **10**, chạy riêng chiều PHẢI |
| **CHƯA ĐẠT** — gãy ở bám line | option **7** |

Bài dừng ở bước [3/5] cho bạn **đo tay khoảng cách tới kệ** — đối chiếu với B3.

### B5 · 🔴 SIÊU ÂM KHI ĐANG CÕNG KIỆN — `test_motion` **8**

**Làm bài này TRƯỚC mọi bài có giao hàng.** 2 phút, và nó quyết định luồng thi đấu
có chạy được không.

```bash
python3 -m tools.check_load_blocks_sonar
```

Nó tự làm cả bài: đặt tay 1 pallet lên càng, đẩy robot ra chỗ trống (phía trước
không có gì trong 60cm), rồi công cụ **nâng càng qua SÀN → TẦNG 1 → TẦNG 2**, đọc
siêu âm ở từng mức, hạ càng về, và in thẳng kết luận + việc phải sửa trong config.
Bánh xe KHÔNG chạy.

| Đọc được | Nghĩa | Hệ quả |
|---|---|---|
| **> 60cm** hoặc báo lỗi | Cảm biến nhìn qua được, kiện không chắn | ✅ luồng giao hàng an toàn |
| **Số nhỏ cố định** (vd 4cm) | 🔴 Cảm biến đang nhìn CHÍNH KIỆN HÀNG | Xem dưới |

Lặp lại với càng ở **tầng 2**.

**Nếu ra số nhỏ cố định:** trong luồng thi đấu, robot cõng kiện đi giao và siêu âm
chỉ nhìn thấy kiện đó. Ba chỗ dùng siêu âm lúc đang cõng:

## ✅ B5 ĐÃ ĐO XONG — 02/08

```
càng ở SÀN 74.6cm · TẦNG 1 76.8cm · TẦNG 2 72.6cm   (phía trước trống)
```

**Kiện hàng cõng KHÔNG che siêu âm.** Luồng giao hàng dùng siêu âm bình thường.

Toàn bộ cơ chế "chống kiện che" từng thêm trong ngày đã bị **xoá** — nó dựa trên
giả định sai này và gây **hai** lần robot lao vào kệ, vì nhánh dự phòng của nó là
"đi tới khi hết line" mà line kéo tới tận chân kệ. Giữ lại **chặn cứng**
`ADVANCE_HARD_STOP_CM = 11.9` vì đó là lưới an toàn cho mọi nguyên nhân, và kiện
đọc 72-77cm nên không bao giờ chạm mốc đó.

Vụ `retreat_from_shelf` timeout hoá ra do `APPROACH_SPEED = 30` quá sát vùng chết
(25) — cõng hàng thì không thắng nổi ma sát. Nâng lên 40 là hết.

**Bài học ghi lại:** đừng thêm phòng thủ cho một tình huống chưa ai đo. Số đo mất
2 phút; bốn lần sửa hỏng dựa trên suy luận mất cả buổi chiều.

Chỗ thứ ba là lỗi **im lặng hoàn toàn**: IR vẫn xác nhận thả, `packages_delivered`
vẫn tăng, log toàn ✅. Báo lại số đo được để chốt cách sửa.

### C2 · Bốc hàng — smoke **2** 🔑 **BÀI QUAN TRỌNG NHẤT**

Ngồi ngang tầm mắt với bánh xe. **Nhìn kỹ 10cm cuối.**

| | |
|---|---|
| **ĐẠT** | **Cả 2 bánh quay đều suốt** quãng luồn; cả 2 IR báo CÓ; IR báo khi còn **cách kệ > 3.0cm**; `classify_pair` đúng cả 2 ô; **3/3 lần** |
| **CHƯA ĐẠT** 🔴 — **một bánh đứng hẳn, robot xoay quanh nó** | Đúng cái đã tính trước: `LINE_KP = 16` chỉnh cho tốc độ 50, chạy ở 32% thì sai số line > 0.44 là bánh trong tụt dưới vùng chết. **Phải kẹp `LINE_KP` trước khi chạy tiếp** |
| **CHƯA ĐẠT** — `đã tới 2.x cm (chặn 2.2cm) mà IR chưa báo` | Càng vẫn không vào khe. Xem lại B1 (độ cao) và B3 (khoảng dừng) |
| **CHƯA ĐẠT** — chỉ **1 IR** báo | Lệch NGANG, không phải lệch góc. Kiểm khoảng cách 2 càng so với 2 khe |
| **CHƯA ĐẠT** — IR chỉ báo ở **2.2–2.5cm** | Về mặt số là đạt nhưng **biên an toàn bằng 0**. Coi như chưa đạt |
| **CHƯA ĐẠT** — nhấc lên thì chạm kệ | `LIFT_PICKUP_RAISE_TIME` quá lớn, hoặc dừng quá sát |

Sau khi C2 **đạt**: đo lại `INSERT_MIN_DISTANCE` (2.2) và `LIFT_PICKUP_RAISE_TIME`
(0.3). Hai số đó đang bị **nới ra để bù cho việc đi lệch** — lệch chữa xong thì giữ
nguyên chúng là để robot chạy sát kệ hơn mức cần thiết.

### C3 · Thả hàng — smoke **3**

| | |
|---|---|
| **ĐẠT** | Cả 2 lần thả đều có IR xác nhận đã RỜI càng; sau kiện 1 càng được **nâng lại ngang càng kia** (chênh ≤ 3mm); sau kiện 2 cả hai càng về sàn |
| **CHƯA ĐẠT** | IR vẫn thấy pallet sau khi thả → pallet chưa rời. Càng không nâng lại → sẽ cạ sàn khi chạy tiếp |

### C4 · Vòng khép kín — smoke **5**

| | |
|---|---|
| **ĐẠT** | Không có bước ❌ nào; kiện tới **đúng** nhà máy (kiểm bằng mắt, không tin log); cuối bài robot đứng **vuông góc** trước Kệ 3, lệch ngang ≤ 3cm |
| **CHƯA ĐẠT** — sai nhà máy | **Chọn sai nửa sân.** Log vẫn xanh — đây là lỗi duy nhất không có tín hiệu báo |
| **CHƯA ĐẠT** — về tới Kệ 3 nhưng lệch | Tích luỹ sai số xoay/lùi → quay lại A1, A2 |

---

## VÒNG D — Chỉ sau khi C4 đạt 3/3

```bash
bash scripts/practice.sh
python3 -m tools.measure_phases
```

| | |
|---|---|
| **ĐẠT** | Dự báo **worst case ≥ 8/12 kiện** trong 240s |
| **CHƯA ĐẠT** | < 8 kiện → chặng ăn nhiều giây nhất là chạy thẳng (~35%), tăng `SPEED_DEFAULT` (đang 50, mức bring-up) theo quy trình trong `config.py` |

Đọc theo **điểm**, không theo "kịp / không kịp": hết giờ vẫn giữ điểm kiện đã giao.

---

## Bảng ghi số — điền vào rồi báo lại

| Mục | Giá trị đo | Hằng số liên quan |
|---|---|---|
| A1 xoay trái / phải | ______° / ______° | `TURN_TIME` |
| A2 trôi tiến / lùi (2m) | ______cm / ______cm | `PWM_COMPENSATION*` |
| A5 lệch trục sau tiến bù | ______cm | `REVERSE_RECENTER_TIME` |
| A5 giây / giao lộ | ______s | đối chiếu `dry_run --forward` |
| A3 tốc độ ở 50% | ______ cm/s | → `EXIT_START_BLIND_TIME` = 45 ÷ ____ = ______ |
| B1 chênh 2 càng T1 / T2 | ______mm / ______mm | `LIFT_*_EXTRA` |
| B3 khoảng dừng TB / tản | ______cm / ______cm | `APPROACH_DISTANCE`, `STOP_RAMP_TIME` |
| C2 khoảng cách khi IR báo | ______cm | `INSERT_MIN_DISTANCE` |
