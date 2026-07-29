#!/usr/bin/env python3
"""
Rút 6 tham số của `tools.estimate_time` ra từ robot_log.txt — trả lời "worst case
giao được mấy kiện" bằng SỐ ĐO THẬT thay vì số đoán.

    python3 -m tools.measure_phases                    # lượt chạy GẦN NHẤT
    python3 -m tools.measure_phases --all              # gộp mọi lượt trong file
    python3 -m tools.measure_phases duong/dan/log.txt

VÌ SAO CÓ FILE NÀY: `estimate_time` nhân số lệnh trong route thật với 6 hằng số
(giây/giao lộ, giây/xoay...). Mặc định 6 số đó là ĐOÁN, nên kết luận "kịp/không kịp"
cũng chỉ là đoán. Đo tay bằng đồng hồ bấm thì vừa lâu vừa sai — trong khi robot_log.txt
đã có mốc thời gian mili-giây ở mọi chặng. Tool này đọc log, ghép cặp mốc bắt đầu/kết
thúc của từng chặng rồi lấy TRUNG VỊ (bỏ ngoại lai do retry).

Chạy thế nào để có log dùng được:
    bash scripts/practice.sh        → chạy 1 lượt thật trên sa bàn (ROBOT_LOOP=1)
    python3 -m tools.measure_phases → đọc số đo + dự báo điểm

Lưu ý về TRUNG VỊ: các chặng chạy hỏng (mất line, IR không thấy pallet, timeout) bị
LOẠI khỏi mẫu chứ không tính trung bình vào — mục đích là đo chi phí một chặng SẠCH,
còn phần phụ trội do hỏng được đếm riêng ở bảng "Phụ trội". Mô hình estimate_time
không tính retry, nên trận thật luôn chậm hơn dự báo đúng bằng phần phụ trội đó.
"""

import argparse
import itertools
import re
import statistics
import sys
from datetime import datetime

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

import config
import navigation as nav
from tools.estimate_time import lap_ops, seconds

# Khớp đúng format ở main.py: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \[(\w+)\] ([\w.]+): (.*)$")
TIME_FMT = "%Y-%m-%d %H:%M:%S,%f"

# Mốc chia lượt chạy — _run_state_machine() in ra ở đầu mỗi lượt (cả thi đấu lẫn
# luyện tập), nên gộp nhầm log của nhiều lượt là không xảy ra.
RUN_SEPARATOR = "BẮT ĐẦU STATE MACHINE"

NEXT_LINE = None        # sentinel cho `end`: kết thúc = dòng log kế tiếp bất kỳ


class Entry:
    __slots__ = ("t", "level", "msg")

    def __init__(self, t, level, msg):
        self.t, self.level, self.msg = t, level, msg


class Span:
    """Một chặng đo được: từ dòng log `start` đến dòng log `end`.

    abort: chặng bắt đầu rồi HỎNG → loại mẫu VÀ đếm là một lần hỏng.
    cancel: mốc bắt đầu hoá ra không phải chặng này → loại mẫu, KHÔNG đếm là hỏng.
        Cần vì vài mốc dùng chung: "Đã đến vị trí kệ" xuất hiện cả khi tiếp cận để
        QUÉT lẫn khi tiếp cận để THẢ hàng; lần thứ hai không có pha quét nào theo sau.
    max_s: mốc vô lý → loại mẫu. Cần vì `end=NEXT_LINE` có thể vớ phải dòng log của
        một việc khác hẳn (vd robot đứng chờ nút) và thổi phồng số đo.
    """

    def __init__(self, key, title, start, end, abort=(), cancel=(), max_s=30.0):
        self.key, self.title, self.max_s = key, title, max_s
        self.start = re.compile(start)
        self.end = re.compile(end) if end is not NEXT_LINE else NEXT_LINE
        self.abort = re.compile("|".join(abort)) if abort else None
        self.cancel = re.compile("|".join(cancel)) if cancel else None


