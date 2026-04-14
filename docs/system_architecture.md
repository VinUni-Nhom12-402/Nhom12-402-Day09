# System Architecture — Lab Day 09

**Nhóm:** Nhom12-402  
**Ngày:** 2026-04-14  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

> Mô tả ngắn hệ thống của nhóm: chọn pattern gì, gồm những thành phần nào.

**Pattern đã chọn:** Supervisor-Worker  
**Lý do chọn pattern này (thay vì single agent):**

Hệ thống IT Helpdesk nội bộ xử lý nhiều loại yêu cầu có đặc điểm khác nhau: câu hỏi tra cứu SLA cần retrieval trực tiếp, câu hỏi về policy hoàn tiền cần kiểm tra rule-based exception, câu hỏi cấp quyền cần gọi external tool. Single agent không thể xử lý hiệu quả tất cả các loại này vì cần một prompt quá lớn và không thể debug từng bước. Supervisor-Worker cho phép **mỗi worker có chuyên môn riêng**, giảm hallucination và dễ dàng test độc lập từng thành phần.

---

## 2. Sơ đồ Pipeline

```
User Request (task: str)
        │
        ▼
┌──────────────────────┐
│      Supervisor      │  ← Phân tích task bằng keyword matching
│   (graph.py)         │    → supervisor_route, route_reason
│                      │    → risk_high, needs_tool
└──────────┬───────────┘
           │
       [route_decision]
           │
   ┌───────┴────────────────────────┐
   │               │                │
   ▼               ▼                ▼
retrieval      policy_tool      human_review
_worker        _worker          _node (HITL)
   │               │                │
   │        ┌──────┘                │
   │        │ Gọi MCP tools:        │
   │        │ - search_kb           │
   │        │ - get_ticket_info     │
   │        │ - check_access_perm   │
   │        │                       │
   │        └───── auto-approve ────┘
   │                   │
   └─────────┬─────────┘
             │  (nếu chưa có chunks → gọi retrieval_worker)
             ▼
    ┌─────────────────┐
    │ Retrieval Worker │  ← ChromaDB dense search
    │                  │    → retrieved_chunks, sources
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │ Synthesis Worker  │  ← LLM (gpt-4o-mini, temp=0.1)
    │                   │    → final_answer + citation
    │                   │    → confidence score
    │                   │    → hitl_triggered nếu conf < 0.4
    └────────┬──────────┘
             │
             ▼
         Output
    (AgentState với full trace,
     final_answer, confidence,
     sources, latency_ms, run_id)
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích task và quyết định route tới worker nào, đặt flag risk và tool need |
| **Input** | `task: str` từ user |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Keyword matching: policy_keywords → `policy_tool_worker`; retrieval_keywords → `retrieval_worker`; human_review_keywords → `human_review`; default → `retrieval_worker` |
| **HITL condition** | `risk_high=True` AND task chứa `err-` hoặc `không rõ` → override sang `human_review` |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Dense retrieval từ ChromaDB — embed query và trả về top-k chunks có độ liên quan cao nhất |
| **Embedding model** | `sentence-transformers/all-MiniLM-L6-v2` (offline, không cần API key); fallback sang OpenAI `text-embedding-3-small` nếu có key |
| **Top-k** | 3 (mặc định, có thể override qua `state["retrieval_top_k"]`) |
| **Stateless?** | Yes — mỗi call độc lập, không giữ session |
| **Collection** | ChromaDB persistent tại `./chroma_db`, collection `day09_docs` (63 chunks từ `sla_p1_2026.txt`, `policy_refund_v4.txt`, `access_control_sop.txt`) |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Kiểm tra rule-based policy exceptions + gọi MCP tools để lấy thêm context |
| **MCP tools gọi** | `search_kb` (nếu chưa có chunks), `get_ticket_info` (nếu task chứa "ticket"/"p1"/"jira") |
| **Exception cases xử lý** | `flash_sale_exception`, `digital_product_exception`, `activated_exception`, `policy_v3_temporal_scope` (đơn trước 01/02/2026) |
| **LLM analysis** | `analyze_with_llm()` dùng gpt-4o-mini (optional, gọi khi cần phân tích phức tạp) |
| **MCP transport** | HTTP REST qua FastAPI `/tools/call` endpoint; fallback in-process nếu server chưa chạy |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | `gpt-4o-mini` (Option A); fallback `gemini-1.5-flash` (Option B) |
| **Temperature** | 0.1 — cực thấp để đảm bảo grounded output, hạn chế hallucination |
| **Grounding strategy** | CHỈ dùng `retrieved_chunks` + `policy_result` làm context. System prompt cấm dùng kiến thức ngoài. Abstain bằng "Không đủ thông tin trong tài liệu nội bộ" nếu không có evidence |
| **Abstain condition** | Khi chunks rỗng hoặc không đủ thông tin → trả lời mẫu chuẩn |
| **Confidence scoring** | Weighted avg của chunk scores − penalty theo số exceptions (0.05/exception); confidence < 0.4 → trigger HITL |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query: str`, `top_k: int=3` | `{chunks, sources, total_found}` |
| `get_ticket_info` | `ticket_id: str` | `{ticket_id, priority, status, assignee, sla_deadline, notifications_sent}` |
| `check_access_permission` | `access_level: int`, `requester_role: str`, `is_emergency: bool=False` | `{can_grant, required_approvers, emergency_override, notes}` |
| `create_ticket` | `priority: str`, `title: str`, `description: str=""` | `{ticket_id, url, created_at}` |

