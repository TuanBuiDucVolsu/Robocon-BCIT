#!/usr/bin/env python3
"""
Kiểm NÚT KHỞI ĐỘNG (GPIO 16) — chạy trên Pi, không cần motor/cẩu/camera.

    python3 -m tools.check_start_button           # theo dõi trực tiếp + đo dội phím
    python3 -m tools.check_start_button flow      # diễn tập LUỒNG THI ĐẤU

Nút này gánh 3 việc khác nhau trong một trận:

    1. Bấm lúc chờ  → BẮT ĐẦU trận (main._handle_init)
    2. Bấm giữa trận → yêu cầu RESET, robot dừng ngay (main._on_reset_button)
    3. Bấm lần nữa   → xác nhận đã đặt robot xong, chạy tiếp (main._wait_for_placement)

Việc 3 là mới và chưa từng chạy trên phần cứng. Nếu nút DỘI (một cú bấm sinh nhiều
sự kiện), lần bấm số 2 có thể tự xảy ra ngay sau lần 1 — robot chạy tiếp trong lúc
người còn đang bê nó, đúng cái mà luồng 2-lần-bấm sinh ra để ngăn. Chế độ `flow`
diễn tập đúng chuỗi đó để kiểm.

Đấu dây (docs/PHAN_CUNG.md mục 6):  GPIO 16 ──[ NÚT BẤM ]── GND
Phần mềm dùng pull_up=True → nhả = HIGH, bấm = LOW.
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

import config

try:
    from gpiozero import Button, Device
    Device.ensure_pin_factory()
except Exception as e:                                  # pragma: no cover - cần Pi
    print(f"❌ Không dùng được gpiozero ({e}) — chạy lệnh này TRÊN Pi.")
    raise SystemExit(1)

# Hai cú bấm cách nhau dưới ngưỡng này = dội phím lọt qua bộ lọc, không phải người bấm
BOUNCE_SUSPECT_S = 0.30


def _open():
    pin = config.START_BUTTON_PIN
    print(f"Nút khởi động: GPIO {pin}, pull_up=True, bounce_time={0.1}s")
    print("Đấu dây đúng:  GPIO %d ──[ NÚT ]── GND\n" % pin)
    try:
        return Button(pin, pull_up=True, bounce_time=0.1)
    except Exception as e:
        print(f"❌ Không mở được GPIO {pin}: {e}")
        raise SystemExit(1)


def mode_live(button):
    """Theo dõi trạng thái + đếm sự kiện + phát hiện dội phím."""
    print("=" * 60)
    print(" THEO DÕI TRỰC TIẾP — bấm/nhả nút vài lần, Ctrl+C để kết thúc")
    print("=" * 60)
    print("\n  Nhả nút ra, KHÔNG chạm gì, xem dòng dưới có đứng yên không.")
    print("  Nhấp nháy khi không ai chạm = nhiễu / dây lỏng / thiếu GND chung.\n")

    presses, releases, bounces = [], [], []

    def on_press():
        now = time.monotonic()
        if presses and now - presses[-1] < BOUNCE_SUSPECT_S:
            bounces.append(now - presses[-1])
        presses.append(now)

    def on_release():
        releases.append(time.monotonic())

    button.when_pressed = on_press
    button.when_released = on_release

    try:
        last = None
        while True:
            state = button.is_pressed
            if state != last:
                # Callback đếm chạy ở LUỒNG KHÁC, thường xong sau vòng lặp này vài
                # phần nghìn giây. Không chờ thì số đếm in ra trễ một dòng và người
                # đọc log tưởng máy đếm sai.
                time.sleep(0.03)
                print(f"  [{time.strftime('%H:%M:%S')}] "
                      f"{'●  ĐANG BẤM ' if state else '○  đã nhả  '}"
                      f"  (bấm: {len(presses)}, nhả: {len(releases)})")
                last = state
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        button.when_pressed = None
        button.when_released = None

    print("\n" + "=" * 60)
    print(f"  Số lần bấm ghi nhận : {len(presses)}")
    print(f"  Số lần nhả ghi nhận : {len(releases)}")
    if bounces:
        print(f"\n  ⚠️ PHÁT HIỆN DỘI PHÍM: {len(bounces)} lần, cách nhau "
              f"{min(bounces)*1000:.0f}–{max(bounces)*1000:.0f}ms")
        print("     Một cú bấm sinh ra nhiều sự kiện. Hậu quả khi thi đấu: bấm reset")
        print("     xong robot tự coi như đã được xác nhận và chạy tiếp NGAY, trong")
        print("     lúc người còn đang bê nó về ô xuất phát.")
        print("     → Tăng bounce_time trong main.py (0.1 → 0.2s), hoặc thêm tụ 100nF")
        print("       song song với nút.")
    else:
        print("\n  ✅ Không thấy dội phím.")
    print("\n  Đối chiếu: số lần bấm ghi nhận phải KHỚP số lần bạn thật sự bấm.")
    print("  Nhiều hơn = dội. Ít hơn = tiếp xúc kém / bounce_time quá lớn.")
    print("=" * 60)


def mode_flow(button):
    """Diễn tập đúng chuỗi nút của một trận, kể cả luồng reset 2 lần bấm."""
    print("=" * 60)
    print(" DIỄN TẬP LUỒNG THI ĐẤU (không chạy motor)")
    print("=" * 60)

    reset_requested = {"flag": False}

    def on_reset_button():
        reset_requested["flag"] = True
        print("     → callback _on_reset_button() đã chạy: yêu cầu RESET")

    # --- 1. Chờ bấm để BẮT ĐẦU (main._handle_init) ---
    print("\n[1] Trạng thái INIT — callback được GỠ để cú bấm này không bị hiểu là reset.")
    button.when_pressed = None
    print("    → BẤM NÚT để bắt đầu trận...")
    button.wait_for_press()
    t_start = time.monotonic()
    print(f"    ✅ Đã bắt đầu (t=0)")

    # --- 2. Gắn callback: từ giờ bấm = yêu cầu reset ---
    button.when_pressed = on_reset_button
    print("\n[2] Đang 'chạy trận'. Callback reset đã gắn.")
    print("    → BẤM NÚT để mô phỏng trọng tài cho RESET...")
    while not reset_requested["flag"]:
        time.sleep(0.02)
    print(f"    ✅ Nhận yêu cầu reset tại t={time.monotonic()-t_start:.1f}s")

    # --- 3. Chờ đặt robot xong (main._wait_for_placement) ---
    print("\n[3] main._wait_for_placement() — ĐÂY LÀ PHẦN CẦN KIỂM KỸ.")
    print("    Gỡ callback, chờ NHẢ, rồi chờ BẤM LẦN NỮA.")
    button.when_pressed = None

    t_wait = time.monotonic()
    button.wait_for_release(timeout=5)
    t_released = time.monotonic()
    print(f"    Đã nhả sau {t_released - t_wait:.2f}s")

    print("    → GIỜ HÃY ĐỢI vài giây rồi mới BẤM LẦN 2 (giả vờ đang bê robot)...")
    button.wait_for_press()
    waited = time.monotonic() - t_released
    print(f"    ✅ Bấm lần 2 sau {waited:.2f}s")

    button.when_pressed = on_reset_button

    print("\n" + "=" * 60)
    if waited < 0.5:
        print("  ❌ CHỜ QUÁ NGẮN — nếu bạn KHÔNG bấm nhanh như vậy thì nút đang DỘI,")
        print("     và robot sẽ tự chạy tiếp mà không ai xác nhận. Chạy chế độ")
        print("     `check_start_button` (không tham số) để đo dội phím.")
    else:
        print(f"  ✅ Luồng 2 lần bấm hoạt động đúng: robot chỉ chạy tiếp sau khi")
        print(f"     có cú bấm thứ 2 THẬT (chờ {waited:.1f}s).")
    print("=" * 60)


def main():
    button = _open()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "flow":
            mode_flow(button)
        else:
            mode_live(button)
    finally:
        button.close()


if __name__ == "__main__":
    main()
