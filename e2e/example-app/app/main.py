"""Example payments API — fixture with planted problems (cyc101-09).
Planted: P1 route without auth dependency, P2 unhandled div-by-zero,
P3 OpenAPI spec drift (documented route missing here), P4 no rate limit.
"""
from fastapi import FastAPI

app = FastAPI(title="payments-example", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/payments")  # P1: no auth, no idempotency key
def create_payment(amount: int, currency: str) -> dict:
    return {"id": "pay_1", "amount": amount, "currency": currency}


@app.get("/payments/{payment_id}/fee")  # P2: ZeroDivisionError unhandled
def fee(payment_id: str, months: int) -> dict:
    return {"fee": 100 / months}


@app.get("/admin/users")  # P1: admin route exposed without guard
def list_users() -> dict:
    return {"users": []}
