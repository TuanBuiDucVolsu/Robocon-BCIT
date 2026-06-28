#!/usr/bin/env python3
"""
Chẩn đoán MCP3008 — kiểm tra SPI bus, nguồn, và từng channel.
Chạy: python3 tools/check_mcp3008.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 1. Kiểm tra SPI kernel module ────────────────────────────────────────────
print("=" * 55)
print("CHẨN ĐOÁN MCP3008")
print("=" * 55)

print("\n[1] Kiểm tra SPI kernel module...")
spi_devs = [f for f in os.listdir("/dev") if f.startswith("spidev")]
if spi_devs:
    print(f"  OK  /dev/{', /dev/'.join(sorted(spi_devs))}")
else:
    print("  LỖI  Không tìm thấy /dev/spidev* !")
    print("       Chạy: sudo raspi-config → Interface Options → SPI → Enable")
    sys.exit(1)

# ── 2. Kiểm tra gpiozero import ──────────────────────────────────────────────
print("\n[2] Kiểm tra gpiozero / MCP3008 driver...")
try:
    from gpiozero import MCP3008, Device
    Device.ensure_pin_factory()
    print("  OK  gpiozero.MCP3008 import thành công")
except Exception as e:
    print(f"  LỖI  {e}")
    sys.exit(1)

# ── 3. Khởi tạo 1 channel và đọc thử ────────────────────────────────────────
import config

print(f"\n[3] Khởi tạo MCP3008 (SPI port={config.MCP3008_SPI_PORT} CS={config.MCP3008_CS})...")
try:
    ch0 = MCP3008(channel=0, port=config.MCP3008_SPI_PORT, device=config.MCP3008_CS)
    val = ch0.value
    adc = int(round(val * 1023))
    print(f"  OK  CH0 đọc được: raw={val:.4f}  ADC={adc}")
    if adc == 0:
        print("  CẢNH BÁO  ADC=0 → VDD/VREF chưa cấp điện HOẶC MISO hở")
    elif adc == 1023:
        print("  CẢNH BÁO  ADC=1023 → input CH0 đang trôi nổi (floating)")
    else:
        print(f"  ADC={adc} — MCP3008 đang phản hồi bình thường")
    ch0.close()
except Exception as e:
    print(f"  LỖI  Không khởi tạo được MCP3008: {e}")
    sys.exit(1)

# ── 4. Đọc tất cả 8 channel một lần ─────────────────────────────────────────
print("\n[4] Đọc 8 channel một lượt...")
channels = []
try:
    for i in range(8):
        ch = MCP3008(channel=i, port=config.MCP3008_SPI_PORT, device=config.MCP3008_CS)
        channels.append(ch)
    vals = [int(round(ch.value * 1023)) for ch in channels]
    labels = ["LINE"]*6 + ["IR-L", "IR-R"]
    for i, (v, lbl) in enumerate(zip(vals, labels)):
        bar = "█" * (v * 20 // 1023) if v > 0 else ""
        status = ""
        if v == 0:
            status = "  ← ADC=0 (VDD mất / hở MISO?)"
        elif v == 1023:
            status = "  ← ADC=1023 (input floating)"
        print(f"  CH{i} [{lbl:4s}]: {v:4d}  {bar:<20}{status}")
    for ch in channels:
        ch.close()
except Exception as e:
    print(f"  LỖI  {e}")
    for ch in channels:
        try: ch.close()
        except: pass
    sys.exit(1)

# ── 5. Quan sát thay đổi real-time ──────────────────────────────────────────
print("\n[5] Quan sát real-time 5 giây (che/bỏ tay lên cảm biến)...")
try:
    chs = [MCP3008(channel=i, port=config.MCP3008_SPI_PORT,
                   device=config.MCP3008_CS) for i in range(8)]
    baseline = [int(round(ch.value * 1023)) for ch in chs]
    changed = set()
    start = time.time()
    while time.time() - start < 5:
        vals = [int(round(ch.value * 1023)) for ch in chs]
        row = "  ".join(f"CH{i}:{v:4d}" for i, v in enumerate(vals))
        print(f"\r  {row}", end="", flush=True)
        for i, (b, v) in enumerate(zip(baseline, vals)):
            if abs(v - b) > 50:
                changed.add(i)
        time.sleep(0.15)
    print()
    for ch in chs:
        ch.close()
except KeyboardInterrupt:
    print()
    for ch in chs:
        try: ch.close()
        except: pass

# ── 6. Kết luận ──────────────────────────────────────────────────────────────
print("\n[6] KẾT LUẬN")
all_zero = all(v == 0 for v in vals)
all_same = len(set(vals)) == 1

if all_zero:
    print("  ❌  TẤT CẢ channel = 0")
    print("      Nguyên nhân 90%: MCP3008 pin 16 (VDD) hoặc pin 15 (VREF) không có 3.3V")
    print("      Kiểm tra:")
    print("        • MCP3008 pin 16 (VDD)  → 3.3V Pi (pin 1 hoặc 17)")
    print("        • MCP3008 pin 15 (VREF) → 3.3V (thường nối chung VDD)")
    print("        • MCP3008 pin  9 (DGND) → GND Pi")
    print("        • MCP3008 pin 14 (AGND) → GND Pi")
    print("        • MCP3008 pin 12 (DOUT/MISO) → GPIO 9 Pi")
elif all_same and changed == set():
    print("  ⚠   Giá trị đồng đều, không thay đổi khi che tay")
    print("      Cảm biến có thể chưa có điện hoặc dây output hở")
elif changed:
    print(f"  ✓   Channel thay đổi khi che tay: {sorted(changed)}")
    print("      MCP3008 ĐANG HOẠT ĐỘNG — vấn đề nằm ở code/ngưỡng")
else:
    print("  ⚠   MCP3008 phản hồi nhưng giá trị không thay đổi")
    print("      Kiểm tra dây nối từ cảm biến đến CH0-CH7")
