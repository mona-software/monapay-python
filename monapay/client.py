"""Synchronous, standard-library-only MONA Pay client."""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Iterator, Mapping, Optional


DEFAULT_BASE_URL = "https://api.monapay.vn"


class ApiError(RuntimeError):
    """Error returned by MONA Pay or raised while decoding its response."""

    def __init__(self, message: str, status: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _segment(value: Any) -> str:
    return urllib.parse.quote(str(value), safe="")


def _log_query(options: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": options.get("status"),
        "from_date": options.get("from_date"),
        "to_date": options.get("to_date"),
        "page": options.get("page"),
        "limit": options.get("limit"),
    }


def _email_log_query(options: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "config_id": options.get("config_id"),
        "status": options.get("status"),
        "event_type": options.get("event_type"),
        "from_date": options.get("from_date"),
        "to_date": options.get("to_date"),
        "page": options.get("page"),
        "limit": options.get("limit"),
    }


class _Resource:
    def __init__(self, client: "MonaPay"):
        self._client = client


class Keys(_Resource):
    def generate(self, name: str = "Default Key") -> Any:
        data = self._client._request("POST", "/api/v1/client-keys/generate", body={"name": name})
        if not self._client.client_secret and isinstance(data, dict):
            self._client.client_secret = data.get("client_secret")
        return data

    def list(self) -> Any:
        return self._client._request("GET", "/api/v1/client-keys/list")

    def destroy(self, key_id: str) -> Any:
        return self._client._request("DELETE", "/api/v1/client-keys/destroy/" + _segment(key_id))


class VirtualAccounts(_Resource):
    def register(self, body: Mapping[str, Any]) -> Any:
        return self._client._request("POST", "/api/v1/acb/virtual-account/registration", body=body)

    def verify(self, request_id: str, code: str) -> Any:
        return self._client._request(
            "POST",
            "/api/v1/acb/{}/virtual-account/verification".format(_segment(request_id)),
            body={"code": code},
        )

    def register_notification(
        self, va_id: str, body: Optional[Mapping[str, Any]] = None
    ) -> Any:
        return self._client._request(
            "POST",
            "/api/v1/acb/{}/notification/registration".format(_segment(va_id)),
            body=body or {"receive_noti_realtime": True},
        )

    def verify_notification(self, request_id: str, code: str) -> Any:
        return self._client._request(
            "POST",
            "/api/v1/acb/{}/notification/verification".format(_segment(request_id)),
            body={"code": code},
        )

    def notification_detail(self, va_id: str) -> Any:
        return self._client._request(
            "GET",
            "/api/v1/acb/{}/notification/details".format(_segment(va_id)),
        )

    def list(self, bank_account_id: str) -> Any:
        return self._client._request(
            "GET", "/api/v1/acb/{}/virtual-account/retrieve".format(_segment(bank_account_id))
        )


class BankAccounts(_Resource):
    def list(self) -> Any:
        return self._client._request("GET", "/api/v1/client/bank-accounts")


class PaymentProfile(_Resource):
    def get(self) -> Any:
        return self._client._request("GET", "/api/v1/payment-profile")

    def set(self, body: Mapping[str, Any]) -> Any:
        return self._client._request("PUT", "/api/v1/payment-profile", body=body)


class Checkouts(_Resource):
    def create(
        self,
        body: Mapping[str, Any],
        idempotency_key: Optional[str] = None,
        sandbox: bool = False,
    ) -> Any:
        request_body = dict(body)
        if sandbox:
            request_body["sandbox"] = True
        return self._client._request(
            "POST",
            "/api/v1/checkouts",
            body=request_body,
            headers={"Idempotency-Key": idempotency_key or str(uuid.uuid4())},
        )

    def get(self, checkout_id: str) -> Any:
        return self._client._request(
            "GET", "/api/v1/checkouts/" + _segment(checkout_id)
        )

    def list(self, **options: Any) -> Any:
        return self._client._request(
            "GET",
            "/api/v1/checkouts",
            query={
                "status": options.get("status"),
                "order_code": options.get("order_code"),
                "from_date": options.get("from_date"),
                "to_date": options.get("to_date"),
                "page": options.get("page"),
                "limit": options.get("limit"),
            },
        )

    def cancel(
        self, checkout_id: str, idempotency_key: Optional[str] = None
    ) -> Any:
        return self._client._request(
            "POST",
            "/api/v1/checkouts/{}/cancel".format(_segment(checkout_id)),
            body={},
            headers={"Idempotency-Key": idempotency_key or str(uuid.uuid4())},
        )


class QrPayments(_Resource):
    def generate(self, body: Mapping[str, Any]) -> Any:
        return self._client._request("POST", "/api/v1/acb/qr-payment/generate", body=body)

    def cancel(self, qr_code_id: str, body: Optional[Mapping[str, Any]] = None) -> Any:
        return self._client._request(
            "DELETE",
            "/api/v1/acb/qr-payment/{}/cancellation".format(_segment(qr_code_id)),
            body=body,
        )


class Transactions(_Resource):
    def list(
        self, virtual_account_number: str, page: int = 1, limit: int = 100
    ) -> Any:
        if not virtual_account_number:
            raise ValueError("virtual_account_number là bắt buộc")
        return self._client._request(
            "GET",
            "/api/v1/acb/virtual-account/transactions",
            query={
                "virtual_account_number": virtual_account_number,
                "page": page,
                "limit": limit,
            },
        )

    def iterate(
        self, virtual_account_number: str, page: int = 1, limit: int = 100
    ) -> Iterator[Any]:
        current_page = page
        while True:
            result = self.list(virtual_account_number, page=current_page, limit=limit)
            for transaction in (result or {}).get("data", []):
                yield transaction
            if "has_next" in (result or {}):
                has_next = bool(result["has_next"])
            else:
                has_next = current_page < int((result or {}).get("last_page", current_page))
            if not has_next:
                return
            current_page += 1

    def retry(
        self, transaction_id: str, target_type: str, target_id: Optional[str] = None
    ) -> Any:
        body = {"target_type": target_type}
        if target_id is not None:
            body["target_id"] = target_id
        return self._client._request(
            "POST",
            "/api/v1/acb/virtual-account/transactions/{}/retry".format(
                _segment(transaction_id)
            ),
            body=body,
        )


class Sandbox(_Resource):
    def transaction(
        self,
        amount: int,
        description: Optional[str] = None,
        virtual_account_number: Optional[str] = None,
    ) -> Any:
        body: Dict[str, Any] = {"amount": amount}
        if description is not None:
            body["description"] = description
        if virtual_account_number is not None:
            body["virtual_account_number"] = virtual_account_number
        return self._client._request("POST", "/api/v1/sandbox/transactions", body=body)


class Webhooks(_Resource):
    def list(self) -> Any:
        return self._client._request("GET", "/api/v1/client-webhooks")

    def create(self, body: Mapping[str, Any]) -> Any:
        return self._client._request("POST", "/api/v1/client-webhooks", body=body)

    def update(self, config_id: str, body: Mapping[str, Any]) -> Any:
        return self._client._request(
            "PUT", "/api/v1/client-webhooks/" + _segment(config_id), body=body
        )

    def remove(self, config_id: str) -> Any:
        return self._client._request(
            "DELETE", "/api/v1/client-webhooks/" + _segment(config_id)
        )

    def test(self, body: Mapping[str, Any]) -> Any:
        return self._client._request("POST", "/api/v1/client-webhooks/test", body=body)


class WebhookLogs(_Resource):
    def list(self, **options: Any) -> Any:
        return self._client._request(
            "GET", "/api/v1/webhook-logs", query=_log_query(options)
        )

    def stats(self, **options: Any) -> Any:
        return self._client._request(
            "GET", "/api/v1/webhook-logs/stats", query=_log_query(options)
        )


class EmailConfigs(_Resource):
    def list(self) -> Any:
        return self._client._request("GET", "/api/v1/email-configs")

    def get(self, config_id: str) -> Any:
        return self._client._request(
            "GET", "/api/v1/email-configs/" + _segment(config_id)
        )

    def create(self, body: Mapping[str, Any]) -> Any:
        return self._client._request("POST", "/api/v1/email-configs", body=body)

    def update(self, config_id: str, body: Mapping[str, Any]) -> Any:
        return self._client._request(
            "PUT", "/api/v1/email-configs/" + _segment(config_id), body=body
        )

    def remove(self, config_id: str) -> Any:
        return self._client._request(
            "DELETE", "/api/v1/email-configs/" + _segment(config_id)
        )

    def verify(self, config_id: str, email: str, code: str) -> Any:
        return self._client._request(
            "POST",
            "/api/v1/email-configs/{}/verify".format(_segment(config_id)),
            body={"email": email, "code": code},
        )

    def resend_verification(self, config_id: str, email: str) -> Any:
        return self._client._request(
            "POST",
            "/api/v1/email-configs/{}/resend-verification".format(
                _segment(config_id)
            ),
            body={"email": email},
        )

    def test(self, config_id: str) -> Any:
        return self._client._request(
            "POST",
            "/api/v1/email-configs/{}/test".format(_segment(config_id)),
            body={},
        )


class EmailLogs(_Resource):
    def list(self, **options: Any) -> Any:
        return self._client._request(
            "GET", "/api/v1/email-logs", query=_email_log_query(options)
        )

    def stats(self, **options: Any) -> Any:
        return self._client._request(
            "GET",
            "/api/v1/email-logs/stats",
            query={
                "from_date": options.get("from_date"),
                "to_date": options.get("to_date"),
            },
        )


class EmailSuppressions(_Resource):
    def list(self) -> Any:
        return self._client._request("GET", "/api/v1/email-suppressions")

    def remove(self, email: str) -> Any:
        return self._client._request(
            "DELETE", "/api/v1/email-suppressions/" + _segment(email)
        )


class MonaPay:
    """Synchronous MONA Pay API client using OAuth client credentials or legacy password login."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30,
        client_id: Optional[str] = None,
    ):
        has_client_credentials = bool(client_id and client_secret)
        has_password_credentials = bool(username and password)
        if not has_client_credentials and not has_password_credentials:
            raise ValueError(
                "Cần client_id + client_secret hoặc username + password; nên dùng "
                "client_id/client_secret, tài khoản bật 2FA không login bằng mật khẩu được"
            )
        self.client_id = client_id
        self.username = username
        self.password = password
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._access_token = None  # type: Optional[str]
        self._token_expires_at = 0.0
        self._login_lock = threading.Lock()

        self.keys = Keys(self)
        self.va = VirtualAccounts(self)
        self.bank_accounts = BankAccounts(self)
        self.payment_profile = PaymentProfile(self)
        self.paymentProfile = self.payment_profile
        self.checkouts = Checkouts(self)
        self.qr = QrPayments(self)
        self.transactions = Transactions(self)
        self.sandbox = Sandbox(self)
        self.webhooks = Webhooks(self)
        self.webhook_logs = WebhookLogs(self)
        self.email_configs = EmailConfigs(self)
        self.email_logs = EmailLogs(self)
        self.email_suppressions = EmailSuppressions(self)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "MonaPay":
        """Create a client, preferring MONAPAY_CLIENT_ID/MONAPAY_CLIENT_SECRET."""
        values = os.environ if env is None else env
        common = {"base_url": values.get("MONAPAY_BASE_URL", DEFAULT_BASE_URL)}
        if values.get("MONAPAY_CLIENT_ID") and values.get("MONAPAY_CLIENT_SECRET"):
            return cls(
                client_id=values["MONAPAY_CLIENT_ID"],
                client_secret=values["MONAPAY_CLIENT_SECRET"],
                **common,
            )
        if values.get("MONAPAY_USERNAME") and values.get("MONAPAY_PASSWORD"):
            return cls(
                username=values["MONAPAY_USERNAME"],
                password=values["MONAPAY_PASSWORD"],
                client_secret=values.get("MONAPAY_CLIENT_SECRET"),
                **common,
            )
        raise ValueError(
            "Thiếu MONAPAY_CLIENT_ID / MONAPAY_CLIENT_SECRET hoặc MONAPAY_USERNAME / "
            "MONAPAY_PASSWORD; nên dùng client_id/client_secret, tài khoản bật 2FA "
            "không login bằng mật khẩu được"
        )

    def me(self) -> Any:
        return self._request("GET", "/api/v1/client/me")

    def register_virtual_account(self, body: Mapping[str, Any]) -> Any:
        return self.va.register(body)

    def verify_virtual_account(self, request_id: str, code: str) -> Any:
        return self.va.verify(request_id, code)

    def register_notification(
        self, va_id: str, body: Optional[Mapping[str, Any]] = None
    ) -> Any:
        return self.va.register_notification(va_id, body)

    def verify_notification(self, request_id: str, code: str) -> Any:
        return self.va.verify_notification(request_id, code)

    def notification_detail(self, va_id: str) -> Any:
        return self.va.notification_detail(va_id)

    def iter_transactions(
        self, virtual_account_number: str, page: int = 1, limit: int = 100
    ) -> Iterator[Any]:
        return self.transactions.iterate(virtual_account_number, page=page, limit=limit)

    def _login(self) -> str:
        with self._login_lock:
            if self._access_token and time.time() < self._token_expires_at:
                return self._access_token
            using_client_credentials = bool(self.client_id and self.client_secret)
            data = self._send(
                "POST",
                "/api/v1/oauth/token" if using_client_credentials else "/api/v1/client/login",
                body=(
                    {
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    }
                    if using_client_credentials
                    else {"username": self.username, "password": self.password}
                ),
                authenticated=False,
            )
            if not isinstance(data, dict) or not data.get("access_token"):
                raise ApiError("Response xác thực không có access_token")
            self._access_token = data["access_token"]
            expires_in = float(data.get("expires_in") or (3600 if using_client_credentials else 86400))
            self._token_expires_at = time.time() + max(0.0, expires_in - 60)
            return self._access_token

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        retry: bool = True,
    ) -> Any:
        if not self._access_token or time.time() >= self._token_expires_at:
            self._access_token = None
            self._login()
        try:
            return self._send(
                method, path, body=body, query=query, headers=headers, authenticated=True
            )
        except ApiError as error:
            if error.status == 401 and retry:
                self._access_token = None
                self._token_expires_at = 0.0
                self._login()
                return self._request(
                    method,
                    path,
                    body=body,
                    query=query,
                    headers=headers,
                    retry=False,
                )
            raise

    def _send(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        authenticated: bool = True,
    ) -> Any:
        clean_query = {key: value for key, value in (query or {}).items() if value is not None}
        url = self.base_url + path
        if clean_query:
            url += "?" + urllib.parse.urlencode(clean_query)

        request_headers = {"Accept": "application/json"}
        request_headers.update(headers or {})
        if authenticated:
            request_headers["Authorization"] = "Bearer " + str(self._access_token)
        if authenticated and method != "GET" and self.client_secret:
            request_headers["X-Client-Secret"] = self.client_secret
        encoded_body = None
        if body is not None:
            request_headers["Content-Type"] = "application/json"
            encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")

        request = urllib.request.Request(
            url, data=encoded_body, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.getcode()
                raw = response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read()
        except urllib.error.URLError as error:
            raise ApiError("Không kết nối được MONA Pay: {}".format(error.reason)) from error

        if raw:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ApiError(
                    "MONA Pay trả response không phải JSON (HTTP {})".format(status),
                    status=status,
                    body=raw,
                ) from error
        else:
            payload = {}

        if not 200 <= status < 300 or payload.get("success") is False:
            detail = payload.get("detail")
            if not isinstance(detail, str):
                detail = None
            raise ApiError(
                payload.get("message") or detail or "MONA Pay API lỗi HTTP {}".format(status),
                status=status,
                body=payload,
            )
        return payload.get("data")
