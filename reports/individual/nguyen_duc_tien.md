# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Đức Tiến  
**Vai trò trong nhóm:** Synthesis Worker Owner / Docs Owner  
**Ngày nộp:** 14/04/2026  
**Độ dài:** ~680 từ

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**

- File chính: `workers/synthesis.py`
- Functions tôi implement: `synthesize()`, `_build_context()`, `_estimate_confidence()`, `_call_llm()`, `run()`
- Contract: phần `synthesis_worker` trong `contracts/worker_contracts.yaml`
- Tài liệu: `docs/single_vs_multi_comparison.md`

Synthesis worker là điểm cuối của pipeline — nhận `retrieved_chunks` từ retrieval_worker và `policy_result` từ policy_tool_worker, gọi LLM để tổng hợp câu trả lời có citation, rồi ghi `final_answer`, `sources`, `confidence`, và `hitl_triggered` vào AgentState.

**Cách công việc của tôi kết nối với phần của thành viên khác:**  
Output của tôi (`final_answer`, `confidence`) là input trực tiếp cho eval_trace. Tôi phụ thuộc vào retrieval_worker (chunks phải có `{text, source, score}`) và policy_tool_worker (`exceptions_found` phải là list, không phải None). Nếu synthesis chưa xong, toàn bộ pipeline không có output để eval.

**Bằng chứng:** Commit `c8609ce` (branch `feature-synthesis`, author `ductiens`) và các thay đổi trong commit `76a0db6` trên `workers/synthesis.py`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Đổi cách tính `confidence` từ weighted average sang best-score với normalization về khoảng `[0.5, 0.95]`.

Có 2 lựa chọn ban đầu:

- **Option A (ban đầu):** Weighted average của tất cả chunk scores — `avg_score = sum(scores) / len(chunks)`
- **Option B (tôi sửa):** Lấy `best_score = max(scores)` rồi normalize theo ngưỡng

Lý do phải sửa: ChromaDB trả về cosine similarity trên full-doc, giá trị thực tế rất thấp (0.05–0.3). Dùng average thì confidence luôn ra ~0.1–0.15 dù answer đúng — không phân biệt được câu tốt và câu xấu. `hitl_triggered` bị set True toàn bộ, làm mất ý nghĩa của field này.

**Lý do chọn best-score + normalization:**  
Chunk có score cao nhất là chunk liên quan nhất — đó là tín hiệu đáng tin hơn average. Normalize về `[0.5, 0.95]` giúp confidence phản ánh thực tế hơn khi có chunks hợp lệ.

**Trade-off đã chấp nhận:** Confidence vẫn là heuristic, không chính xác bằng LLM-as-Judge. Nhưng đủ để phân biệt "có chunks tốt" vs "không có chunks".

**Bằng chứng từ code (git diff):**

```python
# Trước (average — luôn ra ~0.1)
avg_score = sum(c.get("score", 0) for c in chunks) / len(chunks)
confidence = min(0.95, avg_score - exception_penalty)

# Sau (best-score + normalization)
best_score = max(c.get("score", 0) for c in chunks)
if best_score >= 0.15:
    base = 0.8
elif best_score >= 0.05:
    base = 0.65
else:
    base = 0.5
confidence = min(0.95, base - exception_penalty)
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** Output bị lỗi encoding khi chạy trên Windows — các ký tự tiếng Việt trong `final_answer` bị garbled hoặc raise `UnicodeEncodeError` khi print ra terminal.

**Symptom:** Chạy `python workers/synthesis.py` trên Windows (PowerShell mặc định cp1252) thì output tiếng Việt bị vỡ hoặc crash với `UnicodeEncodeError: 'charmap' codec can't encode character`.

**Root cause:** Windows terminal mặc định không dùng UTF-8. `sys.stdout` và `sys.stderr` encode theo codepage hệ thống (cp1252), không handle được ký tự Unicode tiếng Việt.

**Cách sửa:** Thêm reconfigure ở đầu file trước khi bất kỳ print nào chạy:

```python
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
```

Dùng `hasattr` để guard — tránh crash trên môi trường không support `reconfigure` (Python < 3.7 hoặc một số CI runner).

**Bằng chứng:** Thay đổi này xuất hiện trong git diff của commit `76a0db6`, file `workers/synthesis.py`, lines +20 đến +25.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở:** Thiết kế `_build_context()` và system prompt — format context có số thứ tự `[i]`, tên source, relevance score giúp LLM biết cite từ đâu. Constraint "CHỈ trả lời dựa vào context" trong system prompt giảm hallucination rõ rệt so với prompt không có guardrail. Ngoài ra, `worker_contracts.yaml` phần synthesis tôi viết chi tiết hơn template ban đầu: thêm `hitl_triggered`, `llm_config`, `confidence_logic`, và schema đầy đủ cho `worker_io_logs`.

**Tôi làm chưa tốt ở:** Confidence vẫn là heuristic thô. Với câu multi-hop phức tạp (q13, q15), chunk score cao nhưng answer thiếu thông tin — confidence bị overestimate. Chưa có LLM-as-Judge để catch case này.

**Nhóm phụ thuộc vào tôi ở:** `final_answer`, `confidence`, `hitl_triggered` — eval_trace đọc 3 fields này để tính metrics và quyết định có flag HITL không. Nếu synthesis chưa xong hoặc output sai format, toàn bộ pipeline không có kết quả để đánh giá.

**Tôi phụ thuộc vào thành viên khác:** Retrieval worker (chunks đúng format `{text, source, score}`) và policy_tool_worker (`exceptions_found` là list). Trong lab này retrieval bị lỗi HuggingFace offline nên `retrieved_chunks=[]` toàn bộ — synthesis chỉ có thể abstain, không phải lỗi của synthesis worker.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement LLM-as-Judge để tính confidence chính xác hơn. Bằng chứng: trace q13 (`run_20260414_173012.json`) cho thấy policy_tool_worker gọi đúng 2 MCP tools (`search_kb` + `get_ticket_info`) nhưng cả hai đều fail với `MCP_HTTP_CALL_FAILED` — synthesis không có chunks nào để tổng hợp. Nếu có LLM-as-Judge, nó sẽ detect được "answer không cover đủ cả hai quy trình" và trả về confidence thấp thay vì để heuristic overestimate.
