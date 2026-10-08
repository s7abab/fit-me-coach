from fastapi import FastAPI
from app.db import get_conn

app = FastAPI(title="Fit me coach")

@app.get("/health")
def health():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "db": "ok"}

