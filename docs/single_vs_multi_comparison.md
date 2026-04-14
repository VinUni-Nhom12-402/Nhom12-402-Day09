# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Nhóm 12 — 402  
**Ngày:** 2026-04-14  
**Pipeline Day 09:** Supervisor-Worker Multi-Agent (LangGraph StateGraph)

> So sánh Day 08 (single-agent RAG) với Day 09 (supervisor-worker multi-agent).  
> Số liệu Day 08 từ `eval.py` scorecard. Số liệu Day 09 từ `artifacts/grading_run.jsonl` (10 câu grading) và `artifacts/traces/` (15 traces).

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|----------------------|-------|---------|
| Avg Faithfulness | 3.70 / 5 | N/A | — | Day 09 không có LLM-as-judge |
| Avg Relevance | 4.20 / 5 | N/A | — | Day 09 không có LLM-as-judge |
| Avg Context Recall | 5.00 / 5 | N/A | — | Day 09 không có LLM-as-judge |
| Avg Completeness | 4.00 / 5 | N/A | — | Day 09 không có LLM-as-judge |
| Avg confidence score | N/A | **0.74** | — | Day 08 không có confidence metric |
| HITL triggered | N/A | 1 / 10 (10%) | — | gq07 abstain đúng, confidence=0.3 |
| Abstain rate (đúng) | 10% (1/10) | **20% (2/10)** | ↑ +10% | Day 09: gq07 + gq02 đều abstain đúng |
| Hallucination cases | 1 (q10: 1/5 faithful) | **0** | ↓ −1 | Day 09: không bịa số liệu, không tự suy chính sách cũ |
| Avg latency — simple query | ~2,000ms (est.) | **1,492ms** | ↓ −508ms | gq05/gq06/gq07/gq08 avg |
| Avg latency — policy query | ~2,000ms (est.) | **6,454ms** | ↑ +4,454ms | gq02/gq03/gq04/gq09/gq10 avg |
| Multi-hop accuracy | Thấp (q03, q10: 1/5) | **Trung bình** | ↑ | gq03 full marks, gq09 partial |
| Routing visibility | ✗ Không có | ✓ `route_reason` mỗi trace | — | |
| MCP tool calls | ✗ | 7 calls (5× search_kb, 2× get_ticket_info) | — | gq02–gq04, gq09, gq10 |

> **Lưu ý:** Day 08 dùng LLM-as-judge cho 4 metrics (Faithfulness/Relevance/Recall/Completeness).  
> Day 09 dùng trace-based metrics (confidence, HITL rate, latency) — hai hệ thống đo khác nhau nên không so sánh trực tiếp.

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document lookup)

| | Day 08 | Day 09 |
|--|--------|--------|
| Ví dụ | q01, q04 | gq04, gq05, gq06, gq08 |
| Accuracy | Cao (q01: 5/5 faithful) | Cao — gq04/gq05/gq06/gq08 full marks |
| Avg latency | ~2,000ms | **1,492ms** (gq05–gq08) |
| Routing | N/A — single pipeline | `retrieval_worker` → `synthesis_worker` |
| Observation | Pipeline thẳng, ít overhead | Supervisor overhead ~200ms, bù lại bằng retrieval nhẹ hơn |

**Kết luận:** Với câu đơn giản, Day 09 có latency tương đương hoặc thấp hơn Day 08. Supervisor phân loại đúng 100% các câu loại này sang `retrieval_worker`.

---

### 2.2 Câu hỏi multi-hop (cross-document)

| | Day 08 | Day 09 |
|--|--------|--------|
| Ví dụ | q13, q15 | gq03, gq09 |
| Accuracy | Thấp — dễ trộn lẫn context | gq03 full, gq09 partial (SLA thiếu PagerDuty) |
| Avg latency | ~2,000ms | **7,972ms** (gq03: 6,795ms; gq09: 9,148ms) |
| MCP tools | ✗ | search_kb + get_ticket_info (2 calls cho gq03, gq09) |
| Trace | Không có | `workers_called: [policy_tool_worker, retrieval_worker, synthesis_worker]` rõ ràng |

