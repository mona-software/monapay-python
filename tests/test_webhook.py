import hashlib
import hmac
import json
import pathlib
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from monapay import verify_webhook


class WebhookTests(unittest.TestCase):
    def signature(self, raw_body, secret, timestamp):
        digest = hmac.new(
            secret.encode(), str(timestamp).encode() + b"." + raw_body, hashlib.sha256
        ).hexdigest()
        return "sha256=" + digest

    def test_valid_signature(self):
        raw = json.dumps({"amount": 2500000, "transaction_code": "FT1"}).encode()
        timestamp = int(time.time())
        result = verify_webhook(
            raw,
            {
                "X-Mona-Timestamp": str(timestamp),
                "x-mona-signature": self.signature(raw, "secret", timestamp),
            },
            "secret",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.payload["transaction_code"], "FT1")

    def test_invalid_signature(self):
        timestamp = int(time.time())
        result = verify_webhook(
            b"{}",
            {
                "x-mona-timestamp": str(timestamp),
                "x-mona-signature": "sha256=" + "0" * 64,
            },
            "secret",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "invalid_signature")

    def test_expired_timestamp(self):
        timestamp = int(time.time()) - 301
        result = verify_webhook(
            b"{}",
            {
                "x-mona-timestamp": str(timestamp),
                "x-mona-signature": self.signature(b"{}", "secret", timestamp),
            },
            "secret",
            tolerance=300,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "timestamp_out_of_tolerance")


if __name__ == "__main__":
    unittest.main()
