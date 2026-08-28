# monapay

MONA Pay là cổng thanh toán và API ngân hàng của The MONA Group, giúp doanh nghiệp Việt Nam nhận và xác nhận tiền chuyển khoản theo thời gian thực qua tài khoản ảo (VA), VietQR, webhook và Telegram — thiết kế để cả lập trình viên lẫn AI agent tích hợp trong vài phút.

SDK Python đồng bộ, chỉ dùng standard library. MONA Pay miễn phí hoàn toàn.

## Cài đặt

```bash
pip install monapay
```

## Bắt đầu nhanh

```python
import os
from monapay import MonaPay

mona = MonaPay(
    os.environ["MONA_USERNAME"],
    os.environ["MONA_PASSWORD"],
    client_secret=os.getenv("MONA_CLIENT_SECRET"),
)

# Tự login và giữ token.
print(mona.me())

# Lần đầu: secret chỉ hiện một lần. SDK giữ key mới cho instance hiện tại.
key = mona.keys.generate("Web ban hang")
print("Lưu MONA_CLIENT_SECRET an toàn:", key["client_secret"])

mona.webhooks.create({
    "name": "Web ban hang",
    "webhook_url": "https://shop.vn/webhooks/monapay",
    "auth_type": "HMAC_SHA256",
    "secret_key": os.environ["MONA_WEBHOOK_SECRET"],
    "payload_format": "application/json",
})

qr = mona.qr.generate({
    "ownerNumber": "123456789", "ownerType": "ORG",
    "merchantId": "MC00012345", "terminalId": "TM0001", "orderId": "DH10234",
    "virtualAccountPrefix": "MONA", "beneficiaryName": "CONG TY ABC",
    "amount": 2500000, "description": "Thanh toan DH10234",
})
print(qr["qr_data_url"])
```

Client tự login lại và thử request đúng một lần khi gặp HTTP 401. Các method trả trực tiếp trường `data`; `ApiError` có `status` và `body`.

Các nhóm method: `keys`, `va`, `bank_accounts`, `qr`, `transactions`, `webhooks`, `webhook_logs`. Tên method dùng snake_case, ví dụ `va.register_notification(...)` và `transactions.retry(id, target_type="WEBHOOK", target_id=...)`.

Đọc hết các trang giao dịch:

```python
for tx in mona.iter_transactions("MONA0000010234", limit=100):
    print(tx["transaction_code"], tx["amount"])
```

## Xác thực webhook

Luôn truyền đúng `request.body` dạng bytes, không parse rồi encode lại.

```python
from monapay import verify_webhook

result = verify_webhook(raw_body, headers, os.environ["MONA_WEBHOOK_SECRET"])
if not result.ok:
    return {"reason": result.reason}, 401
save_once(result.payload["transaction_code"], result.payload)
```

Ví dụ nhận webhook cho Flask, FastAPI và Django nằm trong `examples/`. Dùng `transaction_code` làm unique key để chống xử lý trùng.

Tài liệu: https://monapay.vn/docs · AI/LLM: https://monapay.vn/llms.txt · Hotline 1900 636 648 · info@themona.global

## Test

Từ thư mục chứa `python/`:

```bash
python3 -m unittest discover python/tests
```

License MIT.
