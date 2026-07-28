#!/usr/bin/env python3
"""
In TOÀN BỘ route mà bộ tìm đường (navigation.py) sinh ra, để đội cầm ra sa bàn
đối chiếu từng đoạn bằng mắt trước khi cho robot chạy thật.

    python3 -m tools.show_routes           # in tất cả
    python3 -m tools.show_routes SHELF0 F_samsung   # in 1 tuyến cụ thể

Cột "chi phí" là số quy đổi mà Dijkstra dùng để chọn tuyến (giao lộ + phạt xoay +
phạt đoạn line đứt), KHÔNG phải giây hay milimet.

Nếu một dòng nào đó KHÔNG khớp sa bàn thật → sửa BẢN ĐỒ trong navigation.py
(NODES / EDGES / TERMINALS), đừng sửa từng route: mọi route đều sinh ra từ bản đồ đó.
"""

import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

import config
import navigation as nav


def _line(src_name, dst, label):
    src = nav.pose_at(src_name) if src_name in nav.TERMINALS else src_name
    route, new_pose = nav.plan(src, dst)
    if route is None:
        print(f"  {label:<34} ❌ KHÔNG CÓ ĐƯỜNG")
        return
    cost = nav.route_cost(src, dst)
    print(f"  {label:<34} [{cost:>3}] {nav.route_to_text(route)}")


def show_all():
    print("\n" + "=" * 74)
    print(" " + nav.board_summary())
    print(" ⚠ KIỂM TRƯỚC MỖI TRẬN: đứng ở ô xuất phát nhìn sang tường giữa sân —")
    print("   cụm nhà máy CÙNG HÀNG ô xuất phát phải đúng là %s."
          % nav.FACTORY_AT_START_ROW.upper())
    print("   Sai thì sửa config.FACTORY_AT_START_ROW (robot KHÔNG tự dò được cái này).")
    if nav.MIRRORED:
        print(" ⚠ Bản đồ đang LẬT GƯƠNG chiều trái/phải.")
    if getattr(config, "BOARD_AUTO_DETECT", False):
        print(" Chiều trái/phải: robot tự dò đầu trận (state DETECT_SIDE, ~2-4s).")
        print("   Thử trên robot thật: python3 tests/test_motion.py → option 13")
    print("=" * 74)

    shelves = [("SHELF0", "Kệ3/R0"), ("SHELF1", "Kệ2/R2"), ("SHELF2", "Kệ1/R4")]
    factories = [(t, l) for l, t in nav.FACTORY_TERMINAL.items()]

    print("\n=== 1. XUẤT PHÁT ===")
    _line(nav.START_POSE, "SHELF0", "Ô start → Kệ 3")

    print("\n=== 2. KỆ → NHÀ MÁY (12 tuyến) ===")
    for st, sn in shelves:
        for ft, fl in factories:
            _line(st, ft, f"{sn} → {fl}")

    print("\n=== 3. NHÀ MÁY → KỆ, quay về kho (12 tuyến) ===")
    for ft, fl in factories:
        for st, sn in shelves:
            _line(ft, st, f"{fl} → {sn}")

    print("\n=== 4. GIỮA 2 NHÀ MÁY, giao kiện thứ 2 (12 tuyến) ===")
    for a, la in factories:
        for b, lb in factories:
            if a != b:
                _line(a, b, f"{la} → {lb}")

    print("\n=== 5. KỆ ↔ KỆ ===")
    _line("SHELF0", "SHELF1", "Kệ 3 → Kệ 2")
    _line("SHELF1", "SHELF2", "Kệ 2 → Kệ 1")
    _line("SHELF2", "SHELF0", "Kệ 1 → Kệ 3")

    print("\n=== 6. NHIỆM VỤ 2 ===")
    for ft, fl in factories:
        _line(ft, nav.LOOSE_TERMINAL, f"{fl} → Kệ 4 (hàng rời)")
    _line(nav.LOOSE_TERMINAL, nav.JOINT_TERMINAL, "Kệ 4 → Nhà máy liên hợp")

    print("\n=== 7. BẢN ĐỒ ĐANG DÙNG ===")
    print("  Giao lộ:", ", ".join(sorted(nav.NODES)))
    print("  Cạnh line:")
    for a, b, extra, note in nav.EDGES:
        phu = f" (+{extra} phạt)" if extra else ""
        print(f"    {a} ↔ {b}{phu}   — {note}")
    print("  ⚠ Hàng R2 (C0R2 ↔ C1R2) CỐ Ý không có cạnh: line đứt ~560mm ở vòng tròn "
          "ROBOCON giữa sân.")


def main():
    if len(sys.argv) == 3:
        _line(sys.argv[1], sys.argv[2], f"{sys.argv[1]} → {sys.argv[2]}")
        return
    show_all()


if __name__ == "__main__":
    main()
