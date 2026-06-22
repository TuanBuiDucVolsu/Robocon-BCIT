#!/bin/bash
# =============================================
# Khởi chạy robot — được gọi bởi systemd service
# =============================================

PROJECT_DIR="/home/mbw12345/Robocon-BCIT"
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

exec $PYTHON main.py
