# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nguyễn Đức Tiến  
**Mã HV:** 2A202600393
**Vai trò trong nhóm:** Người 5 — Synthesis Worker  
**Ngày nộp:** 14/04/2026  
**Độ dài:** ~650 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Trong đợt Lab Day 09 này, tôi đảm nhận vai trò là **Người 5**, chịu trách nhiệm chính về module Synthesis và đối soát dữ liệu. Công việc của tôi tập trung vào việc đảm bảo hệ thống có thể tổng hợp thông tin từ nhiều nguồn để đưa ra câu trả lời cuối cùng có độ tin cậy cao.

**Module/file tôi chịu trách nhiệm:**
- `workers/synthesis.py`: Logic tổng hợp câu trả lời, gọi LLM (OpenAI/Gemini) và tính toán độ tin cậy.
- `contracts/worker_contracts.yaml`: Thiết kế phần contract cho Synthesis Worker, đảm bảo input/output tương thích với các worker khác.
- `docs/single_vs_multi_comparison.md`: Tài liệu phân tích và so sánh hiệu năng giữa kiến trúc Single-Agent (Day 08) và Multi-Agent (Day 09).

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Tôi là điểm hội tụ cuối cùng của pipeline. Tôi nhận các mảnh bằng chứng (chunks) từ Retrieval Worker và các ràng buộc nghiệp vụ từ Policy Tool Worker. Tôi chịu trách nhiệm "đóng gói" toàn bộ kết quả để trả về cho người dùng và cung cấp dữ liệu đầu vào cho quy trình đánh giá (eval_trace). Nếu Synthesis Worker chưa hoàn thiện, toàn bộ luồng xử lý của nhóm sẽ không có đầu ra có giá trị.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**
- Các thay đổi trong `workers/synthesis.py` với commit hash `76a0db6`.
- Phần định nghĩa `synthesis_worker` trong file contract được commit bởi `ductiens`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Sử dụng phương pháp **Best-Score Normalization** thay vì Weighted Average để tính toán giá trị `confidence` cho câu trả lời.

**Lý do:**
Khi làm việc với các hệ thống Vector DB như ChromaDB, tôi phát hiện ra một vấn đề: điểm số tương đồng (distance/similarity) thường không ổn định và có xu hướng rất thấp (0.05 - 0.25) ngay cả khi tài liệu rất liên quan. Nếu dùng phương pháp trung bình cộng trọng số như ban đầu, chỉ số `confidence` luôn bị kéo xuống mức rất thấp (~0.1), dẫn đến việc hệ thống liên tục kích hoạt cờ `hitl_triggered` (Human-in-the-loop) một cách sai lệch cho hầu hết các câu hỏi.

Tôi quyết định thay đổi logic: sử dụng điểm số cao nhất của chunk liên quan nhất (`best_score`) làm cơ sở chính, sau đó ánh xạ (normalize) kết quả này về một dải giá trị thực tế hơn `[0.5, 0.95]`. Điều này giúp hệ thống phân loại chính xác hơn giữa các trường hợp "có bằng chứng tốt" và "không có thông tin". 

**Trade-off đã chấp nhận:**
Quyết định này chấp nhận rủi ro rằng nếu chỉ một chunk có score cao nhưng nội dung lại không đầy đủ để trả lời câu hỏi phức tạp, chỉ số confidence vẫn sẽ cao. Tuy nhiên, nó giải quyết được vấn đề quan trọng nhất là làm cho cờ HITL hoạt động đúng ý đồ thiết kế.

**Bằng chứng từ code:**

