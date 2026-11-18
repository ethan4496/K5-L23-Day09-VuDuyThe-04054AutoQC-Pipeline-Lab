# Báo cáo Day 09 — Vũ Duy Thế, 2A202604054

## 1. Kết luận trước
Pipeline kết luận **HOLD** (mã thoát 10). **224** ảnh vào, **22** ảnh bị loại ở cửa vào, **202/224** ảnh vào `clean_v1`. Bản này chỉ là **bản nháp, chưa phát hành** (`manifest.json` ghi `decision=Hold`).
Lý do: không còn lỗi bắt buộc nào (`n_errors = 0`), nhưng **38/202 ảnh (18,8%)** còn cảnh báo chưa có người duyệt, vượt ngưỡng 10%. Hàng đợi có **125** ảnh trong khi ngân sách duyệt chỉ có **80** ảnh (`08_summary.json`).

## 2. Lỗi và phân việc
Số liệu lấy từ `02_error_list_v1` (202 ảnh sau cửa vào) và `01_intake` (224 ảnh). Cột "Số" ghi số issue, trong ngoặc là số ảnh.

| Mã lỗi | Số | Ai sửa | Vì sao |
|---|---:|---|---|
| `DUP_IMAGE_EXACT` / `DUP_IMAGE_NEAR` | 8 / 4 ảnh | máy (`remove_image`) | Ảnh trùng làm lệch phân bố. Ảnh đầu tiên được giữ. |
| `LEAK_TEST` | 5 ảnh | máy (`remove_image`) | Ảnh trùng với test/val làm mAP bị thổi phồng. Bắt buộc loại. |
| `CORRUPT_IMAGE` / `BAD_SIZE` | 2 / 3 ảnh | máy (`remove_image`) | Ảnh không mở được, hoặc cạnh ngắn < 250 px. |
| `BAD_FORMAT`, `BAD_CLASS_ID`, `BOX_ZERO`, `DUP_BOX` | 3 / 6 / 4 / 7 dòng | máy (`drop_line`, 20 dòng) | Dòng hỏng thì không có cách sửa an toàn. Xoá dòng, rồi đưa ảnh vào hàng đợi (`FIXED_DROP_LINE`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | máy (`clip_box`, 8) | Cắt box về [0,1] và giữ nguyên lớp. |
| `BAD_CLASS_NAME` | 2 (1 file `data.yaml`) | máy (`rename_classes`) | Ghi lại `names` cho đúng `cfg.classes`. |
| `MISSING_LABEL_FILE` | 6 ảnh | **người** (`needs_label`) | Máy không bịa nhãn. Một file rỗng nghĩa là "ảnh nền", không phải "chưa gán". |
| `POSSIBLE_MISSING` / `WRONG_CLASS` / `LOOSE_BOX` / `FALSE_POS` | 53 / 18 / 28 / 29 (52 / 18 / 24 / 27 ảnh) | **người** | Lỗi ngữ nghĩa. Model lớn cũng có thể sai, nên chỉ cảnh báo. |
| `EMPTY_LABEL`, `BOX_TINY`, `BOX_HUGE`, `CLASS_RARE` | 12 / 6 / 3 / 4 | **người** | Đây là cảnh báo theo quy tắc dự án. Phải nhìn ảnh mới biết có sai hay không. |

Tổng cộng `03_fixes.csv` có 35 thay đổi: 20 `drop_line`, 8 `clip_box`, 6 `needs_label` và 1 `rename_classes`. Autofix có hệ quả phụ. Số `EMPTY_LABEL` tăng từ 12 (v1) lên 15 (v2), vì có 3 file mà mọi dòng đều hỏng. Số `BOX_TINY` tăng từ 6 lên 7, vì có một box sau khi cắt còn quá nhỏ. Cả hai đều thành cảnh báo cho người xem, không bị bỏ qua.

**Thứ tự hàng đợi.** Đầu hàng là `img_0020` (11,5 điểm), vì ảnh này vừa bị máy xoá dòng vừa có cờ `MISSING` và `WRONG_CLASS`. Tiếp theo là 6 ảnh `NEEDS_LABEL` (10 điểm mỗi ảnh), vì chỉ người mới gán nhãn được và đó cũng là lỗi bắt buộc duy nhất còn lại. Sau đó là các ảnh có `WRONG_CLASS` (trọng số 3) và `MISSING` (2). Điểm được nhân thêm `1 + conf`. `LOOSE_BOX` (1,5) và `BOX_TINY` (0,3) nằm cuối hàng.
**Ngân sách 80 ảnh.** Có 123 cảnh báo ngữ nghĩa trên 103 ảnh. Người duyệt xem được **94/123 (76%)**, nằm trên 74 ảnh. Ảnh cuối cùng được duyệt có 3,343 điểm. Ảnh đầu tiên bị cắt (`img_0210`, 3,333 điểm) vẫn có cờ `POSSIBLE_MISSING`. Trong số cảnh báo còn lại chưa ai xem, phần lớn là `LOOSE_BOX` (16) và `FALSE_POS` (11).

## 3. Calibration (2 ngưỡng)
Số liệu lấy từ `submission/calibration/calibration_report.md`, đo trên `data/calib` (39 ảnh).

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | `DUP_IMAGE_NEAR`: 1,00 / 0,50 → **1,00 / 0,67** | Ảnh bị cờ sẽ **bị xoá**, nên một FP là mất ảnh tốt. Ưu tiên precision. Trên calib, các giá trị từ 4 đến 14 cho kết quả như nhau. Mình chọn 12 dựa trên raw: ngưỡng này bắt được cặp trùng thật `img_0061/img_0186` (khoảng cách 10). Cặp ảnh *khác nhau* gần nhất cách 16, nên còn biên an toàn 4. Ở mức 20, recall của `DUP_IMAGE_EXACT` trên calib rơi còn 0,33, tức là đã gộp nhầm. |
| `second_opinion.conf` | 0.25 | **0.6** | `WRONG_CLASS` 0,56 / 0,83 → **0,62 / 0,83**; `MISSING` 0,50 / 1,00 → **0,57 / 1,00**; `LOOSE_BOX` 0,29 / 0,40 → 0,20 / 0,20 | Đây là cảnh báo cho người, nên một FN đắt hơn một FP. Ngưỡng 0,6 giảm báo động giả mà **không làm giảm recall** của `WRONG_CLASS` và `MISSING`. Không chọn 0,8 (F1 của `WRONG_CLASS` là 0,91, cao nhất), vì ở đó recall của `MISSING` rơi còn 0,75, tức sót 2/8 vật. Cái giá phải trả là recall của `LOOSE_BOX`. Mã này có trọng số thấp nhất trong hàng đợi. `FALSE_POS` không đổi ở mọi giá trị (0,31 / 1,00), vì nó dùng `fp_conf` chứ không dùng `conf`. |

**Chỗ calibration đánh lừa: giá trị "tốt nhất" trên calib lại sai trên raw.** Theo calib, `phash_dist = 16` cho F1 của `DUP_IMAGE_NEAR` cao nhất (0,91). Còn 8, giá trị mình chọn lúc đầu, thì "ngang" các giá trị từ 4 đến 14. Khi mở xem ảnh trên raw:
- Với ngưỡng 8, cặp **img_0061/img_0186** bị bỏ sót. Đây là cùng một ảnh người ngồi ghế băng, chỉ bị cắt và chỉnh sáng, khoảng cách 10.
- Với ngưỡng 16, **img_0008** (trượt tuyết) và **img_0011** (quần vợt), hai ảnh rõ ràng khác nhau, sẽ bị coi là trùng và bị xoá. Thêm vào đó, **6 ảnh raw** cách ảnh test đúng 16 và sẽ bị gắn cờ `LEAK_TEST` sai.

Nguyên nhân: calib chỉ có 6 cặp gần trùng, nên mỗi cặp làm recall nhảy khoảng 17%. Calib cũng không có ca `LEAK_TEST` nào. Vì vậy calib không cho thấy phân bố khoảng cách thật. Kết quả của ngưỡng 12 trên raw: 4 ảnh `DUP_IMAGE_NEAR` (khoảng cách 0, 0, 6 và 10) và 5 ảnh `LEAK_TEST` (khoảng cách 0 đến 6). Mở xem thì cả 9 ảnh đều đúng.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Mình chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`. Kết luận là **REWORK — "còn 6 lỗi bắt buộc chưa sửa (MISSING_LABEL_FILE: 6)"**, **mã thoát 20**, log in ra "KHÔNG xuất: còn lỗi bắt buộc (Rework)", và thư mục `work/exp_nb` **không được tạo**. Không có người duyệt thì 6 ảnh thiếu nhãn vẫn còn nguyên, và gate không để lọt. So sánh với lần chạy có ngân sách 80 ảnh: 6 ảnh `NEEDS_LABEL` đứng đầu hàng đợi và được người gán nhãn, nên `n_errors = 0` và kết luận chuyển thành Hold.

**(b) Điểm mù có bằng chứng.**
1. **Ảnh trùng bị cắt mạnh.** Cặp `img_0074/img_0084` là cùng một ảnh cô gái che ô, chỉ bị cắt, nhưng có khoảng cách phash là **16**, bằng đúng khoảng cách của cặp ảnh *khác nhau* `img_0008/img_0011`. Không ngưỡng phash nào tách được hai trường hợp này, nên ảnh trùng đó vẫn nằm trong `clean_v1`.
2. **Box lỏng nhẹ.** Recall của `POSSIBLE_LOOSE_BOX` trên calib chỉ là **0,20** (1/5). Trên raw, đây là loại cảnh báo còn nhiều nhất trong nhóm chưa duyệt (16 issue). Hai lý do: chỉ báo khi IoU < 0,5, và trọng số trong hàng đợi thấp, nên các box lệch nhẹ gần như không được xem.
3. **`FALSE_POS` nhiễu.** Precision trên calib là **0,31** (11 FP / 16 cờ). Ngưỡng `fp_conf` đã cố định nên không calibrate được. Người duyệt phải mở xem khoảng 2/3 số cờ loại này mà không có lỗi.
4. **Nhầm lớp mà model lớn cũng nhầm.** `WRONG_CLASS` trên calib có 1 FN (recall 0,83). Ngoài ra, lỗi chèn trong calib chủ yếu là person→car, còn raw nghiêng về car/truck/bus. Đây là những lớp model cũng hay lẫn, nên recall trên raw có thể thấp hơn calib.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Cấu hình train: `yolo26n.pt`, 20 epoch, imgsz 640, batch 16, 2 seed (0 và 1), GPU T4 trên Colab. Đánh giá trên cùng tập `data/test` (100 ảnh). `clean` là **bản nháp Hold** (`manifest_sha1 = f1fbd72…`), còn 38 ảnh có cảnh báo chưa duyệt. Bảng lấy từ `submission/results/comparison.md`:

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

**Chênh mAP50 (clean − raw) = −0,025.** Con số này **bằng đúng độ lệch chuẩn giữa các seed của `clean`** (0,025). Hai seed của `clean` cho 0,718 và 0,683, chênh nhau 0,035. Riêng seed 0 thì chỉ chênh −0,008 (0,718 so với 0,726). Với 2 seed và 100 ảnh test, khoảng chênh này **nằm trong nhiễu**. Vì vậy **chưa kết luận được** rằng clean kém hơn hay tốt hơn raw. Điều duy nhất nói được là, trong thí nghiệm này, làm sạch **không cho thấy lợi ích đo được** về mAP50.

Phân rã theo lớp cho thấy phần lớn khoảng chênh đến từ **truck**. AP50 của truck ở clean là 0,590 và 0,486, còn ở raw là 0,657 và 0,640. Car và person gần như không đổi (car khoảng 0,74 so với 0,74, person khoảng 0,82 so với 0,82). Truck chỉ có 41 box và bus 32 box (`class_stats.csv`), nên mỗi seed dao động rất mạnh.

**Giả thuyết và cách kiểm:**
1. **Rò rỉ test làm điểm của raw bị thổi phồng.** Raw chứa 5 ảnh `LEAK_TEST` trùng đúng ảnh test (`test_009`, `test_033`, `test_039`, `test_044`, `test_085`), nên model raw đã "thấy" một phần đề thi. *Cách kiểm:* đánh giá lại cả hai model trên test **sau khi bỏ 5 ảnh đó** (95 ảnh). Nếu raw tụt nhiều hơn clean thì một phần lợi thế của raw là do rò rỉ.
2. **Clean ít dữ liệu hơn, lớp hiếm bị ảnh hưởng nhiều nhất.** Clean có ít hơn 22 ảnh (−10%). Autofix còn xoá 20 dòng nhãn, và 3 file nhãn thành rỗng. Với lớp truck vốn đã ít box, mất vài box là đủ làm AP dao động. *Cách kiểm:* đếm box truck/bus trong `clean_v1/labels` so với raw. Tăng lên ≥ 5 seed để ước lượng độ lệch đáng tin hơn. Train thêm một biến thể "raw chỉ bỏ 5 ảnh leak" để tách tác động của rò rỉ khỏi tác động của việc làm sạch.
3. **Clean vẫn còn nhãn máy chưa duyệt.** Bản này là Hold: 45 ảnh trong hàng đợi chưa được duyệt, còn 16 cờ `LOOSE_BOX` và 11 cờ `FALSE_POS`. Ngoài ra 80 ảnh được người duyệt chiếm chưa đến 40% bộ dữ liệu, nên khác biệt giữa raw và clean về chất lượng nhãn có thể quá nhỏ để thấy được trên 100 ảnh test. *Cách kiểm:* duyệt hết hàng đợi để gate ra Release, rồi train lại và so sánh.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: HOLD, chưa phát hành `clean_v1`.** Để chuyển thành Release, số ảnh còn cảnh báo chưa duyệt phải giảm từ 38 xuống dưới 20,2 (10% của 202). Tức là cần duyệt thêm **≥ 18 ảnh**, tiếp tục từ `img_0210` trong `05_review_queue.csv`. Không nên hạ `conf` hay nâng ngưỡng chỉ để hàng đợi vừa ngân sách, vì checker gần như không thấy lỗi thì sẽ ra một Release giả.

**(b) Có dùng AI (Claude Code).**
- *Prompt chính:* dán docstring của module cùng file test tương ứng, yêu cầu viết `label_format`, `gate`, `autofix`, `second_opinion`, giải thích từng dòng bằng tiếng Việt, không viết cứng ngưỡng, không sửa `data/raw`.
- *Cách kiểm:* đọc lướt theo `docs/PROMPTING.md`. Chỉ `autofix` xoá file, và chỉ trong `ds`. Không có `except: pass`, mọi chỗ chỉ bắt `ValueError` rồi báo thành issue hoặc ghi vào `fixes`. Mọi ngưỡng đọc từ `cfg`. Sau đó chạy `pytest` và chạy pipeline trên raw, mở xem kết quả bằng ảnh.
- *Một lần AI sai:* AI đề xuất `phash_dist = 8` chỉ dựa trên bảng sweep của calib. Khi mình tính khoảng cách mọi cặp ảnh trên raw rồi mở xem, 8 bỏ sót cặp trùng `img_0061/img_0186` (khoảng cách 10). Mình sửa thành 12 và chạy lại `make calibrate` + `make run`. Kết quả không đổi trên calib, và trên raw bắt thêm được 1 ảnh trùng.