**Kết luận:** Multi-agent có lợi thế rõ ở câu multi-hop — supervisor route đúng sang `policy_tool_worker`, MCP tools gọi đúng loại. Latency cao hơn Day 08 nhưng đánh đổi được bằng accuracy và traceability.

---

### 2.3 Câu hỏi cần abstain (thông tin không có trong tài liệu)

| | Day 08 | Day 09 |
|--|--------|--------|
| Ví dụ | q09, q10 | gq07, gq02 |
| Abstain đúng | q09: đúng; q10: hallucinate (1/5) | gq07: đúng; gq02: đúng (từ chối suy v3 từ v4) |
| Mechanism | LLM tự quyết định | confidence < 0.4 → `hitl_triggered=True`; policy_version_note → hard-stop |
| Hallucination | 1 case (q10) | **0 case** |

**Kết luận:** Day 09 xử lý abstain tốt hơn qua 2 cơ chế độc lập: confidence threshold cho trường hợp thiếu evidence, và policy version guard trong `synthesis_worker` cho trường hợp version không khớp. Day 08 q10 hallucinate vì single agent không có circuit breaker.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow

```
Khi answer sai → phải đọc toàn bộ RAG pipeline code → tìm lỗi ở indexing/retrieval/generation
Không có trace → không biết bắt đầu từ đâu
Thời gian ước tính: ~15–20 phút
```

### Day 09 — Debug workflow

```
Khi answer sai → đọc grading_run.jsonl → xem supervisor_route + sources
  → Nếu route sai → sửa supervisor routing logic trong graph.py
  → Nếu sources sai → test retrieval_worker độc lập
  → Nếu synthesis sai → test synthesis_worker độc lập
Thời gian thực tế trong lab: ~5 phút mỗi bug
```

**Ví dụ debug thực tế trong lab:**

| Lỗi | Phát hiện qua | Fix |
|-----|--------------|-----|
| gq08: "Không đủ thông tin" dù `it_helpdesk_faq.txt` có đáp án | `sources` trong grading_run không có `it_helpdesk_faq.txt` | Thêm keyword fallback vào `retrieval.py` |
| gq01/gq09 degraded sau khi re-index | `sources` chỉ còn 1 file thay vì 3 → section chunking tách nhỏ SLA doc | Tăng `DEFAULT_TOP_K` từ 3 → 5 |
| gq02 hallucinate v3 | Đọc `answer` trực tiếp trong JSONL | Đặt `policy_version_note` lên đầu context trước tài liệu |

Cả 3 bug đều được xác định chính xác trong < 5 phút nhờ trace ghi `sources`, `workers_called`, `confidence` cho từng câu.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|----------|--------|--------|
| Thêm 1 tool/API mới | Sửa toàn prompt + RAG pipeline | Thêm tool vào `mcp_server.py`, đăng ký trong `policy_tool.py` |
| Thêm 1 loại policy mới | Phải retrain/re-prompt toàn bộ | Thêm rule vào `analyze_policy()`, không đụng worker khác |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline duy nhất | Sửa `workers/retrieval.py` độc lập — test với `python workers/retrieval.py` |
| A/B test một phần | Khó — phải clone toàn pipeline | Swap worker, giữ nguyên supervisor + synthesis |
| Audit trail | ✗ | ✓ `worker_io_logs` + `history` mỗi trace |

**Ví dụ thực tế:** Khi thêm keyword fallback vào `retrieval.py`, chỉ sửa 1 file, không cần chạm vào `graph.py`, `synthesis.py`, hay `policy_tool.py`. Fix gq08 mà không làm hỏng gq02–gq07.

---

## 5. Cost & Latency Trade-off

