#!/usr/bin/env python3
"""
Cô lập lỗi "bánh phải chạy mãi sau khi stop()".

Chạy bánh PHẢI tiến 1.5s → gọi stop() → GIỮ NGUYÊN trạng thái để bạn đo VOM.
Mục đích: tách bạch LỖI PHẦN MỀM (chân IN vẫn cao sau stop) khỏi LỖI PHẦN CỨNG
(chân IN đã về 0V nhưng L298N/motor vẫn chạy).

Chạy trên Pi:
    python3 -m tools.test_right_wheel

Sau khi thấy "ĐÃ STOP", đo bằng VOM (que đen ở GND chung), so với GND:
    • GPIO 23 = IN1_XE_P (tiến phải)  → chân vật lý 16 trên Pi
    • GPIO 22 = IN2_XE_P (lùi phải)   → chân vật lý 15 trên Pi

KẾT LUẬN:
    • Cả 2 chân ~0V mà bánh VẪN quay  → LỖI PHẦN CỨNG (L298N kênh phải / dây OUT).
    • GPIO 23 (hoặc 22) vẫn ~3.3V      → LỖI PHẦN MỀM/gpiozero (báo lại mình).
"""

import sys
import time

sys.path.insert(0, ".")

import config
from control import Motion


def main():
    m = Motion()
    speed = 0.5  # 50% duty

    print("=" * 55)
    print("CÔ LẬP LỖI BÁNH PHẢI CHẠY MÃI")
    print("=" * 55)
    print(f"\n[1] Chạy bánh PHẢI tiến 1.5s (GPIO {config.IN1_XE_P})...")
    # Chỉ đụng bánh phải, giữ bánh trái đứng yên
    m._left_fwd.value = 0
    m._left_rev.value = 0
    m._right_rev.value = 0
    m._right_fwd.value = speed
    time.sleep(1.5)

    print("[2] Gọi m.stop()...")
    m.stop()

    print("\n>>> ĐÃ STOP <<<")
    print("Bánh phải CÓ nên dừng ngay bây giờ.")
    print("\nĐo VOM (que đen ở GND), so với GND:")
    print(f"  • GPIO {config.IN1_XE_P} (IN1_XE_P, tiến) — chân vật lý 16")
    print(f"  • GPIO {config.IN2_XE_P} (IN2_XE_P, lùi)  — chân vật lý 15")
    print("\nKẾT LUẬN:")
    print("  • Cả 2 ~0V mà bánh VẪN quay → LỖI PHẦN CỨNG (L298N kênh phải / OUT).")
    print("  • Có chân vẫn ~3.3V          → LỖI PHẦN MỀM (báo lại).")
    print("\nGiữ nguyên trạng thái để đo. Nhấn Ctrl+C khi xong.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        m.stop()
        m.cleanup()
        print("\nĐã cleanup. Thoát.")


if __name__ == "__main__":
    main()
