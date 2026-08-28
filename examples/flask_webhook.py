import os

from flask import Flask, jsonify, request
from monapay import verify_webhook

app = Flask(__name__)


@app.post("/webhooks/monapay")
def monapay_webhook():
    result = verify_webhook(
        request.get_data(cache=True), request.headers, os.environ["MONA_WEBHOOK_SECRET"]
    )
    if not result.ok:
        return jsonify(ok=False, reason=result.reason), 401
    save_once(result.payload["transaction_code"], result.payload)
    return jsonify(ok=True), 200


def save_once(transaction_code, payload):
    print(transaction_code, payload)