```python
# logic calculation in workers/synthesis.py
best_score = max(c.get("score", 0) for c in chunks)
if best_score >= 0.15:
    base = 0.8  # Normalize to a trustworthy level
elif best_score >= 0.05:
    base = 0.65
else:
    base = 0.5
confidence = min(0.95, base - exception_penalty)
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Synthesis Worker bỏ qua các ràng buộc ngoại lệ từ Policy Tool Worker.

**Symptom (pipeline làm gì sai?):**
Khi xử lý các câu hỏi nhạy cảm về chính sách (ví dụ: yêu cầu hoàn tiền cho đơn hàng Flash Sale), hệ thống vẫn trả lời là "được phép hoàn tiền" dựa trên tài liệu chung trong Knowledge Base. Mặc dù `policy_tool_worker` đã chạy thành công và detect được ngoại lệ (exception), nhưng câu trả lời cuối cùng vẫn bị sai lệch, gây rủi ro về nội dung nghiệp vụ.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**
Lỗi nằm ở logic build prompt trong hàm `_build_context`. Ban đầu, tôi chỉ tập trung vào việc xử lý các `retrieved_chunks` từ Retrieval Worker mà quên mất việc tích hợp kết quả từ Policy Worker vào context. Do đó, LLM chỉ tổng hợp câu trả lời từ tài liệu kỹ thuật mà không biết rằng có những "ngoại lệ" (exceptions) đang được áp dụng cho trường hợp cụ thể đó.

**Cách sửa:**
Tôi đã cập nhật hàm `_build_context` để kiểm tra field `exceptions_found` trong `policy_result`. Nếu có dữ liệu, tôi sẽ tạo một mục riêng biệt có tên `=== POLICY EXCEPTIONS ===` chèn vào ngay sau phần tài liệu tham khảo. Đồng thời, tôi bổ sung quy tắc thứ 5 trong System Prompt: "Nếu có exceptions/ngoại lệ → nêu rõ ràng trước khi kết luận" để ép LLM phải ưu tiên thông tin này.

**Bằng chứng trước/sau:**
- **Trước khi sửa:** Trace câu `q12` trả về "Bạn có thể hoàn tiền..." dựa trên quy trình chung, bỏ qua trạng thái Flash Sale của đơn hàng.
- **Sau khi sửa:** Trình biên dịch hiển thị câu trả lời chính xác: "Đơn hàng Flash Sale không được hoàn tiền theo Điều 3 chính sách v4" (lấy đúng từ `policy_result`).

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**
Tôi đã hoàn thiện file `docs/single_vs_multi_comparison.md` một cách chi tiết, phân tích rõ ràng các điểm mù của kiến trúc Day 08 so với lợi thế về traceability của Day 09. Ngoài ra, việc tôi triển khai system prompt với các ràng buộc "grounded strictly on context" đã giúp giảm tỉ lệ hallucination của synthesis xuống mức tối thiểu.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Chỉ số `confidence` hiện tại mới chỉ phản ánh được sự tồn tại của bằng chứng, chưa đánh giá được tính nhất quán của nội dung (fact-checking) bên trong câu trả lời do LLM sinh ra.

**Nhóm phụ thuộc vào tôi ở đâu?**
Nếu Synthesis Worker gặp lỗi, toàn bộ pipeline sẽ không có câu trả lời cuối để trả về. Mọi nỗ lực của Retrieval hay Policy đều trở nên vô nghĩa nếu không có một module tổng hợp dữ liệu chuẩn xác.

**Phần tôi phụ thuộc vào thành viên khác:**
Tôi phụ thuộc vào dữ liệu đầu vào ổn định từ Retrieval Worker. Trong lab này, có thời điểm HuggingFace bị downtime dẫn đến `retrieved_chunks` bị trống, làm synthesis cũng bị ảnh hưởng theo.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ tập trung vào việc hiện thực hóa logic **LLM-as-Judge** trực tiếp bên trong synthesis để tự động hóa việc chấm điểm `faithfulness`. Hiện tại, tôi đang sử dụng heuristics sơ bộ, nhưng nếu có thêm thời gian, một bước gọi LLM nhanh để kiểm chứng câu trả lời với các chunks sẽ giúp nâng cao đáng kể độ chính xác của chỉ số confidence, giảm tải cho human reviewer.

---
*Lưu file này với tên: `reports/individual/nguyen_duc_tien.md`*
