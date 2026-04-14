# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Dương Chí Thành  
**Vai trò trong nhóm:**  Worker Owner   
**Ngày nộp:** 14/4/2026  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Tôi phụ trách phần `policy_tool_worker`, bao gồm thiết kế và triển khai logic kiểm tra policy trong `workers/policy_tool.py` và đảm bảo contract tương ứng trong `contracts/worker_contracts.yaml`.

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/policy_tool.py`
- Contract: `contracts/worker_contracts.yaml`
- Functions tôi implement: `run(state)`, `analyze_policy(task, chunks)`, `_call_mcp_tool(tool_name, tool_input)`

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Supervisor quyết định route task đến `policy_tool_worker`; nếu worker cần evidence thì có thể sử dụng `retrieved_chunks` từ `retrieval_worker`; kết quả `policy_result` và `mcp_tools_used` sau đó được dùng bởi `workers/synthesis.py` để xây dựng câu trả lời cuối cùng.

**Bằng chứng:**
- `contracts/worker_contracts.yaml` xác định rõ `policy_tool_worker` và file `workers/policy_tool.py`
- `README.md` mô tả `policy_tool.py` là “Policy/Tool Worker — kiểm tra policy + MCP tools”
- `workers/policy_tool.py` có block `if __name__ == "__main__"` để test độc lập

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Tôi chọn triển khai logic phân tích policy theo cách rule-based trong `analyze_policy` trước khi chuyển sang LLM hoặc cố gắng triển khai một hệ thống inference phức tạp.

**Lý do:**
Worker này được thiết kế như một gate kiểm tra policy nên cần đầu ra deterministic, dễ kiểm chứng theo contract. Rule-based keyword detection với các exception cụ thể như `flash sale`, `license key`, `subscription`, `đã kích hoạt` giúp tôi đảm bảo `policy_result` tuân thủ đúng schema và không bị hallucination. Giải pháp này cũng phù hợp với yêu cầu Sprint 2: “Policy worker xử lý đúng ít nhất 1 exception case”.

**Trade-off đã chấp nhận:**
- Ưu điểm: logic đơn giản, dễ test, dễ đồng bộ với contract.
- Nhược điểm: chưa đủ linh hoạt cho mọi ngữ cảnh phức tạp, cần nâng cấp sau này bằng LLM hoặc rule mở rộng.

**Bằng chứng từ code:**
```python
if "flash sale" in task_lower or "flash sale" in context_text:
    exceptions_found.append({
        "type": "flash_sale_exception",
        "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
        "source": "policy_refund_v4.txt",
    })
```
Đoạn code trên cho thấy tôi đã hiện thực hoá detection cho exception case theo yêu cầu contract.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Implementation ban đầu của `policy_tool.py` chưa khớp chính xác với contract `contracts/worker_contracts.yaml` và thiếu chuẩn hoá output khi gọi MCP tool.

**Symptom:**
- `policy_tool.py` có thể trả về `policy_result`, nhưng nếu worker cần gọi MCP thì phần `mcp_tools_used` chưa được đảm bảo luôn tồn tại và cập nhật đầy đủ.
- `source` trong `policy_result` cũng cần luôn là array để hợp lệ với contract.

**Root cause:**
Sự sai lệch nằm ở layer worker logic, khi output `policy_result` và `state` không được thiết kế đầy đủ theo schema contract `policy_tool_worker`.

**Cách sửa:**
Tôi đã rà soát và hoàn thiện `run(state)` để:
- khởi tạo `state.setdefault("mcp_tools_used", [])`
- thêm `policy_result` vào state
- ghi `worker_io_logs` và `history`
- đảm bảo `policy_result` chứa `policy_applies`, `policy_name`, `exceptions_found`, `source`, `policy_version_note`

**Bằng chứng trước/sau:**
Trước: contract yêu cầu `mcp_tools_used` nhưng code chỉ cập nhật trong một vài branch. Sau: `state["mcp_tools_used"].append(mcp_result)` luôn được gọi khi worker cần tool, phù hợp với contract.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**
Tôi làm tốt nhất ở việc xác định rõ ràng ranh giới worker và contract, biến `policy_tool.py` thành một module có thể test độc lập. Tôi tập trung vào việc giữ input/output đúng theo `contracts/worker_contracts.yaml`, giúp phần `policy_result` có cấu trúc nhất quán cho synthesis.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Tôi còn yếu ở phần tích hợp MCP tool thực tế và logic phân tích policy phức tạp. Hiện worker sử dụng rule-based cơ bản và vẫn còn TODO cho LLM support, nên cần bổ sung thêm nếu muốn xử lý edge case sâu hơn.

**Nhóm phụ thuộc vào tôi ở đâu?**
Nhóm phụ thuộc vào tôi ở bước policy gate: nếu `policy_tool_worker` chưa xong thì các câu hỏi refund/policy không có kết quả `policy_result` chính xác, và synthesis sẽ thiếu thông tin bắt buộc để trả lời an toàn.

**Phần tôi phụ thuộc vào thành viên khác:**
Tôi cần supervisor phải route đúng `policy_tool_worker` và retrieval worker/KB trả về `retrieved_chunks` khi cần. Nếu không có evidence đúng, policy tool sẽ thiếu context để phân tích ngoại lệ.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ xây một script validate contract tự động để so sánh output của `workers/policy_tool.py` với schema trong `contracts/worker_contracts.yaml`, đồng thời tự động cập nhật `actual_implementation.status` khi test worker thành công. Hiện tại repo đang dùng metadata thủ công, nên script này sẽ giảm lỗi manual và giữ `policy_tool_worker` luôn đúng với contract.
