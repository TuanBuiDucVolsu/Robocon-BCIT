"""
Công cụ calibrate màu HSV cho 4 kiện hàng cố định (vision.py).

4 kiện hàng (Samsung/Foxconn/Amkor/Hana Micron) dán hình CỐ ĐỊNH theo thể lệ —
không đổi giữa các trận. COLOR_RANGES trong config.py hiện ước lượng bằng mắt,
dễ lệch dưới ánh sáng thi đấu thật (đây là lý do camera "không nhạy" trên Pi).

Tool này chụp ảnh THẬT từng kiện trên Pi (đúng ROI mà vision.py dùng khi quét),
tự tính dải HSV sát dữ liệu thật rồi in ra để dán thẳng vào config.COLOR_RANGES.
Không đoán tay nữa — vẫn quét camera mỗi trận (đúng thể lệ "Camera AI bắt buộc"),
chỉ có ngưỡng nhận diện là được chốt cứng theo đúng 4 hình thật.

Kiện hàng khá nhỏ so với ROI (khối 40x40x40mm trên pallet 90x90mm, trong ngăn kệ
240x120x240mm) → phần lớn ROI có thể là NỀN (kệ + pallet, màu tuỳ vật liệu thật
đang dùng — theo thể lệ chuẩn là kệ đen/pallet nâu, nhưng bản in/thực tế có thể
khác) chứ không phải khối hàng. Tool chụp thêm 1 mẫu "nền trống" (không có kiện
hàng nào, đúng màu thật đang dùng) rồi kiểm tra xem nền có lọt vào dải màu nào
đã tính không.

QUAN TRỌNG — ROI khi calibrate PHẢI giống hệt lúc quét thật (dùng chung
config.ROI_MARGIN, không cắt chặt hơn): nếu ROI lúc calibrate hẹp hơn, range
tính ra "sạch" hơn thực tế, nhưng lúc classify_package()/classify_pair() chạy
thật với ROI rộng hơn, % pixel đúng màu bị pha loãng bởi nền xung quanh nhiều
hơn, khiến confidence tụt dưới ngưỡng dù đúng kiện hàng (đã từng xảy ra — dùng
margin riêng cho calibrate rồi bỏ vì lý do này). Muốn né nền lẫn vào mẫu màu,
dùng phông trắng/xám trơn chắn phía sau kiện hàng lúc calibrate, KHÔNG cắt ROI
khác đi.

Chạy trên Pi (đã cắm camera CSI):
    python3 -m tools.calibrate_vision

Không có camera/OpenCV → in hướng dẫn rồi thoát.
"""

import time

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

import config
from vision import Vision


SAMPLE_SECONDS = 2.0     # Thời gian chụp mẫu mỗi kiện hàng
SAMPLE_INTERVAL = 0.1    # Giãn cách giữa các frame lấy mẫu

# ĐÃ BỎ margin riêng cho lúc calibrate (từng thử cắt chặt hơn config.ROI_MARGIN để né nền
# phòng) — gây lệch: range tính từ ROI hẹp, nhưng classify_package()/classify_pair() thật
# lại dùng ROI rộng hơn (config.ROI_MARGIN), % pixel đúng màu bị pha loãng bởi nền/tay/khung
# robot nhiều hơn lúc calibrate, khiến confidence thật tụt dưới ngưỡng dù đúng kiện hàng.
# Cách đúng để né nền: dùng phông trắng/xám trơn chắn phía sau kiện hàng lúc calibrate (xem
# hướng dẫn Bước 0-4 khi chạy tool), KHÔNG phải cắt ROI khác với lúc quét thật.

# Ngưỡng lọc pixel "có màu" (chip/logo) khỏi nền trắng/xám của pallet+kệ —
# cùng logic chromatic/achromatic mà config.py đang dùng để phân loại.
CHROMA_SAT_MIN = 60      # S >= ngưỡng này mới coi là pixel có màu (không phải nền)
ACHROMA_SAT_MAX = 50     # S < ngưỡng này mới coi là ứng viên xám (Amkor)
ACHROMA_VAL_MIN = 50     # Loại vùng quá tối (bóng đổ)
ACHROMA_VAL_MAX = 235    # Loại vùng quá sáng (nền giấy trắng)

PERCENTILE_LOW = 5
PERCENTILE_HIGH = 95
PAD_H = 5                # Nới thêm quanh percentile để không quá khít (sát mép mất điểm khi ánh sáng đổi nhẹ)
PAD_SV = 12

