#!/bin/bash
# =============================================
# CHẾ ĐỘ LUYỆN TẬP — chạy 1 lượt → nhấn nút → chạy lại, KHÔNG thoát.
# Khác thi đấu: lặp vô hạn cho đến khi Ctrl+C.
#
#   bash scripts/practice.sh
#
# Mỗi lượt: đặt robot về ô xuất phát (hướng 9h) rồi nhấn nút khởi động.
# =============================================

# Đường dẫn suy từ vị trí CHÍNH FILE NÀY, không viết cứng: trước đây ghi
# /home/mbw12345/Robocon-BCIT nên trên phantom (/home/bcit/...) là hỏng ngay.
# dien_tap_1_ke.sh vốn đã làm đúng cách này.
cd "$(dirname "$0")/.." || exit 1

# Dùng venv nếu có, không thì system Python
if [ -f "$HOME/robot_env/bin/python3" ]; then
    PYTHON="$HOME/robot_env/bin/python3"
else
    PYTHON="/usr/bin/python3"
fi

echo "=== LUYỆN TẬP === Nhấn nút mỗi lượt. Ctrl+C để thoát."
export ROBOT_LOOP=1
exec "$PYTHON" main.py
