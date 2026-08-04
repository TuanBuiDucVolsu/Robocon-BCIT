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

import logging
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



def _pause(msg: str):
    input(f"\n  {msg}\n  Nhấn Enter để tiếp tục...")


def _ask(msg: str, default: str = "") -> str:
    return input(f"  {msg}").strip().lower() or default


def _hoi_tang(mac_dinh: int = 1) -> int:
    """Hỏi lấy hàng ở TẦNG nào. Sai tầng thì hỏng im lặng ở HAI chỗ cùng lúc.

    1. Càng nâng lên sai độ cao → luồn trượt ra ngoài khe pallet, IR không báo.
    2. Vùng quét camera DỊCH THEO TẦNG (config.ROI_Y_CENTER) — soi nhầm tầng thì
       classify_pair vẫn trả về nhãn, chỉ là nhãn của kiện tầng kia. Không có tín
       hiệu lỗi nào; log vẫn ✅.
    """
    while True:
        tra_loi = _ask(f"Lấy hàng ở TẦNG nào? (1/2) [{mac_dinh}]: ", str(mac_dinh))
        if tra_loi in ("1", "2"):
            tang = int(tra_loi)
            print(f"  → Tầng {tang}. Kiểm: kệ CÓ 2 kiện ở tầng {tang} chứ?")
            return tang
        print("  Chỉ nhận 1 hoặc 2.")


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
# SMOKE 1 — Xuất phát: exit start → [dò nửa sân nếu bật] → vào Kệ 3
# ==========================================================

def smoke_exit_and_navigate(m: Motion, **_):
    """Đúng thứ tự main.py: START → DETECT_SIDE → NAVIGATE_TO_SHELF."""
    buoc_do = "→ dò nửa sân " if getattr(config, "BOARD_AUTO_DETECT", False) else ""
    print(f"\n[SMOKE 1] Xuất phát {buoc_do}→ Kệ 3")
    if not buoc_do:
        print("  (BOARD_AUTO_DETECT=False — bỏ bước xoay phải dò nhánh, đi thẳng ra kệ)")
    print("  Đặt robot trong ô start, quay mặt về phía Kệ 3.")
    _pause("Sẵn sàng?")

    # ⚠️ DỌN TRẠNG THÁI CÕNG HÀNG TRƯỚC MỖI LƯỢT. Menu smoke dùng CHUNG một đối
    # tượng Motion cho mọi lần chạy, nên lượt trước hỏng giữa chừng lúc đang cõng
    # hàng là cờ kẹt True — lượt sau advance BỎ QUA SIÊU ÂM, đi tới hết line và
    # ĐÂM VÀO KỆ. main.py không dính vì _reset_for_new_run() dọn sẵn.
    m.dang_cong_hang = False
    m.xung_da_luon = 0

    if not m.exit_start_zone():
        print("  ❌ exit_start_zone THẤT BẠI")
        return False, nav.START_POSE
    print("  ✅ exit_start_zone OK")
    pose = nav.pose_sau_xuat_phat(getattr(m, "tren_giao_lo_dau", False) is True)
    if pose != nav.START_POSE:
        print("     (căn giữa đã chạy tới C0R0 — route bỏ bớt 1 giao lộ)")

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

