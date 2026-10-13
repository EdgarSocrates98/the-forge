"""Tiny FastAPI app used as an example workspace for the API Forge adapter."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/orders")
def list_orders():
    return []


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    return {"id": order_id, "total": 0.0}


@app.delete("/orders/{order_id}")
def cancel_order(order_id: str):
    return {"id": order_id, "cancelled": True}
