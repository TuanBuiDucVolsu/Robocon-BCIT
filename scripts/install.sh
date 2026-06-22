#!/bin/bash
# =============================================
# Cài đặt service tự khởi động robot khi bật Pi
# Chạy 1 lần duy nhất: sudo bash scripts/install.sh
# =============================================

set -e

SERVICE_FILE="/home/mbw12345/Robocon-BCIT/scripts/robot.service"
DEST="/etc/systemd/system/robot.service"

echo "=== Cài đặt Robot Service ==="

# Cấp quyền chạy cho start.sh
chmod +x /home/mbw12345/Robocon-BCIT/scripts/start.sh

# Copy service file
cp "$SERVICE_FILE" "$DEST"
echo "[1/4] Đã copy robot.service vào systemd"

# Reload systemd
systemctl daemon-reload
echo "[2/4] Đã reload systemd"

# Bật tự khởi động
systemctl enable robot.service
echo "[3/4] Đã bật tự khởi động khi boot"

# Khởi động ngay
systemctl start robot.service
echo "[4/4] Đã khởi động robot service"

echo ""
echo "=== HOÀN TẤT ==="
echo ""
echo "Lệnh hữu ích:"
echo "  sudo systemctl status robot     — Xem trạng thái"
echo "  sudo systemctl stop robot       — Dừng robot"
echo "  sudo systemctl restart robot    — Khởi động lại"
echo "  sudo systemctl disable robot    — Tắt tự khởi động"
echo "  journalctl -u robot -f          — Xem log realtime"
echo "  cat robot_log.txt               — Xem log file"
echo ""
echo "Khi Pi khởi động → robot tự chạy → chờ nút bấm GPIO $( grep START_BUTTON_PIN /home/mbw12345/Robocon-BCIT/config.py | head -1 )"
