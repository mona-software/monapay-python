import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from monapay import verify_webhook


@csrf_exempt
def monapay_webhook(request):
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)
    result = verify_webhook(request.body, request.headers, os.environ["MONA_WEBHOOK_SECRET"])
    if not result.ok:
        return JsonResponse({"ok": False, "reason": result.reason}, status=401)
    save_once(result.payload["transaction_code"], result.payload)
    return JsonResponse({"ok": True}, status=200)


def save_once(transaction_code, payload):
    print(transaction_code, payload)
