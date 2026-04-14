# Routing Decisions Log — Lab Day 09

**Nhóm:** Nhom12-402  
**Ngày:** 2026-04-14

> **Hướng dẫn:** Ghi lại ít nhất **3 quyết định routing** thực tế từ trace của nhóm.
> Không ghi giả định — phải từ trace thật (`artifacts/traces/`).
> 
> Mỗi entry phải có: task đầu vào → worker được chọn → route_reason → kết quả thực tế.

---

## Routing Decision #1

**Task đầu vào:**
> SLA xử lý ticket P1 là bao lâu?

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `task contains retrieval keyword`  
**MCP tools được gọi:** Không có (`needs_tool = false`)  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): "Không đủ thông tin trong tài liệu nội bộ để xác định SLA xử lý ticket P1."
- confidence: 0.3
- Correct routing? **Yes**

**Nhận xét:**  
Routing đúng worker — task chứa từ khoá "sla", "ticket", "p1" khớp `retrieval_keywords`. Tuy nhiên synthesis abstain với confidence 0.3 vì top-3 chunks từ `sla_p1_2026.txt` lấy nhầm về P2/P3 (embedding similarity thấp ~0.60 cho P1 chunk cụ thể). HITL được tự động trigger (`hitl_triggered=True` do confidence < 0.4). Đây là vấn đề chất lượng retrieval (top-k chưa lấy đúng chunk P1), không phải lỗi routing logic.

---

## Routing Decision #2

**Task đầu vào:**
> Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword`  
**MCP tools được gọi:** `search_kb` (thành công, trả về chunks từ `policy_refund_v4.txt`)  
**Workers called sequence:** `policy_tool_worker → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): "Không, khách hàng không thể yêu cầu hoàn tiền cho sản phẩm lỗi trong trường hợp Flash Sale. Theo chính sách, đơn hàng Flash Sale không được hoàn tiền [1]."
- confidence: 0.68
- Correct routing? **Yes**

**Nhận xét:**  
Routing chính xác — task chứa "flash sale" và "hoàn tiền" khớp `policy_keywords`. `policy_tool_worker` phát hiện đúng exception `flash_sale_exception` qua rule-based check. Retrieval lấy được chunk score cao nhất 0.81 từ `policy_refund_v4.txt` (Điều 3). Synthesis tổng hợp câu trả lời rõ ràng có citation. Pipeline hoạt động end-to-end đúng.

---

## Routing Decision #3

**Task đầu vào:**
> Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword | risk_high flagged`  
**MCP tools được gọi:** `search_kb`, `get_ticket_info` (IT-9847 P1 in_progress, escalated)  
**Workers called sequence:** `policy_tool_worker → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer (đầy đủ):
  > Để cấp quyền Level 3 khắc phục sự cố P1 khẩn cấp, quy trình như sau:
  > 1. **Phê duyệt**: On-call IT Admin cần được Tech Lead phê duyệt bằng lời.
  > 2. **Cấp quyền tạm thời**: Quyền được cấp tạm thời tối đa 24 giờ.
  > 3. **Ticket chính thức**: Sau 24 giờ cần có ticket chính thức, nếu không quyền sẽ bị thu hồi tự động.
  > 4. **Ghi log**: Tất cả quyền tạm thời phải được ghi log vào hệ thống Security Audit. [1][2]
- confidence: 0.68
- Sources: `access_control_sop.txt`, `sla_p1_2026.txt`
- Correct routing? **Yes**

**Nhận xét:**  
Supervisor đặt đúng cả hai flag: `risk_high=True` (chứa "khẩn cấp") và `needs_tool=True` (chứa "level 3"). MCP `get_ticket_info` trả về IT-9847 đang escalate, cung cấp context thực tế. Retrieval lấy chunk về quy trình escalation khẩn cấp từ `access_control_sop.txt`. Synthesis tổng hợp câu trả lời có 4 bước rõ ràng với citation. End-to-end hoạt động tốt sau khi API key được cấu hình đúng.

---

## Routing Decision #4 (tuỳ chọn — bonus)

**Task đầu vào:**
> Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình.

**Worker được chọn:** `policy_tool_worker`  
**Route reason:** `task contains policy/access keyword | risk_high flagged`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**  
Task này đồng thời yêu cầu **hai loại thông tin**: (1) quy trình cấp quyền Level 2 emergency → thuộc `policy_tool_worker`, và (2) SLA notification cho P1 ticket → thuộc `retrieval_worker`. Supervisor chỉ chọn được **một** route duy nhất — đây là điểm yếu cơ bản của keyword-based single-route architecture.  

May mắn thay, pipeline có fallback tự nhiên: sau `policy_tool_worker`, `retrieval_worker` vẫn được gọi tự động khi chunks rỗng. Kết quả (confidence=0.65) trả lời đúng cả hai quy trình từ `access_control_sop.txt` và `sla_p1_2026.txt`. Đây là trường hợp "vô tình đúng" nhờ pipeline design chứ không nhờ routing logic.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 1 | 25% |
| policy_tool_worker | 3 | 75% |
| human_review | 0 | 0% |

### Routing Accuracy

> Trong số 4 câu nhóm đã chạy, bao nhiêu câu supervisor route đúng?

- Câu route đúng: **4 / 4**
- Câu route sai (đã sửa bằng cách nào?): 0
- Câu trigger HITL: 1 (Decision #1 — synthesis tự set `hitl_triggered=True` khi confidence 0.3 < 0.4)

### Lesson Learned về Routing

> Quyết định kỹ thuật quan trọng nhất nhóm đưa ra về routing logic là gì?

1. **Ưu tiên policy_keywords trước retrieval_keywords bằng `if/elif`**: Nếu task chứa cả "p1" lẫn "access", supervisor ưu tiên `policy_tool_worker`. Quyết định này đúng vì câu hỏi về access control cần policy check phức tạp hơn chỉ retrieval đơn thuần.
2. **risk_high là metadata flag, không phải routing override**: `risk_high=True` không tự động chuyển sang `human_review` trừ khi đi kèm unknown error code (`err-`). Điều này tránh over-blocking các câu hỏi khẩn cấp nhưng có context rõ ràng — vẫn cho pipeline xử lý thẳng để ra kết quả nhanh hơn.

### Route Reason Quality

> Nhìn lại các `route_reason` trong trace — chúng có đủ thông tin để debug không?

Hiện tại `route_reason` ở dạng string đơn giản như `"task contains policy/access keyword | risk_high flagged"`. Đủ để biết *worker nào* được chọn và *loại trigger nào*, nhưng **chưa đủ** để debug routing sai vì không chỉ rõ keyword cụ thể nào đã match và không có confidence score.

**Cải tiến đề xuất**: Format `route_reason` thành structured JSON:
```json
{
  "matched_keywords": ["level 3", "khẩn cấp"],
  "rule_applied": "policy_keywords_match",
  "risk_factors": ["khẩn cấp"],
  "override": null
}
```
Điều này giúp `eval_trace.py` parse và thống kê routing pattern tự động.
