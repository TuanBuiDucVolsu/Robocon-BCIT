#!/usr/bin/env python3
"""
Unit test cho tools/ — chạy trên PC, không cần GPIO.
  python3 tests/test_tools.py

Trọng tâm: `tools.measure_phases` đo thời gian bằng cách khớp REGEX với chuỗi log.
Chuỗi log nằm rải rác trong main.py / control/*.py và sẽ bị sửa theo thời gian —
sửa xong mà quên đổi regex thì tool im lặng trả "0 mẫu, dùng số mặc định", tức là
lặng lẽ quay về đoán mò đúng cái nó sinh ra để thay thế. Test dưới đây bóc mọi
chuỗi logger.* ra khỏi source rồi đối chiếu, nên hỏng là biết ngay.
"""

import ast
import os
import re
import statistics
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from tools.measure_phases import (ANOMALIES, RESULT_ELAPSED, RESULT_PACKAGES,
                                  SPANS, derive, parse_log, split_runs, summarize)

ROOT = os.path.join(os.path.dirname(__file__), "..")
SOURCES = ["main.py", "control/motion.py", "control/lift.py", "vision/vision.py",
           "navigation.py", "control/board_switch.py", "control/mcp3008_bus.py"]

# %-placeholder → giá trị mẫu, để dựng lại chuỗi log ĐÚNG như lúc chạy thật
_SPEC = re.compile(r"%[-+ #0]*[\d.]*([difsxX%])")
_SAMPLE = {"d": "7", "i": "7", "f": "4.2", "s": "trái", "x": "f", "X": "F", "%": "%"}


def _rendered_log_messages() -> list[str]:
    """Mọi chuỗi truyền vào logger.info/warning/error/... trong source, đã %-format."""
    out = []
    for rel in SOURCES:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("debug", "info", "warning", "error", "critical")
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                out.append(_SPEC.sub(lambda m: _SAMPLE[m.group(1)], node.args[0].value))
    return out


class TestPatternsMatchRealLogStrings(unittest.TestCase):
    """Mọi regex phải khớp một chuỗi log CÓ THẬT trong source."""

    @classmethod
    def setUpClass(cls):
        cls.msgs = _rendered_log_messages()

    def test_source_scan_found_messages(self):
        self.assertGreater(len(self.msgs), 100, "không bóc được chuỗi log — sai AST?")

    def test_every_span_pattern_matches_source(self):
        for spec in SPANS:
            for name, rx in (("start", spec.start), ("end", spec.end),
                             ("abort", spec.abort), ("cancel", spec.cancel)):
                if rx is None:      # end=NEXT_LINE, hoặc không khai báo abort/cancel
                    continue
                with self.subTest(span=spec.key, part=name):
                    self.assertTrue(
                        any(rx.search(m) for m in self.msgs),
                        f"{spec.key}.{name} = {rx.pattern!r} không khớp chuỗi log nào "
                        f"— log đã đổi, sửa lại tools/measure_phases.py")

    def test_every_anomaly_pattern_matches_source(self):
        for title, pattern in ANOMALIES:
            with self.subTest(anomaly=title):
                rx = re.compile(pattern)
                self.assertTrue(any(rx.search(m) for m in self.msgs),
                                f"phụ trội {title!r} không khớp chuỗi log nào")

    def test_result_patterns_match_source(self):
        for rx in (RESULT_PACKAGES, RESULT_ELAPSED):
            self.assertTrue(any(rx.search(m) for m in self.msgs), rx.pattern)


# ============================================================
# Round-trip: nhúng thời gian ĐÃ BIẾT vào log rồi đo lại
# ============================================================

TRUTH = dict(forward=1.80, reverse=2.30, turn=0.90, advance=1.50, approach=1.40,
             retreat=0.80, pickup=4.00, drop=2.20, raise_=0.70, scan=0.60)


