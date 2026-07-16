# Khôi phục mật khẩu Raspberry Pi 4 khi quên

Áp dụng khi màn hình Pi báo **"Incorrect password, please try again"** và không nhớ mật khẩu đăng nhập.

Không cần cài lại OS — chỉ cần rút thẻ nhớ ra sửa trên laptop rồi cắm lại.

---

## Yêu cầu

- Đầu đọc thẻ microSD (hoặc adapter SD) cắm vào laptop
- Laptop Windows / Mac / Linux đều dùng được (chỉ cần đọc/ghi được partition `bootfs` dạng FAT32)

---

## Bước 1: Tắt Pi, rút thẻ nhớ

1. Ở màn hình login, chọn **Shut Down** để tắt Pi an toàn
2. Rút thẻ microSD ra khỏi Pi
3. Cắm thẻ vào đầu đọc, cắm vào laptop

---

## Bước 2: Mở file `cmdline.txt` trên partition boot

Trên laptop, thẻ nhớ sẽ hiện ra 1 partition tên `bootfs` (hoặc `boot`) — đây là partition FAT32 đọc được trên mọi hệ điều hành.

Mở file `cmdline.txt` trong đó bằng text editor (Notepad, VS Code...).

Nội dung là **1 dòng duy nhất**, ví dụ:
```
console=serial0,115200 console=tty1 root=PARTUUID=xxxxxxxx-02 rootfstype=ext4 fsck.repair=yes rootwait quiet
```

Thêm `init=/bin/sh` vào **cuối dòng** (cách 1 khoảng trắng, KHÔNG xuống dòng mới):
```
console=serial0,115200 console=tty1 root=PARTUUID=xxxxxxxx-02 rootfstype=ext4 fsck.repair=yes rootwait quiet init=/bin/sh
```

Lưu file.

---

## Bước 3: Cắm thẻ lại vào Pi, khởi động

1. Rút thẻ khỏi laptop, cắm lại vào Pi
2. Cắm nguồn — Pi sẽ boot vào shell root, **không cần mật khẩu**
3. Màn hình dừng ở dấu nhắc dạng:
   ```
   (initramfs) 
   ```
   hoặc `#` — đây là root shell

---

## Bước 4: Đặt lại mật khẩu

Trong shell đó, gõ lần lượt:

```bash
mount -o remount,rw /
passwd manhfcdsbg
```

> Thay `manhfcdsbg` bằng đúng username hiện ra ở màn hình login (theo ảnh chụp là `manhfcdsbg`).

Nhập mật khẩu mới 2 lần khi được hỏi.

Sau đó gõ:
```bash
sync
reboot -f
```

(nếu `reboot -f` không có tác dụng, rút nguồn Pi trực tiếp)

---

## Bước 5: Gỡ `init=/bin/sh` đã thêm

Pi lúc này vẫn chưa boot bình thường được vì `cmdline.txt` còn `init=/bin/sh`.

1. Tắt Pi, rút thẻ nhớ, cắm lại vào laptop
2. Mở lại `cmdline.txt` trên partition `bootfs`
3. Xoá đúng phần ` init=/bin/sh` đã thêm ở Bước 2, trả về dòng gốc
4. Lưu file, rút thẻ, cắm lại vào Pi

---

## Bước 6: Boot bình thường và đăng nhập

Cắm nguồn Pi, đợi boot xong, đăng nhập bằng mật khẩu mới vừa đặt ở Bước 4.

---

## Xử lý sự cố

### Không thấy partition `bootfs` trên laptop

- Windows chỉ đọc được partition FAT32 đầu tiên (`bootfs`), không đọc được partition `rootfs` (ext4) — vậy là bình thường, chỉ cần sửa `cmdline.txt` ở đây là đủ.
- Nếu không thấy ổ đĩa nào hiện ra, thử đầu đọc thẻ khác hoặc cổng USB khác.

### Gõ `passwd` báo lỗi "Authentication token manipulation error"

Nguyên nhân: quên `mount -o remount,rw /` ở Bước 4 (filesystem đang ở chế độ read-only). Chạy lại lệnh mount rồi thử `passwd` lại.

### Không nhớ chắc username

Xem lại ảnh màn hình login — username hiện sẵn trong ô dropdown phía trên ô nhập mật khẩu (ví dụ `manhfcdsbg`). Nếu vẫn không chắc, trong root shell ở Bước 3 gõ:
```bash
cat /etc/passwd | grep "/home"
```
để liệt kê các user có thư mục home (loại trừ user hệ thống).

### Sau khi đổi xong, muốn tránh quên lần sau

Ghi mật khẩu vào trình quản lý mật khẩu (password manager), hoặc lưu note riêng — **không** ghi mật khẩu vào file trong repo Git.
