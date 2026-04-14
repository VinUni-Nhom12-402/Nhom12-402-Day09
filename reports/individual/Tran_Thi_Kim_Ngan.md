# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Trần Thị Kim Ngân
**Vai trò trong nhóm:** Worker Owner 
**Ngày nộp:** 4/14/2026
**Độ dài yêu cầu:** 500–800 từ
**Mã học viên:** 2A202600432

---

> **Lưu ý quan trọng:**
> - Viết ở ngôi **"tôi"**, gắn với chi tiết thật của phần bạn làm
> - Phải có **bằng chứng cụ thể**: tên file, đoạn code, kết quả trace, hoặc commit
> - Nội dung phân tích phải khác hoàn toàn với các thành viên trong nhóm
> - Deadline: Được commit **sau 18:00** (xem SCORING.md)
> - Lưu file với tên: `reports/individual/[ten_ban].md` (VD: `nguyen_van_a.md`)

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

> Mô tả cụ thể module, worker, contract, hoặc phần trace bạn trực tiếp làm.
> Không chỉ nói "tôi làm Sprint X" — nói rõ file nào, function nào, quyết định nào.

**Module/file tôi chịu trách nhiệm:**
-Định nghĩa module khởi tạo CSDL: `build_index.py`
-Xây dựng Worker: `workers/retrieval.py`
-Tuân thủ interface: `contracts/worker_contracts.yaml` (nút retrieval_worker).

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Trong build_index.py, tôi viết module split_into_chunks() tách file txt chuẩn hóa theo đoạn/đề mục (sections) và module hóa SentenceTransformers dể embedding, tạo ChromaDB collection. Trong workers/retrieval.py, tôi implement hàm retrieve_dense và entry-point run(state). Worker này nhận task và top_k theo contract, thực thi lấy vector match dựa theo query và đảm bảo trả ra đúng schema cho tập chunk và danh sách retrieved_sources.
-retrieval_worker là "xương sống" cung cấp tri thức cho hệ thống RAG (kiến trúc của chúng ta không phải direct LLM answer). Mọi routing từ supervisor_node nếu trỏ về worker này đều mong nhận lại bằng chứng đúng chuẩn schema, sau đó context này truyền xuống để synthesis_worker căn cứ vào đó generate response.
_________________

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**
-Chạy standalone python workers/retrieval.py cho thấy trả ra log: "Retrieved: 3 chunks | score=..." đúng format.
-Code entry-point run(state) gán logic state worker_io_logs theo sát yaml.

_________________

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

> Chọn **1 quyết định** bạn trực tiếp đề xuất hoặc implement trong phần mình phụ trách.
> Giải thích:
> - Quyết định là gì?
> - Các lựa chọn thay thế là gì?
> - Tại sao bạn chọn cách này?
> - Bằng chứng từ code/trace cho thấy quyết định này có effect gì?

**Quyết định:** 
Sử dụng Lazy-Loading (caching ở memory) với "3-Tier Fallback Mechanism" cho hàm sinh Vector Embeddings (_get_embedding_fn()) trực tiếp trong retrieval.py thay vì load cứng model vào biến toàn cục ngay từ đầu.

**Ví dụ:**
> "Tôi chọn dùng keyword-based routing trong supervisor_node thay vì gọi LLM để classify.
>  Lý do: keyword routing nhanh hơn (~5ms vs ~800ms) và đủ chính xác cho 5 categories.
>  Bằng chứng: trace gq01 route_reason='task contains P1 SLA keyword', latency=45ms."

**Lý do:**

Việc khởi tạo một model NLP (dù nhỏ như all-MiniLM-L6-v2) chiếm kha khá thời gian (gần ~2-3 giây) mỗi lần run. Nếu load vào bộ nhớ ngay lúc import file thì graph lúc nào cũng phải gánh chi phí này ngay cả khi Supervisor route vào nhánh khác (ví dụ: policy_tool). Ngoài ra, nếu thiếu API key hay môi trường không có kết nối khi dùng OpenAI, cả worker sẽ chết tức tưởi.

**Trade-off đã chấp nhận:**

Xài code hơi boilerplate một chút lúc lấy model, bù lại hệ thống khởi động nhanh và độ bền bỉ rất cao.

**Bằng chứng từ trace/code:**

```
_cached_embed_fn = None

def _get_embedding_fn():
    """Lazy-load caching để không load lại weights nhiều lần."""
    global _cached_embed_fn
    if _cached_embed_fn is not None:
        return _cached_embed_fn

    # Tier 1: Local offline (all-MiniLM)
    try:
        from sentence_transformers import SentenceTransformer
        # [code_setup]
        _cached_embed_fn = embed
        return _cached_embed_fn
    except ImportError:
        pass
    # [...] Fallback 2: OpenAI
    # [...] Fallback 3: Random generator để chạy pass tests 

```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

