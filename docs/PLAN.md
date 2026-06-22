# PLAN: Chuyển đổi Robot sang chế độ Tự động hoàn toàn (Bảng O2 - Robocon Bắc Ninh mở rộng 2026)

---

## 1. MÔ TẢ ĐỀ BÀI

### 1.1 Bối cảnh
Đội đang chuẩn bị tham gia **Giải Robocon Bắc Ninh mở rộng 2026 – Tranh Cúp Foxconn**, thi đấu ở **Bảng O2** (chủ đề "Khát vọng công nghệ"). Robot hiện tại đã được lắp ráp phần cứng và có một bản code Python (Flask + Raspberry Pi GPIO) cho phép **điều khiển bằng tay qua giao diện web** (nhấn giữ nút Tiến/Lùi/Xoay/Nâng/Hạ).

**Vấn đề cần giải quyết:** Theo thể lệ chính thức, robot dự thi phải là **robot tự động hoàn toàn** — sau khi được kích hoạt bằng một lệnh khởi động duy nhất, robot phải tự thực hiện toàn bộ nhiệm vụ theo chương trình đã lập trình sẵn, **không có bất kỳ sự can thiệp điều khiển trực tiếp nào của con người** trong suốt quá trình thi. Code hiện tại (điều khiển tay qua web) **vi phạm trực tiếp quy định này** và cần được viết lại.

### 1.2 Nhiệm vụ thi đấu cần robot thực hiện (Bảng O2)
Sa bàn 4000mm x 2000mm, có 2 phần sân đối xứng (xanh/đỏ). Mỗi phần sân gồm:
- **Khu vực xuất phát**: 400mm x 400mm
- **Kho hải quan**: có 3 giá kệ chứa hàng (mỗi giá kệ kích thước 240x120x265mm, 2 tầng, mỗi giá chứa tối đa 4 kiện hàng/pallet)
- **Kho hàng rời**: 1 giá kệ với 1 pallet chứa 4 khối hàng hóa
- **4 Khu vực nhà máy** (Samsung, Foxconn, Amkor, Hana Micron Vina) — mỗi khu kích thước 250mm x 250mm
- **1 Nhà máy liên hợp** ở giữa sân (chung cho cả 2 đội)

Mỗi kiện hàng = 1 pallet (90x90x26mm) + 4 khối hàng hóa lập phương (40x40x40mm) dán hình ảnh đại diện trên 6 mặt, gắn cố định lên pallet.

**Nhiệm vụ 1 – Phân loại và vận chuyển hàng hóa (240 điểm tối đa):**
1. Sau hiệu lệnh bắt đầu, robot tự di chuyển đến Kho hải quan.
2. Dùng **Camera AI** quét và nhận diện hình ảnh trên khối hàng hóa để xác định loại kiện hàng (01–04).
3. Robot **bắt buộc lấy kiện hàng bằng cách nâng pallet theo kiểu xe nâng (forklift)**.
4. Di chuyển và đặt kiện hàng đúng vị trí, đúng chiều (mặt pallet song song mặt sa bàn) vào đúng khu nhà máy tương ứng:
   - Kiện hàng 01 → Nhà máy Samsung
   - Kiện hàng 02 → Nhà máy Foxconn
   - Kiện hàng 03 → Nhà máy Amkor
   - Kiện hàng 04 → Nhà máy Hana Micron Vina
5. Tổng cộng 12 kiện hàng/phần sân. Mỗi kiện đặt đúng = 20 điểm.

**Nhiệm vụ 2 – Vận chuyển vào nhà máy liên hợp (30 điểm), chỉ thực hiện sau khi hoàn thành 100% Nhiệm vụ 1:**
- Lấy kiện hàng tại Kho hàng rời, mang đến Nhà máy liên hợp ở giữa sân, đặt đúng vị trí.

**Ràng buộc thời gian:** Toàn bộ trận đấu tối đa **240 giây (4 phút)**.

