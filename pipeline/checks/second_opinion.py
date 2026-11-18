"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds

CHECK = "second_opinion"                                # tên check trong báo cáo


def _labels_with_lines(ds, stem):
    """[(số dòng gốc, lớp, (cx, cy, w, h))] của các dòng hợp lệ; dòng hỏng bị bỏ qua (label_format đã báo)."""
    out = []
    for ln, text in ds.read_label_lines(stem) or []:    # giữ số dòng gốc (valid_boxes thì không giữ)
        try:
            cls, x, y, w, h = parse_yolo_line(text)
        except ValueError:                              # dòng hỏng: không làm script chết, check khác đã báo BAD_FORMAT
            continue
        if 0 <= cls < len(ds.classes):                  # bỏ id lớp lạ (BAD_CLASS_ID do label_format báo)
            out.append((ln, cls, (x, y, w, h)))
    return out


def run(ds, cfg, preds=None):
    c = cfg["second_opinion"]                           # mọi ngưỡng từ config (sẽ calibrate ở Bước 3)
    conf_min = c["conf"]                                # chỉ tin dự đoán có conf >= mức này
    min_area = c["min_area_px"]                         # bỏ dự đoán nhỏ hơn (px²): guideline không gán vật quá nhỏ
    fp_conf = c["fp_conf"]                              # ngưỡng conf (thấp hơn) dùng cho FALSE_POS
    iou_missing = c["iou_missing"]                      # IoU < mức này = "không chạm" box nào
    iou_match = c["iou_match"]                          # IoU >= mức này = "cùng vật" (dùng cho WRONG_CLASS)
    iou_loose = c["iou_loose"]                          # cùng lớp nhưng IoU < mức này = box lỏng/lệch
    if preds is None:
        preds = get_preds(ds, cfg, "checker")           # đọc cache dự đoán của model lớn (yolo26l)
    names = ds.classes

    def cname(k):                                       # id lớp -> tên, để message dễ đọc
        return names[k] if 0 <= k < len(names) else str(k)

    issues = []
    for p in ds.image_files():                          # thứ tự issue: theo ảnh (sắp theo tên)
        stem = p.stem
        if stem not in preds or ds.read_label_lines(stem) is None:   # không có dự đoán hoặc không có file nhãn => bỏ qua
            continue
        labels = _labels_with_lines(ds, stem)           # box nhãn hợp lệ kèm số dòng
        size = ds.image_size(stem)                      # (rộng, cao) px để tính diện tích dự đoán
        rows = [(int(r[0]), float(r[1]), tuple(float(v) for v in r[2:6]))   # [lớp, conf, cx, cy, w, h] -> (lớp, conf, box)
                for r in preds[stem] or [] if len(r) >= 6]

        # --- (A) Với từng dự đoán ĐÁNG TIN -> tối đa MỘT issue: MISSING / LOOSE_BOX / WRONG_CLASS
        for cls, conf, box in rows:                     # giữ thứ tự dự đoán trong preds[stem]
            if conf < conf_min:                         # model không chắc => không cờ
                continue
            if size and box[2] * size[0] * box[3] * size[1] < min_area:   # vật quá nhỏ (ảnh không mở được thì không lọc)
                continue
            cands = []                                  # nhãn MỌI lớp chạm dự đoán này (IoU >= iou_missing)
            for _, l_cls, l_box in labels:
                iou = iou_xywh(box, l_box)
                if iou >= iou_missing:
                    cands.append((l_cls, iou))
            extra = {"conf": round(conf, 4), "pred_class": cname(cls)}   # conf để hàng đợi duyệt xếp ưu tiên
            if not cands:                               # (1) model thấy vật, nhãn không có box nào ở đó
                issues.append(Issue(CHECK, WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy {cname(cls)} (conf {conf:.2f}) nhưng nhãn không có box nào khớp", extra=extra))
                continue
            same = [iou for l_cls, iou in cands if l_cls == cls]   # các nhãn cùng lớp với dự đoán
            if same:                                    # (2) có nhãn đúng lớp phủ vật này
                best = max(same)
                if best < iou_loose:                    # ... nhưng box lỏng/lệch
                    issues.append(Issue(CHECK, WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box {cname(cls)} lỏng/lệch so với model (IoU {best:.2f} < {iou_loose})",
                                        extra={**extra, "iou": round(best, 4)}))
                continue                                # khớp tốt => im lặng, kể cả khi có nhãn khác lớp chồng lên
            best_cls, best = max(cands, key=lambda t: t[1])   # (3) chỉ có nhãn khác lớp: lấy cái IoU cao nhất
            if best >= iou_match:                       # cùng vật nhưng khác lớp => có thể gán nhầm lớp
                issues.append(Issue(CHECK, WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"nhãn ghi {cname(best_cls)} nhưng model thấy {cname(cls)} (conf {conf:.2f}, IoU {best:.2f})",
                                    extra={**extra, "iou": round(best, 4), "label_class": cname(best_cls)}))
            # IoU trong [iou_missing, iou_match): mơ hồ => không cờ

        # --- (B) Với từng box nhãn: không khớp dự đoán nào (conf >= fp_conf, KHÔNG lọc diện tích) -> FALSE_POS
        fp_boxes = [box for _, conf, box in rows if conf >= fp_conf]
        for ln, l_cls, l_box in labels:                 # theo số dòng tăng dần
            best = max((iou_xywh(l_box, b) for b in fp_boxes), default=0.0)   # không có dự đoán nào => IoU 0
            if best < iou_missing:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box {cname(l_cls)} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})", ln,
                                    {"iou": round(best, 4), "label_class": cname(l_cls)}))   # Issue.line = số dòng gốc
    return issues
