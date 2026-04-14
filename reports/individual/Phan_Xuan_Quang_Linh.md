# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Phan Xuân Quang Linh
**Vai trò trong nhóm:**  MCP Owner   
**Ngày nộp:** 14/4/2026
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Tôi phụ trách xây dựng **policy_tool_worker**, tập trung vào việc kiểm tra và áp dụng các quy tắc policy trong hệ thống. Nhiệm vụ chính của tôi là thiết kế và triển khai logic xử lý policy, đồng thời đảm bảo dữ liệu đầu vào/đầu ra luôn tuân thủ đúng contract được định nghĩa trong hệ thống.

Cụ thể, tôi chịu trách nhiệm triển khai các chức năng xử lý chính của worker, chuẩn hoá output như `policy_result` và `mcp_tools_used`, và đảm bảo dữ liệu luôn nhất quán với contract.

Trong hệ thống, worker của tôi được Supervisor gọi khi cần kiểm tra policy. Nếu cần ngữ cảnh, worker sẽ sử dụng dữ liệu từ retrieval. Kết quả sau đó sẽ được chuyển sang bước synthesis để tạo câu trả lời cuối cùng.

Bằng chứng là contract định nghĩa rõ worker này, README mô tả vai trò của nó, và module có thể chạy độc lập để kiểm thử.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

Quyết định quan trọng nhất của tôi là sử dụng phương pháp **rule-based** để phân tích policy thay vì dùng LLM ngay từ đầu.

Lý do chính là worker này đóng vai trò như một “policy gate”, nên yêu cầu quan trọng nhất là tính ổn định và khả năng kiểm chứng. Việc sử dụng rule-based giúp đảm bảo output không bị sai lệch hoặc hallucination, đồng thời dễ dàng kiểm thử và so sánh với contract. Tôi sử dụng các keyword và điều kiện cụ thể để phát hiện các trường hợp ngoại lệ như flash sale, license key, subscription hoặc sản phẩm đã kích hoạt.

Giải pháp này phù hợp với mục tiêu của hệ thống ở giai đoạn hiện tại, đặc biệt là yêu cầu phải xử lý đúng ít nhất một trường hợp ngoại lệ.

Tuy nhiên, tôi chấp nhận trade-off là cách tiếp cận này chưa đủ linh hoạt để xử lý các tình huống ngữ nghĩa phức tạp. Trong tương lai, có thể mở rộng bằng cách kết hợp thêm LLM để cải thiện khả năng hiểu ngữ cảnh.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

Một lỗi quan trọng mà tôi đã xử lý là việc output của worker chưa tuân thủ hoàn toàn contract đã định nghĩa.

Cụ thể, trong một số trường hợp, dữ liệu trả về không đầy đủ hoặc không nhất quán. Ví dụ, danh sách các MCP tool đã sử dụng không luôn được khởi tạo hoặc cập nhật đầy đủ, và một số trường trong kết quả policy chưa đúng định dạng yêu cầu.

Nguyên nhân chính là do thiết kế ban đầu chưa đảm bảo tất cả các nhánh logic đều trả về dữ liệu theo cùng một cấu trúc.

Để khắc phục, tôi đã rà soát và chuẩn hoá lại toàn bộ quá trình xử lý trong worker. Tôi đảm bảo rằng mọi output đều chứa đầy đủ các trường bắt buộc, dữ liệu luôn đúng định dạng, và các thông tin liên quan đến tool hoặc log đều được ghi nhận nhất quán.

Kết quả là worker trở nên ổn định hơn, dễ tích hợp với các thành phần khác, và hoàn toàn tuân thủ contract của hệ thống.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

Điểm mạnh nhất của tôi là xác định rõ ràng ranh giới giữa worker và contract, từ đó xây dựng một module có thể hoạt động độc lập và dễ kiểm thử. Tôi tập trung đảm bảo dữ liệu đầu ra luôn nhất quán, giúp các bước xử lý phía sau hoạt động ổn định.

Tuy nhiên, tôi vẫn còn hạn chế ở việc xử lý các tình huống phức tạp về ngữ nghĩa và chưa tích hợp sâu với các công cụ MCP thực tế. Logic hiện tại vẫn mang tính cơ bản và cần được mở rộng thêm.

Trong nhóm, phần của tôi đóng vai trò như một lớp kiểm soát quan trọng. Nếu worker này không chính xác, các câu trả lời liên quan đến policy có thể bị sai hoặc không an toàn.

Tôi cũng phụ thuộc vào các thành phần khác như supervisor và retrieval để có dữ liệu đầu vào đúng và đầy đủ.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Nếu có thêm thời gian, tôi sẽ xây dựng một công cụ tự động kiểm tra tính đúng đắn giữa output của worker và contract đã định nghĩa. Công cụ này sẽ giúp phát hiện lỗi sớm, giảm phụ thuộc vào kiểm tra thủ công và đảm bảo hệ thống luôn duy trì được tính nhất quán trong quá trình phát triển.

---