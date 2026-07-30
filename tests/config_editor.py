"""Ghi đè hằng số float trong `config.py` — dùng bởi các menu calibrate tương tác.

Dùng chung cho `test_motion.py` và `test_lift.py`: trước đây mỗi file có một bản
`_save_config` riêng, và cả hai đều gọi `re.sub` mà KHÔNG kiểm đã khớp chưa. Regex
không khớp (đổi tên hằng số, giá trị viết bằng biểu thức, thêm tiền tố...) thì
`re.sub` im lặng trả về nguyên văn — người dùng gõ `t1+` hay `c+` cả chục lần, giá
trị trên màn hình không đổi, không có lỗi nào hiện ra, và ngồi calibrate mãi không
xong mà không hiểu vì sao.
"""

import os
import re

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.py")


def save_config(key: str, value: float, path: str | None = None) -> bool:
    """Đặt `key = value` trong config.py. Trả False (và in lý do) nếu không khớp đúng 1 chỗ."""
    path = path or CONFIG_PATH
    text = open(path, encoding="utf-8").read()
    new_text, n = re.subn(
        rf"^({re.escape(key)}\s*=\s*)[\d.+-]+",
        lambda m: f"{m.group(1)}{value:.3f}",
        text,
        flags=re.MULTILINE,
    )
    if n != 1:
        print(f"  ❌ KHÔNG lưu được {key}: khớp {n} chỗ trong config.py (cần đúng 1). "
              "Sửa tay trong config.py.")
        return False
    open(path, "w", encoding="utf-8").write(new_text)
    return True
