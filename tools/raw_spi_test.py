#!/usr/bin/env python3
"""
Test SPI THÔ (qua spidev, KHÔNG qua gpiozero) — chốt lỗi MCP3008 đọc toàn 0.

Bổ sung cho tools/check_mcp3008.py (dùng gpiozero). Tool này nói chuyện trực tiếp
với /dev/spidev nên tách bạch được 3 tầng lỗi khi bị all-0:

    Pi SPI hỏng?  ──→  Dây MISO/MOSI/CLK hỏng?  ──→  Chip/VREF/AGND hỏng?

Chạy trên Pi:
    python3 -m tools.raw_spi_test          # đọc thô 8 channel
    python3 -m tools.raw_spi_test loopback # self-test SPI (cần nối MOSI↔MISO)

Giao thức MCP3008 (SPI mode 0):
    Gửi 3 byte:  [0x01, (0x08|channel)<<4, 0x00]
    Nhận 3 byte: [_, hi, lo]  →  value = ((hi & 0x03) << 8) | lo   (0..1023)
"""

import sys

try:
    import spidev
except ImportError:
    print("❌ Thiếu spidev. Cài: sudo apt install python3-spidev")
    sys.exit(1)

import config

PORT = config.MCP3008_SPI_PORT   # 0 → /dev/spidev0.x
CS   = config.MCP3008_CS         # 0 → CE0
SPEED = 1_000_000                # 1 MHz — an toàn cho MCP3008 ở 3.3V


def _open() -> spidev.SpiDev:
    spi = spidev.SpiDev()
    spi.open(PORT, CS)
    spi.max_speed_hz = SPEED
    spi.mode = 0
    return spi


def read_channel(spi: spidev.SpiDev, channel: int) -> int:
    """Đọc 1 kênh MCP3008 (0..1023) bằng SPI thô."""
    resp = spi.xfer2([0x01, (0x08 | channel) << 4, 0x00])
    return ((resp[1] & 0x03) << 8) | resp[2]


def read_all():
    print("=" * 55)
    print(f"ĐỌC SPI THÔ — /dev/spidev{PORT}.{CS} @ {SPEED//1000} kHz")
    print("=" * 55)

    try:
        spi = _open()
    except FileNotFoundError:
        print(f"❌ Không mở được /dev/spidev{PORT}.{CS}")
        print("   → SPI chưa bật: raspi-config → Interface → SPI → Enable → reboot")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Lỗi mở SPI: {e}")
        sys.exit(1)

    vals = [read_channel(spi, ch) for ch in range(8)]
    labels = ["LINE"] * 6 + ["IR-L", "IR-R"]
    for i, (v, lbl) in enumerate(zip(vals, labels)):
        bar = "█" * (v * 20 // 1023)
        note = ""
        if v == 0:
            note = "  ← 0"
        elif v >= 1020:
            note = "  ← floating/bão hoà"
        print(f"  CH{i} [{lbl:4s}]: {v:4d}  {bar:<20}{note}")

    spi.close()

    print("\n" + "-" * 55)
    if all(v == 0 for v in vals):
        print("❌ SPI THÔ cũng đọc TOÀN 0 → KHÔNG phải lỗi gpiozero.")
        print("   Lỗi phần cứng cấp chip. MISO đang bị kéo xuống 0 hoặc chip")
        print("   không convert. Chạy loopback để tách Pi vs chip:")
        print("       python3 -m tools.raw_spi_test loopback")
        print("   • loopback OK  → Pi + MISO/MOSI tốt → lỗi VREF(pin15)/AGND(pin14)")
        print("                    hoặc dây MISO từ CHIP (pin12) đứt.")
        print("   • loopback FAIL→ Pi SPI hoặc chân GPIO 9/10 có vấn đề.")
    elif all(v >= 1020 for v in vals):
        print("⚠  Toàn ~1023: input floating (chưa nối cảm biến) hoặc VREF>VDD.")
    else:
        print("✓  SPI thô đọc được số hợp lệ — chip giao tiếp OK.")
        print("   Nếu robot vẫn lỗi → vấn đề ở ngưỡng/polarity trong config.py,")
        print("   KHÔNG phải phần cứng. Dùng: python3 -m tools.calibrate_line")


def loopback():
    print("=" * 55)
    print("SPI LOOPBACK SELF-TEST (không cần MCP3008)")
    print("=" * 55)
    print("Mục đích: chứng minh khối SPI của Pi + chân MOSI/MISO chạy được,")
    print("tách bạch 'lỗi Pi' khỏi 'lỗi chip/VREF/AGND'.\n")
    print("CHUẨN BỊ ĐẤU DÂY:")
    print("  1. RÚT dây MISO khỏi chip (hoặc rút cả chip ra cho chắc).")
    print("  2. Nối JUMPER trực tiếp:  GPIO 10 (MOSI, chân vật lý 19)")
    print("                          ↔ GPIO  9 (MISO, chân vật lý 21)")
    print("  → Dữ liệu gửi ra MOSI sẽ vòng thẳng về MISO nếu Pi SPI tốt.\n")
    try:
        input("  Đã nối MOSI↔MISO xong, nhấn Enter để test...")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    try:
        spi = _open()
    except Exception as e:
        print(f"❌ Lỗi mở SPI: {e}")
        return

    patterns = [0x00, 0xFF, 0xAA, 0x55, 0x3C, 0x81]
    ok = True
    for p in patterns:
        echo = spi.xfer2([p])[0]
        mark = "OK" if echo == p else "✗ SAI"
        if echo != p:
            ok = False
        print(f"  Gửi 0x{p:02X}  →  Nhận 0x{echo:02X}   {mark}")
    spi.close()

    print("\n" + "-" * 55)
    if ok:
        print("✓  LOOPBACK OK — Pi SPI + chân MOSI/MISO HOẠT ĐỘNG TỐT.")
        print("   → Lỗi all-0 nằm ở PHÍA CHIP: nghi ngờ theo thứ tự")
        print("     [1] VREF (pin 15) chưa có 3.3V")
        print("     [2] AGND (pin 14) chưa nối GND")
        print("     [3] Dây MISO từ CHIP pin 12 → GPIO 9 đứt/tuột")
        print("   (Nhớ cắm lại MISO vào chip sau khi test.)")
    else:
        print("✗  LOOPBACK SAI — không nhận lại đúng byte đã gửi.")
        print("   → Vấn đề ở chính Pi: jumper MOSI↔MISO chưa chắc, sai chân")
        print("     GPIO 9/10, hoặc SPI peripheral lỗi. Kiểm tra lại jumper trước.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "loopback":
        loopback()
    else:
        read_all()
