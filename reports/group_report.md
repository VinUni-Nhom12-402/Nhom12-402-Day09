# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Nhóm 12 — 402  
**Thành viên:**

| Tên | MSSV | Vai trò |
|-----|------|---------|
| [Bùi Cao Chính] | [MSSV] | Supervisor & Graph Owner |
| [Trần Thị Kim Ngân] | [MSSV] | Retrieval Worker Owner |
| [Dương Chí Thành] | [MSSV] | Policy Tool Worker Owner |
| [Phan Xuân Quang Linh] | [MSSV] | MCP Server Owner |
| [Nguyễn Đức Tiến] | [MSSV] | Synthesis Worker Owner |
| [Nguyễn Trọng Thiên Khôi] | [MSSV] | Trace & Eval Owner |

**Ngày nộp:** 2026-04-14  
**Repo:** VinUni-Nhom12-402/Nhom12-402-Day09

---

## 1. Kiến trúc nhóm đã xây dựng

Hệ thống Day 09 được xây dựng theo mô hình **Supervisor-Worker Multi-Agent** dùng **LangGraph StateGraph**. Pipeline gồm 1 supervisor node và 4 worker nodes kết nối thành directed graph:

```
supervisor → retrieval_worker → synthesis → END
supervisor → policy_tool_worker → retrieval_worker → synthesis → END
supervisor → human_review → retrieval_worker → synthesis → END
```

Tổng cộng **3 workers chính** (retrieval, policy_tool, synthesis) và 1 HITL node (human_review). Shared state truyền qua `AgentState` TypedDict, mỗi worker đọc và ghi fields riêng theo `worker_contracts.yaml`.

**Routing logic cốt lõi:**  
Supervisor dùng **rule-based keyword matching** — không gọi LLM. Task được scan theo 3 điều kiện theo thứ tự ưu tiên:
1. Chứa từ khoá `policy`, `access`, `level`, `hoàn tiền`, `refund`, `phê duyệt` → `policy_tool_worker`
2. Chứa từ khoá `sla`, `ticket`, `escalat`, `remote`, `leave`, `mật khẩu` → `retrieval_worker`
3. `risk_high=True` (confidence < 0.4 sau retrieval sơ bộ) → `human_review`

Không dùng LLM classifier để giữ latency thấp và routing deterministic — dễ debug khi sai.

**MCP tools đã tích hợp:**
- `search_kb`: Tìm kiếm knowledge base qua ChromaDB, trả về top-3 chunks có relevance score. Được gọi trong 5/10 grading questions (gq02–gq04, gq09, gq10).
- `get_ticket_info`: Truy vấn thông tin ticket theo ID, trả về severity và trạng thái. Được gọi trong 2/10 grading questions (gq03, gq09).

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định: Chunking strategy cho ChromaDB — whole-file vs section-based**

**Bối cảnh vấn đề:**  
Khi indexing 5 tài liệu vào ChromaDB, nhóm phải chọn cách chia chunk. Ban đầu index mỗi file thành 1 document (whole-file). Kết quả: gq08 ("mật khẩu đổi sau bao nhiêu ngày") trả về "Không đủ thông tin" dù `it_helpdesk_faq.txt` có đáp án rõ — vì embedding của cả file bị "trung bình hóa", không capture được section cụ thể.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Whole-file (1 chunk/file) | Đơn giản, context đầy đủ, tốt cho multi-hop | Embedding bị dilute, câu hỏi cụ thể không match được đúng file |
| Section-based chunking (split theo `=== ... ===`) | Retrieval chính xác hơn cho câu cụ thể | Section nhỏ → multi-hop query có thể miss info từ section khác |
| Fixed-size sliding window | Phổ biến | Cắt giữa câu, mất ngữ nghĩa đoạn Q&A |

**Phương án đã chọn:**  
Section-based chunking kết hợp với tăng `DEFAULT_TOP_K = 5` và **keyword fallback** trong `retrieval.py`. Kết quả: 34 chunks từ 5 files. gq08 được fix (it_helpdesk_faq.txt Section 1 match đúng). top_k=5 giúp multi-hop query lấy được nhiều section SLA hơn.

