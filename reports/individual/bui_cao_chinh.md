# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Bùi Cao Chinh — MHV: 2A202600001
**Vai trò trong nhóm:** Supervisor Owner / Graph Owner
**Ngày nộp:** 14/04/2026
**Độ dài:** ~620 từ

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py`
- Functions tôi implement: `supervisor_node()`, `route_decision()`, `build_graph()`, `run_graph()`, `save_trace()`, các wrapper node `retrieval_worker_node()`, `policy_tool_worker_node()`, `synthesis_worker_node()`

Tôi phụ trách **supervisor orchestrator** — bộ não trung tâm của pipeline. `supervisor_node()` nhận task từ user, phân tích bằng keyword matching để quyết định route sang `retrieval_worker`, `policy_tool_worker` hay `human_review`, ghi lý do vào `route_reason`, và đặt các flag `risk_high`/`needs_tool`. Sau đó `build_graph()` tổ chức toàn bộ luồng: supervisor → worker → synthesis → output, và `save_trace()` lưu execution trace ra file JSON trong `artifacts/traces/`.

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Quyết định routing của tôi là điểm xuất phát cho toàn pipeline. Nếu supervisor route sai, retrieval và policy worker sẽ nhận task không phù hợp, synthesis sẽ thiếu context. Tôi cũng là người uncomment và kết nối các worker module thật (`retrieval_run`, `policy_tool_run`, `synthesis_run`) vào graph thay vì placeholder data.

**Bằng chứng:** `graph.py` là file tôi chỉnh sửa chính, các trace file trong `artifacts/traces/` (VD: `run_20260414_174347.json`) là output trực tiếp từ `save_trace()` tôi viết.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Implement routing logic dùng `if/elif` ưu tiên rõ ràng thay vì dùng các `if` độc lập cho mỗi keyword group.

Ban đầu code template dùng `if` riêng biệt cho `policy_keywords` và `risk_keywords`, không có `elif` cho `retrieval_keywords` — nghĩa là một task có thể match cả hai nhánh và bị override không kiểm soát được. Tôi có hai lựa chọn:

- **Option A (template):** Các `if` độc lập — policy check rồi risk check riêng, route bị ghi đè tùy thứ tự
- **Option B (tôi chọn):** `if/elif` chain với thứ tự ưu tiên rõ: `policy_keywords` → `retrieval_keywords` → `human_review_keywords` → default `retrieval_worker`

**Lý do chọn Option B:** Thứ tự ưu tiên có nghĩa ngữ nghĩa cụ thể — câu hỏi về access/policy phức tạp hơn câu hỏi tra cứu SLA đơn giản, nên cần policy check trước. Nếu task chứa cả "p1" lẫn "level 3", phải route sang `policy_tool_worker` chứ không phải `retrieval_worker`.

**Trade-off đã chấp nhận:** Keyword-based routing nhanh (~2ms) nhưng không handle được ambiguous intent. Câu hỏi phức hợp (vừa cần SLA vừa cần access control) bị route single-path, dù pipeline tự giải quyết được nhờ fallback trong `build_graph()`.

**Bằng chứng từ trace:**

```json
// run_20260414_174347.json — task chứa cả "level 3" (policy) lẫn "p1" (retrieval)
{
  "task": "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp. Quy trình là gì?",
  "supervisor_route": "policy_tool_worker",
  "route_reason": "task contains policy/access keyword | risk_high flagged",
  "workers_called": ["policy_tool_worker", "retrieval_worker", "synthesis_worker"]
}
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `async with` được dùng bên trong một hàm synchronous (`_call_mcp_tool` trong `workers/policy_tool.py`), đồng thời import một module không tồn tại `mcp.client.http`.

