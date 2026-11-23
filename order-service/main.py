import os, time, uuid
import psycopg2, requests
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8003")
DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    dbname=os.getenv("DB_NAME", "orders"),
    user=os.getenv("DB_USER", "app"),
    password=os.getenv("DB_PASSWORD", "secret"),
)

app = FastAPI(title="order-service")


def run(sql, params=(), fetch=None):
    c = psycopg2.connect(**DB)
    try:
        with c, c.cursor() as cur:
            cur.execute(sql, params)
            if fetch == "all":
                return cur.fetchall()
    finally:
        c.close()


def init_db():
    for _ in range(30):
        try:
            run("create table if not exists orders("
                "id serial primary key, ref text, username text, "
                "item text, amount numeric, status text)")
            return
        except psycopg2.OperationalError:
            time.sleep(1)
    raise RuntimeError("database not reachable")


init_db()


class Order(BaseModel):
    item: str
    amount: float


def current_user(authorization: str):
    """يسأل auth-service: التوكن ده بتاع مين؟"""
    try:
        r = requests.get(f"{AUTH_URL}/verify",
                         headers={"Authorization": authorization or ""}, timeout=3)
    except requests.RequestException:
        raise HTTPException(503, "auth-service unavailable")
    if r.status_code != 200:
        raise HTTPException(401, "invalid token")
    return r.json()["username"]


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/orders", status_code=201)
def create_order(o: Order, authorization: str = Header(None)):
    user = current_user(authorization)
    ref = uuid.uuid4().hex[:8]
    try:
        r = requests.post(f"{PAYMENT_URL}/pay",
                          json={"order_ref": ref, "amount": o.amount}, timeout=3)
        status = "paid" if r.json().get("status") == "paid" else "payment_failed"
    except requests.RequestException:
        status = "payment_unavailable"
    run("insert into orders(ref, username, item, amount, status) values(%s,%s,%s,%s,%s)",
        (ref, user, o.item, o.amount, status))
    if status == "payment_unavailable":
        raise HTTPException(503, f"order {ref} saved, but payment-service is down")
    return {"order": ref, "status": status}


@app.get("/orders")
def my_orders(authorization: str = Header(None)):
    user = current_user(authorization)
    rows = run("select ref, item, amount, status from orders where username=%s order by id",
               (user,), fetch="all")
    return [{"order": r[0], "item": r[1], "amount": float(r[2]), "status": r[3]} for r in rows]