**Bằng chứng từ trace:**

Trước fix (whole-file, top_k=3) — gq08:
```json
{
  "answer": "Không đủ thông tin trong tài liệu nội bộ.",
  "sources": ["policy_refund_v4.txt", "hr_leave_policy.txt", "access_control_sop.txt"],
  "confidence": 0.3,
  "hitl_triggered": true
}
```

Sau fix (section chunking + keyword fallback, top_k=5) — gq08:
```json
{
  "answer": "Nhân viên phải đổi mật khẩu sau 90 ngày. Hệ thống sẽ cảnh báo trước 7 ngày.",
  "sources": ["policy_refund_v4.txt", "hr_leave_policy.txt", "access_control_sop.txt", "sla_p1_2026.txt", "it_helpdesk_faq.txt"],
  "confidence": 0.8,
  "hitl_triggered": false
}
```

---

## 3. Kết quả grading questions

**Tổng điểm raw ước tính: ~79 / 96**  
Quy đổi: 79/96 × 30 ≈ **24.7 / 30 điểm** cho grading section.

**Câu pipeline xử lý tốt nhất:**
- **gq02** — Nhận ra đơn đặt 31/01/2026 phải dùng chính sách v3 (không phải v4 đang có), abstain đúng hoàn toàn mà không hallucinate. Cơ chế: `policy_version_note` được đặt đầu context, synthesis_worker có rule cứng ngừng suy luận khi thấy cảnh báo version.
- **gq07** — Không bịa mức phạt tài chính dù câu hỏi có vẻ hợp lý. Confidence=0.3 trigger HITL đúng.
- **gq08** — Sau khi fix chunking: truy xuất đúng "90 ngày, cảnh báo 7 ngày" từ `it_helpdesk_faq.txt`.

**Câu pipeline partial:**
- **gq01** (10 điểm) — Trả lời được deadline 10 phút và đề cập PagerDuty, nhưng thiếu Slack #incident-p1 và email incident@company.internal. Root cause: SLA doc có nhiều section, section về kênh notification không phải top-1 chunk.
- **gq09** (16 điểm) — SLA steps nêu được Slack + email nhưng thiếu PagerDuty; Level 2 emergency approver ghi "Tech Lead" thay vì "Line Manager VÀ IT Admin on-call". Root cause: `access_control_sop.txt` section Level 2 và Level 3 emergency dùng thuật ngữ khác nhau, retrieval chỉ lấy được 1 section.

**Câu gq07 (abstain):**  
Pipeline trả về "Không đủ thông tin trong tài liệu nội bộ" và trigger `hitl_triggered=True` nhờ confidence=0.3. `synthesis_worker` detect keyword "Không đủ thông tin" để hạ confidence xuống 0.3, thấp hơn threshold 0.4 → HITL. Không hallucinate bất kỳ con số phạt nào.

**Câu gq09 (multi-hop khó nhất):**  
Trace ghi đủ 2 workers: `workers_called: ["policy_tool_worker", "retrieval_worker", "synthesis_worker"]` và 2 MCP tools: `mcp_tools_used: ["search_kb", "get_ticket_info"]`. Kết quả partial — phần SLA notification đúng cấu trúc nhưng thiếu PagerDuty; phần Level 2 access có logic nhưng approver chain chưa chính xác.

---

## 4. So sánh Day 08 vs Day 09 — Điều nhóm quan sát được

**Metric thay đổi rõ nhất:**

| Metric | Day 08 | Day 09 | Delta |
|--------|--------|--------|-------|
| Hallucination cases | 1 (q10: 1/5 faithful) | 0 | ↓ −1 |
| Abstain đúng | 1/10 (10%) | 2/10 (20%) | ↑ +10% |
| Avg latency — simple query | ~2,000ms | 1,492ms | ↓ −25% |
| Avg latency — policy/multi-hop | ~2,000ms | 6,454ms | ↑ +3× |
| Debug time khi có bug | ~15–20 phút | ~5 phút | ↓ −75% |

