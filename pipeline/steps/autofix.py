"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}                       # lỗi dòng => xoá dòng
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}                                                       # box tràn => cắt về [0,1]
REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}   # lỗi ảnh => xoá ảnh + nhãn


def _fx(image, line, action, before, after):
    """Một dòng của 03_fixes.csv: bằng chứng máy đã sửa gì, để người kiểm lại."""
    return dict(image=image, line="" if line is None else line, action=action, before=before, after=after)


def _clip(text):
    """Cắt box về [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích."""
    cls, x, y, w, h = parse_yolo_line(text)                 # dòng này đã qua label_format nên parse được
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)       # kẹp mép trái/phải vào [0,1]
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)       # kẹp mép trên/dưới vào [0,1]
    if x2 <= x1 or y2 <= y1:                                # box nằm hẳn ngoài ảnh => không còn gì để giữ
        return None
    return f"{cls} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"   # đổi lại về tâm + rộng/cao, giữ nguyên lớp


def _remove_image(ds, stem):
    """Xoá ảnh (mọi đuôi) + file nhãn của `stem` TRONG ds; trả về tên các file đã xoá."""
    files = [p for p in ds.image_files() if p.stem == stem]  # ảnh có thể là .jpg/.JPG/.png
    lp = ds.label_path(stem)
    if lp.exists():
        files.append(lp)
    for p in files:
        p.unlink()                                          # chỉ xoá trong ds (bản sao), không đụng data/raw/
    return [p.name for p in files]


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]     # chỉ sửa lỗi bắt buộc; WARN để người xem
    fixes = []                                              # danh sách thay đổi => 03_fixes.csv

    # 1) Xoá ảnh TRƯỚC: các lỗi dòng của ảnh đã xoá sẽ được bỏ qua êm ở bước 4.
    removed = set()
    for i in errors:
        if i.code in REMOVE_CODES and i.image not in removed:   # một ảnh có thể có nhiều lỗi: chỉ xoá một lần
            gone = _remove_image(ds, i.image)
            removed.add(i.image)
            if gone:                                            # chạy lần 2: ảnh đã mất => không ghi fix (idempotent)
                fixes.append(_fx(i.image, None, "remove_image", ", ".join(gone), f"(đã xoá: {i.code})"))

    # 2) data.yaml: ghi lại names MỘT lần dù có nhiều issue BAD_CLASS_NAME.
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        data = {}
        if ds.yaml_path.exists():
            data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}   # giữ các khoá khác (path, train...)
        old = ds.yaml_names()                                   # tên lớp hiện tại {id: tên}
        new = dict(enumerate(cfg["classes"]))                   # tên lớp đúng theo dự án
        if old != new:                                          # đã đúng rồi thì không ghi (idempotent)
            data["names"] = new
            ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append(_fx("data.yaml", None, "rename_classes", str([old[k] for k in sorted(old)]), str(cfg["classes"])))

    # 3) Thiếu file nhãn: máy KHÔNG bịa nhãn (kể cả file rỗng = "ảnh nền"), chỉ ghi lại để chuyển người gán.
    seen_missing = set()
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and i.image not in seen_missing:
            seen_missing.add(i.image)
            if not ds.label_path(i.image).exists():
                fixes.append(_fx(i.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # 4) Sửa dòng: gom theo file, dùng số dòng GỐC, ghi lại file MỘT lần (xoá từng dòng một sẽ làm lệch số dòng).
    drops, clips = defaultdict(set), defaultdict(set)       # stem -> tập số dòng cần xoá / cần cắt
    for i in errors:
        if i.image in removed or i.line in (None, ""):      # ảnh đã xoá, hoặc lỗi không gắn với dòng nào
            continue
        if i.code in DROP_CODES:
            drops[i.image].add(int(i.line))
        elif i.code in CLIP_CODES:
            clips[i.image].add(int(i.line))

    for stem in sorted(set(drops) | set(clips)):
        lp = ds.label_path(stem)
        if not lp.exists():                                 # file đã mất: bỏ qua, không chết
            continue
        raw = lp.read_text(encoding="utf-8", errors="replace")
        out, changed = [], False
        for n, text in enumerate(raw.splitlines(), 1):      # đếm cả dòng trống => khớp số dòng gốc của issue
            if n in drops[stem]:                            # xoá thắng: dòng vừa DUP_BOX vừa tràn thì chỉ xoá
                fixes.append(_fx(stem, n, "drop_line", text, ""))
                changed = True
                continue
            if n in clips[stem]:
                try:
                    new = _clip(text)
                except ValueError:                          # không parse được => không cắt được: xoá dòng và GHI LẠI fix
                    new = None
                if new is None:                             # cắt xong không còn diện tích => xoá thay vì ghi box rỗng
                    fixes.append(_fx(stem, n, "drop_line", text, ""))
                    changed = True
                    continue
                if new != text:
                    fixes.append(_fx(stem, n, "clip_box", text, new))
                    text, changed = new, True
            out.append(text)                                # dòng không lỗi giữ nguyên
        if changed:                                         # chỉ ghi file khi thật sự có thay đổi
            lp.write_text("".join(ln + "\n" for ln in out), encoding="utf-8")

    return fixes
