"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401

CHECK = "label_format"                                   # tên check, ghi vào cột "check" của báo cáo


def _overflow(x, y, w, h):
    """Mức tràn lớn nhất ra ngoài [0,1] trên 4 mép (<= 0 nghĩa là box nằm trọn trong ảnh)."""
    left, right = x - w / 2, x + w / 2                  # mép trái/phải = tâm ∓ nửa chiều rộng
    top, bottom = y - h / 2, y + h / 2                  # mép trên/dưới = tâm ∓ nửa chiều cao
    return max(0.0 - left, right - 1.0, 0.0 - top, bottom - 1.0)   # phần thò ra ngoài nhiều nhất trong 4 mép


def run(ds, cfg):
    c = cfg["label_format"]                             # mọi ngưỡng lấy từ config, không viết cứng
    tol = c["overflow_tol"]                             # tràn ít hơn mức này thì bỏ qua (sai số làm tròn)
    min_px = c["min_box_px"]                            # cạnh ngắn (px) nhỏ hơn => BOX_TINY
    max_frac = c["max_box_frac"]                        # diện tích (tỉ lệ ảnh) lớn hơn => BOX_HUGE
    dup_iou = c["dup_box_iou"]                          # IoU lớn hơn (cùng lớp) => DUP_BOX
    n_cls = len(ds.classes)                             # id lớp hợp lệ: 0 .. n_cls-1
    issues = []                                         # kết quả trả về: list[Issue]

    for lp in ds.label_files():                         # duyệt từng file nhãn (chỉ ĐỌC, không sửa)
        stem = lp.stem                                  # tên ảnh không đuôi, vd "img_001"
        size = None                                     # (rộng, cao) px của ảnh, chỉ mở ảnh khi cần
        size_loaded = False                             # đã thử mở ảnh chưa (tránh mở lại mỗi dòng)
        prev = []                                       # (lớp, box, số dòng) các dòng hợp lệ phía trước

        for ln, text in ds.read_label_lines(stem) or []:   # ln = số dòng GỐC (dòng trống vẫn được đếm)
            try:
                cls, x, y, w, h = parse_yolo_line(text)     # tách 5 cột; thiếu/thừa cột, chữ, nan => ValueError
            except ValueError as e:
                issues.append(Issue(CHECK, ERROR, "BAD_FORMAT", stem, f"dòng không đúng định dạng YOLO: {e}", ln))
                continue                                    # dòng hỏng: không kiểm tiếp hình học
            if not 0 <= cls < n_cls:                        # id lớp âm hoặc vượt số lớp
                issues.append(Issue(CHECK, ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls} ngoài 0..{n_cls - 1}", ln,
                                    {"class_id": cls}))
                continue
            if w <= 0 or h <= 0:                            # box không có diện tích
                issues.append(Issue(CHECK, ERROR, "BOX_ZERO", stem, f"box không có diện tích (w={w}, h={h})", ln))
                continue

            over = _overflow(x, y, w, h)                    # mức tràn ra ngoài ảnh
            if over > tol:                                  # chỉ báo khi tràn quá dung sai
                issues.append(Issue(CHECK, ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ra ngoài ảnh {over:.4f}", ln,
                                    {"overflow": round(over, 6)}))

            box = (x, y, w, h)
            for p_cls, p_box, p_ln in prev:                 # so với các dòng hợp lệ ĐỨNG TRƯỚC
                iou = iou_xywh(p_box, box)
                if p_cls == cls and iou > dup_iou:          # cùng lớp và gần như trùng khít => báo ở dòng SAU
                    issues.append(Issue(CHECK, ERROR, "DUP_BOX", stem, f"trùng box dòng {p_ln} (IoU {iou:.3f})", ln,
                                        {"of_line": p_ln, "iou": round(iou, 4)}))
                    break                                   # một dòng chỉ báo DUP_BOX một lần
            prev.append((cls, box, ln))

            if not size_loaded:                             # lần đầu cần kích thước thì mới mở ảnh
                size, size_loaded = ds.image_size(stem), True
            if size:                                        # ảnh hỏng/không có => bỏ qua BOX_TINY (check images báo)
                short_px = min(w * size[0], h * size[1])    # cạnh ngắn của box, đổi ra pixel
                if short_px < min_px:
                    issues.append(Issue(CHECK, WARN, "BOX_TINY", stem, f"cạnh ngắn {short_px:.1f}px < {min_px}px", ln,
                                        {"short_px": round(short_px, 2)}))
            if w * h > max_frac:                            # box gần phủ cả ảnh: thường là gán nhầm
                issues.append(Issue(CHECK, WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.0%} ảnh", ln,
                                    {"frac": round(w * h, 4)}))
    return issues