**Symptom:** Khi chạy `graph.py`, toàn bộ pipeline crash ngay khi import `workers/policy_tool.py`. Hai lỗi xuất hiện liên tiếp:
1. `ModuleNotFoundError: No module named 'mcp.client.http'` — module không tồn tại trong phiên bản `mcp` đã cài
2. Sau khi sửa import, vẫn gặp `SyntaxError: 'async with' can only be used inside an async function` vì `async with HttpClient(...)` nằm bên trong `def _call_mcp_tool(...)` thông thường

**Root cause:** `HttpClient` yêu cầu `async def` và `async with`, nhưng hàm wrapper `_call_mcp_tool()` lại là synchronous. Ngoài ra phiên bản thư viện `mcp` đã cài không có submodule `mcp.client.http` — class `HttpClient` không tồn tại.

**Cách sửa (hai bước):**

1. Xóa `from mcp.client.http import HttpClient`, thay bằng `import httpx` (có sẵn trong venv)
2. Viết lại hàm dùng `httpx.AsyncClient` để gọi REST API của FastAPI server, đổi `def` thành `async def`, và dùng `asyncio.run()` tại call site trong `run()` (sync)

**Bằng chứng trước/sau:**

```python
# Trước — crash khi import
from mcp.client.http import HttpClient          # ❌ ModuleNotFoundError

def _call_mcp_tool(tool_name, tool_input):
    async with HttpClient(server_url) as client:  # ❌ SyntaxError

# Sau — hoạt động đúng
import httpx                                       # ✅

async def _call_mcp_tool(tool_name, tool_input):
    server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
    async with httpx.AsyncClient() as client:      # ✅
        response = await client.post(f"{server_url}/tools/call",
                                     json={"tool_name": tool_name, "tool_input": tool_input})
        return {"tool": tool_name, "output": response.json().get("result"), "error": None}

# Tại call site trong run() — sync wrapper:
mcp_result = asyncio.run(_call_mcp_tool("search_kb", {"query": task, "top_k": 3}))
```


---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở:** Thiết kế `build_graph()` với fallback tự nhiên — sau `policy_tool_worker` nếu `retrieved_chunks` vẫn rỗng thì tự động gọi thêm `retrieval_worker`. Nhờ vậy các câu hỏi phức hợp (vừa cần policy vừa cần SLA) vẫn có kết quả đúng dù supervisor chỉ route single-path. Tôi cũng implement `save_trace()` giúp toàn bộ nhóm debug được qua file JSON thay vì đọc log terminal.

**Tôi làm chưa tốt ở:** `supervisor_node()` dùng lowercase matching nhưng không normalize ký tự tiếng Việt (ví dụ: "cấp quyền" vs "CAP QUYEN"). Routing sẽ miss nếu user gõ hoa hoặc không dấu. Phần `human_review_node` cũng chỉ là auto-approve placeholder, chưa implement HITL thật.

**Nhóm phụ thuộc vào tôi ở:** Toàn bộ execution flow — nếu `build_graph()` hoặc `supervisor_node()` chưa xong thì pipeline không có entry point để test. Trace files là output của tôi, mọi thành viên cần trace để viết routing_decisions.md và đánh giá kết quả.

**Tôi phụ thuộc vào thành viên khác:** Tôi cần `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py` export đúng hàm `run(state)` theo contract để graph có thể gọi được. Khi synthesis fail do thiếu API key, pipeline của tôi vẫn chạy nhưng `final_answer` ra error string.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ nâng cấp `supervisor_node()` từ keyword matching sang LLM-based routing. Bằng chứng: trace `run_20260414_170315.json` (Decision #1) cho thấy câu "SLA xử lý ticket P1 là bao lâu?" được route đúng sang `retrieval_worker`, nhưng synthesis abstain với confidence 0.3 vì retrieval lấy nhầm chunks P2/P3. Một LLM-based supervisor không chỉ route đúng worker mà còn có thể rewrite query ("SLA P1 response time resolution") trước khi gửi vào retrieval, giúp ChromaDB trả về chunk P1 chính xác hơn và đẩy confidence từ 0.3 lên trên 0.6.
