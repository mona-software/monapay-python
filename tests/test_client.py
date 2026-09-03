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
    def test_client_credentials_use_oauth_and_cache_token(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(
                {
                    "success": True,
                    "data": {"access_token": "oauth-token", "expires_in": 3600},
                }
            ),
            FakeResponse({"success": True, "data": {"id": "hook-1"}}),
            FakeResponse({"success": True, "data": {"username": "shop"}}),
        ]
        client = MonaPay(
            client_id="client-id",
            client_secret="client-secret",
            base_url="https://example.test",
        )
        client.webhooks.create({"name": "Shop", "webhook_url": "https://shop.test/hook"})
        client.me()

        oauth_request = urlopen.call_args_list[0].args[0]
        write_request = urlopen.call_args_list[1].args[0]
        self.assertEqual(oauth_request.full_url, "https://example.test/api/v1/oauth/token")
        self.assertEqual(
            json.loads(oauth_request.data),
            {
                "grant_type": "client_credentials",
                "client_id": "client-id",
                "client_secret": "client-secret",
            },
        )
        self.assertEqual(write_request.get_header("X-client-secret"), "client-secret")
        self.assertEqual(urlopen.call_count, 3)

    def test_from_env_prefers_client_credentials(self):
        client = MonaPay.from_env(
            {
                "MONAPAY_CLIENT_ID": "client-id",
                "MONAPAY_CLIENT_SECRET": "client-secret",
                "MONAPAY_USERNAME": "legacy-user",
                "MONAPAY_PASSWORD": "legacy-pass",
            }
        )
        self.assertEqual(client.client_id, "client-id")
        self.assertIsNone(client.username)

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

    @patch("urllib.request.urlopen")
    def test_va_has_all_five_bank_linking_methods(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"success": True, "data": {"access_token": "token"}}),
            FakeResponse({"success": True, "data": {"ok": True}}),
            FakeResponse({"success": True, "data": {"ok": True}}),
            FakeResponse({"success": True, "data": {"ok": True}}),
            FakeResponse({"success": True, "data": {"ok": True}}),
            FakeResponse({"success": True, "data": {"ok": True}}),
        ]
        client = MonaPay(
            client_id="client-id",
            client_secret="client-secret",
            base_url="https://example.test",
        )
        client.register_virtual_account(
            {
                "account_number": 123456789,
                "virtual_account_info": {"virtual_account_prefix_code": "LOC"},
            }
        )
        client.verify_virtual_account("request/id", "123456")
        client.register_notification("va/id")
        client.verify_notification("notification/id", "654321")
        client.notification_detail("va/id")

        api_requests = [call.args[0] for call in urlopen.call_args_list[1:]]
        self.assertEqual(
            api_requests[0].full_url,
            "https://example.test/api/v1/acb/virtual-account/registration",
        )
        self.assertEqual(
            api_requests[1].full_url,
            "https://example.test/api/v1/acb/request%2Fid/virtual-account/verification",
        )
        self.assertEqual(json.loads(api_requests[1].data), {"code": "123456"})
        self.assertEqual(
            api_requests[2].full_url,
            "https://example.test/api/v1/acb/va%2Fid/notification/registration",
        )
        self.assertEqual(
            json.loads(api_requests[2].data), {"receive_noti_realtime": True}
        )
        self.assertEqual(
            api_requests[3].full_url,
            "https://example.test/api/v1/acb/notification%2Fid/notification/verification",
        )
        self.assertEqual(
            api_requests[4].full_url,
            "https://example.test/api/v1/acb/va%2Fid/notification/details",
        )
        self.assertEqual(api_requests[4].method, "GET")

    @patch("urllib.request.urlopen")
    def test_email_resources_map_configs_logs_stats_and_suppressions(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"success": True, "data": {"access_token": "token"}}),
            *[FakeResponse({"success": True, "data": {"ok": True}}) for _ in range(12)],
        ]
        client = MonaPay(
            client_id="client-id",
            client_secret="client-secret",
            base_url="https://example.test",
        )
        client.email_configs.list()
        client.email_configs.get("config/id")
        client.email_configs.create(
            {
                "name": "Kế toán",
                "recipients": ["kt@example.com"],
                "events": ["TRANSACTION_IN"],
            }
        )
        client.email_configs.update(
            "config/id", {"is_active": True, "virtual_account_id": None}
        )
        client.email_configs.remove("config/id")
        client.email_configs.verify("config/id", "kt@example.com", "123456")
        client.email_configs.resend_verification("config/id", "kt@example.com")
        client.email_configs.test("config/id")
        client.email_logs.list(
            config_id="config/id",
            status="sent",
            event_type="TEST",
            from_date="2026-09-01",
            page=2,
            limit=100,
        )
        client.email_logs.stats(from_date="2026-09-01", to_date="2026-09-03")
        client.email_suppressions.list()
        client.email_suppressions.remove("bounce+tag@example.com")

        requests = [call.args[0] for call in urlopen.call_args_list[1:]]
        self.assertEqual(len(requests), 12)
        self.assertEqual(requests[0].full_url, "https://example.test/api/v1/email-configs")
        self.assertEqual(
            requests[1].full_url,
            "https://example.test/api/v1/email-configs/config%2Fid",
        )
        self.assertEqual(
            json.loads(requests[2].data),
            {
                "name": "Kế toán",
                "recipients": ["kt@example.com"],
                "events": ["TRANSACTION_IN"],
            },
        )
        self.assertEqual(
            json.loads(requests[3].data),
            {"is_active": True, "virtual_account_id": None},
        )
        self.assertEqual(requests[4].method, "DELETE")
        self.assertEqual(
            json.loads(requests[5].data),
            {"email": "kt@example.com", "code": "123456"},
        )
        self.assertTrue(requests[6].full_url.endswith("/config%2Fid/resend-verification"))
        self.assertEqual(json.loads(requests[7].data), {})
        self.assertIn("config_id=config%2Fid", requests[8].full_url)
        self.assertIn("event_type=TEST", requests[8].full_url)
        self.assertIn("to_date=2026-09-03", requests[9].full_url)
        self.assertEqual(
            requests[10].full_url, "https://example.test/api/v1/email-suppressions"
        )
        self.assertEqual(
            requests[11].full_url,
            "https://example.test/api/v1/email-suppressions/bounce%2Btag%40example.com",
        )
        for request in requests:
            if request.method != "GET":
                self.assertEqual(request.get_header("X-client-secret"), "client-secret")

    @patch("urllib.request.urlopen")
    def test_checkouts_and_payment_profile_map_six_methods(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({"success": True, "data": {"access_token": "token"}}),
            *[FakeResponse({"success": True, "data": {"ok": True}}) for _ in range(6)],
        ]
        client = MonaPay(
            client_id="client-id",
            client_secret="client-secret",
            base_url="https://example.test",
        )
        client.payment_profile.get()
        client.paymentProfile.set({"display_name": "Shop MONA", "locale": "vi"})
        client.checkouts.create(
            {
                "amount": 250000,
                "order_code": "DH_10234",
                "return_url": "https://shop.test/return",
            },
            idempotency_key="create-key",
        )
        client.checkouts.get("checkout/id")
        client.checkouts.list(
            status="pending",
            order_code="DH_10234",
            from_date="2026-09-01",
            page=2,
            limit=50,
        )
        client.checkouts.cancel("checkout/id", idempotency_key="cancel-key")

        requests = [call.args[0] for call in urlopen.call_args_list[1:]]
        self.assertEqual(len(requests), 6)
        self.assertEqual(requests[0].full_url, "https://example.test/api/v1/payment-profile")
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(requests[1].method, "PUT")
        self.assertEqual(
            json.loads(requests[1].data), {"display_name": "Shop MONA", "locale": "vi"}
        )
        self.assertEqual(requests[2].full_url, "https://example.test/api/v1/checkouts")
        self.assertEqual(requests[2].get_header("Idempotency-key"), "create-key")
        self.assertEqual(
            requests[3].full_url,
            "https://example.test/api/v1/checkouts/checkout%2Fid",
        )
        self.assertIn("status=pending", requests[4].full_url)
        self.assertIn("order_code=DH_10234", requests[4].full_url)
        self.assertIn("limit=50", requests[4].full_url)
        self.assertEqual(
            requests[5].full_url,
            "https://example.test/api/v1/checkouts/checkout%2Fid/cancel",
        )
        self.assertEqual(requests[5].get_header("Idempotency-key"), "cancel-key")
        self.assertEqual(json.loads(requests[5].data), {})
        for request in requests:
            if request.method != "GET":
                self.assertEqual(request.get_header("X-client-secret"), "client-secret")


if __name__ == "__main__":
    unittest.main()