def smoke_pickup_cycle(m: Motion, lift: Lift, vision: Vision, tier: int = 1,
                       doc_lap: bool = True, **_):
    print(f"\n[SMOKE 2] Pickup tầng {tier} (classify_pair → nâng → luồn → lùi)")
    if doc_lap:
        _pause(f"Đặt robot trước kệ có 2 kiện ở tầng {tier}, càng đang ở sàn")
    else:
        # Gọi từ bài LỚN HƠN (option 5): robot vừa TỰ LÁI tới đây. In "đặt robot
        # trước kệ" ở đây là gây rối — người test tưởng phải bê robot.
        _pause(f"Robot đã TỰ tới trước kệ. Kiểm: có thẳng hàng với kệ không, "
               f"có 2 kiện ở tầng {tier} không")

    # KHÔNG tiếp cận thêm — xem chú thích ở main._handle_pickup_pair.
    print("  (bỏ bước tiếp cận: advance đã dừng ở ~20cm, IR trên càng dẫn nốt)")

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
    # Dừng sau MỖI bước để kiểm bằng mắt. Thứ tự đúng là: nâng càng → tiến → nhấc.
    # Thấy robot TIẾN rồi mới nâng càng nghĩa là bước nâng không chạy (_current_level
    # đang tin sai) — và đó chính là lúc càng chui vào gầm kệ thay vì vào khe pallet.
    def _buoc(ten, mo_ta):
        print(f"\n  ── [{ten}] {mo_ta}")
        if ten == "raise":
            print("     KIỂM BẰNG MẮT trước khi cho tiến:")
            print("       • Càng có ĐANG NGANG khe pallet không (không phải ở sàn)?")
            print("       • 2 càng có bằng nhau không?")
            print("       • Càng có thẳng hàng với 2 khe của pallet không?")
            input("     Enter để cho robot TIẾN vào (Ctrl+C để dừng)...")

    # Cờ phải bật TRƯỚC bước lùi ngay sau đây — lùi cũng bị kiện chắn siêu âm.
    # main.py đặt carried_labels trước _insert_and_lift() nên cũng đúng thứ tự này.
    m.dang_cong_hang = True
    if not insert_and_lift_once(m, lift, tier, require_both=True, on_step=_buoc):
        m.dang_cong_hang = False
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

    if not doc_lap:
        # Được gọi từ bài LỚN HƠN (option 5) — kiện phải Ở NGUYÊN trên càng để chở
        # đi giao. Hỏi "hạ càng?" ở đây là bẫy: mặc định CÓ, người test bấm Enter
        # theo quán tính là thả cả 2 kiện xuống sàn rồi robot đi giao tay không.
        print(f"  → Giữ càng ở tầng {tier}, kiện vẫn trên càng (còn phải chở đi giao).")
        return True, (label_l, label_r)

    # ⚠️ main.py KHÔNG hạ càng ở đây — nó chở kiện đi giao, càng phải giữ nguyên độ
    # cao tầng. Nhưng smoke 2 dừng tại chỗ, để càng treo ở tầng 1/2 thì lượt chạy sau
    # bắt đầu từ trạng thái SAI: không có limit switch nên Lift chỉ tin `_current_level`,
    # mà người test lại hay tắt script rồi chạy lại. Hỏi để người quyết, mặc định HẠ.
    print(f"\n  Càng đang ở TẦNG {tier} (kiện vẫn trên càng).")
    print("  main.py giữ nguyên độ cao này để chở đi giao — smoke thì nên hạ về sàn")
    print("  trước khi chạy lượt tiếp, không thì trạng thái càng lệch.")
    if _ask("  Hạ càng về sàn? (Y/n): ", "y") != "n":
        released = drop_both(lift)
        print(f"  dropoff(): {'✅ IR xác nhận kiện đã rời càng' if released else '❌ IR VẪN thấy pallet'}")
        if not released:
            print("     Kiện có thể còn mắc trên càng — gỡ tay trước khi chạy lượt sau.")
        print("  → Càng đã về sàn, _current_level = 0. Sẵn sàng chạy lại.")
    else:
        print("  → Giữ càng ở tầng. Nhớ hạ trước khi chạy lượt khác.")
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
    # Bài này là bài BÀN THỬ — robot đứng yên, không có gì để lùi. Truyền hàm rỗng
    # cho tường minh; để trống thì drop_side() cảnh báo (đúng, vì trên sa bàn thật
    # thiếu bước lùi là xúc lại kiện vừa thả).
    dropped = drop_side(lift, side, last=False, lui=lambda: None)
    print(f"  drop_side({side}, last=False): "
          f"{'✅ IR xác nhận đã rời càng' if dropped else '❌ IR vẫn thấy pallet / lỗi đọc'}")
    print(f"  ✅ đã nâng lại càng {side} — chạy LUÔN dù IR {'OK' if dropped else 'FAIL'}")
    if not dropped:
        print("  ⚠ main.py sẽ KHÔNG cộng điểm kiện này (packages_delivered chỉ tăng khi IR xác nhận)")

    other = "right" if side == "left" else "left"
    if _ask(f"Thả nốt càng {other} + gập càng? (y/N): ") != "y":
        return dropped, None

    dropped2 = drop_side(lift, other, last=True, lui=lambda: None)
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
    """Kệ 3 (tầng CHỌN được) → giao 2 nhà máy → quay về Kệ 3 lấy tầng kia.

    Đây là kịch bản duy nhất chạy qua ĐỦ 3 loại tuyến vừa viết lại:
    kệ→nhà máy, nhà máy→nhà máy, nhà máy→kệ. Cũng là chỗ mà bảng route tĩnh cũ sai
    9/12 trường hợp — bắt buộc chạy trước khi tin vào bản đồ.
    """
    print("\n[SMOKE 5] MỘT LƯỢT ĐẦY ĐỦ — pickup → giao 2 nhà máy → quay về lấy tầng kia")
    print(f"  Nửa sân đang dùng: nhà máy cùng hàng ô xuất phát = "
          f"{nav.FACTORY_AT_START_ROW.upper()}")
    print("  ⚠ Sai nửa sân = giao nhầm nhà máy mà không có báo lỗi nào.")

    tang = _hoi_tang()
    tang_sau = 2 if tang == 1 else 1

    ok, pose = smoke_exit_and_navigate(m)
    if not ok:
        return False, None

    ok, labels = smoke_pickup_cycle(m, lift, vision, tier=tang, doc_lap=False)
    if not ok:
        return False, None
    label_l, label_r = labels
    m.dang_cong_hang = True          # như main._dat_co_cong_hang() (đã bật từ pickup)

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

        # Không tiếp cận bằng siêu âm khi đang cõng hàng — kiện trên càng chắn
        # chùm sóng (xem main._dat_co_cong_hang). advance đã dừng ở cuối line.
        print("  (bỏ bước tiếp cận điểm thả: đang cõng hàng, siêu âm bị kiện chắn)")

        if len(queue) == 1:
            dropped = drop_both(lift)
            print(f"  drop_both(): {'✅' if dropped else '❌'}")
        else:
            side = "left" if carried[0] == label else "right"
            last = i >= len(queue)          # kiện cuối → gập càng, còn nữa → nâng lại
            # LÙI nằm GIỮA thả và nâng càng — xem control/handling.drop_side.
            dropped = drop_side(lift, side, last=last,
                                lui=lambda: m.retreat_from_shelf())
            print(f"  drop_side({side}, last={last}): {'✅' if dropped else '❌'}"
                  f" — đã lùi ra rồi {'gập càng' if last else 'nâng lại càng'}")
            continue
        m.retreat_from_shelf()

    m.dang_cong_hang = False         # đã thả hết, siêu âm dùng lại được

    # --- Quay về kho lấy TẦNG CÒN LẠI cùng kệ ---
    print(f"\n  --- Quay về Kệ 3 để lấy tầng {tang_sau} ---")
    ok, cur_pose = _run(m, "SHELF0", cur_pose)
    if not ok:
        print("  ❌ Quay về kho THẤT BẠI")
        return False, None

    print("\n  ✅ HOÀN TẤT 1 lượt đầy đủ.")
    print("  Kiểm bằng mắt: robot có đang đứng ĐÚNG trước Kệ 3, quay mặt vào kệ không?")
    if _ask(f"  Chạy tiếp pickup tầng {tang_sau} để khép vòng? (y/N): ") == "y":
        return smoke_pickup_cycle(m, lift, vision, tier=tang_sau)
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


