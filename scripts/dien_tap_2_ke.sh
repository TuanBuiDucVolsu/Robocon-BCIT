#!/usr/bin/env bash
# DIỄN TẬP 2 KỆ — 8 PALLET, chạy ĐÚNG state machine thi đấu.
#
#   bash scripts/dien_tap_2_ke.sh
#
# 2 kệ × 2 tầng × 2 kiện = 8 pallet = 4 LƯỢT BỐC. Robot dừng sau lượt thứ 4, không
# chạy tiếp Kệ 1 và không làm NV2.
#
# Thứ tự robot sẽ đi (main._advance_position: xong tầng 1 → tầng 2 cùng kệ, xong
# tầng 2 → sang kệ kế, tầng 1):
#
#     lượt 1   Kệ 3 (R0)  tầng 1   → giao 2 nhà máy → về
#     lượt 2   Kệ 3 (R0)  tầng 2   → giao 2 nhà máy → về
#     lượt 3   Kệ 2 (R2)  tầng 1   → giao 2 nhà máy → về
#     lượt 4   Kệ 2 (R2)  tầng 2   → giao 2 nhà máy → DỪNG
#
# Khác dien_tap_1_ke.sh: bài đó chỉ 1-2 lượt, không chạm tới việc CHUYỂN KỆ. Bài
# này là bài đầu tiên chạy qua chặng Kệ 3 → Kệ 2, tức tuyến kệ↔kệ mà bảng route
# tĩnh cũ từng sai 9/12 trường hợp.
#
# Khác practice.sh: dừng sau 4 lượt thay vì 6 lượt + NV2 — đủ ngắn để lặp lại
# trong buổi test, đủ dài để phủ chuyển kệ và cả hai tầng.
set -euo pipefail
cd "$(dirname "$0")/.."

export ROBOT_MAX_PICKUPS=4
export ROBOT_LOOP=1          # xong 4 lượt thì chờ bấm nút để chạy lại từ đầu

echo "======================================================================"
echo "  DIỄN TẬP 2 KỆ — 8 PALLET (4 lượt bốc), state machine THẬT"
echo "======================================================================"
echo "  XẾP KIỆN — cần ĐỦ 8 pallet:"
echo "     Kệ 3 (R0) tầng 1: 2 kiện      Kệ 2 (R2) tầng 1: 2 kiện"
echo "     Kệ 3 (R0) tầng 2: 2 kiện      Kệ 2 (R2) tầng 2: 2 kiện"
echo "     Mỗi cặp là HAI nhà máy KHÁC nhau (xem docs/HAPPY_CASE.md)"
echo
echo "  TRƯỚC KHI BẤM NÚT:"
echo "     1. Gạt công tắc nửa sân cho đúng — đọc dòng 'NỬA SÂN:' trong log"
echo "     2. HẠ CÀNG VỀ SÀN bằng tay (HOME_AT_INIT = False)"
echo "     3. Đặt robot đúng dấu trong ô xuất phát, quay mặt về Kệ 3"
echo "     4. Service thi đấu phải TẮT:  sudo systemctl stop robot"
echo
echo "  NHÌN BẰNG MẮT (log không tự phát hiện được):"
echo "     • Kiện có rơi TRONG ô nhà máy 25x25cm không"
echo "     • Tấm in dưới mỗi kiện có ĐÚNG nhãn không (giao nhầm = 0 điểm)"
echo
echo "  Xong 4 lượt thì bấm nút để chạy lại. Ctrl+C để thoát."
echo "  Sau khi chạy:  python3 -m tools.measure_phases"
echo "======================================================================"

exec python3 main.py
