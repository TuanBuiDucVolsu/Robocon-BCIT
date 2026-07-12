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
LINE_CHANNELS = set(range(6))          # CH0-5 = QTR-8A  (VCC 5V)
IR_CHANNELS   = {6, 7}                 # CH6-7 = IR pallet (VCC 3.3V)
CH_LABELS     = ["LINE"] * 6 + ["IR-L", "IR-R"]

all_zero = all(v == 0 for v in vals)
all_max = all(v >= 1020 for v in vals)
all_same = len(set(vals)) == 1

if all_zero:
    print("  ❌  TẤT CẢ 8 channel = 0 (kể cả CH6/CH7 IR pallet)")
    print("      → Lỗi ở CẤP CON CHIP MCP3008, KHÔNG phải ở QTR/IR.")
    print("        (Nếu chỉ cảm biến hỏng thì kênh hở sẽ trôi nổi ~cao, không phải 0 sạch.)")
    print("      Kiểm tra theo thứ tự khả năng:")
    print("      [1] Cắm NGƯỢC chip (hay gặp nhất): so chấm tròn/khấc = pin 1.")
    print("          Cắm ngược → all-zero và chip có thể NÓNG. Sờ thử chip.")
    print("      [2] MISO hở: MCP3008 pin 12 (DOUT) → GPIO 9 Pi (pin 21).")
    print("          Dây này đứt → SPI đọc ra toàn 0 y hệt mất nguồn.")
    print("      [3] Mất nguồn 3.3V (đo bằng VOM so với GND, KHÔNG dùng 5V):")
    print("          • MCP3008 pin 16 (VDD)  → 3.3V Pi (pin 1 hoặc 17)")
    print("          • MCP3008 pin 15 (VREF) → 3.3V (thường nối chung VDD)")
    print("      [4] GND chưa đủ:")
    print("          • MCP3008 pin  9 (DGND) → GND Pi")
    print("          • MCP3008 pin 14 (AGND) → GND Pi")
    print("      [5] Sai chân SPI còn lại:")
    print("          • pin 13 (CLK) → GPIO 11  • pin 11 (DIN) → GPIO 10  • pin 10 (CS) → GPIO 8 (CE0)")
    print("      [6] SPI chưa bật: `ls /dev/spidev*` phải thấy spidev0.0")
    print("          (nếu không → raspi-config → Interface → SPI → Enable → reboot)")
elif all_max:
    print("  ⚠   TẤT CẢ channel ≈ 1023 (bão hoà)")
    print("      • Có thể VREF > VDD, hoặc toàn bộ input đang floating (chưa nối cảm biến)")
    print("      • Nối cảm biến vào CH0-CH7 rồi đo lại")
elif all_same and changed == set():
    print("  ⚠   Giá trị đồng đều, không thay đổi khi che tay")
    print("      MCP3008 có phản hồi nhưng cảm biến chưa có điện hoặc dây OUT hở")
    print("      • QTR-8A VCC → 5V, GND chung; IR pallet VCC → 3.3V, GND chung")
elif changed:
    print(f"  ✓   Channel thay đổi khi che tay: {sorted(changed)}")
    print("      MCP3008 ĐANG HOẠT ĐỘNG — vấn đề (nếu có) nằm ở code/ngưỡng")
    print("      • Chỉnh LINE_THRESHOLD (QTR) / PALLET_THRESHOLD (IR) trong config.py")
else:
    print("  ⚠   MCP3008 phản hồi nhưng giá trị không thay đổi khi che tay")
    print("      Kiểm tra dây OUT từng cảm biến đến CH0-CH7")

# ── 7. Chẩn đoán từng channel báo lỗi ────────────────────────────────────────
# Bỏ qua nếu toàn 0 / toàn 1023 — hai ca đó đã có hướng dẫn tổng ở mục [6].
if not (all_zero or all_max):
    print("\n[7] CHI TIẾT TỪNG CHANNEL")
    bad_zero, bad_float, no_test = [], [], []
    for i, v in enumerate(vals):
        is_ir = i in IR_CHANNELS
        vcc   = "3.3V" if is_ir else "5V"
        who   = ("IR " + ("trái" if i == 6 else "phải")) if is_ir else f"QTR mắt {i}"
        if i in changed:
            print(f"  CH{i} [{CH_LABELS[i]}]: {v:4d}  ✓ đổi khi che → channel OK")
            continue
        if v == 0:
            bad_zero.append(i)
            print(f"  CH{i} [{CH_LABELS[i]}]: {v:4d}  ❌ =0 (kéo xuống đất)")
            print(f"       • Dây OUT cảm biến → CH{i} tuột/đứt (chân đọc bị nối đất)")
            print(f"       • {who} chết, hoặc cụm cảm biến mất VCC {vcc} / GND chung")
        elif v >= 1020:
            bad_float.append(i)
            print(f"  CH{i} [{CH_LABELS[i]}]: {v:4d}  ⚠ ~1023 (trôi nổi/floating)")
            print(f"       • Chưa nối cảm biến vào CH{i}, hoặc dây OUT hở → chân treo cao")
            print(f"       • Nếu ĐÃ nối: {who} chưa cấp {vcc}, hoặc OUT không ra tín hiệu")
        else:
            no_test.append(i)
            print(f"  CH{i} [{CH_LABELS[i]}]: {v:4d}  – trị hợp lệ (chưa che thử kênh này?)")

    # Gợi ý theo cụm — nhiều channel cùng nhóm lỗi ⇒ nghi nguồn/GND cả cụm
    bad = bad_zero + bad_float
    if not bad:
        print("\n  → Không channel nào ở mức lỗi rõ (0 hoặc 1023).")
        if no_test:
            print(f"     (CH {no_test}: hãy che/đưa vật vào để xác nhận còn sống.)")
    else:
        print(f"\n  → Channel cần kiểm: {sorted(bad)}")
        line_bad = [i for i in bad if i in LINE_CHANNELS]
        ir_bad   = [i for i in bad if i in IR_CHANNELS]
        if len(line_bad) >= 2:
            print(f"     • CH{line_bad} (nhóm LINE) cùng lỗi → nghi QTR-8A mất VCC 5V")
            print("       hoặc GND chung của thanh QTR, không phải từng mắt lẻ.")
        if len(ir_bad) == 2:
            print("     • Cả CH6+CH7 (IR) lỗi → nghi nguồn 3.3V / GND chung của 2 IR.")
        if line_bad and ir_bad:
            print("     • CH0-5 (LINE) và CH6-7 (IR) ĐỀU lỗi tuy dùng nguồn khác nhau")
            print("       → nghi cấp con chip MCP3008 (xem hướng dẫn all-0 ở mục [6]).")
        if bad_float and bad_zero:
            print("     • Có kênh =0 lẫn kênh =1023 → thường là lỗi DÂY từng cảm biến,")
            print("       chip vẫn convert được (không phải hỏng chip).")
