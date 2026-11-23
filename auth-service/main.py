import os, time, hashlib, secrets
import jwt, psycopg2
from psycopg2 import errors
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

SECRET = os.getenv("JWT_SECRET", "dev-secret")
DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    dbname=os.getenv("DB_NAME", "auth"),
    user=os.getenv("DB_USER", "app"),
    password=os.getenv("DB_PASSWORD", "secret"),
)

app = FastAPI(title="auth-service")


def run(sql, params=(), fetch=False):
    c = psycopg2.connect(**DB)
    try:
        with c, c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone() if fetch else None
    finally:
        c.close()


def init_db():
    for _ in range(30):  # استنى الـ database لحد ما تجهز
        try:
            run("create table if not exists users("
                "id serial primary key, username text unique, "
                "password_hash text, salt text)")
            return
        except psycopg2.OperationalError:
            time.sleep(1)
    raise RuntimeError("database not reachable")


init_db()


def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


class Creds(BaseModel):
    username: str
    password: str


@app.get("/health")
def health():
    return {"status": "UP"}


@app.post("/register", status_code=201)
def register(c: Creds):
    salt = secrets.token_hex(8)
    try:
        run("insert into users(username, password_hash, salt) values(%s,%s,%s)",
            (c.username, hash_pw(c.password, salt), salt))
    except errors.UniqueViolation:
        raise HTTPException(409, "username already exists")
    return {"message": "registered"}


@app.post("/login")
def login(c: Creds):
    row = run("select password_hash, salt from users where username=%s",
              (c.username,), fetch=True)
    if not row or hash_pw(c.password, row[1]) != row[0]:
        raise HTTPException(401, "wrong username or password")
    token = jwt.encode({"sub": c.username, "exp": int(time.time()) + 3600},
                       SECRET, algorithm="HS256")
    return {"token": token}


@app.get("/verify")
def verify(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing token")
    try:
        data = jwt.decode(authorization[7:], SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")
    return {"username": data["sub"]}
