#!/usr/bin/env python3
"""
Smoke test tích hợp — chạy trên Pi + SA BÀN THẬT.

    python3 tests/test_smoke.py

Khác `test_motion`/`test_lift`/`test_vision` (kiểm từng module riêng): file này chạy
các ĐOẠN LUỒNG THI ĐẤU nối liền nhau, dùng đúng bộ sinh route `navigation.plan()` như
main.py. Mục đích: bắt lỗi ở chỗ ghép nối giữa các module.

Nguyên tắc: fail ở bước nào thì DỪNG ngay tại đó, không chạy tiếp — smoke test dùng
để tìm điểm gãy đầu tiên, không phải để đo hết mọi thứ.

⚠️ Các smoke này KHÔNG chạy state machine của main.py. Chạy trọn trận thật thì dùng
`bash scripts/practice.sh` (luyện tập lặp, nhấn nút mỗi lượt).
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import navigation as nav
from control import Motion, Lift
from control.mcp3008_bus import reset_mcp3008_bus
from control.handling import drop_both, drop_side, insert_and_lift_once
from vision import Vision


def _pause(msg: str):
    input(f"\n  {msg}\n  Nhấn Enter để tiếp tục...")


def _ask(msg: str, default: str = "") -> str:
    return input(f"  {msg}").strip().lower() or default


def _run(m: Motion, goal: str, pose) -> tuple[bool, tuple]:
    """Đi từ `pose` tới `goal` bằng đúng route mà main.py sẽ dùng."""
    route, new_pose = nav.plan(pose, goal)
    if route is None:
        print(f"  ❌ Không có đường {pose} → {goal}")
        return False, pose
    print(f"  Route {nav.describe(pose)} → {goal}:\n     {nav.route_to_text(route)}")
    ok = m.execute_route(route)
    print(f"  {'✅' if ok else '❌'} execute_route: {ok}")
    return ok, (new_pose if ok else nav.apply(pose, m.last_route_progress))


# ==========================================================
# SMOKE 1 — Xuất phát: exit start → dò nửa sân → vào Kệ 3
# ==========================================================

def smoke_exit_and_navigate(m: Motion, **_):
    """Đúng thứ tự main.py: START → DETECT_SIDE → NAVIGATE_TO_SHELF."""
    print("\n[SMOKE 1] Xuất phát → dò nửa sân → Kệ 3")
    print("  Đặt robot trong ô start, quay mặt về phía Kệ 3.")
    _pause("Sẵn sàng?")

    if not m.exit_start_zone():
        print("  ❌ exit_start_zone THẤT BẠI")
        return False, nav.START_POSE
    print("  ✅ exit_start_zone OK")
    pose = nav.START_POSE

    # --- Bước DETECT_SIDE của main.py ---
    if getattr(config, "BOARD_AUTO_DETECT", False):
        ok, pose = _run(m, nav.PROBE_NODE, pose)
        if not ok:
            print("  ❌ Không tới được giao lộ dò nửa sân")
            return False, pose
        found = m.probe_side_branch("right")
        if found is None:
            print("  ⚠ Dò nửa sân: cảm biến lỗi — giữ nguyên bản đồ")
        else:
            mirrored = not found
            print(f"  {'✅' if mirrored == nav.MIRRORED else '⚠'} Dò nửa sân: "
                  f"chiều {'GƯƠNG' if mirrored else 'CHUẨN'} "
                  f"(cấu hình đang là {'GƯƠNG' if nav.MIRRORED else 'CHUẨN'})")
            if mirrored != nav.MIRRORED:
                nav.set_mirrored(mirrored)
                print("  → Đã nạp lại bản đồ theo kết quả dò")
        pose = (nav.PROBE_NODE, nav.TOWARD_SHELVES)

    ok, pose = _run(m, "SHELF0", pose)
    return ok, pose


# ==========================================================
# SMOKE 2 — Pickup 1 lượt
# ==========================================================

def smoke_pickup_cycle(m: Motion, lift: Lift, vision: Vision, tier: int = 1, **_):
    print(f"\n[SMOKE 2] Pickup tầng {tier} (approach → classify_pair → nâng → lùi)")
    _pause(f"Đặt robot trước kệ có 2 kiện ở tầng {tier}, càng đang ở sàn")

    if not m.approach_shelf():
        print("  ❌ approach_shelf THẤT BẠI (timeout hoặc không thấy mục tiêu)")
        return False, None

    print("  ✅ approach_shelf OK")

    # Truyền tầng như main.py — vùng quét dịch theo tầng (config.ROI_Y_CENTER)
    label_l, label_r = vision.classify_pair(tier)
    print(f"  classify_pair: trái={label_l}, phải={label_r}")
    if label_l is None or label_r is None:
        print("  ❌ classify_pair không đủ 2 kiện")
        m.retreat_from_shelf()
        return False, None
    print("  ✅ classify_pair OK")
    print("  ⚠ KIỂM BẰNG MẮT: nhãn TRÁI/PHẢI ở trên có khớp kiện thật trên càng "
          "trái/phải không? Lệch = cả 2 kiện đi nhầm nhà máy mà log vẫn báo OK.")

    # Luồng THẬT của main.py: nâng ngang tầng → LUỒN càng vào pallet (IR dẫn) →
    # nhấc bổng → xác nhận. Gọi lift.pickup() ở đây là sai: hàm đó nâng tại chỗ,
    # không tiến vào, nên chỉ chạy được khi người test tự tay đặt càng vào pallet.
    if not insert_and_lift_once(m, lift, tier, require_both=True):
        print("  ❌ BỐC HÀNG THẤT BẠI (luồn càng hoặc IR không xác nhận)")
        print("     Kiểm: càng có thẳng hàng khe pallet không? APPROACH_DISTANCE "
              "(vị trí chờ) có quá gần/xa không?")
        # ⚠️ LÙI RA TRƯỚC rồi mới hạ càng. Lúc này càng đang NẰM TRONG khe pallet
        # (robot còn cách kệ vài cm) — hạ càng ngay tại đó là kéo càng xuống trong
        # lòng khe, vướng đáy khe hoặc mép kệ, ghì motor và có thể lôi cả pallet theo.
        # main.py cũng lùi trước: `_insert_and_lift()` xong là `_retreat_from_shelf()`
        # chạy NGAY, bất kể thành hay bại. Để test lệch khỏi luồng thật là mất chính
        # cái giá trị mà test_smoke sinh ra để có.
        m.retreat_from_shelf()
        lift.go_to_level(0)
        return False, None
    print("  ✅ bốc hàng OK (nâng → luồn → nhấc, IR xác nhận)")

    if not m.retreat_from_shelf():
        print("  ⚠ retreat timeout (vẫn coi pickup OK)")
    else:
        print("  ✅ retreat OK")
    return True, (label_l, label_r)


# ==========================================================
# SMOKE 3 — Thả từng càng (khớp ĐÚNG hành vi main.py)
# ==========================================================

def smoke_drop_single_side(lift: Lift, **_):
    """Mô phỏng _drop_single_side() + DROP_SECOND của main.py.

    Điểm quan trọng: main.py LUÔN nâng lại / gập càng, KỂ CẢ khi IR không xác nhận —
    nếu chỉ nâng khi IR OK thì càng sẽ cạ sàn lúc robot lùi và chạy tiếp. Smoke phải
    làm y hệt, nếu không sẽ không bao giờ test được nhánh "IR fail".
    """
    print("\n[SMOKE 3] Thả từng càng — 2 kiện đi 2 nhà máy khác nhau")
    _pause("Robot đang mang 2 kiện — đặt trước điểm thả thử")

    side = _ask("Thả càng nào trước? (left/right) [left]: ", "left")
    if side not in ("left", "right"):
        print("  Lựa chọn không hợp lệ.")
        return False, None

    # Chuỗi thả ở control/handling.py — CÙNG hàm main.py gọi, nên không thể lệch
    dropped = drop_side(lift, side, last=False)
    print(f"  drop_side({side}, last=False): "
          f"{'✅ IR xác nhận đã rời càng' if dropped else '❌ IR vẫn thấy pallet / lỗi đọc'}")
    print(f"  ✅ đã nâng lại càng {side} — chạy LUÔN dù IR {'OK' if dropped else 'FAIL'}")
    if not dropped:
        print("  ⚠ main.py sẽ KHÔNG cộng điểm kiện này (packages_delivered chỉ tăng khi IR xác nhận)")

    other = "right" if side == "left" else "left"
    if _ask(f"Thả nốt càng {other} + gập càng? (y/N): ") != "y":
        return dropped, None

    dropped2 = drop_side(lift, other, last=True)
    print(f"  drop_side({other}, last=True): {'✅' if dropped2 else '❌'}")
    print("  ✅ đã gập càng — cả 2 càng về sàn, sẵn sàng di chuyển")
    return dropped and dropped2, None


# ==========================================================
# SMOKE 4 — NV2
# ==========================================================

def smoke_nv2_pickup(m: Motion, lift: Lift, **_):
    print("\n[SMOKE 4] NV2 — nhấc 1 kiện hàng rời (require_both=False)")
    _pause("Đặt robot trước Kệ 4 / kho hàng rời")

    if not m.approach_shelf():
        print("  ❌ approach THẤT BẠI")
        return False, None
    ok = insert_and_lift_once(m, lift, tier=1, require_both=False)
    print(f"  pickup NV2: {'✅' if ok else '❌'}")
    m.retreat_from_shelf()
    return ok, None


# ==========================================================
# SMOKE 5 — MỘT LƯỢT ĐẦY ĐỦ (kịch bản calibrate quan trọng nhất)
# ==========================================================

def smoke_full_lap(m: Motion, lift: Lift, vision: Vision, **_):
    """Kệ 3 T1 → giao 2 nhà máy → quay về Kệ 3 T2.

    Đây là kịch bản duy nhất chạy qua ĐỦ 3 loại tuyến vừa viết lại:
    kệ→nhà máy, nhà máy→nhà máy, nhà máy→kệ. Cũng là chỗ mà bảng route tĩnh cũ sai
    9/12 trường hợp — bắt buộc chạy trước khi tin vào bản đồ.
    """
    print("\n[SMOKE 5] MỘT LƯỢT ĐẦY ĐỦ — pickup → giao 2 nhà máy → quay về lấy tầng 2")
    print(f"  Nửa sân đang dùng: nhà máy cùng hàng ô xuất phát = "
          f"{nav.FACTORY_AT_START_ROW.upper()}")
    print("  ⚠ Sai nửa sân = giao nhầm nhà máy mà không có báo lỗi nào.")

    ok, pose = smoke_exit_and_navigate(m)
    if not ok:
        return False, None

    ok, labels = smoke_pickup_cycle(m, lift, vision, tier=1)
    if not ok:
        return False, None
    label_l, label_r = labels

    # --- Chọn thứ tự giao giống _plan_delivery() của main.py ---
    if label_l == label_r:
        queue = [label_l]
        print(f"\n  2 kiện cùng loại ({label_l}) — giao 1 điểm, thả cả 2 càng")
    else:
        def total(a, b):
            t1, t2 = nav.FACTORY_TERMINAL[a], nav.FACTORY_TERMINAL[b]
            return (nav.route_cost(pose, t1)
                    + nav.route_cost(nav.pose_at(t1), t2)
                    + nav.route_cost(nav.pose_at(t2), "SHELF0"))
        queue = ([label_l, label_r] if total(label_l, label_r) <= total(label_r, label_l)
                 else [label_r, label_l])
        print(f"\n  Thứ tự giao tối ưu: {queue[0]} → {queue[1]}")

    carried = [label_l, label_r]
    cur_pose = pose

    for i, label in enumerate(queue, 1):
        goal = nav.FACTORY_TERMINAL[label]
        print(f"\n  --- Giao kiện {i}/{len(queue)}: {label} ---")
        ok, cur_pose = _run(m, goal, cur_pose)
        if not ok:
            print("  ⚠ Navigation lệch — main.py vẫn thử hạ. Dừng smoke ở đây để xem xét.")
            return False, None

        if not m.approach_shelf():
            print("  ⚠ Không tiếp cận được điểm thả (main.py sẽ thử lại 1 lần rồi thả tại chỗ)")

        if len(queue) == 1:
            dropped = drop_both(lift)
            print(f"  drop_both(): {'✅' if dropped else '❌'}")
        else:
            side = "left" if carried[0] == label else "right"
            last = i >= len(queue)          # kiện cuối → gập càng, còn nữa → nâng lại
            dropped = drop_side(lift, side, last=last)
            print(f"  drop_side({side}, last={last}): {'✅' if dropped else '❌'}"
                  f" — đã {'gập càng' if last else 'nâng lại càng'}")
        m.retreat_from_shelf()

    # --- Quay về kho lấy TẦNG 2 cùng kệ ---
    print("\n  --- Quay về Kệ 3 để lấy tầng 2 ---")
    ok, cur_pose = _run(m, "SHELF0", cur_pose)
    if not ok:
        print("  ❌ Quay về kho THẤT BẠI")
        return False, None

    print("\n  ✅ HOÀN TẤT 1 lượt đầy đủ.")
    print("  Kiểm bằng mắt: robot có đang đứng ĐÚNG trước Kệ 3, quay mặt vào kệ không?")
    if _ask("  Chạy tiếp pickup tầng 2 để khép vòng? (y/N): ") == "y":
        return smoke_pickup_cycle(m, lift, vision, tier=2)
    return True, None


# ==========================================================
# SMOKE 6 — Chặn chạy mù của approach_shelf
# ==========================================================

def smoke_approach_blind_guard(m: Motion, **_):
    """Bỏ vật chắn ra → approach_shelf phải DỪNG sớm, không lao đi hết timeout."""
    print("\n[SMOKE 6] Chặn chạy mù khi siêu âm không thấy gì")
    print(f"  approach_shelf() phải dừng sau ~{config.APPROACH_BLIND_TIMEOUT}s nếu")
    print(f"  không đo được vật nào trong {config.APPROACH_DETECT_DISTANCE}cm.")
    print("  ⚠ Kê robot lên đế hoặc để trống ÍT NHẤT 1m phía trước.")
    _pause("Dọn trống phía trước robot (KHÔNG có vật trong tầm)")

    t0 = time.time()
    ok = m.approach_shelf()
    elapsed = time.time() - t0

    print(f"  Kết quả: {'ĐÃ ĐẾN (?!)' if ok else 'dừng an toàn'} sau {elapsed:.2f}s")
    if ok:
        print("  ❌ Báo 'đã đến' dù không có gì phía trước — kiểm lại siêu âm")
    elif elapsed <= config.APPROACH_BLIND_TIMEOUT + 0.5:
        print("  ✅ Dừng đúng lúc — robot sẽ không lao ra khỏi sa bàn khi mất echo")
    else:
        print(f"  ❌ Chạy quá lâu ({elapsed:.2f}s) — chặn chạy mù KHÔNG hoạt động")
    return not ok, None


# ==========================================================

def smoke_task2_full(m: Motion, lift: Lift, **_):
    """NV2 ĐẦY ĐỦ: nhà máy cuối → Kệ 4 → nhấc hàng rời → nhà máy liên hợp → thả.

    NV2 chỉ 30 điểm nhưng là 30 điểm mất trắng nếu chưa từng chạy thử — và nó chỉ
    được phép làm SAU khi xong 100% NV1, nên trong trận thật hầu như không có cơ hội
    tập. Phải tách ra chạy riêng.
    """
    print("\n[SMOKE 7] NHIỆM VỤ 2 đầy đủ — Kệ 4 → nhà máy liên hợp")
    print("  Đặt 1 kiện hàng rời trên Kệ 4.")

    start = _ask("  Robot đang đứng ở nhà máy nào? "
                 "(foxconn/amkor/hana_micron/samsung) [foxconn]: ", "foxconn")
    if start not in nav.FACTORY_TERMINAL:
        print(f"  Tên không hợp lệ. Hợp lệ: {', '.join(nav.FACTORY_TERMINAL)}")
        return False, None
    pose = nav.pose_at(nav.FACTORY_TERMINAL[start])
    _pause(f"Đặt robot tại nhà máy {start}, quay mặt vào khu nhà máy")

    print("\n  --- Đi tới Kệ 4 (kho hàng rời) ---")
    ok, pose = _run(m, nav.LOOSE_TERMINAL, pose)
    if not ok:
        return False, None

    print("\n  --- Nhấc hàng rời (chỉ cần 1 IR) ---")
    if not m.approach_shelf():
        print("  ❌ Không tiếp cận được Kệ 4")
        return False, None
    if not insert_and_lift_once(m, lift, tier=1, require_both=False):
        print("  ❌ pickup NV2 THẤT BẠI")
        m.retreat_from_shelf()
        return False, None
    print("  ✅ pickup NV2 OK")
    m.retreat_from_shelf()

    print("\n  --- Đi tới nhà máy liên hợp ---")
    ok, pose = _run(m, nav.JOINT_TERMINAL, pose)
    if not ok:
        return False, None

    print("\n  --- Thả tại nhà máy liên hợp ---")
    if not m.approach_shelf():
        print("  ⚠ Không tiếp cận được — vẫn thả tại chỗ (giống main.py)")
    dropped = lift.dropoff()
    print(f"  dropoff(): {'✅ NHIỆM VỤ 2 HOÀN THÀNH (+30 điểm)' if dropped else '❌ IR vẫn thấy pallet'}")
    m.retreat_from_shelf()
    return dropped, None


SMOKES = {
    "1": ("Xuất phát: exit start → dò nửa sân → Kệ 3", smoke_exit_and_navigate),
    "2": ("Pickup 1 lượt (approach + classify_pair + nâng)", smoke_pickup_cycle),
    "3": ("Thả từng càng + nâng lại / gập càng", smoke_drop_single_side),
    "4": ("NV2 — chỉ nhấc hàng rời", smoke_nv2_pickup),
    "5": ("★ MỘT LƯỢT ĐẦY ĐỦ: pickup → giao 2 NM → quay về tầng 2", smoke_full_lap),
    "6": ("Chặn chạy mù của approach_shelf", smoke_approach_blind_guard),
    "7": ("NHIỆM VỤ 2 đầy đủ: Kệ 4 → nhà máy liên hợp", smoke_task2_full),
}

# Smoke nào cần camera — tránh khởi tạo Vision (mất ~2s) khi không dùng
NEEDS_VISION = {"2", "5"}


def main():
    print("=" * 60)
    print("SMOKE TEST TÍCH HỢP — Bảng O2")
    print("=" * 60)
    print(f"\n{nav.board_summary()}")

    print("\nChọn smoke test:")
    for k, (name, _) in SMOKES.items():
        print(f"  {k}. {name}")

    choice = input(f"\nNhập số (1-{len(SMOKES)}): ").strip()
    if choice not in SMOKES:
        print("Lựa chọn không hợp lệ.")
        return

    m = Motion()
    lift = Lift()
    vision = Vision() if choice in NEEDS_VISION else None

    try:
        SMOKES[choice][1](m=m, lift=lift, vision=vision)
    except KeyboardInterrupt:
        print("\n\nDừng bởi người dùng.")
    finally:
        m.stop()
        m.cleanup()
        lift.cleanup()
        if vision is not None:
            vision.cleanup()
        reset_mcp3008_bus()
        print("\nĐã cleanup.")


if __name__ == "__main__":
    main()
