"""FastAPI app of the cross proof workspace: serves the daily orders dataset produced by
the data-pipeline repository (cross-forge-foundation)."""

from fastapi import FastAPI

app = FastAPI(title="Daily Orders API")


@app.get("/daily-orders")
def list_daily_orders(order_date: str):
    return []


@app.get("/daily-orders/{order_id}")
def get_daily_order(order_id: str):
    return {"order_id": order_id, "customer_id": "", "order_date": "", "total": 0.0}