# ==========================================================
# SMOKE 8 — Đường dài, KHÔNG bốc hàng
# ==========================================================

def smoke_route_to_samsung(m: Motion, **_):
    """Ô xuất phát → trước Kệ 3 → lùi ra → nhà máy Samsung. KHÔNG bốc hàng.

    Vì sao tách thành bài riêng: đây là ĐƯỜNG ĐI dài nhất mà không đụng tới lift hay
    camera. Bốc hàng hỏng thì mọi bài có pickup đều dừng ở đó và ta không bao giờ
    chạy tới phần điều hướng phía sau — mà phần đó mới là chỗ dùng những hằng số
    chưa ai đo: bù PWM chiều LÙI, TURN_TIME chiều PHẢI.

    Tuyến Kệ 3 → Samsung là tuyến ĐẮT NHẤT trong 12 tuyến kệ→nhà máy:
        LÙI 1 giao lộ → xoay phải → tiến 2 giao lộ → xoay phải → tiến 1 → vào điểm cuối
    Hai lần xoay PHẢI và một lần lùi — đúng ba thứ chưa xác nhận, cộng dồn sai số.

    ⚠️ Samsung nằm hàng nào là do NỬA SÂN quyết định. Bài này in rõ ra để kiểm bằng
    mắt: đi nhầm nhà máy là lỗi DUY NHẤT không có tín hiệu báo nào.
    """
    hang = "R4 (xa ô xuất phát nhất)" if nav.FACTORY_AT_START_ROW == "foxconn" else "R0 (CÙNG hàng ô xuất phát)"
    print("\n[SMOKE 8] Ô xuất phát → trước Kệ 3 → lùi ra → Samsung (KHÔNG bốc hàng)")
    print(f"  Nửa sân: nhà máy cùng hàng ô xuất phát = {nav.FACTORY_AT_START_ROW.upper()}")
    print(f"  → SAMSUNG nằm ở hàng {hang}")
    print("  ⚠ NHÌN LÊN TƯỜNG XÁC NHẬN trước khi chạy. Sai nửa sân = robot đi tới")
    print("    đúng vị trí nó tin là Samsung, và không có gì báo lỗi.")
    if _ask("  Đúng chưa? (y/N): ") != "y":
        print("  Dừng. Chạy lại và chọn nửa sân khác ở đầu phiên.")
        return False, None

    print("  Đặt robot trong ô start, quay mặt về phía Kệ 3.")
    _pause("Sẵn sàng?")

    # --- 1. Rời ô xuất phát ---
    if not m.exit_start_zone():
        print("  ❌ [1/5] exit_start_zone THẤT BẠI")
        return False, nav.START_POSE
    print("  ✅ [1/5] rời ô xuất phát")
    pose = nav.pose_sau_xuat_phat(getattr(m, "tren_giao_lo_dau", False) is True)
    if pose != nav.START_POSE:
        print("     (căn giữa đã chạy tới C0R0 — route bỏ bớt 1 giao lộ)")

    # --- 2. Tới Kệ 3 ---
    ok, pose = _run(m, "SHELF0", pose)
    if not ok:
        print("  ❌ [2/5] không tới được Kệ 3")
        return False, pose
    print("  ✅ [2/5] tới Kệ 3")

    # --- 3. Tiếp cận kệ (như thật, chỉ không bốc) ---
    if not m.approach_shelf():
        print("  ⚠ [3/5] approach_shelf thất bại — vẫn chạy tiếp để xem phần điều hướng")
    else:
        print("  ✅ [3/5] đứng trước kệ")
    print(f"     ĐO TAY: cách kệ bao nhiêu? (kỳ vọng {config.APPROACH_DISTANCE}cm)")
    _pause("Đo xong nhấn Enter để lùi ra và đi Samsung")

    # --- 4. Lùi ra (main.py cũng lùi ngay sau khi bốc, dù thành hay bại) ---
    if not m.retreat_from_shelf():
        print("  ⚠ [4/5] retreat timeout")
    else:
        print("  ✅ [4/5] lùi ra khỏi kệ")

    # --- 5. Kệ 3 → Samsung ---
    print("\n  --- [5/5] Kệ 3 → Samsung ---")
    print("  ⚠ Đoạn này dùng 3 hằng số CHƯA xác nhận: bù PWM chiều LÙI,")
    print("    REVERSE_RECENTER_TIME, và TURN_TIME chiều PHẢI (mới đo chiều trái).")
    ok, pose = _run(m, nav.FACTORY_TERMINAL["samsung"], pose)
    if not ok:
        print("  ❌ [5/5] không tới được Samsung")
        print("     Gãy ở lệnh nào? Xem log. Lùi → option 15/18 của test_motion.")
        print("     Xoay → option 10. Bám line → option 7.")
        return False, pose

    print("  ✅ [5/5] tới khu Samsung")
    print("\n  KIỂM BẰNG MẮT — cả ba đều phải đúng:")
    print("    1. Robot có đang ở ĐÚNG khu SAMSUNG không (nhìn ảnh in trên tường)?")
    print("    2. Robot có quay mặt VÀO nhà máy không?")
    print("    3. Lệch ngang so với tâm khu ≤ 3cm?")
    print("  Sai nhà máy = chọn sai nửa sân. Đúng nhà máy nhưng lệch = tích luỹ")
    print("  sai số xoay/lùi, quay lại test_motion option 18.")
    return True, pose


