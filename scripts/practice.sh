#!/bin/bash
# =============================================
# CHẾ ĐỘ LUYỆN TẬP — chạy 1 lượt → nhấn nút → chạy lại, KHÔNG thoát.
# Khác thi đấu: lặp vô hạn cho đến khi Ctrl+C.
#
#   bash scripts/practice.sh
#
# Mỗi lượt: đặt robot về ô xuất phát (hướng 9h) rồi nhấn nút khởi động.
# =============================================

PROJECT_DIR="/home/mbw12345/Robocon-BCIT"
cd "$PROJECT_DIR" || exit 1

# Dùng venv nếu có, không thì system Python
if [ -f "$HOME/robot_env/bin/python3" ]; then
    PYTHON="$HOME/robot_env/bin/python3"
else
    PYTHON="/usr/bin/python3"
fi

echo "=== LUYỆN TẬP === Nhấn nút mỗi lượt. Ctrl+C để thoát."
export ROBOT_LOOP=1
exec "$PYTHON" main.py