# Decal có nhiều chi tiết (icon, chữ, viền...) chứ không phải màu đặc 1 khối — pixel
# "có màu" (S>=CHROMA_SAT_MIN) có thể lẫn nhiều cụm Hue khác nhau (nền, chi tiết phụ,
# phản chiếu ánh sáng). Nếu lấy percentile trên TOÀN BỘ pixel đó, dải sẽ bị kéo rộng ra
# bao trùm cả cụm màu "rác". Nên tìm đỉnh histogram Hue (cụm lớn nhất) trước, chỉ lấy
# percentile trong cụm đó.
HUE_BIN_WIDTH = 5        # Độ rộng mỗi bin histogram Hue
HUE_PEAK_WINDOW = 3      # Số bin mỗi bên quanh đỉnh giữ lại (cửa sổ rộng ~2*3*5=30 đơn vị Hue)


def _prompt(msg: str):
    try:
        input(msg)
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)


def _roi_hsv_pixels(vision: Vision, seconds: float):
    """Chụp nhiều frame, cắt ROI (giống hệt _classify_by_color — dùng đúng config.ROI_MARGIN
    để mô phỏng chính xác khung hình lúc quét thật), gộp toàn bộ pixel HSV."""
    margin = getattr(config, "ROI_MARGIN", 0.2)
    pixels = []
    end = time.time() + seconds
    while time.time() < end:
        frame = vision._capture_frame()
        if frame is None:
            time.sleep(SAMPLE_INTERVAL)
            continue
        h, w = frame.shape[:2]
        mx, my = int(w * margin), int(h * margin)
        roi = frame[my:h - my, mx:w - mx]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        pixels.append(hsv.reshape(-1, 3))
        time.sleep(SAMPLE_INTERVAL)
    if not pixels:
        return np.empty((0, 3), dtype=np.uint8)
    return np.concatenate(pixels, axis=0)


def _percentile_range(values, pad: int, lo_bound: int, hi_bound: int):
    if len(values) == 0:
        return lo_bound, hi_bound
    lo = int(np.percentile(values, PERCENTILE_LOW)) - pad
    hi = int(np.percentile(values, PERCENTILE_HIGH)) + pad
    return max(lo_bound, lo), min(hi_bound, hi)


def _hue_peak_window(values, domain_min: int, domain_max: int):
    """Tìm đỉnh histogram Hue (cụm màu lớn nhất) rồi trả về (lo, hi, %pixel thuộc cụm đó).
    Lọc bỏ các cụm màu phụ/nhiễu (nền, chi tiết khác trên decal...) trước khi lấy percentile."""
    bins = np.arange(domain_min, domain_max + HUE_BIN_WIDTH, HUE_BIN_WIDTH)
    counts, edges = np.histogram(values, bins=bins)
    if counts.sum() == 0:
        return domain_min, domain_max, 0.0
    peak_idx = int(np.argmax(counts))
    lo_bin = max(0, peak_idx - HUE_PEAK_WINDOW)
    hi_bin = min(len(counts) - 1, peak_idx + HUE_PEAK_WINDOW)
    lo, hi = int(edges[lo_bin]), int(edges[hi_bin + 1])
    dominance = counts[lo_bin:hi_bin + 1].sum() / counts.sum()
    return lo, hi, float(dominance)


