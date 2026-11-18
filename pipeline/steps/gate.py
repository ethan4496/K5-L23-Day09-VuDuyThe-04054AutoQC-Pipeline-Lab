"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from collections import Counter

from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)                                      # tập ảnh còn trong dataset
    reviewed = set(reviewed)                                      # ảnh người đã duyệt
    hold_at = cfg["gate"]["warn_ratio_hold"]                      # ngưỡng Hold lấy từ config

    errors = [i for i in issues if i.severity == ERROR]           # lỗi bắt buộc: KHÔNG bao giờ bỏ qua, kể cả ảnh đã duyệt
    warn_images = {i.image for i in issues                        # set => đếm ẢNH, không đếm issue
                   if i.severity == WARN
                   and i.image in stems                           # bỏ "<dataset>", "data.yaml", ảnh đã bị xoá
                   and i.image not in reviewed}                   # cảnh báo của ảnh đã duyệt coi như đã xử lý
    n_images = len(stems)                                         # mẫu số = số ảnh
    ratio = round(len(warn_images) / n_images, 4) if n_images else 0.0   # dataset rỗng: tránh chia cho 0

    reasons = []                                                  # giải thích kết luận, có số liệu
    if errors:                                                    # nhánh 1: còn lỗi bắt buộc => Rework
        decision = "Rework"
        by_code = Counter(i.code for i in errors)                 # đếm theo mã lỗi để người đọc biết sửa gì trước
        reasons.append(f"còn {len(errors)} lỗi bắt buộc chưa sửa ("
                       + ", ".join(f"{c}: {n}" for c, n in by_code.most_common()) + ")")
    elif n_images and ratio >= hold_at:                           # nhánh 2: tỉ lệ ảnh còn cảnh báo >= ngưỡng (">=": đúng ngưỡng vẫn Hold)
        decision = "Hold"
        reasons.append(f"không còn lỗi bắt buộc, nhưng {len(warn_images)}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo "
                       f"chưa người duyệt, >= ngưỡng {hold_at:.0%}")
    else:                                                         # nhánh 3: còn lại => Release
        decision = "Release"
        reasons.append(f"không còn lỗi bắt buộc; {len(warn_images)}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo "
                       f"chưa duyệt, < ngưỡng {hold_at:.0%}")
    if reviewed:
        reasons.append(f"{len(reviewed & stems)} ảnh đã được người duyệt (cảnh báo của chúng không tính)")

    return dict(decision=decision, n_errors=len(errors), n_warn_images=len(warn_images), n_images=n_images,
                warn_ratio=ratio, reasons=reasons)