SMOKES = {
    "1": ("Xuất phát: exit start → Kệ 3 (dò nửa sân nếu BOARD_AUTO_DETECT)",
          smoke_exit_and_navigate),
    "2": ("Pickup 1 lượt (approach + classify_pair + nâng)", smoke_pickup_cycle),
    "3": ("Thả từng càng + nâng lại / gập càng", smoke_drop_single_side),
    "4": ("NV2 — chỉ nhấc hàng rời", smoke_nv2_pickup),
    "5": ("★ MỘT LƯỢT ĐẦY ĐỦ: pickup (chọn tầng) → giao 2 NM → quay về tầng kia",
          smoke_full_lap),
    "6": ("Chặn chạy mù của approach_shelf", smoke_approach_blind_guard),
    "7": ("NHIỆM VỤ 2 đầy đủ: Kệ 4 → nhà máy liên hợp", smoke_task2_full),
    "8": ("Đường dài KHÔNG bốc hàng: xuất phát → trước Kệ 3 → lùi → Samsung",
          smoke_route_to_samsung),
}

# Smoke nào cần camera — tránh khởi tạo Vision (mất ~2s) khi không dùng
NEEDS_VISION = {"2", "5"}


def _ask_board_side() -> str:
    """HỎI đang ở nửa sân nào, thay vì bắt robot tự dò.

    Thi đấu thì CÔNG TẮC GẠT (GPIO 12) quyết định thứ tự nhà máy. Trên bàn test thì
    công tắc có thể chưa lắp hoặc gạt sai, mà đặt sai KHÔNG có tín hiệu báo lỗi nào
    — IR vẫn báo thả thành công, log vẫn xanh, chỉ mất sạch điểm. Một câu hỏi rẻ
    hơn nhiều so với chạy hết một lượt rồi mới biết.

    Đây KHÔNG phải thứ mà `probe_side_branch()` dò được: bước dò chỉ kiểm chiều
    trái/phải, còn thứ tự nhà máy thì hai nửa giống hệt nhau qua cảm biến line.
    """
    hien = nav.FACTORY_AT_START_ROW
    print("\n" + "=" * 62)
    print("  ĐỨNG Ở Ô XUẤT PHÁT, NHÌN SANG TƯỜNG GIỮA SÂN.")
    print("  Khu nhà máy NGANG TẦM ô xuất phát (cùng hàng với bạn) là khu nào?")
    print("=" * 62)
    print("  Đối chiếu CẢ CỤM cho chắc — thứ tự từ chỗ bạn đứng đi RA XA:")
    print()
    print("                        chọn 1        chọn 2")
    print("                       ─────────     ─────────")
    print("     ngang tầm bạn  →   FOXCONN       SAMSUNG")
    print("                        Amkor         Hana Micron")
    print("     giữa sân       →   Liên hợp      Liên hợp      (dùng chung 2 đội)")
    print("                        Hana Micron   Amkor")
    print("     xa nhất        →   SAMSUNG       FOXCONN")
    print()
    print("  Liên hợp LUÔN ở giữa — dùng nó làm mốc nếu nhìn không rõ hai đầu.")
    tra = input(f"  Chọn [1/2, Enter = giữ {hien.upper()}]: ").strip()
    side = {"1": "foxconn", "2": "samsung"}.get(tra, hien)
    if side != nav.FACTORY_AT_START_ROW:
        nav.set_factory_order(side)
        print(f"  → Đã nạp lại bản đồ: nhà máy cùng hàng ô xuất phát = {side.upper()}")
    else:
        print(f"  → Giữ nguyên: nhà máy cùng hàng ô xuất phát = {side.upper()}")
    return side


def main():
    print("=" * 60)
    print("SMOKE TEST TÍCH HỢP — Bảng O2")
    print("=" * 60)
    _ask_board_side()
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
