# Hướng dẫn cài đặt lần đầu trên Raspberry Pi 4

Tài liệu này hướng dẫn từ lúc bật Pi lần đầu đến khi chạy được robot.

---

## Yêu cầu phần cứng

- Raspberry Pi 4 Model B (đã cài Raspberry Pi OS)
- Thẻ nhớ microSD ≥ 16GB (đã flash OS)
- Màn hình + cáp HDMI micro (chỉ cần cho bước cài đặt)
- Bàn phím USB
- Nguồn 5V/3A (USB-C)
- Kết nối Internet (WiFi hoặc Ethernet)

---

## Bước 1: Flash Raspberry Pi OS vào thẻ nhớ (trên laptop)

Nếu thẻ nhớ chưa có OS:

1. Tải **Raspberry Pi Imager** tại https://www.raspberrypi.com/software/
2. Cắm thẻ nhớ vào laptop
3. Mở Raspberry Pi Imager:
   - **OS**: chọn `Raspberry Pi OS (64-bit)` — bản có desktop
   - **Storage**: chọn thẻ nhớ
   - Nhấn bánh răng (⚙) cấu hình trước khi flash:
     - **Hostname**: `raspberrypi`
     - **Enable SSH**: bật, chọn "Use password authentication"
     - **Username**: `pi`
     - **Password**: đặt mật khẩu (ghi nhớ lại)
     - **WiFi**: nhập tên WiFi + mật khẩu (tuỳ chọn, có thể làm sau)
     - **Locale**: `Asia/Ho_Chi_Minh`, Keyboard `us`
4. Nhấn **Write**, đợi hoàn tất
5. Rút thẻ nhớ, cắm vào Pi

> Nếu đã cấu hình SSH + WiFi ở bước này, có thể bỏ qua bước 3 và 4 bên dưới.

---

## Bước 2: Khởi động Pi lần đầu

1. Cắm thẻ nhớ vào Pi
2. Nối màn hình (HDMI micro), bàn phím (USB)
3. Cắm nguồn USB-C → Pi tự khởi động
4. Lần đầu sẽ mất 1-2 phút để mở rộng filesystem
5. Đăng nhập bằng user/password đã đặt ở bước 1

---

## Bước 3: Bật SSH

Nếu chưa bật SSH ở bước flash:

```bash
sudo raspi-config
```

Chọn:
```
Interface Options → SSH → Yes → OK → Finish
```

Kiểm tra:
```bash
sudo systemctl status ssh
# Phải thấy: Active: active (running)
```

---

## Bước 4: Kết nối WiFi

Nếu chưa cấu hình WiFi ở bước flash:

```bash
# Xem danh sách WiFi
sudo nmcli dev wifi list

# Kết nối (thay tên và mật khẩu thật)
sudo nmcli dev wifi connect "TÊN_WIFI" password "MẬT_KHẨU"
```

Kiểm tra:
```bash
# Xem IP
hostname -I
# Ví dụ: 192.168.1.50

# Kiểm tra Internet
ping -c 3 google.com
```

**Ghi lại IP** — dùng để SSH từ laptop sau này.

(Tuỳ chọn) Thêm hotspot điện thoại để test ngoài sân:
```bash
sudo nmcli dev wifi connect "TÊN_HOTSPOT" password "MẬT_KHẨU_HOTSPOT"
```

Pi sẽ nhớ cả 2 mạng, tự kết nối mạng khả dụng khi bật.

---

## Bước 5: Bật SPI và Camera

```bash
sudo raspi-config
```

Chọn lần lượt:
```
Interface Options → SPI    → Yes → OK
Interface Options → Camera → Yes → OK
Finish
```

Khởi động lại:
```bash
sudo reboot
```

Sau khi reboot, kiểm tra SPI:
```bash
ls /dev/spidev*
# Phải thấy: /dev/spidev0.0  /dev/spidev0.1
```

---

## Bước 6: Cài đặt Git

```bash
sudo apt update
sudo apt install -y git
```

---

## Bước 7: Clone code về Pi

```bash
cd ~
git clone https://github.com/TÊN_TÀI_KHOẢN/Robocon-BCIT.git
cd Robocon-BCIT
```

> Thay URL bằng địa chỉ repo thật của đội. Nếu repo private, cần cấu hình SSH key hoặc dùng HTTPS + token.

Kiểm tra:
```bash
ls
# Phải thấy: main.py  config.py  control/  vision/  debug/  tests/  scripts/  docs/
```

---

## Bước 8: Cài thư viện hệ thống (apt)

Một số thư viện **bắt buộc cài qua apt**, không cài được bằng pip:

```bash
sudo apt update
sudo apt install -y \
    python3-lgpio \
    python3-gpiozero \
    python3-spidev \
    python3-picamera2 \
    python3-libcamera \
    python3-opencv \
    python3-numpy
```

Thời gian: ~2-5 phút tuỳ tốc độ mạng.

---

## Bước 9: Tạo virtualenv và cài thư viện pip

