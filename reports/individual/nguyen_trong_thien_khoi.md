# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Trọng Thiên Khôi  
**Vai trò trong nhóm:** Trace & Eval Owner (Sprint 4)  
**Ngày nộp:** 2026-04-14  

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `eval_trace.py`
- Functions tôi implement: `run_test_questions()`, `run_grading_questions()`, `analyze_traces()`, `compare_single_vs_multi()`, `save_eval_report()`
- Output artifacts: `artifacts/traces/` (15 trace files `.json`), `artifacts/grading_run.jsonl`, `reports/group_report.md`

Tôi không implement bất kỳ worker nào — nhiệm vụ của tôi là gọi `run_graph()` từ `graph.py` cho từng câu hỏi, ghi lại toàn bộ output của pipeline dưới dạng trace JSON, sau đó tính metrics tổng hợp từ các traces đó.

**Cách công việc của tôi kết nối với phần của thành viên khác:**  
`eval_trace.py` phụ thuộc vào `graph.py` (Bùi Cao Chính) đã chạy được end-to-end. Tôi là người **đọc output của tất cả các worker** — nếu retrieval_worker trả về sources sai, synthesis_worker trả về confidence thấp, hay policy_tool_worker không gọi MCP đúng, tôi là người đầu tiên phát hiện qua `grading_run.jsonl`. Thực tế trong lab, tôi đã phát hiện 3 vấn đề và báo lại để nhóm sửa.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Dùng **JSONL streaming write** cho `grading_run.jsonl` thay vì collect tất cả rồi write một lần.

Khi implement `run_grading_questions()`, tôi có hai lựa chọn: (A) chạy tất cả 10 câu, lưu vào list, rồi `json.dump` cả list ra file; hoặc (B) sau mỗi câu, ghi ngay một dòng JSON vào file và flush.

Tôi chọn phương án B vì pipeline có thể crash giữa chừng — đặc biệt với `gq01` latency lên tới 54 giây do model loading. Nếu dùng phương án A, crash ở câu 7 sẽ mất toàn bộ kết quả 6 câu trước. Với streaming write, dù crash ở câu bất kỳ, tất cả câu đã chạy xong đều được ghi vào file và có thể nộp.

**Trade-off đã chấp nhận:** JSONL không phải valid JSON array nên không đọc được bằng `json.load()` thông thường — phải dùng `readlines()` và parse từng dòng. Tôi thêm comment trong code để nhắc điều này.

**Bằng chứng từ code:**

```python
with open(output_file, "w", encoding="utf-8") as out:
    for i, q in enumerate(questions, 1):
        # ...
        result = run_graph(question_text)
        record = { "id": q_id, "answer": ..., "sources": ..., ... }
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        # Flush ngay sau mỗi câu — không mất data nếu crash
```

Thực tế: trong session grading, gq01 mất 54,832ms (cold start model loading) nhưng các câu sau chỉ còn 800–9,000ms. Nếu dùng batch write, khoảng thời gian dài đó sẽ là rủi ro mất data.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** gq08 ("mật khẩu đổi sau bao nhiêu ngày") trả về "Không đủ thông tin" dù `it_helpdesk_faq.txt` có đáp án.

**Symptom:** Đọc `grading_run.jsonl` sau lần chạy đầu tiên, thấy gq08:
```json
{
  "answer": "Không đủ thông tin trong tài liệu nội bộ.",
  "sources": ["policy_refund_v4.txt", "hr_leave_policy.txt", "access_control_sop.txt"],
  "confidence": 0.3,
  "hitl_triggered": true
}
```
`it_helpdesk_faq.txt` không có trong `sources` dù câu hỏi rõ ràng về IT policy.

**Root cause:** Tôi xác định được từ trace: ChromaDB đang index mỗi file là 1 document lớn. Model embedding `all-MiniLM-L6-v2` là English-only — khi query tiếng Việt "mật khẩu", cosine similarity của whole-file `it_helpdesk_faq.txt` (chứa nhiều section không liên quan) thấp hơn các file nhỏ hơn như `policy_refund_v4.txt`. Kết quả là `it_helpdesk_faq.txt` không vào top-3.

**Cách sửa:** Tôi báo lại cho Trần Thị Kim Ngân (retrieval worker owner). Nhóm thực hiện 2 thay đổi: (1) re-index với section-based chunking (34 chunks từ 5 files), và (2) thêm keyword fallback trong `retrieval.py` — sau dense retrieval, nếu chunk nào có ≥40% từ khoá từ query thì bổ sung vào kết quả.

**Bằng chứng sau fix:**
```json
{
  "answer": "Nhân viên phải đổi mật khẩu sau 90 ngày. Hệ thống sẽ cảnh báo trước 7 ngày.",
  "sources": ["...", "it_helpdesk_faq.txt"],
  "confidence": 0.8,
  "hitl_triggered": false
}
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào:**  
Đọc và phân tích output pipeline nhanh. Trong session grading 1 tiếng, tôi phát hiện được 3 vấn đề (gq08 wrong sources, gq02 hallucinate v3, gq01/gq09 degraded sau re-index) chỉ bằng cách đọc `grading_run.jsonl` và so sánh `sources` với nội dung câu hỏi — không cần chạy lại pipeline từng bước.

**Tôi làm chưa tốt:**  
`analyze_traces()` tính metrics nhưng không có assertion hay alert — nếu một worker bị lỗi silent (trả về rỗng thay vì exception), metrics vẫn tính bình thường mà không có cảnh báo. Nên thêm validation check cho từng trace trước khi aggregate.

**Nhóm phụ thuộc vào tôi ở đâu:**  
`grading_run.jsonl` là artifact duy nhất được nộp cho chấm điểm grading section (30 điểm nhóm). Nếu file này thiếu field hay sai format, toàn bộ 30 điểm bị ảnh hưởng — không phải lỗi của worker nào mà là lỗi của pipeline runner.

**Phần tôi phụ thuộc vào thành viên khác:**  
`eval_trace.py` phải đợi `graph.py` chạy được end-to-end (Sprint 1+2+3 xong). Trong thực tế tôi bắt đầu test `run_test_questions()` ngay sau khi Sprint 1 xong với mock workers, sau đó swap worker thật vào dần.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **automated source validation** trong `analyze_traces()`: với mỗi câu trong `grading_questions.json`, kiểm tra xem `sources` trong trace có chứa file được kỳ vọng không (ví dụ gq08 phải có `it_helpdesk_faq.txt`, gq01 phải có `sla_p1_2026.txt`). Bằng chứng từ trace: gq08 ban đầu fail vì tôi chỉ đọc `answer` mà không check `sources` ngay — nếu có validation tự động, tôi sẽ phát hiện ngay sau lần chạy đầu tiên thay vì phải đọc thủ công từng dòng JSONL.

---

*Lưu tại: `reports/individual/nguyen_trong_thien_khoi.md`*
