#!/usr/bin/env bash
# DIỄN TẬP 1 KỆ — chạy ĐÚNG state machine thi đấu, dừng sau 1 lượt bốc.
#
#   bash scripts/dien_tap_1_ke.sh        # 1 lượt bốc (2 kiện, 2 nhà máy)
#   bash scripts/dien_tap_1_ke.sh 2      # 2 lượt
#
# Khác test_smoke option 5: bài này chạy THẬT main.py, nên có cả nút bấm, công tắc
# nửa sân, đồng hồ 240s, cơ chế retry/bỏ tầng và luồng reset 2-lần-bấm — những thứ
# smoke test không đụng tới.
#
# Khác practice.sh: dừng sau n lượt thay vì chạy hết 6 lượt + NV2.
set -euo pipefail
cd "$(dirname "$0")/.."
export ROBOT_MAX_PICKUPS="${1:-1}"
export ROBOT_LOOP=1          # lặp: xong 1 lượt thì chờ bấm nút để chạy lại
echo "======================================================================"
echo "  DIỄN TẬP $ROBOT_MAX_PICKUPS LƯỢT BỐC — state machine THẬT"
echo "======================================================================"
echo "  TRƯỚC KHI BẤM NÚT:"
echo "    1. Gạt công tắc nửa sân cho đúng"
echo "    2. HẠ CÀNG VỀ SÀN bằng tay (HOME_AT_INIT = False)"
echo "    3. Đặt robot đúng dấu trong ô xuất phát, quay mặt về Kệ 3"
echo "    4. Xếp kiện lên kệ theo docs/HAPPY_CASE.md"
echo
echo "  Xong lượt thì bấm nút để chạy lại. Ctrl+C để thoát."
echo "======================================================================"
exec python3 main.py
