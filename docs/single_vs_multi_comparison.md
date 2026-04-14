# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Nhóm 12 — 402  
**Ngày:** 2026-04-14

> So sánh Day 08 (single-agent RAG) với Day 09 (supervisor-worker multi-agent).
> Số liệu Day 08 từ `eval.py` scorecard. Số liệu Day 09 từ `artifacts/traces/` (15 traces).

---

## 1. Metrics Comparison

> Điền vào bảng sau. Lấy số liệu từ:
>
> - Day 08: chạy `python eval.py` từ Day 08 lab
> - Day 09: chạy `python eval_trace.py` từ lab này

| Metric                | Day 08 (Single Agent)     | Day 09 (Multi-Agent) | Delta     | Ghi chú                                                         |
| --------------------- | ------------------------- | -------------------- | --------- | --------------------------------------------------------------- |
| Avg Faithfulness      | 3.70/5                    | N/A                  | —         | Day 09 không có LLM judge                                       |
| Avg Relevance         | 4.20/5                    | N/A                  | —         | Day 09 không có LLM judge                                       |
| Avg Context Recall    | 5.00/5                    | N/A                  | —         | Day 09 không có LLM judge                                       |
| Avg Completeness      | 4.00/5                    | N/A                  | —         | Day 09 không có LLM judge                                       |
| Avg confidence        | N/A                       | 0.10                 | —         | Day 08 không có confidence metric                               |
| Avg latency (ms)      | N/A                       | 3,622                | —         | Day 08 không đo latency                                         |
| Abstain rate (%)      | 10% (1/10 câu)            | 87% (13/15 câu)      | ↑ +77%    | Day 09 retrieval lỗi offline — lỗi môi trường, không phải logic |
| Multi-hop accuracy    | Thấp (q03: 1/5, q10: 1/5) | N/A                  | —         | Day 09 không có LLM judge để score                              |
| Routing visibility    | ✗ Không có                | ✓ Có route_reason    | N/A       |                                                                 |
| Debug time (estimate) | ~15 phút                  | ~3 phút              | ↓ 12 phút | Day 09 có trace JSON, xác định lỗi ngay từ `history[]`          |

> **Lưu ý:** Day 08 dùng LLM-as-Judge (Faithfulness/Relevance/Recall/Completeness), Day 09 dùng trace-based metrics — hai hệ thống đo khác nhau nên một số cột không so sánh trực tiếp được.

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét    | Day 08                               | Day 09                             |
| ----------- | ------------------------------------ | ---------------------------------- |
| Ví dụ       | q01 (SLA P1), q04 (tài khoản khóa)   | q01, q04, q05, q06, q08            |
| Accuracy    | Cao (q01: 5/5 faithful)              | 0% do retrieval lỗi                |
| Latency     | ~2000ms (est.)                       | 1,545–1,974ms                      |
| Observation | Single agent trả lời tốt, đủ context | Routing đúng nhưng không có chunks |

**Kết luận:** Với câu đơn giản, Day 08 cho kết quả tốt hơn vì pipeline thẳng không phụ thuộc nhiều component. Day 09 có overhead từ supervisor + nhiều worker, nhưng latency thực tế thấp hơn khi retrieval fail nhanh.

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét         | Day 08                                                    | Day 09                                            |
| ---------------- | --------------------------------------------------------- | ------------------------------------------------- |
| Ví dụ            | q13 (Contractor + P1 + Level 3), q15 (P1 + Level 2 + SLA) | q13, q15                                          |
| Accuracy         | Thấp — single agent không tách được domain                | Routing đúng: policy_tool_worker + 2 MCP calls    |
| Routing visible? | ✗                                                         | ✓ route_reason rõ ràng                            |
| Latency          | ~2000ms                                                   | 7,012ms (q13), 6,490ms (q15)                      |
| Observation      | Dễ hallucinate khi cross-domain                           | Gọi đúng search_kb + get_ticket_info, dù MCP fail |

**Kết luận:** Multi-agent có lợi thế rõ ở câu multi-hop — supervisor phân tách đúng domain, policy_tool_worker gọi đúng MCP tools. Latency cao hơn nhưng đánh đổi được bằng traceability.

### 2.3 Câu hỏi cần abstain

| Nhận xét            | Day 08                                   | Day 09                                             |
| ------------------- | ---------------------------------------- | -------------------------------------------------- |
| Ví dụ               | q09 (ERR-403-AUTH), q10 (store credit)   | q09                                                |
| Abstain rate        | 10% (q09 abstain đúng)                   | q09 → human_review đúng                            |
| Hallucination cases | q10: answer sai hoàn toàn (1/5 faithful) | q12: answer có logic đúng từ policy rule           |
| Observation         | q10 hallucinate vì không có context      | Day 09 q09 route → human_review, không hallucinate |

