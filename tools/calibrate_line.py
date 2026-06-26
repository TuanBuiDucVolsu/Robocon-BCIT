"""
Công cụ calibrate cảm biến dò line QTR-8A (qua MCP3008).

Mục đích: chốt 2 giá trị trong config.py mà lưới sa bàn KHÔNG quyết định được:
  - LINE_BLACK_IS_HIGH : QTR-8A của bạn đọc line ĐEN ra giá trị cao hay thấp?
  - LINE_THRESHOLD     : ngưỡng phân biệt line/nền.

Chạy trên Pi (đã cắm QTR-8A + MCP3008):
    python3 -m tools.calibrate_line

Đọc giá trị THẬT từ ADC (chưa qua đảo polarity) để quyết định cờ.
Không có phần cứng → in hướng dẫn rồi thoát.
"""

import time
import statistics

import config
from control.mcp3008_bus import get_mcp3008_bus


CHANNELS = list(range(config.LINE_SENSOR_COUNT))


def _sample(bus, seconds: float) -> list[float]:
    """Lấy trung bình ADC 0-1023 mỗi kênh trong `seconds` giây."""
    buckets: list[list[int]] = [[] for _ in CHANNELS]
    end = time.time() + seconds
    while time.time() < end:
        for i, ch in enumerate(CHANNELS):
            buckets[i].append(bus.read_adc(ch))
        time.sleep(0.02)
    return [statistics.mean(b) if b else 0.0 for b in buckets]


def _prompt(msg: str):
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def main():
    bus = get_mcp3008_bus()
    if not bus.available:
        print("❌ MCP3008 không khả dụng (đang chạy trên PC?).")
        print("   Chạy lệnh này TRÊN PI sau khi đã cắm QTR-8A + MCP3008.")
        print("   Khi chạy: làm theo hướng dẫn để chốt LINE_BLACK_IS_HIGH + LINE_THRESHOLD.")
        return

    print("=== CALIBRATE QTR-8A (6 mắt CH0-CH5) ===\n")
    print("Bước 1: Đặt CẢ 6 mắt lên LINE ĐEN.")
    _prompt("   → Đặt xong, nhấn Enter...")
    black = _sample(bus, 2.0)
    print("   ADC trên line đen :", [round(v) for v in black], "| TB =", round(statistics.mean(black)))

    print("\nBước 2: Đặt CẢ 6 mắt lên NỀN SÁNG (ngoài line).")
    _prompt("   → Đặt xong, nhấn Enter...")
    white = _sample(bus, 2.0)
    print("   ADC trên nền sáng :", [round(v) for v in white], "| TB =", round(statistics.mean(white)))

    black_avg = statistics.mean(black)
    white_avg = statistics.mean(white)
    threshold = round((black_avg + white_avg) / 2)
    black_is_high = black_avg > white_avg

    print("\n=== KẾT QUẢ — cập nhật vào config.py ===")
    print(f"   LINE_BLACK_IS_HIGH = {black_is_high}"
          f"   # line đen đọc ra giá trị {'CAO' if black_is_high else 'THẤP'}")
    print(f"   LINE_THRESHOLD     = {threshold}   # điểm giữa đen/sáng")

    margin = abs(black_avg - white_avg)
    if margin < 150:
        print(f"\n   ⚠️ Chênh lệch đen/sáng chỉ {round(margin)} (<150) — tương phản yếu.")
        print("      Chỉnh độ cao cảm biến (3-8mm) hoặc biến trở QTR rồi calibrate lại.")
    else:
        print(f"\n   ✅ Chênh lệch {round(margin)} — tương phản tốt.")
    print("\n   Sau khi đặt LINE_BLACK_IS_HIGH, code tự chuẩn hoá: 0.0=line, không cần sửa gì khác.")


if __name__ == "__main__":
    main()
