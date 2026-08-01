#!/usr/bin/env python3
"""
Đo các mốc cho luồng BỐC HÀNG (luồn càng → nâng) — chạy trên Pi, tại sa bàn.

    python3 -m tools.measure_pickup

VÌ SAO CẦN TOOL RIÊNG: mấy số đo này đều phải đọc siêu âm TRONG LÚC càng đang được
nâng ở một tầng nhất định. `test_lift.py` giữ càng nhưng không đọc siêu âm, còn
`test_motion.py` đọc siêu âm nhưng không nâng càng — và chạy song song 2 script thì
tranh nhau GPIO. Tool này mở CẢ Motion lẫn Lift trong một tiến trình.

CÁCH DÙNG: motor bánh KHÔNG chạy trong tool này. Bạn ĐẨY ROBOT BẰNG TAY tới từng tư
thế, tool chỉ nâng càng và đọc số cho bạn.

⚠️ Càng nâng lên rồi thì phải cẩn thận khi đẩy robot — đừng để càng đập vào kệ.
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

import config
from control import Motion, Lift
from control.mcp3008_bus import reset_mcp3008_bus

LEVEL_NAMES = {0: "SÀN", 1: "TẦNG 1", 2: "TẦNG 2"}

# Từng mốc cần đo: (khoá, tên, tầng càng, hướng dẫn đặt robot)
STEPS = [
    ("APPROACH_STANDOFF_DISTANCE", "① Vị trí CHỜ", 0,
     "Càng ở SÀN. Đẩy robot tới chỗ xa nhất mà vẫn hợp lý, sao cho khi nâng càng\n"
     "     lên TẦNG 2 thì càng KHÔNG chạm vào kệ. Đây là chỗ robot dừng trước khi nâng."),
    ("APPROACH_INSERT_DISTANCE_T1", "② Luồn xong — TẦNG 1", 1,
     "Càng đang ở ngang TẦNG 1. Đẩy robot vào tới khi càng LỒNG HẾT vào pallet\n"
     "     tầng 1, đúng độ sâu để nhấc được."),
    ("APPROACH_INSERT_DISTANCE_T2", "③ Luồn xong — TẦNG 2", 2,
     "Càng đang ở ngang TẦNG 2. Đẩy robot vào tới khi càng LỒNG HẾT vào pallet\n"
     "     tầng 2. (Bằng ② thì chỉ cần một hằng số.)"),
    ("RETREAT_DISTANCE", "④ Rút ra an toàn", 2,
     "Càng đang mang kiện (hoặc giả lập ở tầng 2). Đẩy robot LÙI tới khi càng rời\n"
     "     hẳn kệ, đủ chỗ xoay 180° mà không vướng gì."),
]


def _stream(m: Motion, title: str) -> float | None:
    """Hiện khoảng cách liên tục; Enter để CHỐT số hiện tại, Ctrl+C để bỏ qua."""
    print(f"\n  Đang đọc siêu âm — đẩy robot tới đúng tư thế rồi nhấn Enter để CHỐT.")
    print("  (Ctrl+C để bỏ qua mốc này)\n")
    import threading
    stop = threading.Event()
    last = {"d": -1.0}

    def loop():
        while not stop.is_set():
            d = m.get_distance()
            last["d"] = d
            bar = "█" * int(min(max(d, 0), 60) / 2)
            print(f"\r    {title}: {d:6.1f} cm  {bar:<30}", end="", flush=True)
            time.sleep(0.1)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    try:
        input()
    except KeyboardInterrupt:
        stop.set(); t.join(timeout=1)
        print("\n    → Bỏ qua.")
        return None
    stop.set(); t.join(timeout=1)
    print()
    return last["d"]


def _measure_lift_seconds(lift: Lift) -> float | None:
    """Đo ⑤ — nhấc bổng: sau khi luồn, nâng thêm bao lâu thì pallet rời mặt kệ."""
    print("\n  ⑤ NHẤC BỔNG — càng đã luồn vào pallet, cần nâng thêm bao nhiêu giây")
    print("     để pallet rời hẳn mặt kệ?")
    print("     Tool sẽ nâng CẢ 2 CÀNG từng nấc 0.1s, bạn nhìn rồi bảo dừng.\n")
    if input("  Bắt đầu? (y/N): ").strip().lower() != "y":
        return None

    total = 0.0
    try:
        while total < 2.0:
            input(f"    Enter → nâng thêm 0.1s (đã nâng {total:.1f}s)...")
            lift._left_en.on(); lift._left_up.on(); lift._left_down.off()
            lift._right_up.on(); lift._right_down.off()
            time.sleep(0.1)
            lift._stop_all()
            total += 0.1
            if input(f"    Pallet đã RỜI mặt kệ chưa? (y=xong / Enter=nâng tiếp): "
                     ).strip().lower() == "y":
                return round(total, 2)
    except KeyboardInterrupt:
        print("\n    → Bỏ qua.")
        return None
    print("    ⚠ Đã nâng 2.0s mà chưa rời — có gì đó không đúng, kiểm lại cơ cấu.")
    return None


def main():
    print("=" * 68)
    print(" ĐO MỐC BỐC HÀNG — luồn càng vào pallet rồi nâng")
    print("=" * 68)
    print("\n Motor BÁNH không chạy. Bạn đẩy robot bằng tay tới từng tư thế.")
    print(" Tool chỉ nâng CÀNG và đọc siêu âm.\n")

    m = Motion()
    lift = Lift()
    results: dict[str, float] = {}

    try:
        if m._distance_sensor is None:
            print(" ❌ Không có cảm biến siêu âm — không đo được. Kiểm HC-SR04 trước.")
            return

        print(" [HOME] Hạ 2 càng về sàn để mốc tầng khớp thực tế...")
        if input(" ⚠ Dưới càng không có vật cản? (y/N): ").strip().lower() != "y":
            print(" Đã huỷ.")
            return
        lift.home_to_floor()
        print(" ✅ Càng ở SÀN.\n")

        for key, title, level, howto in STEPS:
            print("-" * 68)
            print(f" {title}   (càng ở {LEVEL_NAMES[level]})")
            print(f"     {howto}")
            ans = input("\n  Đo mốc này? (y=đo / s=bỏ qua / q=thoát): ").strip().lower()
            if ans == "q":
                break
            if ans != "y":
                continue

            if lift._current_level != level:
                print(f"  Đưa càng về {LEVEL_NAMES[level]}...")
                lift.go_to_level(level)
                time.sleep(0.5)

            val = _stream(m, title)
            if val is not None and val >= 0:
                results[key] = round(val, 1)
                print(f"  ✅ {key} = {results[key]} cm")

        lift_s = _measure_lift_seconds(lift)
        if lift_s:
            results["LIFT_PICKUP_RAISE_TIME"] = lift_s

    except KeyboardInterrupt:
        print("\n\n Dừng bởi người dùng.")
    finally:
        try:
            lift.home_to_floor()
        except Exception:
            pass
        m.stop(); m.cleanup(); lift.cleanup()
        reset_mcp3008_bus()

    print("\n" + "=" * 68)
    print(" KẾT QUẢ — gửi nguyên khối này")
    print("=" * 68)
    if not results:
        print("  (chưa đo được mốc nào)")
    for k, v in results.items():
        unit = "s" if k.endswith("_TIME") else "cm"
        print(f"  {k:32} = {v}   # {unit}")
    print("=" * 68)


if __name__ == "__main__":
    main()
