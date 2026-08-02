#!/usr/bin/env python3
"""
Test module motion.py — kiểm tra từng chức năng động cơ & cảm biến dò line.
Chạy trên Raspberry Pi 4 với phần cứng kết nối.
"""

import logging
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control import Motion
from tests.config_editor import save_config
from control.mcp3008_bus import reset_mcp3008_bus

# Không script test nào bật logging → root logger mặc định ở mức WARNING và MỌI dòng
# logger.info() của control/* bị nuốt. Mất trắng phần chẩn đoán quan trọng nhất:
# khoảng cách dừng thật, thời gian nâng từng càng, lý do luồn càng thất bại...
# Đã tốn nhiều lượt thử chỉ vì các số đó không hiện ra.
# CHỈ ra màn hình, KHÔNG ghi file: robot_log.txt là của trận đấu thật, tools.measure_phases
# đọc nó — trộn log test vào là số đo trận bị bịa.
logging.basicConfig(
    level=logging.INFO,
    format="    %(levelname)-7s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)



def test_forward_backward(m: Motion):
    print("\n[TEST] Tiến 2 giây...")
    m.forward(config.SPEED_DEFAULT)
    time.sleep(2)
    m.stop()
    time.sleep(1)

    print("[TEST] Lùi 2 giây...")
    m.backward(config.SPEED_DEFAULT)
    time.sleep(2)
    m.stop()
    time.sleep(1)


def test_turning(m: Motion):
    print("\n[TEST] Xoay trái 1.5 giây...")
    m.turn_left()
    time.sleep(1.5)
    m.stop()
    time.sleep(1)

    print("[TEST] Xoay phải 1.5 giây...")
    m.turn_right()
    time.sleep(1.5)
    m.stop()
    time.sleep(1)


def test_speed_levels(m: Motion):
    print("\n[TEST] Test các mức tốc độ...")
    for speed in [30, 50, 70, 100]:
        print(f"  Tốc độ {speed}%...")
        m.forward(speed)
        time.sleep(1)
    m.stop()


def test_line_sensor(m: Motion):
    print("\n[TEST] Đọc cảm biến dò line digital (10 lần, cách 0.5s)...")
    for i in range(10):
        values = m.read_line_sensor()
        error = m.compute_line_error(values)
        active = sum(values)
        print(f"  Lần {i+1}: {values}  active={active}  error={error:.2f}")
        time.sleep(0.5)


def test_line_sensor_raw(m: Motion):
    print(f"\n[TEST] Calibrate QTR-8A — raw ADC (ngưỡng LINE_THRESHOLD={config.LINE_THRESHOLD})")
    print("  Đặt từng mắt lên line đen / nền trắng để xem giá trị.")
    print("  Nhấn Ctrl+C để dừng.\n")
    try:
        while True:
            adc = m.read_line_sensor_adc()
            raw = m.read_line_sensor_raw()
            digital = m.read_line_sensor()
            adc_str = " ".join(f"{v:4d}" for v in adc)
            dig_str = "".join("█" if d else "░" for d in digital)
            err = m.compute_line_error_analog(raw)
            print(f"  ADC: [{adc_str}]  {dig_str}  err={err:+.2f}")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n  Dừng calibrate.")


def test_forward_find_and_follow(m: Motion):
    print(f"\n[TEST] Tiến thẳng 2 giây (speed={config.SPEED_DEFAULT})...")
    m.forward(config.SPEED_DEFAULT)
    time.sleep(1.5)

    print(f"  Tìm line (tối đa {config.EXIT_START_TIMEOUT}s)...")
    start = time.time()
    found = False
    while time.time() - start < config.EXIT_START_TIMEOUT:
        values = m.read_line_sensor()
        if sum(values) > 0:
            found = True
            break
        time.sleep(0.01)
    m.stop()

    if not found:
        print("  Không tìm thấy line!")
        return

    print("  Đã thấy line — bám line tối đa 5s (hoặc đến khi gặp giao lộ)...")
    start = time.time()
    while time.time() - start < 5:
        at_intersection, _ = m.follow_line()
        if at_intersection:
            print("  -> Phát hiện giao lộ! Dừng.")
            break
        time.sleep(0.01)
    m.stop()


def test_line_follow(m: Motion):
    print("\n[TEST] Bám line 10 giây (hoặc đến khi gặp giao lộ)...")
    start = time.time()
    while time.time() - start < 10:
        is_intersection, _ = m.follow_line()
        if is_intersection:
            print("  -> Phát hiện giao lộ! Dừng.")
            break
        time.sleep(0.01)
    m.stop()


def test_distance_sensor(m: Motion):
    print("\n[TEST] Cảm biến siêu âm HC-SR04 real-time — Ctrl+C để thoát")
    print("  Di chuyển vật trước robot để xem khoảng cách thay đổi:")
    i = 0
    while True:
        dist = m.get_distance()
        i += 1
        if dist < 0:
            print(f"\r  [{i:4d}] KHÔNG CÓ cảm biến siêu âm (GPIO {config.ULTRASONIC_TRIG_PIN}/{config.ULTRASONIC_ECHO_PIN})", end="", flush=True)
        else:
            bar = "█" * int(min(dist, 60) / 2)
            print(f"\r  [{i:4d}] {dist:6.1f}cm  {bar:<30}", end="", flush=True)
        time.sleep(0.2)


def test_approach_shelf(m: Motion):
    print(f"\n[TEST] Tiếp cận kệ (dừng ở {config.APPROACH_DISTANCE}cm)...")
    print("  Đặt vật/kệ phía trước robot.")
    input("  Nhấn Enter để bắt đầu...")
    success = m.approach_shelf()
    dist = m.get_distance()
    print(f"  Kết quả: {'ĐÃ ĐẾN' if success else 'TIMEOUT'} — khoảng cách {dist:.1f}cm")

    print(f"\n  Lùi ra ({config.RETREAT_DISTANCE}cm)...")
    success = m.retreat_from_shelf()
    dist = m.get_distance()
    print(f"  Kết quả: {'ĐÃ LÙI' if success else 'TIMEOUT'} — khoảng cách {dist:.1f}cm")


def test_turn_90(m: Motion):
    print(f"\n[TEST] Xoay 90° (TURN_TIME={config.TURN_TIME}s) — calibrate trên sa bàn")
    print("  Đặt robot song song line, quan sát có vuông góc không.")
    input("  Nhấn Enter để xoay TRÁI 90°...")
    m.turn_left_90()
    time.sleep(1)
    ans = input("  Góc ~90°? (y=OK / n=cần chỉnh TURN_TIME trong config.py): ").strip().lower()
    print(f"  Ghi nhận: {'OK' if ans == 'y' else 'Cần chỉnh TURN_TIME'}")

    input("  Nhấn Enter để xoay PHẢI 90° (về hướng cũ)...")
    m.turn_right_90()


def test_execute_route(m: Motion):
    import navigation as nav

    print("\n[TEST] execute_route — route do navigation.plan() TÍNH RA")
    cases = {
        "1": ("Ô xuất phát → Kệ 3", nav.START_POSE, "SHELF0"),
        "2": ("Kệ 3 → Kệ 2", nav.pose_at("SHELF0"), "SHELF1"),
        "3": ("Kệ 3 → Foxconn (cùng hàng R0)", nav.pose_at("SHELF0"), "F_foxconn"),
        "4": ("Kệ 3 → Samsung (khác hàng, vòng cột kệ)", nav.pose_at("SHELF0"), "F_samsung"),
        "5": ("Kệ 2 → Foxconn (né đoạn đứt R2)", nav.pose_at("SHELF1"), "F_foxconn"),
        "6": ("Foxconn → Kệ 3 (quay về kho)", nav.pose_at("F_foxconn"), "SHELF0"),
        "7": ("Foxconn → Samsung (giữa 2 nhà máy)", nav.pose_at("F_foxconn"), "F_samsung"),
        "8": ("Foxconn → Kệ 4 → Liên hợp (NV2)", nav.pose_at("F_foxconn"), "LOOSE"),
    }
    for k, (name, src, dst) in cases.items():
        route, _ = nav.plan(src, dst)
        print(f"    {k}. {name}\n       {nav.route_to_text(route)}")
    sub = input(f"  Chọn route (1-{len(cases)}): ").strip()
    if sub not in cases:
        print("  Lựa chọn không hợp lệ.")
        return
    name, src, dst = cases[sub]
    route, new_pose = nav.plan(src, dst)
    print(f"  Route {name}: {route}")
    print(f"  Đặt robot tại: {nav.describe(src)}")
    input("  Nhấn Enter để chạy...")
    ok = m.execute_route(route)
    print(f"  Kết quả: {'THÀNH CÔNG' if ok else 'THẤT BẠI — mất line / timeout giao lộ'}")
    print(f"  Vị trí kỳ vọng sau route: {nav.describe(new_pose)}")


def test_spi_line_and_ir(m: Motion):
    """Đọc line + IR liên tục — kiểm tra shared MCP3008 bus."""
    from control import Lift
    lift = Lift()
    print("\n[TEST] Shared SPI — line (CH0-5) + IR pallet (CH6-7) đồng thời")
    print("  Nhấn Ctrl+C để dừng.\n")
    try:
        while True:
            line = m.read_line_sensor_adc()
            left, right, ok = lift.pallet.read_status()
            line_str = " ".join(f"{v:3d}" for v in line)
            ir_str = (
                f"IR trái={'CÓ' if left else 'KHÔNG'} phải={'CÓ' if right else 'KHÔNG'}"
                if ok else "IR LỖI đọc"
            )
            print(f"  LINE [{line_str}]  {ir_str}")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n  Dừng.")
    finally:
        lift.cleanup()


def test_motor_diagnosis(m: Motion):
    """Chạy từng motor riêng lẻ để xác định motor nào bị ngược chiều."""
    speed = 50
    dur = 1.5

    print("\n[CHẨN ĐOÁN] Chạy từng motor riêng — quan sát bánh nào quay và chiều quay")
    print(f"  Tốc độ {speed}%, mỗi bước {dur}s\n")

    actions = [
        ("BÁNH TRÁI — tiến",  lambda: _run_left(m, speed, forward=True)),
        ("BÁNH TRÁI — lùi",   lambda: _run_left(m, speed, forward=False)),
        ("BÁNH PHẢI — tiến",  lambda: _run_right(m, speed, forward=True)),
        ("BÁNH PHẢI — lùi",   lambda: _run_right(m, speed, forward=False)),
    ]

    for label, fn in actions:
        input(f"  Nhấn Enter để chạy: {label} ...")
        fn()
        time.sleep(dur)
        m.stop()
        time.sleep(0.5)

    print("\n  Nếu TRÁI tiến nhưng bánh quay ngược → swap IN1_XE_T ↔ IN2_XE_T trong config.py")
    print("  Nếu PHẢI tiến nhưng bánh quay ngược → swap IN1_XE_P ↔ IN2_XE_P trong config.py")


def _run_left(m: Motion, speed: float, forward: bool):
    m._left_rev.value = 0
    m._right_fwd.value = 0
    m._right_rev.value = 0
    if forward:
        m._left_fwd.value = speed / 100
    else:
        m._left_fwd.value = 0
        m._left_rev.value = speed / 100


def _run_right(m: Motion, speed: float, forward: bool):
    m._left_fwd.value = 0
    m._left_rev.value = 0
    m._right_rev.value = 0
    if forward:
        m._right_fwd.value = speed / 100
    else:
        m._right_fwd.value = 0
        m._right_rev.value = speed / 100


def test_encoder_live(m: Motion):
    """Đọc xung encoder 2 bánh real-time trong khi tiến — kiểm tra dây/đấu đúng kênh."""
    if not (m._encoder_left.available and m._encoder_right.available):
        print("  Encoder chưa sẵn sàng — kiểm tra ENCODER_LEFT_PIN/ENCODER_RIGHT_PIN trong config.py.")
        return

    print("\n[TEST] Đọc xung encoder real-time khi tiến — Ctrl+C để dừng")
    m.forward(config.SPEED_DEFAULT)
    try:
        while True:
            left, right = m.sample_wheel_pulses(0.2)
            print(f"  trái={left:3d} xung/0.2s   phải={right:3d} xung/0.2s")
    except KeyboardInterrupt:
        print("\n  Dừng.")
    finally:
        m.stop()


def test_calibrate_pwm_by_encoder(m: Motion):
    """So xung 2 bánh khi tiến thẳng → tự tính & lưu PWM_COMPENSATION (bánh phải)."""
    import importlib

    if not (m._encoder_left.available and m._encoder_right.available):
        print("  Encoder chưa sẵn sàng — kiểm tra ENCODER_LEFT_PIN/ENCODER_RIGHT_PIN trong config.py.")
        return

    print("\n[CALIBRATE] Đo xung 2 bánh khi tiến thẳng 1s, tự tính PWM_COMPENSATION")
    print("  Đặt robot lên đế (bánh không chạm đất) trước khi chạy.")
    print("  Chỉ chỉnh chiều TIẾN — chiều lùi vẫn phải tự chỉnh PWM_COMPENSATION_REV bằng tay.\n")

    while True:
        importlib.reload(config)
        print(f"  PWM_COMPENSATION hiện tại (bánh phải, tiến) = {config.PWM_COMPENSATION:.3f}")
        cmd = input("  Enter = tiến 1s và đo xung / q = thoát: ").strip().lower()
        if cmd == "q":
            break

        m.forward(config.SPEED_DEFAULT)
        left, right = m.sample_wheel_pulses(1.0)
        m.stop()

        print(f"  trái={left} xung   phải={right} xung")
        if left == 0 or right == 0:
            print("  Không đọc được xung ở 1 trong 2 bánh — kiểm tra dây encoder (C1/VCC/GND) trước khi calibrate.")
            continue

        ratio = left / right
        suggested = max(0.5, min(1.0, config.PWM_COMPENSATION * ratio))
        nhanh_hon = "phải" if right > left else "trái"
        print(f"  Bánh {nhanh_hon} đang quay nhanh hơn.")
        print(f"  Đề xuất PWM_COMPENSATION = {suggested:.3f} (hiện {config.PWM_COMPENSATION:.3f})")

        if input("  Lưu giá trị đề xuất vào config.py? (y/N): ").strip().lower() == "y":
            save_config("PWM_COMPENSATION", suggested)
            print("  Đã lưu.")


def test_cross_line_gap(m: Motion):
    """Vượt khoảng ĐỨT của line ở ô xuất phát — calibrate LINE_GAP_COAST_TIME.

    Sa bàn có 1 chỗ line đứt thật mà robot BẮT BUỘC đi qua: hàng R0 tại ô xuất phát
    (~245mm). Mất line thì robot giữ lái và trôi thẳng LINE_GAP_COAST_TIME giây rồi
    mới coi là lạc và quét tìm lại. Đặt quá ngắn = quay ngang giữa khoảng đứt.
    """
    print(f"\n[TEST] Vượt khoảng đứt line (LINE_GAP_COAST_TIME={config.LINE_GAP_COAST_TIME}s)")
    print("  Đặt robot trên hàng R0 phía KỆ, quay mặt về phía nhà máy (hướng ô xuất phát).")
    print("  Robot sẽ bám line qua khoảng đứt ô xuất phát tới giao lộ cột giữa.")
    input("  Nhấn Enter để chạy...")

    t0 = time.time()
    ok = m.navigate_intersections(1)
    print(f"  Kết quả: {'✅ qua được' if ok else '❌ mất line'} sau {time.time()-t0:.1f}s")
    if not ok:
        print(f"  → Tăng LINE_GAP_COAST_TIME (đang {config.LINE_GAP_COAST_TIME}s) hoặc giảm tốc độ.")
    else:
        print("  → Nếu robot có lúc quay ngang giữa khoảng trống thì vẫn nên tăng thêm.")


def test_back_out_of_shelf(m: Motion):
    """LÙI ra khỏi kệ tới giao lộ — lệnh ("back", N), thay cho xoay 180°.

    ĐÂY LÀ TEST QUAN TRỌNG NHẤT của tính năng lùi. Thanh cảm biến gắn ở ĐẦU xe nên
    khi lùi nó thành đuôi, và luật lái phải ĐẢO DẤU mới hội tụ (xem Motion.follow_line).
    Lý thuyết nói đảo dấu là đúng, nhưng chỉ chạy thật mới biết:

      - Đảo dấu SAI  → robot ngoáy đuôi mỗi lúc một mạnh rồi văng khỏi line.
      - Đảo dấu ĐÚNG → robot lùi thẳng, bám line, dừng khi thanh cảm biến chạm
        vạch ngang của giao lộ.

    Sau khi dừng, thân xe nằm QUÁ giao lộ một đoạn bằng khoảng cách trục bánh → cảm
    biến. Nếu xoay tiếp mà bị trượt line thì đo đoạn đó rồi đặt REVERSE_RECENTER_TIME.
    """
    print(f"\n[TEST] LÙI ra khỏi kệ (REVERSE_SPEED={config.REVERSE_SPEED}%, "
          f"RECENTER={config.REVERSE_RECENTER_TIME}s)")
    print("  Đặt robot Ở SÁT KỆ như vừa nâng hàng xong: trên line, QUAY MẶT VÀO KỆ.")
    print("  Robot sẽ LÙI dọc line (không xoay) cho tới khi gặp giao lộ.")
    print("  ⚠ Đứng sẵn cạnh công tắc nguồn — nếu đảo dấu sai robot sẽ ngoáy đuôi.")
    input("  Nhấn Enter để chạy...")

    t0 = time.time()
    ok = m.back_to_intersection(1)
    dt = time.time() - t0
    print(f"  Kết quả: {'✅ tới giao lộ' if ok else '❌ THẤT BẠI'} sau {dt:.1f}s")

    if not ok:
        print("  → Mất line hoặc timeout. Kiểm theo thứ tự:")
        print("     1. Robot có ngoáy đuôi tăng dần không? → dấu đảo đang SAI,")
        print("        xem lại nhánh `if reverse: correction = -correction`.")
        print("     2. Chạy quá nhanh? → giảm config.REVERSE_SPEED.")
        print("     3. Không bao giờ thấy giao lộ? → kiểm INTERSECTION_THRESHOLD.")
        return

    print("  Giờ kiểm phần QUAN TRỌNG: robot dừng có đúng chỗ không.")
    print("  Đo khoảng cách từ TRỤC BÁNH tới vạch ngang của giao lộ:")
    print("    - Trục nằm NGAY TRÊN vạch  → tốt, để REVERSE_RECENTER_TIME = 0")
    print("    - Trục nằm QUÁ vạch (về phía xa kệ) → đó là khoảng trục→cảm biến.")
    print(f"      Đặt REVERSE_RECENTER_TIME ≈ khoảng đó ÷ tốc độ lùi rồi chạy lại.")
    ans = input("  Xoay thử 90° tại chỗ để xem có bắt lại được line không? (y/N): ")
    if ans.strip().lower() == "y":
        m.turn_right_90()
        values = m.read_line_sensor()
        print(f"  Sau khi xoay, cảm biến đọc: {values} (tổng {sum(values)})")
        print("  → Có ít nhất 1 mắt thấy line = bắt được line mới, tốt.")
        print("  → Toàn 0 = lệch quá xa, phải chỉnh REVERSE_RECENTER_TIME.")


def test_retreat_turn_and_go(m: Motion):
    """RÚT KHỎI KỆ → XOAY → BÁM LINE TỚI GIAO LỘ KẾ — mở đầu MỌI tuyến giao hàng.

    Option 15 dừng ngay sau khi xoay: nó chỉ đọc cảm biến một lần rồi báo "có bắt
    được line không". Bài này chạy trọn chuỗi, vì đây đúng là 3 lệnh đầu của mọi
    route giao hàng:

        SHELF0 → Samsung : LÙI 1 giao lộ → xoay phải → tiến 2 giao lộ → ...

    Chuỗi này xâu 3 thứ mà không thứ nào đã được xác nhận:
      1. back_to_intersection  — dùng PWM_COMPENSATION_REV, CHƯA calibrate bao giờ
      2. REVERSE_RECENTER_TIME — tiến bù cho khoảng trục bánh → cảm biến
      3. turn_*_90             — TURN_TIME mới xác nhận cho chiều TRÁI

    Sai số của cả ba CỘNG DỒN rồi mới tới bước bám line. Chạy rời từng cái thì mỗi
    cái "có vẻ ổn" mà ghép lại vẫn trượt — đó là lý do phải có bài này.
    """
    print("\n[TEST] Rút khỏi kệ → xoay → bám line tới giao lộ kế")
    print(f"  REVERSE_SPEED={config.REVERSE_SPEED}%  "
          f"RECENTER={config.REVERSE_RECENTER_TIME}s  TURN_TIME={config.TURN_TIME}s")
    print("  Đặt robot SÁT KỆ như vừa nâng hàng xong: trên line, QUAY MẶT VÀO KỆ.")

    huong = input("  Xoay về phía nào sau khi lùi? (r=phải / l=trái) [r]: ").strip().lower()
    huong = "l" if huong == "l" else "r"
    try:
        so_gl = int(input("  Bám line qua mấy giao lộ sau khi xoay? [1]: ").strip() or "1")
    except ValueError:
        so_gl = 1
    input("  ⚠ Đứng sẵn cạnh công tắc nguồn. Nhấn Enter để chạy...")

    # --- BƯỚC 1: lùi ---
    t0 = time.time()
    ok = m.back_to_intersection(1)
    print(f"\n  [1/3] LÙI tới giao lộ: {'✅' if ok else '❌ THẤT BẠI'} sau {time.time()-t0:.1f}s")
    if not ok:
        print("     ĐẠT nếu: lùi thẳng, lắc ngang ≤ ±2cm và KHÔNG tăng dần.")
        print("     Lắc tăng dần  → dấu đảo khi lùi SAI (follow_line, nhánh reverse).")
        print("     Trôi lệch đều → PWM_COMPENSATION_REV / _LEFT_REV chưa calibrate.")
        return
    values = m.read_line_sensor()
    print(f"     Cảm biến sau khi lùi + tiến bù: {values} (tổng {sum(values)})")
    print("     ĐO TAY: trục bánh phải nằm NGAY TRÊN vạch ngang của giao lộ.")
    print(f"     Lệch quá 2cm → chỉnh REVERSE_RECENTER_TIME (đang {config.REVERSE_RECENTER_TIME}s).")

    # --- BƯỚC 2: xoay ---
    if input("\n  Xoay tiếp? (Enter = có, n = dừng): ").strip().lower() == "n":
        return
    if huong == "r":
        m.turn_right_90()
    else:
        m.turn_left_90()
    values = m.read_line_sensor()
    print(f"  [2/3] XOAY {'PHẢI' if huong == 'r' else 'TRÁI'}: "
          f"cảm biến {values} (tổng {sum(values)})")
    if sum(values) == 0:
        print("     ❌ KHÔNG mắt nào thấy line — chưa bắt được line mới. Nguyên nhân:")
        print("        a) REVERSE_RECENTER_TIME sai → robot không đứng đúng tâm giao lộ")
        print("        b) TURN_TIME sai cho CHIỀU NÀY (mới xác nhận chiều trái)")
        print("     Phân biệt: chạy option 10 riêng cho chiều này. Đúng 90° thì lỗi là (a).")
        return
    print("     ✅ bắt được line mới.")

    # --- BƯỚC 3: bám line tới giao lộ kế ---
    if input(f"\n  Bám line qua {so_gl} giao lộ? (Enter = có, n = dừng): ").strip().lower() == "n":
        return
    t0 = time.time()
    ok = m.navigate_intersections(so_gl)
    dt = time.time() - t0
    print(f"  [3/3] BÁM LINE qua {so_gl} giao lộ: {'✅' if ok else '❌ THẤT BẠI'} sau {dt:.1f}s")
    print(f"     ĐẠT nếu: tới đủ {so_gl} giao lộ, KHÔNG mất line giữa chừng,")
    print(f"     và robot đi giữa vạch chứ không men theo mép.")
    if ok:
        print(f"     Ghi lại {dt/max(1, so_gl):.2f}s/giao lộ — đối chiếu --forward của tools.dry_run.")
    else:
        print("     Mất line ngay sau khi xoay → sai số 3 bước đầu cộng dồn quá lớn.")
        print("     Quay lại option 10 (xoay) và option 15 (lùi) tách riêng từng cái.")
    print("\n  ⚠ Lặp 3 LẦN mới tính đạt — xem tests/NGHIEM_THU.md.")


def test_speed_limit(m: Motion):
    """Giới hạn tốc độ THẬT — đo tần số đọc cảm biến rồi tính biên an toàn giao lộ.

    Vòng lặp bám line đọc cảm biến rời rạc. Chạy càng nhanh thì mỗi lần đọc robot đi
    được càng xa, tới lúc nào đó nó BAY QUA vạch giao lộ giữa 2 lần đọc mà không kịp
    thấy. Lỗi này không hiện ra khi chạy thử vài mét — nó hiện ra giữa trận, dưới
    dạng robot đếm thiếu giao lộ rồi rẽ sai chỗ.

    Không đoán được bằng mắt, phải đo. Chạy bài này TRƯỚC khi tăng SPEED_DEFAULT.
    """
    print("\n[TEST] Giới hạn tốc độ — biên an toàn phát hiện giao lộ")

    # --- 1. Đo tần số vòng lặp thật (gồm cả đọc SPI + sleep như lúc bám line) ---
    print("\n  Bước 1: đo tần số đọc cảm biến (2 giây, robot đứng yên)...")
    n, t0 = 0, time.time()
    while time.time() - t0 < 2.0:
        m.read_line_sensor_raw()
        time.sleep(0.01)          # đúng nhịp sleep trong follow_line()
        n += 1
    hz = n / (time.time() - t0)
    period_ms = 1000.0 / hz
    print(f"    {hz:.0f} lần đọc/giây → mỗi lần cách nhau {period_ms:.1f}ms")

    # --- 2. Tốc độ thật của robot ---
    print(f"\n  Bước 2: đo tốc độ thật ở SPEED_DEFAULT={config.SPEED_DEFAULT}%")
    print("    Đặt robot trên sàn phẳng, đánh dấu vạch xuất phát.")
    if input("    Chạy thẳng 3 giây? (y/N): ").strip().lower() != "y":
        print("    Bỏ qua — nhập tay tốc độ nếu đã biết.")
        raw = input("    Tốc độ đã biết (mm/giây), Enter để thoát: ").strip()
        if not raw:
            return
        speed_mm = float(raw)
    else:
        m.forward(config.SPEED_DEFAULT)
        time.sleep(3.0)
        m.stop()
        dist = input("    Đo bằng thước: robot đi được bao nhiêu mm? ").strip()
        if not dist:
            return
        speed_mm = float(dist) / 3.0
    print(f"    → {speed_mm:.0f} mm/giây ở mức {config.SPEED_DEFAULT}%")

    # --- 3. Biên an toàn ---
    lw = input("\n  Bước 3: bề rộng vạch line (mm) [20]: ").strip() or "20"
    line_w = float(lw)
    print(f"\n  {'Tốc độ':>7} {'mm/giây':>9} {'mm mỗi lần đọc':>16} {'số lần đọc trên vạch':>22}")
    print("  " + "-" * 60)
    safe_max = 0
    for pct in range(40, 101, 10):
        v = speed_mm * pct / config.SPEED_DEFAULT
        per_read = v * period_ms / 1000.0
        samples = line_w / per_read if per_read else 999
        if samples >= 3.0:
            safe_max = pct
        flag = "✅" if samples >= 3.0 else ("⚠ sát" if samples >= 2.0 else "❌ TRƯỢT")
        mark = "  ← đang dùng" if pct == config.SPEED_DEFAULT else ""
        print(f"  {pct:>6}% {v:>9.0f} {per_read:>16.1f} {samples:>18.1f}  {flag}{mark}")

    print(f"\n  → Cần ≥3 lần đọc rơi trên vạch mới chắc chắn không trượt giao lộ.")
    print(f"  → Mức cao nhất còn an toàn theo phép đo này: {safe_max}%")
    if safe_max < 80:
        print(f"  ⚠ Muốn chạy trên {safe_max}% thì phải làm vòng lặp nhanh hơn trước:")
        print("     bỏ time.sleep(0.01) trong follow_line, hoặc đọc SPI thô "
              "(xem tools/raw_spi_test.py), hoặc dùng vạch line rộng hơn.")
    print("  ⚠ Đây là biên LÝ THUYẾT. Vẫn phải chạy option 11 và đếm tay để xác nhận.")


def test_continuous_intersections(m: Motion):
    """A/B chế độ đếm giao lộ: dừng-từng-cái vs chạy liền.

    Đây là đòn bẩy phần mềm lớn nhất cho ngân sách 240s, nhưng đụng vào vòng lặp
    quan trọng nhất — phải tự tay đo trên sa bàn rồi mới bật, đừng tin số ước tính.
    """
    import importlib

    print("\n[TEST] A/B: đếm giao lộ DỪNG-TỪNG-CÁI vs CHẠY LIỀN")
    n = input(f"  Đi qua mấy giao lộ? [3]: ").strip() or "3"
    if not n.isdigit() or int(n) < 1:
        print("  Số không hợp lệ.")
        return
    n = int(n)

    results = {}
    for mode, label in ((False, "DỪNG từng giao lộ (hiện tại)"),
                        (True, "CHẠY LIỀN (chỉ dừng ở cái cuối)")):
        config.CONTINUOUS_INTERSECTIONS = mode
        print(f"\n  --- {label} ---")
        print(f"  Đặt robot lên line, cách giao lộ đầu tiên vài chục cm.")
        input("  Nhấn Enter để chạy...")
        t0 = time.time()
        ok = m.navigate_intersections(n)
        dt = time.time() - t0
        results[label] = (ok, dt)
        print(f"  {'✅' if ok else '❌'} {dt:.2f}s cho {n} giao lộ ({dt/n:.2f}s/giao lộ)")
        real = input(f"  ĐẾM TAY: robot thật sự qua mấy giao lộ? [{n}]: ").strip() or str(n)
        if real != str(n):
            print(f"  ⚠ ĐẾM SAI: robot báo {n} nhưng thực tế {real} giao lộ!")
            print("    → chỉnh INTERSECTION_THRESHOLD / INTERSECTION_CLEAR_THRESHOLD")
            results[label] = (False, dt)

    importlib.reload(config)      # trả cờ về đúng giá trị trong file
    print("\n  === KẾT QUẢ ===")
    for label, (ok, dt) in results.items():
        print(f"    {label:38s} {dt:6.2f}s  {'OK' if ok else 'ĐẾM SAI'}")
    vals = list(results.values())
    if all(ok for ok, _ in vals):
        saved = vals[0][1] - vals[1][1]
        print(f"    → Chạy liền tiết kiệm {saved:.2f}s cho {n} giao lộ "
              f"({saved/n:.2f}s mỗi giao lộ)")
        print(f"    → Cả trận đi ~65 giao lộ ⇒ tiết kiệm ~{saved/n*65:.0f}s")
        print("    Đếm đúng cả 2 lần thì đặt CONTINUOUS_INTERSECTIONS = True trong config.py")
    else:
        print("    Có lần đếm sai — CHƯA được bật chế độ chạy liền.")


def test_probe_board_side(m: Motion):
    """Dò nửa sân: đứng TẠI giao lộ Kệ 3, xoay phải thử xem có nhánh line không."""
    import navigation as nav

    print("\n[TEST] Tự dò NỬA SÂN (dùng đầu mỗi trận)")
    print("  Đặt robot ĐÚNG TẠI giao lộ Kệ 3 (chỗ line dọc cột kệ gặp line ngang R0),")
    print("  quay mặt về phía KỆ — y như lúc thi đấu sau khi thoát ô xuất phát.")
    print(f"  Robot sẽ xoay phải 90°, tiến {config.PROBE_TRAVEL_TIME}s, đọc line, rồi lùi lại và xoay về.")
    input("  Nhấn Enter để dò...")

    found = m.probe_side_branch("right")
    if found is None:
        print("  ❌ Không kết luận được — cảm biến line lỗi.")
        return
    mirrored = not found
    print(f"  Kết quả: {'CÓ' if found else 'KHÔNG có'} nhánh line bên phải")
    print(f"  → Đang ở nửa {'GƯƠNG' if mirrored else 'CHUẨN'} "
          f"(BOARD_MIRRORED nên = {mirrored})")
    print(f"  config.BOARD_MIRRORED hiện tại = {config.BOARD_MIRRORED}"
          f"{'  ⚠ KHÁC kết quả dò' if bool(config.BOARD_MIRRORED) != mirrored else '  ✅ khớp'}")
    print("  (Khi thi đấu robot tự dò và tự nạp lại bản đồ — cờ trong config chỉ là dự phòng.)")
    nav.set_mirrored(mirrored)
    route, _ = nav.plan((nav.PROBE_NODE, nav.TOWARD_SHELVES), "SHELF0")
    print(f"  Route tiếp theo vào Kệ 3: {nav.route_to_text(route)}")


def main():
    print("=" * 50)
    print("TEST MODULE ĐỘNG CƠ DI CHUYỂN")
    print("=" * 50)

    m = Motion()

    tests = {
        "1": ("Tiến/Lùi", test_forward_backward),
        "2": ("Xoay trái/phải", test_turning),
        "3": ("Các mức tốc độ", test_speed_levels),
        "4": ("Đọc cảm biến dò line (digital)", test_line_sensor),
        "5": ("Calibrate QTR-8A (raw ADC)", test_line_sensor_raw),
        "6": ("Tiến thẳng tìm line + bám line 5s/giao lộ", test_forward_find_and_follow),
        "7": ("Bám line (chạy thực tế)", test_line_follow),
        "8": ("Cảm biến siêu âm (đo khoảng cách)", test_distance_sensor),
        "9": ("Tiếp cận + lùi khỏi kệ", test_approach_shelf),
        "10": ("Xoay 90° (calibrate TURN_TIME)", test_turn_90),
        "11": ("execute_route (route config)", test_execute_route),
        "12": ("Shared SPI: line + IR cùng lúc", test_spi_line_and_ir),
        "13": ("Tự dò NỬA SÂN tại giao lộ Kệ 3", test_probe_board_side),
        "14": ("Vượt khoảng đứt line ô xuất phát", test_cross_line_gap),
        "16": ("A/B đếm giao lộ: dừng từng cái vs chạy liền", test_continuous_intersections),
        "17": ("Giới hạn tốc độ (đo trước khi tăng SPEED_DEFAULT)", test_speed_limit),
        "15": ("LÙI ra khỏi kệ tới giao lộ (lệnh back)", test_back_out_of_shelf),
        "18": ("Rút khỏi kệ → xoay → bám line tới giao lộ kế (mở đầu MỌI tuyến giao)",
               test_retreat_turn_and_go),
        "d": ("Chẩn đoán motor từng bánh riêng", test_motor_diagnosis),
        "e": ("Đọc xung encoder real-time (Ctrl+C để thoát)", test_encoder_live),
        "f": ("Calibrate PWM_COMPENSATION bằng encoder (lưu config)", test_calibrate_pwm_by_encoder),
        "0": ("Chạy tất cả", None),
    }

    print("\nChọn test:")
    for key, (name, _) in tests.items():
        print(f"  {key}. {name}")

    choice = input("\nNhập số (0-17, d-f): ").strip()

    try:
        if choice == "0":
            for key, (name, func) in tests.items():
                if func and key not in ("5", "10", "11", "12", "13", "14", "15", "16", "17", "e"):
                    func(m)
        elif choice in tests and tests[choice][1]:
            tests[choice][1](m)
        else:
            print("Lựa chọn không hợp lệ.")
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        m.cleanup()
        reset_mcp3008_bus()
        print("\nĐã cleanup GPIO.")


if __name__ == "__main__":
    main()