| Loại query | Day 08 LLM calls | Day 09 LLM calls | Day 09 MCP calls | Day 09 avg latency |
|-----------|-----------------|-----------------|-----------------|-------------------|
| Simple retrieval (gq05, gq06, gq08) | 1 | 1 (synthesis only) | 0 | 1,492ms |
| Policy query (gq04, gq10) | 1 | 1 (synthesis) | 1 (search_kb) | 4,105ms |
| Multi-hop (gq03, gq09) | 1 | 1 (synthesis) | 2 (search_kb + get_ticket_info) | 7,972ms |
| Abstain — HITL (gq07) | 1 | 0 (HITL, skip synthesis) | 0 | 1,122ms |

**Nhận xét:** Supervisor dùng rule-based routing (không gọi LLM) → không tốn thêm token so với Day 08. Chi phí tăng chủ yếu từ MCP network calls cho policy queries. Với câu `risk_high` (gq07), Day 09 còn rẻ hơn Day 08 vì không gọi LLM.

---

## 6. Grading Questions — Kết quả thực tế

| ID | Điểm tối đa | Kết quả Day 09 | Ghi chú |
|----|------------|---------------|---------|
| gq01 | 10 | Partial | Có PagerDuty + thời gian đúng, thiếu Slack + email |
| gq02 | 10 | Full | Abstain đúng, không suy v3 từ v4 |
| gq03 | 10 | Full | 3 approvers, IT Security cuối |
| gq04 | 6 | Partial | 110% đúng, thiếu giải thích bonus 10% |
| gq05 | 8 | Full | Escalate → Senior Engineer đúng |
| gq06 | 8 | Full | Probation block, 2 ngày/tuần, Team Lead |
| gq07 | 10 | Full | Abstain đúng, không hallucinate số phạt |
| gq08 | 8 | Full | 90 ngày + 7 ngày cảnh báo từ `it_helpdesk_faq.txt` |
| gq09 | 16 | Partial | SLA steps có Slack + email, Level 2 approver chưa đủ chính xác |
| gq10 | 10 | Partial | Flash Sale exception đúng, thiếu cite "Điều 3" rõ |
| **Ước tính** | **96** | **~79** | **~82% → ~24.7 / 30 grading điểm** |

---

## 7. Kết luận

**Multi-agent tốt hơn single agent ở:**

1. **Anti-hallucination** — 0 hallucination cases vs 1 ở Day 08. Cơ chế kép: confidence threshold + policy version guard.
2. **Abstain chính xác** — 2/10 câu abstain đúng (gq02 + gq07). Day 08 q10 hallucinate cùng scenario.
3. **Debuggability** — mỗi trace ghi đủ `supervisor_route`, `route_reason`, `sources`, `confidence`. Bug được xác định và fix trong < 5 phút.
4. **Extensibility** — thêm keyword fallback vào retrieval, thêm policy version guard vào synthesis, không làm hỏng component khác.
5. **Multi-hop queries** — gq03 full marks, gq09 partial nhờ MCP tools gọi đúng loại.

**Multi-agent kém hơn hoặc không khác biệt ở:**

1. **Latency cho policy queries** — 6,454ms vs ~2,000ms Day 08. MCP network calls là chi phí chính.
2. **Dependency chain** — section chunking làm gq01/gq09 degraded; cần tăng top_k để bù. Day 08 single pipeline ít điểm lỗi hơn.
3. **Setup complexity** — ChromaDB index, MCP server, LangGraph StateGraph, nhiều worker file cần maintain.

**Khi nào KHÔNG nên dùng multi-agent:**  
Use case đơn giản, single-domain, không cần audit trail, latency là ưu tiên. Chatbot FAQ với 1 document source — single RAG agent là đủ và nhanh hơn 4×.

**Nếu tiếp tục phát triển:**  
(1) Dùng multilingual embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) thay `all-MiniLM-L6-v2` để cải thiện semantic search tiếng Việt. (2) Tăng độ chính xác gq01/gq09 bằng cách lưu section header vào chunk text để synthesis biết đây là "SLA P1 Notification Steps". (3) Level 2 emergency approver logic cần bổ sung vào `access_control_sop.txt` hoặc fine-tune policy_tool_worker để phân biệt Level 2 vs Level 3 approval chain.