# Chuỗi log lấy nguyên văn từ control/motion.py, control/lift.py, main.py.
# Sửa log ở đó thì phải sửa theo ở đây — test_tools.py canh chuyện này.
SPANS = [
    Span("forward", "Đi 1 khoảng giữa 2 giao lộ",
         start=r"Đi đến giao lộ \d+/\d+",
         end=r"Phát hiện giao lộ \(active=",
         abort=(r"Không tìm thấy giao lộ", r"Timeout bám line",
                r"Không tìm lại được line", r"Mất line quá")),
    Span("reverse", "LÙI 1 khoảng ra khỏi kệ",
         start=r"Lùi về giao lộ \d+/\d+",
         end=r"Phát hiện giao lộ \(active=",
         abort=(r"Lùi: (mất line|timeout)",)),
    Span("turn", "Xoay 90°",
         start=r"Xoay 90° (trái|phải)",
         end=NEXT_LINE, max_s=5.0),
    Span("advance", "Bám line đoạn cuối (advance)",
         start=r"Bám line tới hết line \(advance",
         end=r"Advance: (đã hết line|đã tới gần mục tiêu)",
         abort=(r"Advance: (timeout|gặp giao lộ)",)),
    Span("approach", "Tiếp cận siêu âm",
         start=r"Tiếp cận kệ 2 pha",
         end=r"Đã đến vị trí kệ",
         abort=(r"Timeout tiếp cận kệ", r"Tiếp cận: chạy mù")),
    Span("retreat", "Lùi ra khỏi kệ",
         start=r"Lùi ra khỏi kệ",
         end=r"Đã lùi đủ xa",
         abort=(r"Timeout lùi ra",)),
    Span("lift_pickup", "Nâng kiện khỏi kệ",
         start=r"Nhấc hàng tầng \d+ — lần",
         end=r"Xác nhận: (CẢ 2 pallet trên càng|có pallet trên càng)",
         abort=(r"Thất bại sau \d+ lần thử nâng",)),
    Span("lift_drop", "Hạ kiện xuống nhà máy",
         start=r"Đặt hàng — ",
         end=r"(Xác nhận: pallet (trái|phải) đã rời càng"
             r"|Cảm biến( (trái|phải))? vẫn thấy pallet"
             r"|Lùi ra khỏi kệ|Nâng lại càng|Gập càng)"),
    Span("lift_raise", "Nâng lại / gập càng sau khi thả",
         start=r"(Nâng lại càng|Gập càng — hạ càng)",
         end=NEXT_LINE, max_s=10.0),
    # Quét nhận diện nằm giữa "đã tiếp cận xong kệ" và "nhận diện xong" trong
    # _handle_pickup_pair. Lần "Đã đến vị trí kệ" của các pha THẢ hàng không có
    # "Nhận diện OK" theo sau nên tự bị huỷ bởi mốc bắt đầu kế tiếp.
    Span("scan", "Quét nhận diện 2 kiện",
         start=r"Đã đến vị trí kệ",
         end=r"(Nhận diện OK \(lần \d+\)|Không nhận diện được sau)",
         cancel=(r"Đặt hàng — ",)),          # tiếp cận đó là để THẢ, không phải để quét
]

# Những thứ mô hình estimate_time KHÔNG tính — đếm riêng để biết dự báo lạc quan bao nhiêu
ANOMALIES = [
    ("Mất line giữa đường",        r"Mất line quá"),
    ("Không tìm thấy giao lộ",     r"Không tìm thấy giao lộ"),
    ("Lùi ra khỏi kệ hỏng",        r"Lùi: (mất line|timeout)"),
    ("Timeout bám line",           r"Timeout bám line"),
    ("Advance hỏng",               r"Advance: (timeout|gặp giao lộ)"),
    ("Tiếp cận hỏng",              r"(Timeout tiếp cận kệ|Tiếp cận: chạy mù)"),
    ("Lùi ra timeout",             r"Timeout lùi ra"),
    ("Nâng lại (IR không thấy)",   r"Lần \d+: KHÔNG thấy pallet"),
    ("Quét lại nhận diện",         r"Lần \d+: không nhận diện đủ 2 kiện"),
    ("Thử lại tầng kệ",            r"thất bại — thử lại tầng"),
    ("BỎ QUA tầng kệ",             r"thất bại — bỏ qua tầng kệ"),
    ("Navigation thất bại",        r"Navigation thất bại"),
    ("RESET giữa trận",            r"RESET lần \d+"),
]

RESULT_PACKAGES = re.compile(r"Kiện hàng đã giao: (\d+)/(\d+)")
RESULT_ELAPSED = re.compile(r"Thời gian: ([\d.]+)/(\d+)s")


# ============================================================
# Đọc log
# ============================================================

def parse_log(path: str) -> list[Entry]:
    entries = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            m = LINE_RE.match(raw.rstrip("\n"))
            if m:      # dòng không khớp = traceback nhiều dòng / echo của start.sh
                entries.append(Entry(datetime.strptime(m.group(1), TIME_FMT),
                                     m.group(2), m.group(4)))
    return entries


def split_runs(entries: list[Entry]) -> list[list[Entry]]:
    """Cắt log theo từng lượt chạy state machine."""
    runs, current = [], []
    for e in entries:
        if RUN_SEPARATOR in e.msg:
            if current:
                runs.append(current)
            current = []
        current.append(e)
    if current:
        runs.append(current)
    return runs or [entries]


