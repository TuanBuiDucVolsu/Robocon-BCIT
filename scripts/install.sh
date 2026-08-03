#!/bin/bash
# =============================================
# Cài service tự khởi động robot khi bật Pi.
# Chạy 1 lần: sudo bash scripts/install.sh
#
# ⚠️ Đường dẫn và user được SUY RA lúc cài, không viết cứng. Bản trước ghi cứng
# /home/mbw12345/Robocon-BCIT và User=mbw12345 (máy dev), nên cài lên phantom
# (/home/bcit/..., user bcit) là service không chạy được — mà lỗi đó chỉ lộ ra
# lúc bật Pi ở sân thi.
# =============================================

set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
# User THẬT SỰ sở hữu thư mục, không phải root (script chạy bằng sudo).
RUN_USER="$(stat -c '%U' "$DIR")"
TEMPLATE="$DIR/scripts/robot.service"
DEST="/etc/systemd/system/robot.service"

echo "=== Cài đặt Robot Service ==="
echo "  Thư mục : $DIR"
echo "  User    : $RUN_USER"
echo ""

if [ "$RUN_USER" = "root" ]; then
    echo "❌ Thư mục thuộc về root — service sẽ chạy bằng root, không đúng."
    echo "   Kiểm lại quyền sở hữu: ls -ld $DIR"
    exit 1
fi

chmod +x "$DIR/scripts/start.sh"

sed -e "s|__USER__|$RUN_USER|g" -e "s|__DIR__|$DIR|g" "$TEMPLATE" > "$DEST"
echo "[1/4] Đã sinh robot.service theo đường dẫn thật"

systemctl daemon-reload
echo "[2/4] Đã reload systemd"

systemctl enable robot.service
echo "[3/4] Đã bật tự khởi động khi boot"

systemctl start robot.service
echo "[4/4] Đã khởi động robot service"

echo ""
echo "=== HOÀN TẤT ==="
echo ""
echo "Lệnh hữu ích:"
echo "  sudo systemctl status robot     — Xem trạng thái"
echo "  sudo systemctl stop robot       — Dừng robot"
echo "  sudo systemctl restart robot    — Khởi động lại"
echo "  sudo systemctl disable robot    — TẮT tự khởi động (dùng khi test tay)"
echo "  journalctl -u robot -f          — Xem log realtime"
echo "  cat $DIR/robot_log.txt          — Xem log file"
echo ""
echo "Bật Pi → robot tự chạy → chờ nút bấm GPIO $(grep -m1 START_BUTTON_PIN "$DIR/config.py")"