**Điều nhóm bất ngờ nhất:**  
Supervisor rule-based routing (không dùng LLM) lại routing chính xác 10/10 câu grading. Nhóm ban đầu lo ngại sẽ phải dùng LLM classifier để xử lý edge cases, nhưng keyword matching đơn giản hoạt động tốt cho domain nội bộ có vocabulary đặc thù (P1, Level 3, Flash Sale, probation).

**Trường hợp multi-agent KHÔNG giúp ích:**  
Với câu đơn giản như gq05 ("on-call không phản hồi 10 phút, hệ thống làm gì"), pipeline phải qua supervisor → retrieval → synthesis — 3 bước thay vì 1. Latency 1,703ms vs ~2,000ms Day 08 — gần như không khác biệt nhưng code phức tạp hơn nhiều. Single-agent xử lý câu này tốt như nhau.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| [Bùi Cao Chính] | `graph.py` — AgentState, supervisor_node, route_decision, LangGraph StateGraph; `docs/system_architecture.md`, `docs/routing_decisions.md` | 1 |
| [Trần Thị Kim Ngân] | `workers/retrieval.py` — ChromaDB dense retrieval, keyword fallback, embedding pipeline; `build_index.py` section chunking; `contracts/worker_contracts.yaml` (retrieval section) | 2 |
| [Dương Chí Thành] | `workers/policy_tool.py` — exception detection (Flash Sale, digital product, version mismatch), LLM policy analysis, MCP client integration; `contracts/worker_contracts.yaml` (policy section) | 2–3 |
| [Phan Xuân Quang Linh] | `mcp_server.py` — FastAPI HTTP server, `search_kb` tool, `get_ticket_info` tool; tích hợp MCP vào policy_tool_worker | 3 |
| [Nguyễn Đức Tiến] | `workers/synthesis.py` — context builder, confidence scoring, LLM call, citation; `contracts/worker_contracts.yaml` (synthesis section); `docs/single_vs_multi_comparison.md` | 2 |
| [Nguyễn Trọng Thiên Khôi] | `eval_trace.py` — test runner 15 câu, trace logger, grading mode; `artifacts/traces/` và `artifacts/grading_run.jsonl`; `reports/group_report.md` | 4 |

**Điều nhóm làm tốt:**  
Anti-hallucination được xử lý ở nhiều tầng: (1) synthesis_worker có SYSTEM_PROMPT với rule cứng, (2) policy_version_note được đặt đầu context trước tài liệu, (3) confidence threshold tự động trigger HITL. Kết quả: 0 hallucination trong 10 grading questions.

**Điều nhóm làm chưa tốt:**  
Chunking strategy không được kiểm tra kỹ trước khi grading — whole-file indexing làm gq08 fail. Nhóm phát hiện và fix trong session grading nhưng cần thêm thời gian để tối ưu top_k và threshold cho tất cả query types.

**Nếu làm lại:**  
Validate retrieval quality sớm hơn bằng cách chạy thử từng grading question qua `retrieval.py` standalone để kiểm tra `sources` trả về trước khi chạy full pipeline.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

**Cải tiến 1 — Multilingual embedding model:**  
Thay `all-MiniLM-L6-v2` (English-only) bằng `paraphrase-multilingual-MiniLM-L12-v2`. Bằng chứng từ trace: gq08 cần keyword fallback thủ công vì semantic search tiếng Việt kém — retrieval chạy đúng nhưng chunk "mật khẩu 90 ngày" không lên top-3 theo cosine similarity. Multilingual model sẽ fix gốc rễ thay vì patch.

**Cải tiến 2 — Level 2 vs Level 3 emergency access phân biệt rõ trong policy_tool_worker:**  
gq09 trả lời sai approver vì `policy_tool_worker` không phân biệt được emergency path của Level 2 (Line Manager + IT Admin on-call, không cần IT Security) với Level 3 (3 approvers bao gồm IT Security). Bằng chứng: trace gq09 `mcp_tools_used: ["search_kb", "get_ticket_info"]` — tools gọi đúng nhưng synthesis nhận context lẫn lộn 2 approval chain. Fix: thêm access level vào rule matching của `analyze_policy()`.

---

*File này lưu tại: `reports/group_report.md`*  
*Commit sau 18:00 được phép theo SCORING.md*
