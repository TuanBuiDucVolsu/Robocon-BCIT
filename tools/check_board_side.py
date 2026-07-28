#!/usr/bin/env python3
"""
Kiểm tra 2 nút/công tắc trên robot — chạy trên Pi, thao tác tay xem có đúng không.

    python3 -m tools.check_board_side

Dùng để:
  1. Kiểm đấu dây sau khi lắp (gạt/bấm → màn hình phải đổi NGAY).
  2. Chống CẮM TRÁO CHÂN: nút khởi động và công tắc nửa sân đấu dây giống hệt nhau
     (GPIO → GND) nên rất dễ cắm nhầm chân của nhau. Nhầm thì gạt công tắc robot sẽ
     chạy, còn bấm nút thì không có gì xảy ra. Màn hình này hiện CẢ HAI cùng lúc nên
     phát hiện trong 5 giây.
  3. Dán nhãn 2 bên công tắc cho khớp: gạt bên nào ra FOXCONN, bên nào ra SAMSUNG.
  4. Kiểm nhanh trước mỗi trận sau khi bốc thăm biết nửa sân.

Màn hình in kèm luôn thứ tự nhà máy theo trạng thái công tắc hiện tại, để đối chiếu
ngay với sa bàn trước mặt.

Nhấn Ctrl+C để thoát.
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

import config
import navigation as nav
from control.board_switch import BoardSideSwitch

try:
    from gpiozero import Button, Device
    Device.ensure_pin_factory()
except Exception:
    Button = None


def _describe(side: str) -> str:
    nav.set_factory_order(side)
    rows = []
    for label in ("foxconn", "amkor", "hana_micron", "samsung"):
        node = nav.TERMINALS[nav.FACTORY_TERMINAL[label]][0]
        rows.append((int(node[-1]), label))
    rows.sort()
    return "  ".join(f"R{r}:{lb}" for r, lb in rows)


def _open_start_button():
    if Button is None:
        return None
    try:
        return Button(config.START_BUTTON_PIN, pull_up=True, bounce_time=0.05)
    except Exception as e:
        print(f" ⚠ Không mở được nút khởi động (GPIO {config.START_BUTTON_PIN}): {e}")
        return None


def main():
    print("=" * 70)
    print(" KIỂM TRA NÚT KHỞI ĐỘNG + CÔNG TẮC GẠT NỬA SÂN")
    print("=" * 70)

    sw = BoardSideSwitch()
    if not sw.available:
        print(f"\n ❌ KHÔNG đọc được công tắc.")
        print(f"    BOARD_SIDE_SWITCH_PIN = {config.BOARD_SIDE_SWITCH_PIN}")
        if config.BOARD_SIDE_SWITCH_PIN is None:
            print("    → Chưa khai báo chân GPIO. Đặt số chân vào config.py.")
        else:
            print("    → Kiểm dây: chân giữa công tắc phải nối GND,")
            print("      một cực nối đúng GPIO trên, cực còn lại để trống.")
        print(f"\n    Đang chạy bằng dự phòng: config.FACTORY_AT_START_ROW = "
              f"{config.FACTORY_AT_START_ROW!r}")
        return

    print(f"\n Công tắc nửa sân : GPIO {sw.pin}")
    print(f"    gạt về phía NỐI GND  → {sw.closed_side.upper()}")
    print(f"    gạt về phía THẢ NỔI  → {sw.open_side.upper()}")
    print(f" Nút khởi động    : GPIO {config.START_BUTTON_PIN}")

    button = _open_start_button()

    print("\n THAO TÁC KIỂM TRA — làm đủ 3 bước:")
    print("   1. GẠT công tắc qua lại  → chỉ dòng NỬA SÂN được đổi")
    print("   2. BẤM giữ nút khởi động → chỉ dòng NÚT được đổi")
    print("   3. Nếu làm 1 mà dòng NÚT đổi (hoặc ngược lại) → CẮM TRÁO CHÂN 2 cái\n")

    last = None
    try:
        while True:
            side = sw.read()
            pressed = bool(button.is_pressed) if button is not None else None
            state = (side, pressed)
            if state != last:
                last = state
                nut = ("(không mở được)" if pressed is None
                       else "ĐANG BẤM" if pressed else "nhả")
                print("\n" + "-" * 70)
                print(f" NỬA SÂN: nhà máy cùng hàng ô xuất phát = {side.upper()}")
                print(f" Thứ tự nhà máy: {_describe(side)}")
                print(f" NÚT khởi động : {nut}")
                print(" Đối chiếu: đứng ở ô xuất phát nhìn sang tường giữa sân,")
                print(f" cụm nhà máy CÙNG HÀNG ô xuất phát có phải {side.upper()} không?")
                print("-" * 70)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n Thoát. Nhớ để công tắc ở đúng nửa sân sắp thi đấu.")
    finally:
        sw.close()
        if button is not None:
            button.close()


if __name__ == "__main__":
    main()
