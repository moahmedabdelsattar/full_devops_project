from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="payment-service")


class Payment(BaseModel):
    order_ref: str
    amount: float


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/pay")
def pay(p: Payment):
    # دفع وهمي: أي مبلغ لحد 5000 ينجح، فوق كده يفشل
    if p.amount <= 5000:
        return {"status": "paid"}
    return {"status": "failed", "reason": "amount too high"}
