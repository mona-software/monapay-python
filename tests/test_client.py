import io
import json
import pathlib
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from monapay import MonaPay


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload

    def getcode(self):
        return self.status


class ClientTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_builds_url_headers_and_caches_token(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"success": True, "data": {"access_token": "token-1"}}),
            FakeResponse({"success": True, "data": {"id": "hook-1"}}),
            FakeResponse({"success": True, "data": {"username": "user"}}),
        ]
        client = MonaPay(
            "user", "pass", client_secret="client-secret", base_url="https://example.test/"
        )
        client.webhooks.create({"name": "Shop", "webhook_url": "https://shop.test/hook"})
        client.me()

        login_request = urlopen.call_args_list[0].args[0]
        write_request = urlopen.call_args_list[1].args[0]
        read_request = urlopen.call_args_list[2].args[0]
        self.assertEqual(login_request.full_url, "https://example.test/api/v1/client/login")
        self.assertEqual(write_request.full_url, "https://example.test/api/v1/client-webhooks")
        self.assertEqual(write_request.get_header("Authorization"), "Bearer token-1")
        self.assertEqual(write_request.get_header("X-client-secret"), "client-secret")
        self.assertIsNone(read_request.get_header("X-client-secret"))
        self.assertEqual(urlopen.call_count, 3)

    @patch("urllib.request.urlopen")
    def test_refreshes_once_after_401(self, urlopen):
        expired = urllib.error.HTTPError(
            "https://example.test/api/v1/client/me",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"detail":"expired"}'),
        )
        urlopen.side_effect = [
            FakeResponse({"success": True, "data": {"access_token": "token-1"}}),
            expired,
            FakeResponse({"success": True, "data": {"access_token": "token-2"}}),
            FakeResponse({"success": True, "data": {"username": "user"}}),
        ]
        client = MonaPay("user", "pass", base_url="https://example.test")
        self.assertEqual(client.me(), {"username": "user"})
        final_request = urlopen.call_args_list[3].args[0]
        self.assertEqual(final_request.get_header("Authorization"), "Bearer token-2")

    @patch("urllib.request.urlopen")
    def test_iter_transactions_reads_all_pages(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"success": True, "data": {"access_token": "token"}}),
            FakeResponse(
                {
                    "success": True,
                    "data": {"data": [{"id": "tx-1"}], "has_next": True, "last_page": 2},
                }
            ),
            FakeResponse(
                {
                    "success": True,
                    "data": {"data": [{"id": "tx-2"}], "has_next": False, "last_page": 2},
                }
            ),
        ]
        client = MonaPay("user", "pass", base_url="https://example.test")
        items = list(client.iter_transactions("MONA 01", limit=1))
        self.assertEqual([item["id"] for item in items], ["tx-1", "tx-2"])
        self.assertIn("virtual_account_number=MONA+01", urlopen.call_args_list[1].args[0].full_url)
        self.assertIn("page=2", urlopen.call_args_list[2].args[0].full_url)


if __name__ == "__main__":
    unittest.main()