**Kết luận:** Day 09 xử lý abstain tốt hơn — supervisor detect `risk_high=True` cho q09 và route sang `human_review` thay vì để LLM đoán. Day 08 q10 hallucinate nghiêm trọng (1/5 faithful).

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
Khi answer sai → đọc trace JSON → xem supervisor_route + route_reason
  → Nếu route sai → sửa supervisor routing logic
  → Nếu retrieval sai → test retrieval_worker độc lập (python workers/retrieval.py)
  → Nếu synthesis sai → test synthesis_worker độc lập (python workers/synthesis.py)
Thời gian ước tính: ~3–5 phút
```

**Ví dụ debug thực tế trong lab:**  
q01 trả về "Không đủ thông tin" → đọc trace → thấy `[retrieval_worker] ERROR — RETRIEVAL_FAILED: couldn't connect to huggingface.co` → xác định ngay nguyên nhân là embedding model chưa cache, không phải lỗi logic. Không cần đọc code, chỉ cần đọc `history[]` trong trace.

---

## 4. Extensibility Analysis

| Scenario                    | Day 08                              | Day 09                                                      |
| --------------------------- | ----------------------------------- | ----------------------------------------------------------- |
| Thêm 1 tool/API mới         | Phải sửa toàn prompt + RAG pipeline | Thêm MCP tool vào `mcp_server.py` + route rule              |
| Thêm 1 domain mới           | Phải retrain/re-prompt toàn bộ      | Thêm 1 worker mới, supervisor tự route                      |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline        | Sửa `retrieval_worker` độc lập, không ảnh hưởng worker khác |
| A/B test một phần           | Khó — phải clone toàn pipeline      | Dễ — swap worker, giữ nguyên supervisor                     |
| Audit trail                 | ✗ Không có                          | ✓ `worker_io_logs` + `history` mỗi trace                    |

**Nhận xét:** Day 09 extensible hơn rõ rệt. Mỗi worker là một unit độc lập — test được, swap được, scale được riêng lẻ. Day 08 là monolith: sửa một chỗ có thể break toàn bộ.

---

## 5. Cost & Latency Trade-off

| Scenario                     | Day 08 LLM calls | Day 09 LLM calls        | Day 09 MCP calls                |
| ---------------------------- | ---------------- | ----------------------- | ------------------------------- |
| Simple query (q01, q04)      | 1                | 1 (synthesis only)      | 0                               |
| Policy query (q02, q07)      | 1                | 1 (synthesis)           | 1 (search_kb)                   |
| Complex multi-hop (q13, q15) | 1                | 1 (synthesis)           | 2 (search_kb + get_ticket_info) |
| Human review path (q09)      | 1                | 0 (HITL, không gọi LLM) | 0                               |

**Nhận xét về cost-benefit:**  
Day 09 không tốn thêm LLM calls so với Day 08 — supervisor dùng rule-based routing (không gọi LLM), chỉ synthesis_worker gọi LLM. Chi phí tăng chủ yếu từ MCP tool calls (network), không phải LLM tokens. Với câu `risk_high`, Day 09 còn tiết kiệm hơn vì route sang HITL thay vì để LLM hallucinate.

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở:**

1. **Traceability & debuggability** — mỗi trace có `supervisor_route`, `route_reason`, `worker_io_logs`, `history`. Tìm bug trong 3 phút thay vì 15 phút.
2. **Policy & exception handling** — `policy_tool_worker` detect đúng `digital_product_exception` (q07), `flash_sale_exception` (q12) mà single agent dễ bỏ sót hoặc hallucinate.
3. **Controlled abstain** — supervisor route `risk_high` sang `human_review` thay vì để LLM đoán, giảm hallucination.
4. **Extensibility** — thêm worker/tool mới không ảnh hưởng component khác.

**Multi-agent kém hơn hoặc không khác biệt ở:**

1. **Latency** — overhead từ supervisor + nhiều worker: avg 3,622ms vs ~2,000ms Day 08. Đặc biệt multi-hop lên tới 7,000ms.
2. **Dependency chain** — nếu một component fail (retrieval offline), toàn bộ pipeline degraded. Day 08 ít dependency hơn.
3. **Setup complexity** — cần build index, cấu hình MCP server, nhiều file hơn để maintain.

**Khi nào KHÔNG nên dùng multi-agent:**  
Khi use case đơn giản, single-domain, không cần audit trail, và latency là ưu tiên hàng đầu. Ví dụ: chatbot FAQ đơn giản với 1 document source — single RAG agent là đủ và nhanh hơn.

**Nếu tiếp tục phát triển:**  
Fix retrieval offline bằng cách cache embedding model local (`SENTENCE_TRANSFORMERS_HOME`), upgrade policy_tool_worker từ rule-based sang LLM-based analysis, và implement real MCP server thay vì mock để MCP tool calls thực sự trả về data.