def _build_log(laps: int = 3) -> str:
    clock = datetime(2026, 8, 8, 9, 0, 0)
    lines = []

    def log(msg, dt=0.01):
        nonlocal clock
        clock += timedelta(seconds=dt)
        lines.append(f"{clock:%Y-%m-%d %H:%M:%S},{clock.microsecond // 1000:03d} "
                     f"[INFO] x: {msg}")

    def go(n):
        for i in range(n):
            log(f"Đi đến giao lộ {i + 1}/{n}")
            log("Phát hiện giao lộ (active=5)", TRUTH["forward"])

    def back(n=1):
        for i in range(n):
            log(f"Lùi về giao lộ {i + 1}/{n} (speed=35%)")
            log("Phát hiện giao lộ (active=5)", TRUTH["reverse"])

    def turn(n):
        for _ in range(n):
            log("Xoay 90° phải")
            log("Dừng", TRUTH["turn"])

    def dock():
        log("Bám line tới hết line (advance, speed=40%)")
        log("Advance: đã hết line — dừng tại điểm cuối", TRUTH["advance"])
        log("Tiếp cận kệ 2 pha — mục tiêu 4.0cm (nhanh 60% → chậm 25% dưới 10.0cm)")
        log("Đã đến vị trí kệ — khoảng cách 3.8cm", TRUTH["approach"])

    def undock():
        log("Lùi ra khỏi kệ — mục tiêu 10.0cm")
        log("Đã lùi đủ xa — khoảng cách 10.4cm", TRUTH["retreat"])

    log("========== BẮT ĐẦU STATE MACHINE ==========", 0.1)
    for _ in range(laps):
        turn(2); go(2); dock()
        log("Nhận diện OK (lần 1): trái=samsung, phải=foxconn", TRUTH["scan"])
        log("Nhấc hàng tầng 1 — lần 1/2 (require_both=True)", 0.01)
        log("Xác nhận: CẢ 2 pallet trên càng", TRUTH["pickup"])
        undock()
        for side, other in (("TRÁI", "trái"), ("PHẢI", "phải")):
            back(); turn(1); go(3); dock()      # rút khỏi kệ bằng cách LÙI
            log(f"Đặt hàng — chỉ càng {side}", 0.01)
            log(f"Xác nhận: pallet {other} đã rời càng", TRUTH["drop"])
            log(f"Nâng lại càng {other} (0.75s)", 0.01)
            log("Dừng", TRUTH["raise_"])
            undock()
    log("Kiện hàng đã giao: 12/12 (trong 6 lượt nâng)", 0.1)
    log("Thời gian: 231.4/240s  (còn 8.6s)")
    return "\n".join(lines) + "\n"


class TestMeasureRoundTrip(unittest.TestCase):
    """Nhúng thời gian đã biết vào log → tool phải đo lại đúng con số đó."""

    @classmethod
    def setUpClass(cls):
        fd, cls.path = tempfile.mkstemp(prefix="fake_log_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_build_log())
        entries = parse_log(cls.path)
        cls.measured = summarize(entries)
        cls.params, cls.source = derive(cls.measured)

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.path)

    def test_every_span_found_samples(self):
        for spec in SPANS:
            with self.subTest(span=spec.key):
                samples, dropped = self.measured[spec.key]
                self.assertTrue(samples, f"{spec.key}: không ghép được cặp mốc nào")
                self.assertEqual(dropped, 0, f"{spec.key}: log sạch mà vẫn báo hỏng")

    def test_derived_params_match_injected_truth(self):
        expected = {
            "forward": TRUTH["forward"],
            "turn": TRUTH["turn"],
            # `reverse` không nằm trong 6 tham số của estimate_time (mô hình gộp lùi
            # vào forward), nhưng vẫn phải ĐO được để hiện lên bảng thời gian.

            "advance": TRUTH["advance"],
            # estimate_time gộp tiếp cận + lùi ra vào một tham số
            "approach": TRUTH["approach"] + TRUTH["retreat"],
            # chu kỳ nâng vs chu kỳ (hạ + nâng lại càng), lấy trung bình
            "lift": (TRUTH["pickup"] + TRUTH["drop"] + TRUTH["raise_"]) / 2,
            "scan": TRUTH["scan"],
        }
        for key, want in expected.items():
            with self.subTest(param=key):
                self.assertAlmostEqual(self.params[key], want, delta=0.05)
                self.assertIn("đo", self.source[key], f"{key} bị rơi về số mặc định")

    def test_reverse_hop_is_measured_separately_from_forward(self):
        """Lùi ra khỏi kệ là chi phí THẬT — không đo thì nó vô hình trong bảng giờ."""
        samples, dropped = self.measured["reverse"]
        self.assertTrue(samples, "không đo được chặng lùi")
        self.assertEqual(dropped, 0)
        self.assertAlmostEqual(statistics.median(samples), TRUTH["reverse"], delta=0.05)
        # ...và KHÔNG được lẫn vào mẫu của chặng tiến (2 chặng dùng chung dòng
        # "Phát hiện giao lộ" làm mốc kết thúc)
        fwd, _ = self.measured["forward"]
        self.assertAlmostEqual(statistics.median(fwd), TRUTH["forward"], delta=0.05)

    def test_drop_approach_is_not_counted_as_a_failed_scan(self):
        """'Đã đến vị trí kệ' dùng chung cho tiếp cận-để-quét và tiếp cận-để-thả."""
        samples, dropped = self.measured["scan"]
        self.assertEqual(len(samples), 3, "mỗi lượt đúng 1 lần quét")
        self.assertEqual(dropped, 0, "tiếp cận để THẢ không phải là quét hỏng")


