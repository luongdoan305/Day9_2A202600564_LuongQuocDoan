# Phần 6: Tổng Kết & Mở Rộng

## 1. So Sánh 5 Stages

| Stage | Pattern | Khi nào dùng | Độ phức tạp |
|---|---|---|---|
| 1 | Direct LLM | Câu hỏi đơn giản, không cần dữ liệu ngoài, không cần tools | Thấp |
| 2 | LLM + Tools / RAG | Cần tra cứu knowledge base, gọi function, tính toán hoặc lấy dữ liệu có cấu trúc | Trung bình thấp |
| 3 | Single Agent ReAct | Cần agent tự quyết định gọi tool nào, gọi nhiều bước và tổng hợp kết quả | Trung bình |
| 4 | Multi-Agent In-Process | Câu hỏi có nhiều domain, cần nhiều agent chuyên môn chạy song song trong cùng một app | Cao |
| 5 | Distributed A2A | Hệ thống production, nhiều service độc lập, cần discovery, scaling, fault isolation | Rất cao |

## 2. Tóm Tắt Kiến Trúc

Stage 1 bắt đầu từ cách gọi LLM đơn giản nhất: gửi prompt và nhận câu trả lời. Cách này dễ hiểu nhưng không có dữ liệu ngoài, không có memory và không thể gọi tool.

Stage 2 thêm tools và RAG. LLM có thể quyết định gọi function như tra cứu knowledge base hoặc tính toán damages. Tuy nhiên orchestration vẫn do code tự viết, thường chỉ chạy một vòng tool-call thủ công.

Stage 3 dùng ReAct Agent. Agent tự lặp chu trình Think -> Act -> Observe: suy nghĩ cần làm gì, gọi tool, đọc kết quả, rồi quyết định gọi tiếp hay trả lời cuối cùng.

Stage 4 tách logic thành nhiều agent trong cùng một process. Lead agent phân tích câu hỏi, router chọn specialist agents, rồi tax/compliance/privacy agents chạy song song và aggregator tổng hợp kết quả.

Stage 5 đưa mô hình multi-agent ra distributed system. Mỗi agent là một HTTP service riêng giao tiếp qua A2A protocol. Registry giúp các agent tự đăng ký và discovery runtime, thay vì hardcode endpoint.

## 3. Câu Hỏi Ôn Tập

### 1. Khi nào nên dùng single agent thay vì multi-agent?

Nên dùng single agent khi bài toán vẫn nằm trong một domain hoặc số lượng bước xử lý chưa quá phức tạp. Ví dụ: một legal assistant có vài tools tra cứu luật, tính penalty và tìm case law.

Single agent phù hợp khi:

- Workflow ngắn, không cần phân tách chuyên môn rõ ràng.
- Không cần chạy song song nhiều domain.
- Muốn giảm độ phức tạp triển khai.
- Muốn debug dễ hơn.

Multi-agent chỉ nên dùng khi bài toán có nhiều chuyên môn độc lập, ví dụ luật hợp đồng, thuế, compliance và privacy cùng xuất hiện trong một request.

### 2. Ưu điểm của A2A protocol so với REST/gRPC thông thường là gì?

A2A được thiết kế cho giao tiếp giữa các agent, nên nó có các khái niệm phù hợp hơn REST/gRPC thuần:

- Agent Card mô tả năng lực của agent.
- Message, Task, Artifact chuẩn hóa cách gửi và nhận kết quả.
- Có thể truyền metadata như `trace_id`, `context_id`, `delegation_depth`.
- Hỗ trợ discovery qua Registry.
- Giúp agent giao tiếp như peer, không chỉ là gọi API endpoint cố định.

REST/gRPC vẫn tốt cho service truyền thống, nhưng A2A phù hợp hơn khi các service là autonomous agents có kỹ năng, context và luồng xử lý riêng.

### 3. Làm thế nào để prevent infinite delegation loops trong A2A?

Cần giới hạn delegation depth. Mỗi request mang theo metadata:

```json
{
  "trace_id": "...",
  "context_id": "...",
  "delegation_depth": 0
}
```

Mỗi lần agent gọi agent khác, `delegation_depth` tăng thêm 1. Nếu vượt ngưỡng, ví dụ `MAX_DELEGATION_DEPTH = 3`, agent không delegate tiếp nữa mà tự tổng hợp hoặc trả lỗi an toàn.

Ngoài ra có thể thêm:

- Allowlist agent được phép gọi.
- Timeout cho mỗi delegation.
- Circuit breaker khi agent lỗi nhiều lần.
- Log toàn bộ trace để debug vòng lặp.

### 4. Tại sao cần Registry service? Có thể hardcode URLs không?

Registry giúp dynamic discovery. Agent không cần biết trước endpoint cụ thể của agent khác, chỉ cần hỏi Registry: "agent nào xử lý được `tax_question`?".

Lợi ích:

- Dễ thay đổi port hoặc deploy location.
- Dễ scale nhiều instance của cùng một agent.
- Dễ thêm agent mới mà không sửa code các agent cũ.
- Có thể mở rộng sang health check và load balancing.

Vẫn có thể hardcode URLs trong demo nhỏ, nhưng không nên dùng cho hệ thống production vì coupling cao và khó mở rộng.

## 4. Bài Tập Nâng Cao

### Challenge 1: Thêm Memory / Conversation History

Mục tiêu: agent nhớ các câu hỏi trước đó trong cùng một `context_id`.

Hướng triển khai:

- Lưu conversation history theo `context_id`.
- Khi agent nhận request mới, nạp lại history cũ.
- Truyền history vào prompt hoặc graph state.
- Có thể dùng in-memory store cho demo, database/Redis cho production.

### Challenge 2: Add Authentication

Mục tiêu: bảo vệ các A2A endpoints.

Hướng triển khai:

- Thêm API key vào header, ví dụ `X-API-Key`.
- Middleware ở mỗi agent kiểm tra key.
- Registry cũng cần authentication cho `/register` và `/discover`.
- Không commit API key vào repo; lưu trong `.env`.

### Challenge 3: Implement Retry Logic

Mục tiêu: khi agent tạm thời lỗi, hệ thống tự retry.

Hướng triển khai:

- Retry khi gặp timeout, 5xx hoặc connection error.
- Dùng exponential backoff: 1s, 2s, 4s.
- Giới hạn số lần retry.
- Nếu vẫn fail, trả về partial result thay vì làm sập toàn bộ request.

### Challenge 4: Monitoring & Observability

Mục tiêu: theo dõi hiệu năng và lỗi của hệ thống multi-agent.

Có thể monitor:

- Latency toàn request.
- Latency từng agent.
- Số lần delegation.
- Tỷ lệ lỗi của từng service.
- Token usage nếu provider hỗ trợ.
- Trace theo `trace_id`.

Công cụ phù hợp:

- LangSmith cho LangChain/LangGraph traces.
- Prometheus + Grafana cho metrics.
- Structured logs theo JSON cho production.

## 5. Bài Tập Cộng Điểm

Sau khi chạy full Stage 5 bằng:

```bash
uv run python test_client.py
```

trả lời hai câu hỏi:

### 1. Latency là bao nhiêu giây?

Trong bản đã hoàn thiện, `test_client.py` sẽ in:

```text
Latency: <số_giây>s
Trace ID for logs: <trace_id>
```

Ghi lại latency thực tế sau khi chạy. Ví dụ:

```text
Latency: 42.18s
```

### 2. Đề xuất phương án giảm latency

Một số phương án:

- Chạy tax agent và compliance agent song song bằng LangGraph `Send`.
- Giảm độ dài prompt của specialist agents.
- Giới hạn response dưới một số từ nhất định.
- Dùng model nhanh hơn cho routing.
- Cache kết quả discovery từ Registry.
- Cache kết quả tool/agent cho câu hỏi trùng lặp.
- Timeout và fallback partial answer nếu một agent quá chậm.

Trong repo này, Tax Agent đã được chỉnh để trả lời ngắn gọn hơn. Khi chạy lại `test_client.py`, so sánh latency trước và sau khi chỉnh prompt để báo cáo mức giảm.

## 6. Kết Luận

Codelab đi từ LLM đơn giản đến hệ thống distributed multi-agent:

- Stage 1 giúp hiểu direct LLM call.
- Stage 2 thêm tool calling và RAG.
- Stage 3 tự động hóa tool loop bằng ReAct.
- Stage 4 chia việc cho nhiều agent chuyên môn trong cùng process.
- Stage 5 triển khai agent thành các service độc lập giao tiếp qua A2A.

Điểm quan trọng nhất là chọn đúng mức kiến trúc cho bài toán. Không phải task nào cũng cần multi-agent hoặc distributed system. Càng nhiều agent và service, hệ thống càng mạnh hơn nhưng cũng khó debug, deploy và vận hành hơn.
