"""
Chuỗi BỐC & THẢ HÀNG dùng chung — MỘT cài đặt duy nhất cho cả thi đấu lẫn test.

VÌ SAO TÁCH RA FILE RIÊNG: đây là chỗ đã sinh ra lỗi nặng nhất của dự án. Trước
đây `main.py` gọi `Lift.pickup()` — hàm nâng càng TỪ SÀN tại chỗ, không hề tiến
vào — trong khi cơ cấu là xe nâng thật, càng phải LUỒN vào pallet rồi mới nhấc
được. Robot không bao giờ móc được hàng.

Lỗi đó sống sót lâu vì `tests/test_lift.py` cũng gọi đúng hàm sai ấy, mà ở test
bàn thì NGƯỜI tự tay canh càng vào pallet trước khi bấm Enter. Test luôn xanh,
robot luôn hỏng, và không có gì đối chiếu hai bên với nhau.

Nên: chuỗi thao tác chỉ được viết Ở ĐÂY. `main.Robot._insert_and_lift()` và
`tests/test_smoke.py` đều gọi vào đây chứ không tự dựng lại. `tests/test_logic.py`
có test quét source để chặn việc ai đó lại chép chuỗi này ra chỗ khác.

THỨ TỰ ĐÚNG (xe nâng luồn-rồi-nâng):
    1. Robot đã dừng ở vị trí CHỜ, càng còn ở sàn   (Motion.approach_shelf)
    2. NÂNG càng lên ngang tầng cần lấy             ← Lift.raise_to_insert
    3. TIẾN THÊM để luồn càng vào pallet            ← Motion.creep_until, IR dẫn
    4. NHẤC thêm để pallet rời mặt kệ               ← Lift.lift_off
    5. Xác nhận IR                                  ← Lift.confirm_pickup

Bước 3 dừng theo CẢM BIẾN IR trên mặt càng chứ không theo siêu âm: siêu âm đo
khoảng cách tới MẶT KỆ, còn thứ cần biết là PALLET đã nằm trên càng chưa. Robot
lệch ngang vài centimet hay pallet đặt lệch trên kệ là số siêu âm sai ngay.
"""

import logging

logger = logging.getLogger(__name__)


def insert_and_lift_once(motion, lift, tier: int, require_both: bool = True,
                         on_step=None) -> bool:
    """MỘT lần thử bốc hàng. Trả True khi IR xác nhận pallet đã trên càng.

    Không tự retry và không tự lùi ra — phần đó thuộc về caller, vì lùi/tiếp cận
    lại cần ngữ cảnh điều hướng mà module này không có. Xem
    `main.Robot._insert_and_lift()`.

    Giả định robot ĐÃ dừng ở vị trí chờ (config.APPROACH_DISTANCE) với càng ở sàn.

    `on_step(ten, mo_ta)` — hook để test QUAN SÁT giữa các bước mà không phải chép
    lại luồng này. Chép ra là sớm muộn test chạy khác main, và mất đúng cái giá trị
    mà smoke test sinh ra để có. main.py không truyền gì (None = không làm gì).
    Thứ tự các bước: raise → creep → lift_off. Bước raise chạy TRƯỚC khi robot tiến;
    thấy robot tiến rồi mới nâng càng là dấu hiệu `_current_level` sai.
    """
    buoc = on_step or (lambda *_a: None)

    lift.raise_to_insert(tier)
    buoc("raise", f"đã nâng càng lên ngang tầng {tier} (robot CHƯA tiến)")

    need = lift.pallet.has_both if require_both else lift.pallet.has_any
    # `is True` chứ không phải truthy: has_both() trả None khi ĐỌC LỖI SPI/ADC, mà
    # None truthy-false — coi lỗi đọc thành "chưa có pallet" thì robot cứ tiến tới
    # khi chạm chặn cứng. Ở đây None nghĩa là "không biết", và không biết thì không
    # được dừng, cũng không được coi là thành công.
    if not motion.creep_until(lambda: need() is True):
        logger.warning("Bốc hàng: không luồn được càng vào pallet")
        buoc("creep_fail", "IR KHÔNG báo — càng chưa vào khe pallet")
        return False
    buoc("creep", "IR đã báo — càng đang NẰM TRONG khe pallet")

    lift.lift_off()
    buoc("lift_off", "đã nhấc bổng, pallet phải RỜI mặt kệ")
    return lift.confirm_pickup(require_both=require_both)


def drop_side(lift, side: str, last: bool) -> bool:
    """Thả kiện ở càng `side`. Trả True khi IR xác nhận pallet đã RỜI càng.

    last=False (DROP_FIRST, còn kiện nữa) → NÂNG LẠI càng vừa thả cho ngang càng kia.
    last=True  (DROP_SECOND, hết kiện)    → GẬP nốt càng còn lại về sàn.

    ⚠️ BẤT BIẾN QUAN TRỌNG: nâng lại / gập càng chạy LUÔN LUÔN, kể cả khi IR KHÔNG
    xác nhận. Càng còn nằm thấp mà robot lùi rồi chạy tiếp là cạ sàn, vướng mép kệ,
    hoặc kéo đổ kiện hàng. Viết thành `if dropped: lift.raise_after_drop(...)` là
    nhánh "IR fail" không bao giờ nâng càng lên — và đó đúng là nhánh hay xảy ra nhất.

    Giá trị trả về CHỈ dùng để quyết định có cộng điểm hay không
    (`packages_delivered`), không dùng để quyết định có nâng càng hay không.
    """
    dropped = lift.dropoff_left() if side == "left" else lift.dropoff_right()
    if last:
        lift.stow_forks(side)
    else:
        lift.raise_after_drop(side)
    return dropped


def drop_both(lift) -> bool:
    """Thả CẢ 2 kiện cùng lúc — dùng khi 2 kiện đi cùng một nhà máy.

    Hạ đồng bộ nên không cần nâng lại: `dropoff()` đưa `_current_level` về 0, càng
    đã ở tư thế di chuyển an toàn.
    """
    return lift.dropoff()
