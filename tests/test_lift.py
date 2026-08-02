#!/usr/bin/env python3
"""
Test module lift.py — kiểm tra cơ cấu nâng/hạ càng forklift.
Chạy trên Raspberry Pi 4 với phần cứng kết nối.

Ba nguyên tắc để không phải "giả định càng đang ở sàn" nữa:

1. **Home MỘT lần lúc vào menu.** Càng không có limit switch nên `_current_level`
   chỉ là con số phần mềm tự khai. Home đầu phiên làm nó khớp thực tế, nhờ vậy
   không option nào còn phải cảnh báo tiền đề.
2. **Menu LẶP.** Chọn xong quay lại menu, không thoát — calibrate thì phải
   nâng/so/chỉnh/nâng lại nhiều vòng, mỗi vòng chạy lại script là chạy lại cả
   home + khởi tạo GPIO.
3. **Ctrl+C và exception đều HOME lại rồi mới về menu.** Ngắt giữa lúc càng đang
   lên thì càng ở lưng chừng mà `_current_level` vẫn nói SÀN — lần nâng sau sẽ
   đội vào cữ cơ khí và kẹt motor.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control import Lift
from control.mcp3008_bus import reset_mcp3008_bus
from tests.config_editor import save_config

LEVEL_NAMES = {0: "SÀN", 1: "TẦNG 1", 2: "TẦNG 2"}


# ==============================================================
# Tiện ích dùng chung
# ==============================================================

def _ask_level(prompt: str = "  Tầng mấy? (1/2) [1]: ") -> int | None:
    raw = input(prompt).strip() or "1"
    if raw not in ("1", "2"):
        print("  Chỉ nhận 1 hoặc 2.")
        return None
    return int(raw)


def _ask_side(prompt: str = "  Càng nào? (left/right) [left]: ") -> str | None:
    raw = input(prompt).strip().lower() or "left"
    if raw not in ("left", "right"):
        print("  Chỉ nhận left hoặc right.")
        return None
    return raw


def _yes(prompt: str) -> bool:
    return input(prompt).strip().lower() in ("y", "yes")


def _ir(lift: Lift) -> str:
    """Một dòng trạng thái IR — in sau mỗi thao tác để thấy máy đang "nghĩ" gì."""
    left, right, ok = lift.pallet.read_status()
    if not ok:
        return "IR: ✖ KHÔNG ĐỌC ĐƯỢC (SPI/ADC) → main.py sẽ KHÔNG cộng điểm"
    return (f"IR: trái={'CÓ' if left else '--'}  phải={'CÓ' if right else '--'}")


def _home(lift: Lift, why: str, ask: bool = True, quick: bool = False) -> bool:
    """Home cả 2 càng để `_current_level` khớp thực tế. Trả False nếu người dùng huỷ.

    `quick=True` — dùng bản RÚT GỌN theo tầng đang tin là đang ở, thay vì luôn chạy
    theo tầng cao nhất. Chỉ dùng cho những lần home mang tính DỌN DẸP (trả càng về
    sàn sau khi xong một option), nơi vừa mới điều khiển càng nên `_current_level`
    đáng tin. Những lần home mang tính CHUẨN LẠI MỐC (đầu phiên, option 9, trước khi
    calibrate) vẫn chạy bản đầy đủ — đó chính là việc của chúng.

    Lý do có nhánh này: menu home lại sau MỖI option, mà home đầy đủ chạy 4.0s trong
    khi hạ từ tầng 1 chỉ cần ~0.9s. Hơn 3 giây motor ghì vào đáy cơ khí ở 100% duty
    mỗi lần, ngồi test một buổi là bào mòn thấy rõ dây curoa.
    """
    level = lift._current_level if quick else None
    secs = lift.home_from(level) if quick else max(config.LIFT_HOME_DURATION,
                                                   lift.min_home_duration())
    print(f"\n  [HOME] {why}")
    if quick:
        print(f"    Hạ {secs:.2f}s — bản RÚT GỌN, tin rằng càng đang ở tầng {level}.")
    else:
        print(f"    Hạ liên tục {secs:.2f}s ép chạm đáy cơ khí "
              f"(cần ≥ {lift.min_home_duration():.2f}s).")
    if ask and not _yes("    ⚠ Dưới càng KHÔNG có vật cản? (y/N): "):
        print("    Đã huỷ — CHÚ Ý: vị trí càng vẫn chưa chắc chắn.")
        return False
    lift.home_to_floor(from_level=level)
    print("    ✅ Cả 2 càng ở SÀN.")
    return True


# ==============================================================
# 1 — diễn tập trọn 1 lượt giao, y hệt main.py
# ==============================================================

def _manual_pickup(lift: Lift, level: int, require_both: bool) -> bool:
    """Bốc hàng khi NGƯỜI đã đặt càng vào pallet sẵn — dùng cho test bàn.

    ⚠️ ĐÂY KHÔNG PHẢI LUỒNG THI ĐẤU. Trong trận, `main._insert_and_lift()` còn
    một bước nữa mà file này không làm được (không có đối tượng Motion): sau khi
    nâng càng ngang tầng, robot phải TIẾN THÊM để luồn càng vào pallet, dừng theo
    tín hiệu IR. Ở đây bước đó do bạn đẩy robot bằng tay.

    Trước kia chỗ này gọi `Lift.pickup()` — một hàm nâng càng TỪ SÀN tại chỗ. Nó
    che mất việc main.py thiếu hẳn bước luồn càng: test bàn luôn xanh vì người test
    tự tay canh càng vào pallet. Hàm đó đã bị xoá; giờ test bàn và trận dùng CHUNG
    bộ nguyên thuỷ raise_to_insert/lift_off/confirm_pickup.
    """
    lift.raise_to_insert(level)
    input("  Đẩy robot vào cho càng LUỒN vào pallet (trong trận robot tự làm) → Enter...")
    lift.lift_off()
    return lift.confirm_pickup(require_both=require_both)


def test_delivery_rehearsal(lift: Lift):
    """Chuỗi thao tác càng của MỘT lượt giao thật, gọi đúng các hàm main.py gọi.

    Trước đây muốn thử luồng này phải chọn tay option 3 → 5 → 7, mỗi option lại có
    tiền đề riêng ("cần đang mang 2 kiện") nên rất dễ chạy sai thứ tự. Ở đây một
    phát chạy hết, và ĐẾM ĐIỂM theo đúng quy tắc của main.py: `packages_delivered`
    chỉ tăng khi IR xác nhận pallet đã rời càng.
    """
    print("\n[DIỄN TẬP] Trọn 1 lượt giao — pickup → thả càng 1 → nâng lại → thả càng 2 → gập")
    level = _ask_level("  Lấy ở tầng mấy? (1/2) [1]: ")
    if level is None:
        return
    same = _yes("  2 kiện CÙNG nhà máy (thả 1 lượt cả 2 càng)? (y/N): ")
    first = None
    if not same:
        first = _ask_side("  Thả càng nào TRƯỚC? (left/right) [left]: ")
        if first is None:
            return

    input(f"\n  Đặt 2 kiện lên kệ tầng {level}, càng vào đúng khe → Enter để PICKUP...")
    if not _manual_pickup(lift, level, require_both=True):
        print(f"  ❌ PICKUP THẤT BẠI — {_ir(lift)}")
        print("     main.py sẽ gọi _retry_or_skip_tier('scan') và có thể BỎ TẦNG này.")
        return
    print(f"  ✅ PICKUP OK ({LEVEL_NAMES[level]}) — {_ir(lift)}")

    delivered = 0
    input("\n  (giả lập robot chạy tới nhà máy) Enter để THẢ...")

    if same:
        ok = lift.dropoff()
        print(f"  dropoff() cả 2 càng: {'✅ IR xác nhận' if ok else '❌ IR vẫn thấy pallet'}")
        print(f"     {_ir(lift)}")
        delivered = 2 if ok else 0
    else:
        second = "right" if first == "left" else "left"

        # --- DROP_FIRST (main.py: _drop_single_side) ---
        ok1 = lift.dropoff_left() if first == "left" else lift.dropoff_right()
        print(f"  dropoff_{first}(): {'✅' if ok1 else '❌ IR chưa xác nhận'} — {_ir(lift)}")
        delivered += 1 if ok1 else 0
        lift.raise_after_drop(first)
        print(f"  raise_after_drop({first}) — nâng lại LUÔN, kể cả khi IR fail "
              "(càng nằm dưới sàn thì cạ sàn/vướng kệ lúc robot lùi)")

        input("\n  (giả lập robot chạy sang nhà máy thứ 2) Enter để THẢ càng còn lại...")

        # --- DROP_SECOND ---
        ok2 = lift.dropoff_left() if second == "left" else lift.dropoff_right()
        print(f"  dropoff_{second}(): {'✅' if ok2 else '❌ IR chưa xác nhận'} — {_ir(lift)}")
        delivered += 1 if ok2 else 0
        lift.stow_forks(second)
        print(f"  stow_forks({second}) — hạ càng còn lại về sàn, sẵn sàng chạy tiếp")

    print(f"\n  ➜ main.py sẽ cộng {delivered}/2 kiện lượt này ({delivered * 20} điểm).")
    if delivered < 2:
        print("     Kiện không được cộng KHÔNG phải lỗi đếm — IR không xác nhận thì")
        print("     coi như chưa thả được. Xem lại IR (option 8) hoặc thời gian hạ (option d).")


# ==============================================================
# 2-4 — nâng/hạ và pickup/dropoff cơ bản
# ==============================================================

def test_shelf_levels(lift: Lift):
    """Đi hết các tầng và về, dừng lại cho quan sát ở từng mốc."""
    print("\n[TEST] Chạy hết dải hành trình: SÀN → T1 → SÀN → T2 → SÀN")
    for target in (1, 0, 2, 0):
        print(f"  → {LEVEL_NAMES[target]} "
              f"(trái {lift._move_duration('left', lift._current_level, target, target > lift._current_level):.2f}s / "
              f"phải {lift._move_duration('right', lift._current_level, target, target > lift._current_level):.2f}s)")
        lift.go_to_level(target)
        time.sleep(1.5)
    print("  Quan sát: có nghe motor đội cữ ở đầu/cuối hành trình không? "
          "Có = thời gian tầng đang dư (option d).")


def test_pickup_dropoff(lift: Lift):
    level = _ask_level()
    if level is None:
        return
    print(f"\n[TEST] Pickup tầng {level} (cần CẢ 2 IR) → dropoff")
    input(f"  Đặt 2 kiện ở tầng {level} → Enter...")
    ok = _manual_pickup(lift, level, require_both=True)
    print(f"  pickup: {'✅ THÀNH CÔNG' if ok else '❌ THẤT BẠI'} — {_ir(lift)}")
    time.sleep(1)
    if not _yes("  Hạ xuống (dropoff)? (y/N): "):
        return
    ok = lift.dropoff()
    print(f"  dropoff: {'✅ ĐÃ HẠ' if ok else '❌ CÓ THỂ KẸT / IR vẫn thấy pallet'} — {_ir(lift)}")


def test_drop_single_side(lift: Lift):
    """Thả 1 càng → nâng lại → thả càng còn lại → gập càng.

    ⚠️ Làm y hệt main.py: LUÔN nâng lại / gập càng, KỂ CẢ khi IR không xác nhận.
    Nếu test chỉ nâng khi IR OK thì nhánh "IR fail" không bao giờ được kiểm.
    """
    print("\n[TEST] Thả từng càng (dropoff_left/right + raise_after_drop + stow_forks)")
    print(f"  Vị trí hiện tại: {LEVEL_NAMES.get(lift._current_level, '?')}")
    if lift._current_level == 0:
        print("  ⚠ Càng đang ở SÀN — thả từ sàn không có gì để quan sát.")
        if not _yes("  Nâng lên tầng 1 trước? (y/N): "):
            return
        lift.go_to_level(1)
    side = _ask_side("  Thả càng nào trước? (left/right) [left]: ")
    if side is None:
        return

    dropped = lift.dropoff_left() if side == "left" else lift.dropoff_right()
    print(f"  dropoff_{side}: {'✅' if dropped else '❌ THẤT BẠI / IR lỗi'} — {_ir(lift)}")
    lift.raise_after_drop(side)
    print(f"  raise_after_drop({side}) — đã nâng lại (main.py luôn nâng dù IR "
          f"{'OK' if dropped else 'FAIL'})")
    if not dropped:
        print("  ⚠ main.py sẽ KHÔNG cộng điểm kiện này")

    other = "right" if side == "left" else "left"
    if not _yes(f"  Tiếp tục thả càng {other}? (y/N): "):
        return
    dropped2 = lift.dropoff_left() if other == "left" else lift.dropoff_right()
    print(f"  dropoff_{other}: {'✅' if dropped2 else '❌ THẤT BẠI'} — {_ir(lift)}")
    lift.stow_forks(other)
    print(f"  stow_forks({other}) — cả 2 càng về sàn, sẵn sàng di chuyển")


def test_pickup_nv2(lift: Lift):
    print("\n[TEST] Pickup NV2 — require_both=False (chỉ cần 1 IR)")
    print("  Đặt 1 kiện trên càng (kho hàng rời).")
    input("  Enter để nâng...")
    ok = _manual_pickup(lift, 1, require_both=False)
    print(f"  Kết quả: {'✅ THÀNH CÔNG' if ok else '❌ THẤT BẠI'} — {_ir(lift)}")
    if ok and _yes("  Hạ thử (dropoff)? (y/N): "):
        print(f"  dropoff: {'✅ OK' if lift.dropoff() else '❌ THẤT BẠI'} — {_ir(lift)}")


def test_dropoff_same_factory(lift: Lift):
    print("\n[TEST] dropoff() đồng bộ — 2 kiện cùng nhà máy")
    print(f"  Vị trí hiện tại: {LEVEL_NAMES.get(lift._current_level, '?')}")
    input("  Enter khi càng đang mang 2 kiện...")
    ok = lift.dropoff()
    print(f"  Kết quả: {'✅ ĐÃ HẠ (IR OK)' if ok else '❌ IR vẫn thấy pallet'} — {_ir(lift)}")


# ==============================================================
# 9 — home
# ==============================================================

def test_home_to_floor(lift: Lift):
    """home_to_floor() — chạy ở ĐẦU MỖI TRẬN (Lift.reset), phải hạ hết cỡ."""
    needed = lift.min_home_duration()
    print("\n[TEST] home_to_floor — ép càng chạm đáy cơ khí (KHÔNG có limit switch)")
    print(f"  LIFT_HOME_DURATION = {config.LIFT_HOME_DURATION:.2f}s")
    print(f"  Cần tối thiểu      = {needed:.2f}s  ← hạ từ tầng {2} về sàn, càng CHẬM NHẤT")
    print("    (= LIFT_TIME_SHELF_2 + LIFT_*_LOWER_EXTRA lớn hơn trong 2 bên — KHÔNG")
    print("     phải chỉ LIFT_TIME_SHELF_2, chỗ này trước đây so sai ngưỡng)")
    if config.LIFT_HOME_DURATION >= needed:
        print(f"  → ✅ ĐẠT (dư {config.LIFT_HOME_DURATION - needed:.2f}s)")
    else:
        print(f"  → ❌ THIẾU {needed - config.LIFT_HOME_DURATION:.2f}s "
              "— home_to_floor() sẽ tự kẹp lên và ghi WARNING, nhưng hãy sửa config")

    print("\n  CÁCH TEST ĐÚNG: nâng lên TẦNG 2 trước rồi home — càng phải chạm đáy hẳn.")
    if _yes("  Nâng lên tầng 2 trước? (y/N): "):
        lift.go_to_level(2)
        time.sleep(1)
    if not _home(lift, "kiểm home từ tầng cao nhất"):
        return
    print("  👀 Kiểm bằng mắt: CẢ 2 càng đã chạm đáy chưa? Còn hở = tăng LIFT_HOME_DURATION.")


# ==============================================================
# 8, a — cảm biến
# ==============================================================

def test_mcp3008_all(lift: Lift):
    """Đọc tất cả 8 channel MCP3008 real-time — tìm xem IR cắm channel nào."""
    from control.mcp3008_bus import get_mcp3008_bus
    bus = get_mcp3008_bus()
    if not bus.available:
        print("  ⚠ MCP3008 không khả dụng")
        return
    print("\n[TEST] Scan tất cả 8 channel MCP3008 — Ctrl+C để về menu")
    print("  Che tay/đặt vật vào cảm biến → xem channel nào thay đổi")
    print(f"  CH{config.PALLET_LEFT_CHANNEL}=IR trái  "
          f"CH{config.PALLET_RIGHT_CHANNEL}=IR phải  (theo config hiện tại)\n")
    i = 0
    while True:
        adcs = [int(round(v * 1023)) for v in bus.read_many(list(range(8)))]
        i += 1
        row = "  ".join(f"CH{c}:{adcs[c]:4d}" for c in range(8))
        print(f"\r  [{i:4d}] {row}", end="", flush=True)
        time.sleep(0.2)


def test_ir_live(lift: Lift):
    print("\n[TEST] Đọc IR real-time — Ctrl+C để về menu")
    print(f"  Ngưỡng PALLET_THRESHOLD={config.PALLET_THRESHOLD} (ADC < ngưỡng = CÓ pallet)")
    if not lift.pallet.available:
        print("  ⚠ MCP3008 không khả dụng")
        return
    i = 0
    while True:
        left, right, ok = lift.pallet.read_status()
        left_adc, right_adc = lift.pallet.read_adc()
        i += 1
        if not ok:
            print(f"\r  [{i:4d}] LỖI đọc SPI/ADC                              ",
                  end="", flush=True)
        else:
            l_bar = "██ CÓ " if left  else "░░ -- "
            r_bar = "██ CÓ " if right else "░░ -- "
            print(f"\r  [{i:4d}] Trái: {l_bar}(ADC {left_adc:4d})   "
                  f"Phải: {r_bar}(ADC {right_adc:4d})", end="", flush=True)
        time.sleep(0.2)


# ==============================================================
# b, c, e — từng càng riêng
# ==============================================================

def _single_fork_cycle(lift: Lift, side: str, level: int):
    """Nâng rồi hạ MỘT càng, dùng ĐÚNG thời gian đã bù như lúc thi đấu.

    Không bật/tắt thẳng chân GPIO mà đi qua _move_duration() + _raise_/_lower_ của
    Lift — nhờ vậy cái quan sát được ở đây chính là cái sẽ xảy ra trong trận (gồm cả
    phần bù LIFT_*_EXTRA riêng của càng đó). Bật GPIO thô với thời gian tự đặt thì
    chỉ kiểm được dây, không kiểm được calibrate.
    """
    up = lift._move_duration(side, 0, level, raising=True)
    down = lift._move_duration(side, level, 0, raising=False)
    label = "TRÁI" if side == "left" else "PHẢI"
    print(f"\n  Càng {label} — sàn ↔ tầng {level}: nâng {up:.3f}s / hạ {down:.3f}s")

    input(f"  Enter → NÂNG càng {label}...")
    (lift._raise_left if side == "left" else lift._raise_right)(up)
    print(f"  ✅ Đã nâng ({up:.3f}s)")

    input(f"  Quan sát độ cao rồi Enter → HẠ càng {label}...")
    (lift._lower_left if side == "left" else lift._lower_right)(down)
    print(f"  ✅ Đã hạ ({down:.3f}s)")


def test_left_only(lift: Lift):
    """Nâng/hạ RIÊNG càng trái — càng phải đứng yên."""
    print(f"\n[TEST] Càng TRÁI riêng (ENA={config.ENA_CAU_T}, "
          f"IN1={config.IN1_CAU_T}, IN2={config.IN2_CAU_T}) — càng phải KHÔNG chạy")
    level = _ask_level()
    if level is not None:
        _single_fork_cycle(lift, "left", level)


def test_right_only(lift: Lift):
    """Nâng/hạ RIÊNG càng phải — càng trái đứng yên."""
    print(f"\n[TEST] Càng PHẢI riêng (IN3={config.IN3_CAU_P}, IN4={config.IN4_CAU_P})"
          " — càng trái KHÔNG chạy")
    level = _ask_level()
    if level is not None:
        _single_fork_cycle(lift, "right", level)


def test_compare_forks(lift: Lift):
    """Nâng lần lượt từng càng lên CÙNG tầng rồi so độ cao bằng mắt.

    Đây là cách chốt LIFT_LEFT_EXTRA / LIFT_RIGHT_EXTRA: nâng cả 2 càng cùng lúc thì
    khó thấy bên nào cao hơn; nâng riêng từng bên rồi GIỮ NGUYÊN mới so được.
    """
    print("\n[TEST] SO SÁNH 2 CÀNG — nâng riêng từng bên lên cùng tầng")
    level = _ask_level()
    if level is None:
        return

    up_l = lift._move_duration("left", 0, level, raising=True)
    up_r = lift._move_duration("right", 0, level, raising=True)
    print(f"\n  Nâng lên tầng {level}: trái {up_l:.3f}s | phải {up_r:.3f}s  "
          f"(chênh {abs(up_l - up_r):.3f}s)")
    print(f"  Do LIFT_LEFT_EXTRA={config.LIFT_LEFT_EXTRA:+.3f} vs "
          f"LIFT_RIGHT_EXTRA={config.LIFT_RIGHT_EXTRA:+.3f}")

    input("\n  Enter → nâng càng TRÁI...")
    lift._raise_left(up_l)
    input("  Enter → nâng càng PHẢI (giữ nguyên càng trái để so)...")
    lift._raise_right(up_r)
    lift._current_level = level   # khai báo ĐÚNG ngay: Ctrl+C lúc này thì phần
                                 # dọn dẹp ở _run() mới home được về đúng chỗ

    print("\n  👀 SO ĐỘ CAO 2 CÀNG NGAY BÂY GIỜ:")
    print("     - Càng TRÁI cao hơn  → giảm LIFT_LEFT_EXTRA")
    print("     - Càng PHẢI cao hơn  → giảm LIFT_RIGHT_EXTRA")
    print("     - Bằng nhau          → đã chuẩn")
    print("     Chỉnh nhanh ở menu d (calibrate): phím l+/l- và r+/r-")

    input("\n  Enter → hạ CẢ 2 càng về sàn...")
    lift.go_to_level(0)
    print("  ✅ Đã hạ về sàn")


# ==============================================================
# d — calibrate
# ==============================================================

def _find_level_by_hand(lift: Lift, target_level: int):
    """Nâng từng xung nhỏ MỘT càng, người dùng chốt khi đúng độ cao → ghi thời gian.

    Chỉ chạy MỘT càng, và trừ lại phần bù của càng đó trước khi lưu. Lý do:
    `LIFT_TIME_SHELF_n` là mốc GỐC, còn thời gian càng thật sự chạy là
    `gốc + LIFT_<side>_EXTRA`. Bản trước chạy CẢ 2 càng cùng số giây rồi lưu thẳng
    số đó vào mốc gốc — với bù hiện tại (-0.45 / -0.30) thì 2 càng dừng ở 2 độ cao
    khác nhau (không biết đang canh theo bên nào), và mốc lưu ra bị lệch đúng bằng
    phần bù, tức càng thật sự chạy sẽ THIẾU 0.45s so với chỗ vừa canh.
    """
    key = "LIFT_TIME_SHELF_1" if target_level == 1 else "LIFT_TIME_SHELF_2"
    pulse = 0.05

    side = _ask_side("  Canh theo càng nào? (left/right) [left]: ")
    if side is None:
        return
    label = "TRÁI" if side == "left" else "PHẢI"

    print(f"\n  [FIND LEVEL {target_level}] Đặt kệ trước càng. Hạ về sàn trước...")
    lift.go_to_level(0)
    if not _home(lift, f"chuẩn mốc 0 trước khi đo tầng {target_level}"):
        return

    print(f"  Enter liên tục để nâng càng {label} từng bước {pulse}s.")
    print(f"  Khi càng VỪA KHÍT dưới pallet tầng {target_level} → gõ 'ok' rồi Enter.")
    print("  (chỉ càng này chạy — càng kia đứng yên để không bị nhìn lẫn)")

    raise_one = lift._raise_left if side == "left" else lift._raise_right
    elapsed = 0.0
    while True:
        raw = input(f"  [{elapsed:.2f}s] Enter=nâng thêm / ok=ghi lại / q=bỏ: ").strip().lower()
        if raw == "ok":
            break
        if raw == "q":
            print("  Đã bỏ — hạ về sàn.")
            lift._current_level = target_level   # để _home hạ đủ lâu
            _home(lift, "trả càng về sàn sau khi bỏ đo", quick=True)
            return
        raise_one(pulse)
        elapsed += pulse

    extra = config.LIFT_LEFT_EXTRA if side == "left" else config.LIFT_RIGHT_EXTRA
    base = elapsed - extra
    print(f"\n  Càng {label} chạy thật {elapsed:.3f}s, bù LIFT_{label}_EXTRA={extra:+.3f}")
    print(f"  → mốc gốc {key} = {elapsed:.3f} − ({extra:+.3f}) = {base:.3f}s")
    if base <= 0:
        print(f"  ❌ Mốc gốc ra {base:.3f}s ≤ 0 — phần bù đang quá lớn, đặt lại về 0 rồi đo lại.")
        return
    if save_config(key, base):
        print(f"  ✅ Đã lưu {key} = {base:.3f}s")
        lift._current_level = target_level


def test_calibrate_lift(lift: Lift):
    """Calibrate độ cao tầng 1/2 và bù lệch trái/phải — lưu vào config.py."""
    import importlib

    step_time  = 0.05   # bước điều chỉnh thời gian (giây)
    step_extra = 0.05   # bước điều chỉnh bù lệch

    print("\n[CALIBRATE] Nâng/hạ lift — điều chỉnh timing, lưu config")
    print("  Nâng: t1+/t1- = tầng1  t2+/t2- = tầng2  l+/l- = bù trái nâng  r+/r- = bù phải nâng")
    print("  Hạ:   ll+/ll- = bù trái hạ  rl+/rl- = bù phải hạ")
    print("  Di chuyển: up1/up2/dn      Đo thực: find1/find2      home = ép chạm đáy")
    print("  q = về menu\n")

    tweaks = {
        "t1+": ("LIFT_TIME_SHELF_1", +step_time),  "t1-": ("LIFT_TIME_SHELF_1", -step_time),
        "t2+": ("LIFT_TIME_SHELF_2", +step_time),  "t2-": ("LIFT_TIME_SHELF_2", -step_time),
        "l+":  ("LIFT_LEFT_EXTRA",  +step_extra),  "l-":  ("LIFT_LEFT_EXTRA",  -step_extra),
        "r+":  ("LIFT_RIGHT_EXTRA", +step_extra),  "r-":  ("LIFT_RIGHT_EXTRA", -step_extra),
        "ll+": ("LIFT_LEFT_LOWER_EXTRA",  +step_extra),
        "ll-": ("LIFT_LEFT_LOWER_EXTRA",  -step_extra),
        "rl+": ("LIFT_RIGHT_LOWER_EXTRA", +step_extra),
        "rl-": ("LIFT_RIGHT_LOWER_EXTRA", -step_extra),
    }

    while True:
        importlib.reload(config)
        print(f"  [vị trí={LEVEL_NAMES.get(lift._current_level, '?')}]  "
              f"shelf1={config.LIFT_TIME_SHELF_1:.3f}s  shelf2={config.LIFT_TIME_SHELF_2:.3f}s  "
              f"nâng: L={config.LIFT_LEFT_EXTRA:+.3f} R={config.LIFT_RIGHT_EXTRA:+.3f}  "
              f"hạ: L={config.LIFT_LEFT_LOWER_EXTRA:+.3f} R={config.LIFT_RIGHT_LOWER_EXTRA:+.3f}")
        need = lift.min_home_duration()
        if config.LIFT_HOME_DURATION < need:
            print(f"  ⚠ LIFT_HOME_DURATION={config.LIFT_HOME_DURATION:.2f}s < {need:.2f}s cần "
                  "— vừa chỉnh bù hạ xong thì home không còn chạm đáy. Tăng lên trong config.")

        cmd = input("  > ").strip().lower()

        if cmd in ("q", "s"):
            print("  Về menu (giá trị đã lưu ngay lúc chỉnh).")
            return
        elif cmd in tweaks:
            key, delta = tweaks[cmd]
            floor = 0.1 if key.startswith("LIFT_TIME_") else None
            new = getattr(config, key) + delta
            save_config(key, max(floor, new) if floor is not None else new)
        elif cmd == "up1":
            lift.go_to_level(1)
        elif cmd == "up2":
            lift.go_to_level(2)
        elif cmd == "dn":
            lift.go_to_level(0)
        elif cmd in ("find1", "find2"):
            _find_level_by_hand(lift, 1 if cmd == "find1" else 2)
        elif cmd == "home":
            _home(lift, "ép chạm đáy cơ khí, chuẩn lại mốc 0")
        else:
            print("  Lệnh không hợp lệ: " + "  ".join(list(tweaks) +
                  ["up1", "up2", "dn", "find1", "find2", "home", "q"]))


# ==============================================================
# Menu
# ==============================================================

TESTS = {
    "1": ("Diễn tập TRỌN 1 lượt giao (như main.py)", test_delivery_rehearsal),
    "2": ("Chạy hết dải hành trình (SÀN/T1/T2)",     test_shelf_levels),
    "3": ("Pickup/Dropoff (chọn tầng)",              test_pickup_dropoff),
    "5": ("Thả từng càng NV1 (left/right + stow)",   test_drop_single_side),
    "6": ("Pickup NV2 (require_both=False)",         test_pickup_nv2),
    "7": ("dropoff() 2 kiện cùng nhà máy",           test_dropoff_same_factory),
    "8": ("IR real-time (Ctrl+C về menu)",           test_ir_live),
    "9": ("home_to_floor + kiểm ngưỡng thời gian",   test_home_to_floor),
    "a": ("Scan cả 8 channel MCP3008 (Ctrl+C về menu)", test_mcp3008_all),
    "b": ("Càng TRÁI riêng — nâng + hạ",             test_left_only),
    "c": ("Càng PHẢI riêng — nâng + hạ",             test_right_only),
    "e": ("So 2 càng cùng tầng (chốt bù lệch)",      test_compare_forks),
    "d": ("Calibrate độ cao + bù lệch (ghi config)", test_calibrate_lift),
}

#: "Chạy tất cả" bỏ qua: cần người đặt hàng lên càng (5/6/7), vòng lặp vô hạn
#: (8/a), ghi config.py (d), và các option 1 càng cần quan sát bằng mắt (b/c/e).
RUN_ALL_SKIP = {"1", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e"}


def _run(lift: Lift, name: str, func):
    """Chạy 1 option; Ctrl+C hoặc lỗi thì HOME lại rồi mới về menu.

    Ngắt giữa lúc càng đang lên → càng ở lưng chừng nhưng `_current_level` vẫn nói
    SÀN (hoặc tầng cũ). Lần nâng sau tính theo con số sai đó sẽ đội vào cữ cơ khí
    và kẹt motor. Không có limit switch nên home là cách duy nhất chuẩn lại mốc.
    """
    try:
        func(lift)
    except KeyboardInterrupt:
        print("\n  ⏹  Đã ngắt.")
    except EOFError:
        # stdin hết (chạy qua pipe/script) — để nó nổi lên main mà thoát, đừng
        # nuốt thành lỗi rồi quay lại menu: menu cũng đọc stdin → lặp vô hạn.
        lift._stop_all()
        raise
    except Exception as e:
        print(f"\n  ❌ LỖI trong [{name}]: {type(e).__name__}: {e}")
    finally:
        lift._stop_all()
    if lift._current_level != 0:
        print(f"  Càng đang ở {LEVEL_NAMES.get(lift._current_level, '?')} — "
              "cần hạ về sàn trước khi chọn option khác.")
        _home(lift, "trả càng về sàn sau khi kết thúc option", quick=True)


def main():
    print("=" * 60)
    print("TEST MODULE CƠ CẤU NÂNG/HẠ")
    print("=" * 60)

    lift = Lift()
    homed = False

    try:
        print("\nCàng KHÔNG có limit switch → phần mềm không đo được càng đang ở đâu.")
        # Từ khi config.HOME_AT_INIT = False, đội LUÔN tự hạ càng về sàn bằng tay
        # trước khi chạy — nên "đã ở sàn sẵn" mới là trường hợp thường gặp, và bắt
        # nó chạy home đầy đủ mỗi lần mở menu chỉ tổ ghì motor vào đáy vô ích.
        # Hỏi thẳng vị trí càng thay vì hỏi vòng qua câu "dưới càng có vật cản không".
        print("\n  Càng ĐANG ở đâu?")
        print(f"    y = đã ở SÀN sẵn      → chỉ ép nhẹ {lift.home_from(0):.2f}s cho chắc")
        print(f"    n = không chắc / ở trên → home đầy đủ "
              f"{max(config.LIFT_HOME_DURATION, lift.min_home_duration()):.2f}s")
        at_floor = _yes("  Càng đã ở sàn sẵn? (y/N): ")
        homed = _home(lift, "chuẩn mốc SÀN đầu phiên", quick=at_floor)
        if not homed:
            print("  ⚠ Chưa home: mọi option sẽ tính thời gian theo giả định "
                  "càng ĐANG Ở SÀN. Sai thì motor đội cữ.")

        while True:
            print("\n" + "-" * 60)
            print(f"Vị trí càng (phần mềm tin): {LEVEL_NAMES.get(lift._current_level, '?')}"
                  f"{'' if homed else '  ← CHƯA HOME, có thể sai'}")
            for key, (name, _) in TESTS.items():
                print(f"  {key}. {name}")
            print("  h. Home lại (chuẩn mốc SÀN)")
            print("  0. Chạy tất cả (bỏ các option cần đặt hàng/quan sát tay)")
            print("  q. Thoát")

            choice = input("\nChọn: ").strip().lower()

            if choice == "q":
                break
            elif choice == "h":
                homed = _home(lift, "chuẩn lại mốc SÀN") or homed
            elif choice == "0":
                for key, (name, func) in TESTS.items():
                    if key in RUN_ALL_SKIP:
                        continue
                    print(f"\n{'=' * 60}\n[{key}] {name}\n{'=' * 60}")
                    _run(lift, name, func)
                print(f"\n  Đã bỏ qua: {' '.join(sorted(RUN_ALL_SKIP))} "
                      "(cần đặt hàng lên càng / quan sát tay / ghi config)")
            elif choice in TESTS:
                _run(lift, TESTS[choice][0], TESTS[choice][1])
            else:
                print("  Lựa chọn không hợp lệ.")

    except (KeyboardInterrupt, EOFError):
        print("\n\nDừng bởi người dùng.")
    finally:
        # Hạ càng TRƯỚC khi đóng chân GPIO — cleanup() chỉ tắt motor, càng đang
        # treo lơ lửng sẽ nằm nguyên đó cho lần chạy sau tính sai mốc.
        if lift._current_level != 0:
            print(f"\nCàng đang ở {LEVEL_NAMES.get(lift._current_level, '?')} — hạ về sàn "
                  "trước khi thoát.")
            try:
                _home(lift, "hạ càng về sàn trước khi thoát", quick=True)
            except KeyboardInterrupt:
                print("  ⚠ Bỏ qua — LẦN CHẠY SAU PHẢI HOME NGAY.")
        lift.cleanup()
        reset_mcp3008_bus()
        print("\nĐã cleanup GPIO.")


if __name__ == "__main__":
    main()