# ============================================================
# Ghép cặp mốc bắt đầu / kết thúc
# ============================================================

def collect(entries: list[Entry], spec: Span) -> tuple[list[float], int]:
    """Trả (danh sách giây đo được, số lần chặng bắt đầu mà không kết thúc sạch)."""
    samples, dropped, pending = [], 0, None

    for e in entries:
        if pending is not None:
            # Kiểm KẾT THÚC trước mốc BẮT ĐẦU: 2 lần xoay liên tiếp thì chính dòng
            # "Xoay 90°" thứ hai vừa là điểm kết của lần 1 vừa là điểm đầu lần 2.
            if spec.cancel is not None and spec.cancel.search(e.msg):
                pending = None          # không phải chặng này — không tính là hỏng
            elif spec.abort is not None and spec.abort.search(e.msg):
                dropped += 1
                pending = None
            elif spec.end is NEXT_LINE or spec.end.search(e.msg):
                secs = (e.t - pending.t).total_seconds()
                if 0 <= secs <= spec.max_s:
                    samples.append(secs)
                else:
                    dropped += 1
                pending = None

        if spec.start.search(e.msg):
            if pending is not None:
                dropped += 1      # lần trước chưa kết thúc → mẫu hỏng, bỏ
            pending = e

    if pending is not None:
        dropped += 1
    return samples, dropped


def summarize(entries: list[Entry]) -> dict:
    return {s.key: collect(entries, s) for s in SPANS}


# ============================================================
# Suy ra 6 tham số cho estimate_time
# ============================================================

DEFAULTS = {"forward": 2.5, "turn": 1.2, "advance": 2.0,
            "approach": 3.0, "lift": None, "scan": 1.0}


def _median(samples):
    return statistics.median(samples) if samples else None


def derive(measured: dict) -> tuple[dict, dict]:
    """(6 tham số, nguồn của từng tham số) — thiếu số đo thì giữ mặc định."""
    med = {k: _median(v[0]) for k, v in measured.items()}
    params, source = {}, {}

    for key in ("forward", "turn", "advance", "scan"):
        params[key] = med.get(key)
        source[key] = "đo" if params[key] is not None else "MẶC ĐỊNH"

    # estimate_time gộp tiếp cận + lùi ra vào một tham số
    if med["approach"] is not None and med["retreat"] is not None:
        params["approach"] = med["approach"] + med["retreat"]
        source["approach"] = "đo (tiếp cận + lùi)"
    else:
        params["approach"] = None
        source["approach"] = "MẶC ĐỊNH"

    # estimate_time dùng CHUNG một --lift cho cả chu kỳ nâng lẫn chu kỳ thả.
    # Chu kỳ thả = hạ càng + nâng lại càng, nên phải cộng lift_raise vào.
    drop_cycle = None
    if med["lift_drop"] is not None:
        drop_cycle = med["lift_drop"] + (med["lift_raise"] or 0.0)
    cycles = [c for c in (med["lift_pickup"], drop_cycle) if c is not None]
    params["lift"] = sum(cycles) / len(cycles) if cycles else None
    source["lift"] = ("đo (TB nâng %.1fs / thả %.1fs)" % (
        med["lift_pickup"] or 0.0, drop_cycle or 0.0)) if cycles else "MẶC ĐỊNH"

    for key, value in params.items():
        if value is None:
            params[key] = (DEFAULTS[key] if DEFAULTS[key] is not None
                           else (config.LIFT_TIME_SHELF_1 + config.LIFT_TIME_SHELF_2))
    return params, source


# ============================================================
# Dự báo điểm
# ============================================================

class _Params:
    def __init__(self, d):
        self.__dict__.update(d)


def project(params: dict) -> list[tuple]:
    """[(tên kịch bản, kiện giao được, điểm, giây đã dùng, giây cần đủ 12 kiện)]"""
    a = _Params(params)
    labels = list(nav.FACTORY_TERMINAL)
    pairs = list(itertools.combinations_with_replacement(labels, 2))
    rows = []

    for title, pick in (("TỆ NHẤT (kiện xếp xấu nhất)", max),
                        ("NHẸ NHẤT (kiện xếp đẹp nhất)", min)):
        laps = []
        for shelf in (0, 1, 2):
            for tier in (1, 2):
                cand = [seconds(ops, a) for ops in
                        (lap_ops(shelf, tier, l, r) for l, r in pairs) if ops]
                laps.append(pick(cand))
        start = a.forward + a.approach + 2 * a.turn + a.advance
        used, delivered = start, 0
        for lap in laps:
            if used + lap > config.MATCH_DURATION:
                break
            used += lap
            delivered += 2
        rows.append((title, delivered, delivered * 20, used, start + sum(laps)))
    return rows