**HTTP Server**: FastAPI tại `http://localhost:8000`, Swagger UI tại `/docs`  
**Endpoints**: `GET /tools` (discovery), `POST /tools/call` (execution)

---

## 4. Shared State Schema

> Liệt kê các fields trong AgentState và ý nghĩa của từng field.

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------:|
| `task` | `str` | Câu hỏi đầu vào từ user | supervisor đọc |
| `supervisor_route` | `str` | Worker được chọn: `retrieval_worker`, `policy_tool_worker`, `human_review` | supervisor ghi |
| `route_reason` | `str` | Lý do routing, accumulate qua pipe với `\|` | supervisor ghi |
| `risk_high` | `bool` | True nếu task có rủi ro cao (emergency/unknown error) | supervisor ghi, synthesis đọc |
| `needs_tool` | `bool` | True nếu cần gọi MCP tool | supervisor ghi, policy_tool đọc |
| `hitl_triggered` | `bool` | True nếu human-in-the-loop được kích hoạt | human_review hoặc synthesis ghi |
| `retrieved_chunks` | `list[dict]` | Evidence từ ChromaDB: `{text, source, score, metadata}` | retrieval ghi, synthesis đọc |
| `retrieved_sources` | `list[str]` | Danh sách source filenames | retrieval ghi, synthesis đọc |
| `policy_result` | `dict` | Kết quả rule-based check: `{policy_applies, exceptions_found, policy_name}` | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | `list[dict]` | Log các MCP tool calls: `{tool, input, output, error, timestamp}` | policy_tool ghi |
| `final_answer` | `str` | Câu trả lời cuối có citation | synthesis ghi |
| `sources` | `list[str]` | Sources được cite trong final_answer | synthesis ghi |
| `confidence` | `float` | Mức độ tin cậy 0.0–1.0 | synthesis ghi |
| `history` | `list[str]` | Log từng bước xử lý để debug | tất cả workers append |
| `workers_called` | `list[str]` | Danh sách workers đã được gọi theo thứ tự | tất cả workers append |
| `latency_ms` | `int` | Thời gian xử lý toàn pipeline (ms) | graph ghi |
| `run_id` | `str` | ID duy nhất của run: `run_YYYYMMDD_HHMMSS` | make_initial_state ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — không rõ lỗi ở đâu | Dễ hơn — test từng worker độc lập qua `python workers/xxx.py` |
| Thêm capability mới | Phải sửa toàn prompt | Thêm worker hoặc MCP tool riêng, không ảnh hưởng các worker khác |
| Routing visibility | Không có | Có `route_reason` + `workers_called` trong mọi trace JSON |
| Xử lý exceptions phức tạp | Prompt phải cover mọi case | `policy_tool_worker` handle exceptions độc lập |
| Gọi external tools | Cần inject vào prompt | MCP dispatch layer tách biệt, pluggable |
| Latency | Một LLM call | Nhiều bước nhưng có thể parallel hoá về sau |

**Nhóm điền thêm quan sát từ thực tế lab:**  
Qua các lần chạy test, nhóm nhận thấy việc có `history[]` trong state rất hữu ích để debug — có thể thấy ngay thứ tự gọi workers và thông tin từng bước mà không cần đọc log. Tuy nhiên, việc tất cả workers đều mutate cùng một state dict dễ gây side effect nếu không cẩn thận với `setdefault()`.

---

## 6. Giới hạn và điểm cần cải tiến

> Nhóm mô tả những điểm hạn chế của kiến trúc hiện tại.

1. **Keyword-based routing quá đơn giản**: Supervisor hiện chỉ dùng string matching nên dễ miss-route các task phức tạp hoặc đa-intent. Cần upgrade lên LLM-based routing classifier để handle ambiguous queries (ví dụ: câu hỏi vừa cần SLA vừa cần access control).

2. **MCP client chưa ổn định**: `HttpClient` trong `mcp.client.http` không tồn tại trong version `mcp` hiện tại → fallback sang `httpx`. Cần một abstraction layer để tránh breaking changes khi upgrade thư viện MCP.

3. **Synthesis phụ thuộc hoàn toàn vào LLM API**: Khi OpenAI API key không có, pipeline fail ở bước cuối với confidence 0.1. Cần implement template-based fallback synthesis để đảm bảo pipeline luôn trả về kết quả, dù chất lượng thấp hơn.