```bash
python3 -m venv --system-site-packages ~/robot_env
source ~/robot_env/bin/activate
pip install -r requirements.txt
```

Giải thích:
- `--system-site-packages`: cho phép venv dùng các gói đã cài qua apt (lgpio, picamera2, opencv...)
- `requirements.txt` cài thêm: `flask`, `gpiozero`, `spidev`, `numpy`, `opencv-python-headless`

Kiểm tra:
```bash
python3 -c "import gpiozero; print('gpiozero OK')"
python3 -c "import spidev; print('spidev OK')"
python3 -c "import cv2; print('opencv OK')"
python3 -c "import numpy; print('numpy OK')"
python3 -c "from flask import Flask; print('flask OK')"
```

Tất cả phải in `OK`.

---

## Bước 10: Sửa đường dẫn trong scripts (nếu username khác)

Các file trong `scripts/` đang hardcode đường dẫn `/home/mbw12345/`. Nếu username trên Pi khác (ví dụ `pi`), cần sửa:

```bash
cd ~/Robocon-BCIT

# Xem username hiện tại
whoami
# Ví dụ: pi

# Sửa tất cả đường dẫn trong scripts
sed -i "s|/home/mbw12345|$HOME|g" scripts/install.sh
sed -i "s|/home/mbw12345|$HOME|g" scripts/start.sh
sed -i "s|/home/mbw12345|$HOME|g" scripts/robot.service
sed -i "s|User=mbw12345|User=$(whoami)|g" scripts/robot.service
```

Kiểm tra đã sửa đúng:
```bash
grep -n "$HOME" scripts/install.sh scripts/start.sh scripts/robot.service
# Tất cả đường dẫn phải trỏ về đúng home directory

grep "User=" scripts/robot.service
# Phải thấy: User=pi (hoặc username thật)
```

---

## Bước 11: Test nhanh (không cần phần cứng robot)

### Unit test logic — chạy được ngay, không cần GPIO:

```bash
cd ~/Robocon-BCIT
source ~/robot_env/bin/activate
python3 -m unittest tests.test_logic -v
```

Tất cả test phải `OK` (hiện **31 test**). Nếu có lỗi import, kiểm tra lại bước 8-9.

### Test debug web UI (không cần cảm biến):

```bash
python3 main.py
```

Mở trình duyệt trên laptop (cùng WiFi): `http://<IP-của-Pi>:5000`

Giao diện web hiện lên = cài đặt thành công. Nếu phần cứng chưa nối, sẽ thấy cảnh báo "Phần cứng chưa sẵn sàng" — bình thường.

Nhấn `Ctrl+C` để dừng.

---

## Bước 12: Test phần cứng (sau khi đấu nối)

Sau khi đấu nối phần cứng theo `docs/PHAN_CUNG.md`, test từng module:

```bash
cd ~/Robocon-BCIT
source ~/robot_env/bin/activate

# 1. Motor bánh xe — tiến/lùi/xoay/tốc độ
python3 tests/test_motion.py    # Option 1, 2, 3

# 2. Cảm biến dò line — calibrate QTR-8A
python3 tests/test_motion.py    # Option 4 (digital), 5 (raw ADC)

# 3. Thoát ô start + bám line + siêu âm
python3 tests/test_motion.py    # Option 6, 7, 8, 9

# 4. Xoay 90° + execute_route trên sa bàn
python3 tests/test_motion.py    # Option 10, 11

# 5. Shared SPI (line + IR đồng thời)
python3 tests/test_motion.py    # Option 12

# 6. Cơ cấu nâng/hạ + IR + drop từng càng + NV2
python3 tests/test_lift.py      # Option 1–8

# 7. Camera + HSV + classify_pair (2 kiện)
python3 tests/test_vision.py    # Option 1, 2, 6

# 8. Smoke test tích hợp (exit → pickup → drop)
python3 tests/test_smoke.py     # Option 5 — scenario return sau 2 NM khác nhau
```

---

## Bước 13: Cài service tự khởi động (tuỳ chọn — chỉ cần khi thi đấu)

### Bước này làm gì?

Mặc định sau khi clone code, Pi bật lên **không tự chạy robot**. Bạn phải SSH vào,
gõ `python3 main.py` mỗi lần muốn chạy.

Bước này đăng ký robot với **systemd** (trình quản lý service của Linux) để Pi
bật nguồn là tự chạy robot — **không cần SSH, không cần gõ lệnh, không cần laptop**.

### Khi nào cần?

- **Ngày thi đấu**: cắm pin → Pi tự bật → robot tự chạy → nhấn nút là đi
- **Test full trên sa bàn**: muốn test giống điều kiện thi thật

### Khi nào KHÔNG cần?

- Luyện tập hàng ngày → SSH vào, gõ `python3 main.py` trực tiếp
- Dùng web debug → SSH + `python3 main.py` (DEBUG_MODE=True)
- Chạy test từng module → `python3 tests/test_motion.py`

