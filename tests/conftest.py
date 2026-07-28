"""
Cấu hình pytest cho thư mục tests/.

`test_motion.py`, `test_lift.py`, `test_vision.py`, `test_smoke.py` là các script
MENU CHẠY TAY trên robot thật (cần GPIO/camera và người bấm Enter), không phải test
tự động. Hàm trong đó tên `test_*` nên pytest tưởng là test và báo "fixture not
found" hàng loạt — nhiễu đến mức che mất test thật khi hỏng.

Chạy chúng bằng:  python3 tests/test_motion.py
Test tự động (chạy được trên PC):  pytest tests/  →  test_logic.py + test_match_sim.py
"""

collect_ignore = [
    "test_motion.py",
    "test_lift.py",
    "test_vision.py",
    "test_smoke.py",
]
