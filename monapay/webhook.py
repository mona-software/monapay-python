"""MONA Pay webhook signature verification."""

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class WebhookResult:
    ok: bool
    reason: Optional[str] = None
    payload: Any = None


def _header(headers: Mapping[str, Any], wanted: str) -> Optional[str]:
    lowered = wanted.lower()
    for name, value in headers.items():
        if str(name).lower() == lowered:
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            return None if value is None else str(value)
    return None


def verify_webhook(
    raw_body: bytes,
    headers: Mapping[str, Any],
    secret: str,
    tolerance: int = 300,
) -> WebhookResult:
    """Verify timestamp + HMAC against the exact request bytes, then parse JSON."""
    if not isinstance(raw_body, bytes):
        raise TypeError("raw_body phải là bytes")
    if tolerance < 0:
        raise ValueError("tolerance phải là số không âm")

    timestamp_text = _header(headers, "x-mona-timestamp")
    signature = _header(headers, "x-mona-signature")
    if not timestamp_text:
        return WebhookResult(False, "missing_timestamp")
    if not timestamp_text.isdigit():
        return WebhookResult(False, "invalid_timestamp")
    timestamp = int(timestamp_text)
    if abs(int(time.time()) - timestamp) > tolerance:
        return WebhookResult(False, "timestamp_out_of_tolerance")
    if not signature:
        return WebhookResult(False, "missing_signature")

    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp_text.encode("ascii") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    match = re.fullmatch(r"sha256=([0-9a-fA-F]{64})", signature)
    supplied = match.group(1).lower() if match else "0" * 64
    valid_signature = hmac.compare_digest(expected, supplied) and match is not None
    if not valid_signature:
        return WebhookResult(False, "invalid_signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return WebhookResult(False, "invalid_json")
    return WebhookResult(True, payload=payload)
