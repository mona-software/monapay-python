# monapay

Python SDK for the MONA Pay API: create checkout links and VietQR codes, manage virtual accounts, webhooks and email notifications, and verify signed webhooks.

The client is synchronous and uses only the standard library. Python 3.8 or later.

## Install

```bash
pip install monapay
```

## Quick start

```python
from monapay import MonaPay

mona = MonaPay.from_env()
checkout = mona.checkouts.create({
    "amount": 250000,
    "order_code": "DH10234",
    "return_url": "https://shop.example/payment/return",
})
print(checkout["checkout_url"])
```

## Usage

### Client

```python
import os
from monapay import MonaPay

# From environment variables (see Configuration)
mona = MonaPay.from_env()

# Or with explicit credentials
client = MonaPay(
    client_id=os.environ["MONAPAY_CLIENT_ID"],
    client_secret=os.environ["MONAPAY_CLIENT_SECRET"],
)

print(mona.me())
```

- The first call fetches an OAuth token. The token is cached until 60 seconds before `expires_in` and reused.
- A request that fails with HTTP 401 is retried once with a fresh token.
- Methods return the `data` field of the API response.
- Errors are raised as `ApiError` with `status` and `body`.
- `MonaPay(...)` also accepts `base_url` and `timeout` (seconds, default 30).
- `checkouts.create` and `checkouts.cancel` send an `Idempotency-Key` header. Pass `idempotency_key=` to set it yourself; otherwise a random UUID is used.

### Resources

| Attribute | Methods |
| --- | --- |
| `keys` | `generate`, `list`, `destroy` |
| `bank_accounts` | `list` |
| `va` | `register`, `verify`, `register_notification`, `verify_notification`, `notification_detail`, `list` |
| `payment_profile` (alias `paymentProfile`) | `get`, `set` |
| `checkouts` | `create`, `get`, `list`, `cancel` |
| `qr` | `generate`, `cancel` |
| `transactions` | `list`, `iterate`, `retry` |
| `sandbox` | `transaction` |
| `webhooks` | `list`, `create`, `update`, `remove`, `test` |
| `webhook_logs` | `list`, `stats` |
| `email_configs` | `list`, `get`, `create`, `update`, `remove`, `verify`, `resend_verification`, `test` |
| `email_logs` | `list`, `stats` |
| `email_suppressions` | `list`, `remove` |

The client also exposes `me()`, `iter_transactions()` and the shortcuts `register_virtual_account`, `verify_virtual_account`, `register_notification`, `verify_notification` and `notification_detail`.

### Test with the sandbox

No bank connection is needed.

```python
checkout = mona.checkouts.create({
    "amount": 10000,
    "order_code": "DH10234",
    "return_url": "https://shop.example/payment/return",
}, sandbox=True)
mona.sandbox.transaction(
    virtual_account_number=checkout["bank"]["account_number"],
    amount=checkout["amount"],
    description=checkout["order_code"],
)
paid = mona.checkouts.get(checkout["id"])
print(paid["status"])  # "paid"
```

The `CHECKOUT_PAID` webhook carries the checkout in `checkout_id`, not `id`.

### Dynamic VietQR

```python
qr = mona.qr.generate({
    "ownerNumber": "123456789", "ownerType": "ORG",
    "merchantId": "MC00012345", "terminalId": "TM0001", "orderId": "DH10234",
    "virtualAccountPrefix": "MONA", "beneficiaryName": "CONG TY ABC",
    "amount": 2500000, "description": "Thanh toan DH10234",
})
print(qr["qr_data_url"])
```

### Connect a bank account with OTP

The bank sends each OTP to the account owner's registered phone number. Your app must ask the user for the code at the verify steps; do not generate or store OTPs.

```python
registration = mona.register_virtual_account({
    "customer_type": "PERS",
    "account_number": 123456789,
    "phone_number": "0901234567",
    "virtual_account_info": {
        "virtual_account_prefix_code": "LOC",
        "virtual_account_content": "DH10234",
        "virtual_account_explain": "Don hang 10234",
    },
    "user_agreement": True,
})

va = mona.verify_virtual_account(registration["acb_request"]["id"], first_otp_from_user)
notification = mona.register_notification(va["id"])
mona.verify_notification(notification["acb_request"]["id"], second_otp_from_user)

print(mona.notification_detail(va["id"]))
```

### Transactions

```python
for tx in mona.iter_transactions("MONA0000010234", limit=100):
    print(tx["transaction_code"], tx["amount"])

mona.transactions.retry("transaction-id", "WEBHOOK", target_id="webhook-config-id")
```

### Webhooks

Register an HMAC webhook:

```python
mona.webhooks.create({
    "name": "Web ban hang",
    "webhook_url": "https://shop.example/webhooks/monapay",
    "auth_type": "HMAC_SHA256",
    "secret_key": os.environ["MONA_WEBHOOK_SECRET"],
    "payload_format": "application/json",
})
```

Verify incoming requests against the raw request body as `bytes`. Do not parse and re-encode it: the signature covers the exact request bytes. `verify_webhook` reads the `X-Mona-Timestamp` and `X-Mona-Signature` headers and rejects timestamps older than `tolerance` seconds (default 300).

```python
from monapay import verify_webhook

result = verify_webhook(raw_body, headers, os.environ["MONA_WEBHOOK_SECRET"])
if not result.ok:
    return {"reason": result.reason}, 401
save_once(result.payload["transaction_code"], result.payload)
```

Flask, FastAPI and Django handlers are in `examples/`. Store `transaction_code` under a unique constraint so redelivered webhooks are not processed twice.

### Email notifications

MONA Pay sends a 6-digit code to each new address. Ask the user for the code from their inbox, then verify it.

```python
config = mona.email_configs.create({"name": "Accounting", "recipients": ["accounting@shop.example"]})
email = config["pending_verification"][0]
code = ask_user_for_code(email)
mona.email_configs.verify(config["id"], email, code)
mona.email_configs.test(config["id"])
print(mona.email_logs.list(config_id=config["id"], status="sent"))
```

Bounced or complained addresses appear in `email_suppressions.list()`. Call `email_suppressions.remove(email)` only after fixing the cause.

## Configuration

`MonaPay.from_env()` reads:

| Variable | Purpose |
| --- | --- |
| `MONAPAY_CLIENT_ID`, `MONAPAY_CLIENT_SECRET` | API key credentials (preferred) |
| `MONAPAY_USERNAME`, `MONAPAY_PASSWORD` | Legacy password login; does not work for accounts with 2FA enabled |
| `MONAPAY_BASE_URL` | API base URL, defaults to `https://api.monapay.vn` |

The examples above also use `MONA_WEBHOOK_SECRET` for the webhook signing secret.

Documentation: https://monapay.vn/docs

## Development

```bash
python -m unittest discover tests
```

## License

MIT

**MONA Pay is part of MONA Cloud by The MONA Group.**