def _calibrate_chromatic(pixels, label: str):
    """Range HSV cho kiện có màu rõ (samsung/foxconn/hana_micron)."""
    h, s, v = pixels[:, 0].astype(int), pixels[:, 1].astype(int), pixels[:, 2].astype(int)
    mask = s >= CHROMA_SAT_MIN
    coverage = mask.mean() if len(mask) else 0.0
    print(f"    Pixel có màu (S>={CHROMA_SAT_MIN}): {coverage*100:.1f}% ROI")
    if coverage < 0.03:
        print("    ⚠️ Quá ít pixel có màu — kiểm tra ánh sáng/khoảng cách tới camera.")

    hf, sf, vf = h[mask], s[mask], v[mask]
    if len(hf) == 0:
        print("    ⚠️ Không có pixel nào lọt ngưỡng — giữ nguyên dải cũ trong config.py.")
        return None

    if label == "hana_micron":
        # Đỏ wrap qua 0/179 — unwrap về khoảng [-90, 89) trước khi tìm đỉnh histogram.
        h_unwrapped = np.where(hf > 90, hf - 180, hf)
        lo_peak, hi_peak, dominance = _hue_peak_window(h_unwrapped, -90, 90)
        print(f"    Đỉnh Hue (unwrap): [{lo_peak},{hi_peak}] — {dominance*100:.0f}% pixel có màu"
              f" thuộc cụm chính")
        if dominance < 0.4:
            print("    ⚠️ Cụm màu chính chiếm <40% — mẫu có thể lẫn nhiều màu khác nhau"
                  " (nền/chi tiết khác trong khung), kết quả kém tin cậy.")
        peak_mask = (h_unwrapped >= lo_peak) & (h_unwrapped <= hi_peak)
        h_unwrapped, sf, vf = h_unwrapped[peak_mask], sf[peak_mask], vf[peak_mask]

        lo_u, hi_u = _percentile_range(h_unwrapped, PAD_H, -90, 89)
        s_lo, s_hi = _percentile_range(sf, PAD_SV, 0, 255)
        v_lo, v_hi = _percentile_range(vf, PAD_SV, 0, 255)
        if lo_u < 0 <= hi_u:
            return [([0, s_lo, v_lo], [hi_u, s_hi, v_hi]),
                    ([lo_u + 180, s_lo, v_lo], [179, s_hi, v_hi])]
        if hi_u < 0:
            return [([lo_u + 180, s_lo, v_lo], [hi_u + 180, s_hi, v_hi])]
        return [([lo_u, s_lo, v_lo], [hi_u, s_hi, v_hi])]

    lo_peak, hi_peak, dominance = _hue_peak_window(hf, 0, 179)
    print(f"    Đỉnh Hue: [{lo_peak},{hi_peak}] — {dominance*100:.0f}% pixel có màu thuộc cụm chính")
    if dominance < 0.4:
        print("    ⚠️ Cụm màu chính chiếm <40% — mẫu có thể lẫn nhiều màu khác nhau"
              " (nền/chi tiết khác trong khung), kết quả kém tin cậy.")
    peak_mask = (hf >= lo_peak) & (hf <= hi_peak)
    hf, sf, vf = hf[peak_mask], sf[peak_mask], vf[peak_mask]

    h_lo, h_hi = _percentile_range(hf, PAD_H, 0, 179)
    s_lo, s_hi = _percentile_range(sf, PAD_SV, 0, 255)
    v_lo, v_hi = _percentile_range(vf, PAD_SV, 0, 255)
    return [([h_lo, s_lo, v_lo], [h_hi, s_hi, v_hi])]