**Luật Reset:** Cho sẵn 50 điểm reset, mỗi lần reset trừ 10 điểm, tối đa 5 lần. Khi đội hô "Reset", **thành viên đội tự tay đặt lại robot** vào ô xuất phát — đây là can thiệp vật lý được phép, không phải can thiệp qua chương trình.

### 1.3 Phần cứng hiện có (đã lắp ráp)
- **Bộ điều khiển:** Raspberry Pi 4 Model B (CPU Broadcom BCM2711, Quad-core Cortex-A72 @1.5GHz)
- **Camera AI:** Module camera (cảm biến OV5647), kết nối CSI-2, xử lý nhận diện bằng OpenCV/TensorFlow Lite (model huấn luyện qua Edge Impulse, export dạng `.tflite`)
- **Mạch công suất L298(N):** điều khiển động cơ di chuyển + động cơ cơ cấu nâng
- **Mạch hạ áp XH-M401:** hạ áp nguồn pin về mức cấp cho Pi/động cơ
- **Cơ cấu di chuyển:** 2 động cơ giảm tốc bánh sau (tỉ số 1:48) + bánh đa hướng (caster) phía trước
- **Cơ cấu nâng (2 càng trái/phải)** dẫn động bằng dây curoa + con lăn trượt dọc trụ cột

**Sơ đồ GPIO đã dùng trong code cũ (tái sử dụng):**
```
# Cụm xe trái
IN1_XE_T, IN2_XE_T

# Cụm xe phải (có PWM chống lệch tốc độ)
IN1_XE_P (PWM 100Hz), IN2_XE_P

# Cụm cẩu trái
IN3_CAU_T, IN4_CAU_T

# Cụm cẩu phải (có ENA bật/tắt)
ENA_CAU_P, IN1_CAU_P, IN2_CAU_P
```

### 1.4 Vấn đề/vi phạm thể lệ cần khắc phục trong code
1. **[NGHIÊM TRỌNG]** Bỏ hoàn toàn cơ chế điều khiển tay qua web (Flask + HTML buttons) khi vào thi đấu. Chỉ giữ **1 lệnh khởi động duy nhất** (ví dụ: 1 nút vật lý hoặc 1 lần gọi script) để bắt đầu chuỗi hành động tự động.
2. Camera AI phải chạy suy luận (inference) **hoàn toàn offline, cục bộ trên Raspberry Pi**, không gọi API cloud của Edge Impulse trong lúc thi (model đã export sẵn dạng file cục bộ).
3. Bộ điều khiển chỉ là 1 vi xử lý duy nhất (Raspberry Pi), tổng số cổng I/O sử dụng (động cơ + camera + cảm biến) không vượt 16 cổng — cần audit lại số GPIO đang dùng.
4. Tổng số động cơ (kể cả servo) không vượt 12.

---

## 2. MỤC TIÊU CỦA TASK (cho Claude Code)

Viết lại toàn bộ phần mềm điều khiển robot theo hướng **tự động hoàn toàn (autonomous state machine)**, tái sử dụng tối đa phần cứng/GPIO đã có, thay thế phần điều khiển tay bằng logic tự vận hành theo trình tự nhiệm vụ, đảm bảo tuân thủ thể lệ.

---

## 3. YÊU CẦU KỸ THUẬT CHI TIẾT

### 3.1 Kiến trúc tổng thể
- Ngôn ngữ: Python 3 (giữ nguyên, tương thích RPi.GPIO/gpiozero hiện có).
- Kiến trúc dạng **state machine** (máy trạng thái), KHÔNG dùng server web nhận lệnh người dùng trong lúc thi.
- Tách rõ 3 module độc lập, dễ test riêng:
  - `motion.py` — điều khiển động cơ di chuyển (tiến/lùi/xoay, PWM bù lệch tốc độ).
  - `lift.py` — điều khiển cơ cấu nâng/hạ 2 càng (trái/phải), có thể dùng time-based hoặc encoder/limit-switch nếu phần cứng có.
  - `vision.py` — load model `.tflite`, chạy inference từ camera, trả về nhãn kiện hàng (01–04) + độ tin cậy.
  - `main.py` — state machine điều phối toàn bộ trình tự nhiệm vụ, gọi 3 module trên.