class TestMeasureRobustness(unittest.TestCase):
    def test_garbage_lines_are_ignored(self):
        fd, path = tempfile.mkstemp(prefix="junk_log_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("Thu 8 Aug: khởi động robot\n"      # echo của scripts/start.sh
                    "Traceback (most recent call last):\n"
                    "    raise ValueError('x')\n")
            f.write(_build_log(laps=1))
        try:
            entries = parse_log(path)
            params, source = derive(summarize(entries))
            self.assertAlmostEqual(params["forward"], TRUTH["forward"], delta=0.05)
            self.assertIn("đo", source["forward"])
        finally:
            os.unlink(path)

    def test_empty_log_falls_back_to_defaults_not_zero(self):
        """Không có mẫu thì phải dùng số mặc định — KHÔNG được trả 0 giây."""
        params, source = derive(summarize([]))
        for key, value in params.items():
            with self.subTest(param=key):
                self.assertGreater(value, 0.0)
                self.assertEqual(source[key], "MẶC ĐỊNH")

    def test_runs_are_split_and_last_one_used(self):
        entries = parse_log_string(_build_log(laps=1) + _build_log(laps=2))
        runs = split_runs(entries)
        self.assertEqual(len(runs), 2)
        self.assertGreater(len(runs[1]), len(runs[0]), "lượt 2 dài hơn (2 lap)")


class TestDryRun(unittest.TestCase):
    """`tools.dry_run` chạy state machine THẬT — bản in phải khớp bản đồ thật."""

    @classmethod
    def setUpClass(cls):
        from tools import dry_run
        cls.mod = dry_run
        args = dry_run.argparse.Namespace(
            forward=2.5, turn=1.2, advance=2.0, approach=1.8,
            retreat=1.2, lift=5.1, scan=1.0, exit=2.0, probe=3.0, reverse=3.0)
        cls.rec = dry_run.Recorder(args)
        robot = dry_run.build_robot(dry_run.DEFAULT_SCENARIO, cls.rec)
        cls.blocks = dry_run.run(robot, cls.rec)
        cls.robot = robot

    def test_reaches_done_without_looping(self):
        self.assertNotIn("!! VÒNG LẶP", [b[0] for b in self.blocks],
                         "state machine không kết thúc — có vòng lặp")

    def test_delivers_all_twelve_packages(self):
        pkg = sum(p for _l, rows, _s, _t in self.blocks for *_r, p, _n in rows)
        self.assertEqual(pkg, config.TOTAL_PACKAGES_TASK1)
        self.assertEqual(self.robot.packages_delivered, config.TOTAL_PACKAGES_TASK1)

    def test_task2_is_reached_after_task1(self):
        labels = [b[0] for b in self.blocks]
        self.assertIn("TASK2_DROP", labels, "xong 12/12 kiện phải chuyển sang NV2")
        self.assertTrue(any(n for _l, rows, _s, _t in self.blocks
                            for *_r, n in rows), "NV2 phải được đánh dấu để tính 30đ")

    def test_every_move_follows_a_real_line(self):
        """`_step()` trả '?' khi không có line/điểm cuối — bản in không được có '?'."""
        for _label, rows, _s, _t in self.blocks:
            for kind, text, *_rest in rows:
                if kind == "đi":
                    self.assertNotIn("→ ?", text,
                                     f"bước đi vào chỗ không có line: {text}")

    def test_scenario_parser_rejects_bad_input(self):
        for bad in ("abc,foxconn", "samsung", "samsung,foxconn"):
            with self.subTest(value=bad):
                with self.assertRaises(SystemExit):
                    self.mod.parse_scenario(bad)

    def test_scenario_parser_accepts_six_valid_pairs(self):
        text = " ".join(f"{l},{r}" for l, r in self.mod.DEFAULT_SCENARIO)
        self.assertEqual(self.mod.parse_scenario(text), self.mod.DEFAULT_SCENARIO)


def parse_log_string(text: str):
    fd, path = tempfile.mkstemp(prefix="split_log_", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        return parse_log(path)
    finally:
        os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