def _calibrate_achromatic(pixels):
    """Range HSV cho Amkor (khối nhôm xám bạc, vô sắc)."""
    s, v = pixels[:, 1].astype(int), pixels[:, 2].astype(int)
    mask = (s < ACHROMA_SAT_MAX) & (v >= ACHROMA_VAL_MIN) & (v <= ACHROMA_VAL_MAX)
    coverage = mask.mean() if len(mask) else 0.0
    print(f"    Pixel xám ứng viên: {coverage*100:.1f}% ROI")
    if coverage < 0.03:
        print("    ⚠️ Quá ít pixel xám lọt ngưỡng — kiểm tra ACHROMA_VAL_MIN/MAX.")

    sf, vf = s[mask], v[mask]
    if len(sf) == 0:
        print("    ⚠️ Không có pixel nào lọt ngưỡng — giữ nguyên dải cũ trong config.py.")
        return None

    s_lo, s_hi = _percentile_range(sf, PAD_SV // 2, 0, 255)
    v_lo, v_hi = _percentile_range(vf, PAD_SV, 0, 255)
    return [([0, max(0, s_lo), v_lo], [179, s_hi, v_hi])]


def _fmt_ranges(ranges) -> str:
    parts = [f"([{lo[0]}, {lo[1]}, {lo[2]}], [{hi[0]}, {hi[1]}, {hi[2]}])" for lo, hi in ranges]
    return "[\n        " + ",\n        ".join(parts) + ",\n    ]"


def _mask_pct(pixels, ranges) -> float:
    """% pixel rơi vào 1 dải màu đã tính — cùng phép so khớp mà vision.py dùng khi phân loại."""
    if pixels is None or len(pixels) == 0 or not ranges:
        return 0.0
    h, s, v = pixels[:, 0].astype(int), pixels[:, 1].astype(int), pixels[:, 2].astype(int)
    mask = np.zeros(len(pixels), dtype=bool)
    for lo, hi in ranges:
        mask |= (h >= lo[0]) & (h <= hi[0]) & (s >= lo[1]) & (s <= hi[1]) & (v >= lo[2]) & (v <= hi[2])
    return float(mask.mean())


def _check_background(bg_pixels, results: dict):
    """Cảnh báo nếu nền trống (kệ + pallet thật, KHÔNG có kiện hàng) vẫn lọt dải màu nào đó.
    Đây là nguyên nhân hay gặp khi kiện hàng nhỏ so với ROI — % pixel tính được chủ yếu đến từ
    nền chứ không phải khối hàng, khiến confidence "ảo" đạt ngưỡng dù không thấy kiện hàng thật."""
    if bg_pixels is None or len(bg_pixels) == 0:
        print("  (Bỏ qua — chưa chụp mẫu nền.)")
        return
    warned = False
    for label, ranges in results.items():
        if ranges is None:
            continue
        pct = _mask_pct(bg_pixels, ranges)
        risky = pct >= config.CONFIDENCE_THRESHOLD
        flag = "⚠️" if risky else "  "
        note = "  — RỦI RO: nền một mình cũng đủ vượt CONFIDENCE_THRESHOLD!" if risky else ""
        print(f"  {flag} Nền trống khớp dải '{label}': {pct*100:.1f}%{note}")
        warned = warned or risky
    if not warned:
        print("  ✅ Nền trống không lọt ngưỡng dải màu nào — an toàn với CONFIDENCE_THRESHOLD hiện tại.")


def _check_overlap(results: dict):
    """Cảnh báo nếu dải HSV 2 kiện hàng chồng lấn — nguyên nhân hay gặp khi nhận nhầm."""
    labels = [l for l in results if results[l] is not None]
    warned = False
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = labels[i], labels[j]
            for lo_a, hi_a in results[a]:
                for lo_b, hi_b in results[b]:
                    if all(lo_a[k] <= hi_b[k] and lo_b[k] <= hi_a[k] for k in range(3)):
                        print(f"  ⚠️ Dải {a} và {b} CHỒNG LẤN — dễ nhận nhầm giữa 2 kiện này.")
                        warned = True
    if not warned:
        print("  ✅ Không phát hiện chồng lấn giữa các dải vừa tính.")


def main():
    if cv2 is None or np is None:
        print("❌ OpenCV/numpy không khả dụng — chạy lệnh này TRÊN Pi (đã cài theo requirements.txt).")
        return

    vision = Vision()
    if vision._camera is None:
        print("❌ Camera không khả dụng (đang chạy trên PC hoặc picamera2 lỗi?).")
        print("   Chạy lệnh này TRÊN Pi sau khi đã gắn camera CSI.")
        return

    print("=== CALIBRATE MÀU HSV — 4 KIỆN HÀNG CỐ ĐỊNH ===\n")
    print("Với mỗi kiện: đặt MỘT MÌNH kiện hàng đó vào giữa khung hình camera,")
    print("đúng khoảng cách/góc như lúc robot quét thật trên kệ, giữ yên rồi nhấn Enter.")
    print("QUAN TRỌNG: dùng phông trắng/xám trơn chắn hết bàn/ghế/đồ vật phía sau —")
    print("ROI ở đây RỘNG BẰNG ĐÚNG lúc quét thật (config.ROI_MARGIN), nền lẫn vào sẽ")
    print("làm range tính sai (xem CLAUDE.md).\n")

    _prompt("  → Bước 0: dọn TRỐNG kệ (không đặt kiện hàng nào), hướng camera vào đúng\n"
            "     vị trí/khoảng cách quét thật (chỉ thấy kệ + pallet thật, màu gì cũng được),\n"
            "     nhấn Enter...")
    bg_pixels = _roi_hsv_pixels(vision, SAMPLE_SECONDS)
    print(f"    Đã lấy {len(bg_pixels)} pixel mẫu nền.\n")

    results = {}
    for label in config.LABEL_TO_FACTORY:
        factory = config.LABEL_TO_FACTORY[label]
        _prompt(f"  → Đặt kiện '{label}' ({factory}) vào khung hình, nhấn Enter...")
        pixels = _roi_hsv_pixels(vision, SAMPLE_SECONDS)
        print(f"    Đã lấy {len(pixels)} pixel mẫu.")
        if label == config.ACHROMATIC_LABEL:
            ranges = _calibrate_achromatic(pixels)
        else:
            ranges = _calibrate_chromatic(pixels, label)
        results[label] = ranges
        print()

    vision.cleanup()

    print("=== KẾT QUẢ — dán đè vào COLOR_RANGES trong config.py ===\n")
    print("COLOR_RANGES = {")
    for label, ranges in results.items():
        if ranges is None:
            print(f'    # "{label}": GIỮ NGUYÊN dải cũ — không đủ dữ liệu để tính lại')
            continue
        print(f'    "{label}": {_fmt_ranges(ranges)}')
    print("}\n")

    print("=== KIỂM TRA CHỒNG LẤN (giữa 4 kiện hàng) ===")
    _check_overlap(results)

    print("\n=== KIỂM TRA NỀN (kệ trống + pallet, KHÔNG có kiện hàng) ===")
    _check_background(bg_pixels, results)

    print("\nSau khi dán vào config.py: chạy `python3 -m tests.test_vision` (test 5 — đánh giá")
    print("độ ổn định) trên từng kiện thật để xác nhận confidence đạt CONFIDENCE_THRESHOLD.")


if __name__ == "__main__":
    main()