# ============================================================
# In kết quả
# ============================================================

def print_report(measured, params, source, entries, runs_used):
    print("=" * 76)
    print(" SỐ ĐO THẬT TỪ LOG")
    print("=" * 76)
    print(f" Lượt phân tích: {runs_used} | {len(entries)} dòng log | "
          f"{entries[0].t:%H:%M:%S} → {entries[-1].t:%H:%M:%S}")

    print(f"\n {'Chặng':<34}{'mẫu':>5}{'trung vị':>10}{'nhanh':>8}{'chậm':>8}  ghi chú")
    print(" " + "-" * 74)
    for spec in SPANS:
        samples, dropped = measured[spec.key]
        if not samples:
            print(f" {spec.title:<34}{0:>5}{'—':>10}{'—':>8}{'—':>8}  "
                  f"KHÔNG có mẫu → dùng số mặc định")
            continue
        note = "" if len(samples) >= 3 else "ít mẫu, chạy thêm 1 lượt"
        if dropped:
            note = (note + " | " if note else "") + f"{dropped} lần hỏng (đã loại)"
        print(f" {spec.title:<34}{len(samples):>5}{statistics.median(samples):>9.2f}s"
              f"{min(samples):>7.2f}s{max(samples):>7.2f}s  {note}")

    print("\n --- Phụ trội KHÔNG có trong mô hình estimate_time ---")
    found = False
    for title, pattern in ANOMALIES:
        rx = re.compile(pattern)
        n = sum(1 for e in entries if rx.search(e.msg))
        if n:
            print(f"   {title:<32}{n:>4} lần")
            found = True
    if not found:
        print("   (không có — lượt chạy sạch)")

    for rx, label in ((RESULT_PACKAGES, "Kết quả lượt chạy"),
                      (RESULT_ELAPSED, None)):
        for e in reversed(entries):
            m = rx.search(e.msg)
            if m:
                if label:
                    print(f"\n {label}: đã giao {m.group(1)}/{m.group(2)} kiện thật")
                else:
                    print(f" {'':<18}  hết {float(m.group(1)):.0f}/{m.group(2)}s")
                break

    print("\n" + "=" * 76)
    print(" 6 THAM SỐ SUY RA")
    print("=" * 76)
    for key in ("forward", "turn", "advance", "approach", "lift", "scan"):
        print(f"   --{key:<10}{params[key]:>6.2f}s   ({source[key]})")

    cmd = " ".join(f"--{k} {params[k]:.2f}" for k in
                   ("forward", "turn", "advance", "approach", "lift", "scan"))
    print(f"\n Chạy lại estimate_time với số đo này:\n   python3 -m tools.estimate_time {cmd}")

    print("\n" + "=" * 76)
    print(" DỰ BÁO ĐIỂM NV1 (BTC xếp kiện ngẫu nhiên → phải xét cả 2 biên)")
    print("=" * 76)
    for title, delivered, points, used, needed in project(params):
        verdict = "✅ ĐỦ 12 KIỆN" if delivered >= config.TOTAL_PACKAGES_TASK1 else "❌ hết giờ giữa chừng"
        print(f"   {title:<30} {delivered:>2}/{config.TOTAL_PACKAGES_TASK1} kiện = "
              f"{points:>3} điểm  (dùng {used:.0f}s, cần {needed:.0f}s)  {verdict}")
    print("\n   ⚠ Dự báo này CHƯA trừ retry — xem bảng 'Phụ trội' ở trên để tự cộng thêm.")
    print("=" * 76)


def main():
    p = argparse.ArgumentParser(
        description="Rút tham số estimate_time từ robot_log.txt")
    p.add_argument("logfile", nargs="?", default=config.LOG_FILE,
                   help=f"đường dẫn log (mặc định {config.LOG_FILE})")
    p.add_argument("--all", action="store_true",
                   help="gộp MỌI lượt trong file (mặc định: chỉ lượt gần nhất)")
    args = p.parse_args()

    try:
        entries = parse_log(args.logfile)
    except OSError as e:
        print(f"Không đọc được log: {e}")
        return 1
    if not entries:
        print(f"{args.logfile}: không có dòng log nào đúng định dạng.\n"
              f"Chạy `bash scripts/practice.sh` 1 lượt trên sa bàn trước.")
        return 1

    runs = split_runs(entries)
    if args.all:
        entries, runs_used = entries, f"tất cả {len(runs)} lượt"
    else:
        entries, runs_used = runs[-1], f"lượt gần nhất (trong {len(runs)} lượt)"

    measured = summarize(entries)
    params, source = derive(measured)
    print_report(measured, params, source, entries, runs_used)
    return 0


if __name__ == "__main__":
    sys.exit(main())