### 3.2 State machine đề xuất (có thể điều chỉnh theo thực tế cảm biến)
```
INIT
  -> chờ lệnh khởi động (1 nút duy nhất / 1 tín hiệu GPIO)
START
  -> di chuyển đến Kho hải quan (giá kệ #1)
SCAN_PACKAGE
  -> camera AI nhận diện loại kiện hàng hiện tại
PICKUP
  -> căn chỉnh vị trí, nâng càng theo kiểu xe nâng để lấy pallet
TRANSPORT
  -> di chuyển đến khu nhà máy tương ứng với loại kiện hàng đã nhận diện
DROP
  -> hạ càng, đặt kiện hàng đúng vị trí/đúng chiều, lùi ra
  -> nếu còn kiện hàng trong Kho hải quan -> quay lại SCAN_PACKAGE (giá kệ tiếp theo)
  -> nếu đã xử lý hết 12 kiện hàng (Nhiệm vụ 1 hoàn thành) -> sang TASK2
TASK2_PICKUP (Kho hàng rời)
  -> lấy kiện hàng tại kho hàng rời
TASK2_TRANSPORT
  -> di chuyển đến Nhà máy liên hợp, đặt hàng
DONE
  -> dừng toàn bộ động cơ, đứng yên chờ hết giờ/trọng tài
```
*Lưu ý: cần có cơ chế theo dõi thời gian (timer 240s) — nếu gần hết giờ mà chưa hoàn thành, ưu tiên dừng an toàn thay vì cố hoàn thành gây lỗi.*

### 3.3 Điều hướng (Navigation)
- **Cảm biến dẫn đường: module dò line 8 mắt (8-channel IR line sensor array)**, đặt ngang dưới gầm robot để bám theo line trên sa bàn.
- Logic line-following đề xuất:
  - Đọc giá trị 8 cảm biến → tính "vị trí lệch" của line so với tâm robot (ví dụ: trọng số theo vị trí từng cảm biến, mắt giữa = 0, lệch trái/phải tăng dần).
  - Dùng giá trị lệch này để hiệu chỉnh PWM bánh trái/phải (tái sử dụng `pwm_phai` đã có trong code cũ) — lệch trái thì giảm tốc bánh trái/tăng bánh phải và ngược lại.
  - Phát hiện giao lộ/điểm rẽ (ví dụ: cả 8 mắt đều thấy line cùng lúc = vạch ngang giao lộ) để biết khi nào đến đúng giá kệ/khu nhà máy mà rẽ hoặc dừng.
- Module `motion.py` cần thêm hàm `read_line_sensor() -> list[int]` (đọc 8 kênh) và `follow_line(sensor_values)` (tính lệch + set PWM), thay cho việc chỉ nhận lệnh tiến/lùi/xoay đơn giản như code cũ.
- **Lưu ý quan trọng về số cổng I/O:** cảm biến dò line 8 mắt thường cần **8 chân digital riêng** nếu đọc trực tiếp từng kênh. Cộng với khoảng 9 chân đang dùng cho động cơ (xe trái/phải + cẩu trái/phải) + cổng camera, tổng có thể **vượt giới hạn 16 cổng** của thể lệ. Cần ưu tiên một trong các hướng sau:
  - Dùng module dò line 8 mắt có sẵn IC chuyển đổi sang **I2C** (chỉ tốn 2 chân SDA/SCL cho cả 8 mắt), hoặc
  - Dùng **shift register** (ví dụ 74HC165) để gom 8 tín hiệu digital vào 3 chân (SPI-like: data/clock/latch), hoặc
  - Nếu module chỉ xuất digital thường, xem xét giảm xuống dùng ít mắt hơn (ví dụ 5 mắt) nếu đủ độ chính xác bám line.
  - **Claude Code cần audit và báo lại tổng số chân thực tế** trước khi hoàn thiện code, để đội kiểm tra có vượt 16 cổng hay không.

