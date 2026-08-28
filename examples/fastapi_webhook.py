import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from monapay import verify_webhook

app = FastAPI()


@app.post("/webhooks/monapay")
async def monapay_webhook(request: Request):
    raw_body = await request.body()
    result = verify_webhook(raw_body, request.headers, os.environ["MONA_WEBHOOK_SECRET"])
    if not result.ok:
        return JSONResponse({"ok": False, "reason": result.reason}, status_code=401)
    await save_once(result.payload["transaction_code"], result.payload)
    return {"ok": True}


async def save_once(transaction_code, payload):
    print(transaction_code, payload)