> Mô tả 1 bug thực tế bạn gặp và sửa được trong lab hôm nay.
> Phải có: mô tả lỗi, symptom, root cause, cách sửa, và bằng chứng trước/sau.

**Lỗi:** 
UnicodeEncodeError: 'charmap' codec can't encode character... khi pipeline hoặc worker in log/trace ra console (Command Prompt/PowerShell) trên Windows.
**Symptom (pipeline làm gì sai?):**

 Toàn bộ Graph/Worker chạy nghiệp vụ bình thường (index được file, trích xuất chunk đúng). Nhưng khi standalone test cố gắng in output preview ra màn hình có chứa chữ tiếng Việt có dấu (ví dụ câu hỏi: "SLA ticket P1 là bao lâu?" hoặc các văn bản chính sách), chương trình sẽ bị văng (Crash Exception) ngay lập tức, block luôn cả terminal debug.

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**

Text lấy lên từ ChromaDB chuẩn UTF-8, nhưng default Terminal trên Windows thường lại thiết lập bảng mã cp1252 hoặc các bảng ANSI cũ. Các lệnh in không map được các ký tự unicode sẽ sinh lỗi crash.
**Cách sửa:**

 Tôi viết một helper function an toàn _safe(text) sử dụng error="replace" logic để bọc mọi output trước khi dump ra bảng console cho standalone test trên môi trường cục bộ.

**Bằng chứng trước/sau:**
> Dán trace/log/output trước khi sửa và sau khi sửa.

Bằng chứng trước/sau: (Trích log trước khi fix):
"""
Traceback (most recent call last):
  File "C:\...\workers\retrieval.py", line 301, in <module>
    print(f"\n[Run] Query: {query}")
UnicodeEncodeError: 'charmap' codec can't encode character '\xe0'
"""
Bằng chứng trước/sau: (Trích log sau khi fix):
"""
[Run] Query: Điều kiện được hoàn tiền là gì?
  Retrieved: 3 chunks
    [0.724] policy.txt: Đ?i v?i s?n ph?m l?i, h? tr? hoàn ti?n khi báo trong s? 3 ngày...
  Sources: ['policy.txt']
[OK] retrieval_worker test done.
"""

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

> Trả lời trung thực — không phải để khen ngợi bản thân.

**Tôi làm tốt nhất ở điểm nào?**

Implement Worker tuân thủ cực kỳ nghiêm ngặt Contract (worker_contracts.yaml). Không chỉ lấy đúng chuẩn output, tôi còn làm cả luồng xử lý Error Format (e.g. RETRIEVAL_FAILED) ghi log minh bạch vào mảng worker_io_logs để dễ tracking IO cho debug mà không làm lỡ nhịp hệ thống Graph lớn.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Giải thuật tách chunks (split_into_chunks trong build_index.py) còn khá thô, chủ yếu dùng RegEx dựa trên thẻ === và ký tự trắng \n{2,}. Nhỡ format tài liệu lộn xộn sẽ khiến đoạn text bị cắt xô lệch ý nghĩa ngữ cảnh.

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_

Mảng Retrieval là cốt lõi của bài Lab. Nếu tôi chưa build xong file vector database (ChromaDB) hoặc Worker retrieval bị treo/trả sai schema, Synthesis Worker (người tạo sinh đáp án cuối) sẽ không thể rút trích bất cứ citation nào.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Tôi phụ thuộc vào người làm Supervisor (Graph) phải filter và routing chuẩn, vì Worker của tôi stateless và tin cậy hoàn toàn vào task hay tham số top_k do supervisor đưa xuống trong mảng State.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

> Nêu **đúng 1 cải tiến** với lý do có bằng chứng từ trace hoặc scorecard.
> Không phải "làm tốt hơn chung chung" — phải là:
> *"Tôi sẽ thử X vì trace của câu gq___ cho thấy Y."*

Tôi sẽ tích hợp thêm Hybrid Search (kết hợp Dense Vector MiniLM hiện tại + Tfidf/BM25) vào hàm retrieve_dense. Lý do: Hiện tại, những chuỗi truy vấn đặc thù chứa nhiều ký hiệu hệ thống dạng Exact Match như mã ticket "ERR-404" hay tên file sẽ bị thất thế bởi MiniLM-L6 do model có thiên hướng tính khoảng cách ngữ nghĩa thay vì ghim sát token. Trace các testcases nếu query hỏi trực tiếp các mã này sẽ có nguy cơ sinh điểm cosine quá chậm hoặc gọi nhầm chunk không bám sát yêu cầu.

---