### Cách cài (chạy 1 lần duy nhất)

```bash
sudo bash ~/Robocon-BCIT/scripts/install.sh
```

Lệnh này làm 3 việc:
1. Copy `robot.service` vào systemd
2. Bảo systemd: "mỗi lần Pi bật → chạy `start.sh`"
3. Khởi động robot ngay lập tức

### Sau khi cài, mỗi lần bật Pi sẽ tự động:

```
Pi bật nguồn
  → systemd đọc robot.service
    → gọi start.sh
      → đặt ROBOT_COMPETE=1 (bỏ qua DEBUG_MODE, luôn chạy thi đấu)
        → chạy python3 main.py
          → robot chờ nhấn nút GPIO 16
            → nhấn nút → chạy tự động 240 giây
```

### Lệnh quản lý service

```bash
sudo systemctl status robot      # Xem trạng thái (đang chạy / dừng / lỗi)
sudo systemctl stop robot        # Dừng robot
sudo systemctl restart robot     # Khởi động lại (sau khi sửa code)
sudo systemctl disable robot     # Tắt tự khởi động (quay về chế độ thủ công)
sudo systemctl enable robot      # Bật lại tự khởi động
journalctl -u robot -f           # Xem log realtime
cat robot_log.txt                # Xem log file
```

### Muốn gỡ hoàn toàn?

```bash
sudo systemctl stop robot
sudo systemctl disable robot
sudo rm /etc/systemd/system/robot.service
sudo systemctl daemon-reload
```

Pi sẽ trở về bình thường — bật lên không tự chạy gì.

### Lưu ý: service chạy ở chế độ thi đấu

`start.sh` luôn đặt `ROBOT_COMPETE=1` → dù `config.py` có `DEBUG_MODE = True`,
robot vẫn chạy **state machine thi đấu** (không mở web debug).

Nếu muốn dùng web debug, **dừng service trước** rồi chạy tay:
```bash
sudo systemctl stop robot
cd ~/Robocon-BCIT
source ~/robot_env/bin/activate
python3 main.py                  # DEBUG_MODE=True → mở web debug
```

---

## Bước 14: Rút màn hình, chuyển sang SSH

Từ giờ trở đi, dùng SSH từ laptop:

```bash
# Trên laptop:
ssh pi@192.168.1.50

# Chạy debug web:
cd ~/Robocon-BCIT
source ~/robot_env/bin/activate
python3 main.py
# Mở trình duyệt: http://192.168.1.50:5000
```

---

## Tóm tắt thứ tự

| Bước | Việc làm | Thời gian |
|:----:|----------|:---------:|
| 1 | Flash OS vào thẻ nhớ | 5 phút |
| 2 | Khởi động Pi, đăng nhập | 2 phút |
| 3 | Bật SSH | 1 phút |
| 4 | Kết nối WiFi | 1 phút |
| 5 | Bật SPI + Camera, reboot | 2 phút |
| 6 | Cài Git | 1 phút |
| 7 | Clone code | 1 phút |
| 8 | Cài thư viện apt | 3 phút |
| 9 | Tạo venv + pip install | 2 phút |
| 10 | Sửa đường dẫn scripts | 1 phút |
| 11 | Test logic + web UI | 2 phút |
| 12 | Test phần cứng | 10+ phút |
| 13 | Cài systemd service | 1 phút |
| 14 | Rút màn hình, dùng SSH | — |
| | **Tổng** | **~30 phút** |

---

## Xử lý sự cố

### Lỗi import lgpio / gpiozero

```
ModuleNotFoundError: No module named 'lgpio'
```

Nguyên nhân: chưa cài qua apt hoặc venv không kế thừa system packages.

```bash
sudo apt install -y python3-lgpio python3-gpiozero
# Nếu đã có venv, tạo lại:
rm -rf ~/robot_env
python3 -m venv --system-site-packages ~/robot_env
source ~/robot_env/bin/activate
pip install -r ~/Robocon-BCIT/requirements.txt
```

### Lỗi SPI: "No such file or directory: /dev/spidev0.0"

```bash
# Chưa bật SPI
sudo raspi-config
# → Interface Options → SPI → Yes
sudo reboot
```

### Lỗi camera: "Camera is not enabled"

```bash
sudo raspi-config
# → Interface Options → Camera → Yes
sudo reboot

# Kiểm tra camera kết nối:
libcamera-hello --timeout 3000
# Phải thấy preview window (nếu có màn hình) hoặc không báo lỗi
```

### Lỗi "Permission denied" khi truy cập GPIO

```bash
sudo usermod -aG gpio,spi,i2c $(whoami)
# Logout rồi login lại (hoặc reboot)
```

### Lỗi Flask: "Address already in use" (port 5000)

```bash
# Có tiến trình khác đang dùng port 5000
sudo lsof -i :5000
# Kill tiến trình đó:
kill <PID>

# Hoặc đổi port trong config.py:
# WEB_PORT = 5001
```
