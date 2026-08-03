#!/bin/bash
# =============================================
# Khởi chạy robot — được gọi bởi systemd service
# =============================================

# Suy từ vị trí CHÍNH FILE NÀY, không viết cứng: trước đây ghi
# /home/mbw12345/Robocon-BCIT (máy dev) nên trên phantom (/home/bcit/...) service
# thi đấu KHÔNG chạy được. practice.sh đã dính đúng lỗi này.
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/robot_log.txt"

cd "$PROJECT_DIR"

# Nếu có venv thì dùng, không thì dùng system Python
if [ -f "$HOME/robot_env/bin/python3" ]; then
    PYTHON="$HOME/robot_env/bin/python3"
else
    PYTHON="/usr/bin/python3"
fi

echo "$(date): Khởi động robot — Python=$PYTHON" >> "$LOG_FILE"
echo "$(date): DEBUG_MODE=$(grep 'DEBUG_MODE' config.py)" >> "$LOG_FILE"

export ROBOT_COMPETE=1

exec $PYTHON main.py