### 3.4 Camera AI / Vision
- Input: ảnh từ camera module (qua `picamera2` hoặc `OpenCV VideoCapture`).
- Model: file `.tflite` đã huấn luyện qua Edge Impulse, đặt cố định trong thư mục project (không tải từ mạng lúc runtime).
- Output: 1 trong 4 nhãn (`samsung`, `foxconn`, `amkor`, `hana_micron`) + confidence score.
- Có cơ chế fallback: nếu confidence thấp, robot dừng lại quét lại 1 lần trước khi quyết định (tránh đặt sai nhà máy bị 0 điểm khu vực đó).

### 3.5 Cơ cấu nâng (Lift / Forklift logic)
- Hàm `pickup()`/`dropoff()` điều khiển 2 động cơ càng (trái/phải) đồng bộ.
- Nếu phần cứng chưa có encoder/limit switch để biết chính xác độ cao càng, dùng time-based control (đo thời gian chạy motor tương ứng từng tầng kệ 1 hoặc 2) — đội cần đo thực nghiệm và đưa vào file config.
- Đảm bảo khi đặt hàng, mặt pallet song song mặt sa bàn (không nghiêng/đổ) — kiểm tra cơ khí kết hợp tốc độ hạ chậm gần điểm đặt.

### 3.6 Cấu hình & Logging
- Tạo file `config.py` chứa toàn bộ hằng số có thể tinh chỉnh: tốc độ động cơ, thời gian nâng/hạ theo tầng, ngưỡng confidence camera, pin GPIO, timeout state.
- Ghi log ra file (vì không có màn hình giám sát lúc thi) để debug sau mỗi lượt chạy thử.
- Thêm flag `DEBUG_MODE` cho phép bật lại giao diện web cũ **chỉ dùng khi luyện tập/test ở nhà**, phải tắt hẳn khi vào thi đấu chính thức.

### 3.7 An toàn & Tuân thủ thể lệ
- Đảm bảo script khởi động chỉ kích hoạt 1 lần qua duy nhất 1 input (không có cách nào can thiệp điều khiển giữa trận).
- Không có bất kỳ network call (HTTP request ra ngoài, cloud inference) trong toàn bộ vòng lặp chính lúc thi đấu.
- Audit lại số chân GPIO sử dụng thực tế, ghi rõ trong README để đối chiếu giới hạn 16 cổng.
- Audit lại số lượng động cơ/servo thực tế, ghi rõ trong README để đối chiếu giới hạn 12 động cơ (bảng O2).

---

## 4. DELIVERABLES MONG ĐỢI

1. Bộ source code Python tổ chức theo cấu trúc module ở mục 3.1 (`main.py`, `motion.py`, `lift.py`, `vision.py`, `config.py`).
2. File `README.md` hướng dẫn: cách cài đặt, cách chạy, cách chuyển `DEBUG_MODE`, danh sách GPIO đã dùng, danh sách động cơ đã dùng.
3. Một bảng (trong README hoặc file riêng) ánh xạ **state → hành động → thời gian dự kiến**, để đội dễ tinh chỉnh khi thử sa bàn thực tế.
4. (Nếu có thể) 1 script test riêng cho từng module (`test_motion.py`, `test_lift.py`, `test_vision.py`) để đội kiểm tra phần cứng độc lập trước khi ráp full state machine.

---

## 5. CÂU HỎI CẦN LÀM RÕ VỚI ĐỘI TRƯỚC/TRONG KHI CODE
- ~~Loại cảm biến dẫn đường cụ thể đang dùng~~ → **Đã xác định: cảm biến dò line 8 mắt.** Cần làm rõ thêm: module này xuất tín hiệu digital trực tiếp (8 chân) hay có IC chuyển đổi I2C/shift register (ít chân hơn)?
- Robot có limit switch hoặc encoder ở cơ cấu nâng để biết chính xác độ cao càng không, hay chỉ chạy theo thời gian?
- Model Edge Impulse đã export ra `.tflite` chưa, đặt ở đâu trong project?
- Cách bố trí vật lý nút khởi động (GPIO button vật lý, hay phím bấm qua bàn phím gắn với Pi)?
