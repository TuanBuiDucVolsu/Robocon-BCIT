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

# ⚠️ SINH RA CHỖ KHÁC RỒI MỚI CHÉP ĐÈ — đừng ghi thẳng vào $DEST.
# `sed ... > "$DEST"` cắt trắng file đích TRƯỚC khi sed chạy. sed hỏng một nhịp là
# còn lại file 0 byte, mà systemd coi unit RỖNG là "masked": `systemctl start`
# báo "Unit robot.service is masked" — một thông báo chẳng liên quan gì tới
# nguyên nhân thật. Đã xảy ra trên phantom 04/08.
if [ ! -s "$TEMPLATE" ]; then
    echo "❌ Không thấy bản mẫu $TEMPLATE (hoặc rỗng)."
    exit 1
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
sed -e "s|__USER__|$RUN_USER|g" -e "s|__DIR__|$DIR|g" "$TEMPLATE" > "$TMP"

# Kiểm TRƯỚC khi chép đè: rỗng, hoặc còn sót chỗ thay thế, đều là hỏng.
if [ ! -s "$TMP" ]; then
    echo "❌ Sinh ra file RỖNG — không chép đè. Kiểm lại $TEMPLATE."
    exit 1
fi
if grep -q "__USER__\|__DIR__" "$TMP"; then
    echo "❌ Còn sót __USER__/__DIR__ chưa thay — không chép đè."
    exit 1
fi
if ! grep -q "^ExecStart=" "$TMP"; then
    echo "❌ File sinh ra không có dòng ExecStart — không chép đè."
    exit 1
fi

install -m 644 "$TMP" "$DEST"
echo "[1/4] Đã sinh robot.service theo đường dẫn thật ($(wc -c < "$DEST") byte)"

systemctl daemon-reload
echo "[2/4] Đã reload systemd"

systemctl enable robot.service
echo "[3/4] Đã bật tự khởi động khi boot"

# ⚠️ CỐ TÌNH KHÔNG khởi động ngay. Service chiếm GPIO, và trong buổi test thì
# mọi bài test tay sau đó sẽ báo lỗi bận chân — người cài không nối được hai
# việc đó với nhau. Bật khi nào muốn, bằng lệnh in ra dưới đây.
echo "[4/4] CHƯA khởi động — service chỉ tự chạy từ LẦN BẬT MÁY SAU"

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
echo "  sudo systemctl start robot      — CHẠY NGAY BÂY GIỜ (chiếm GPIO)"
echo ""
echo "⚠️ Service ĐANG TẮT. Từ lần bật máy sau nó mới tự chạy."
echo "   Còn test tay hôm nay thì cứ để nguyên, đừng start."
echo ""
echo "Bật Pi → robot tự chạy → chờ nút bấm GPIO $(grep -m1 START_BUTTON_PIN "$DIR/config.py")"
