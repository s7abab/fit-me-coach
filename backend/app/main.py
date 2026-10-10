import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent import run_agent
from app.config import settings
from app.db import get_conn

from app.schema import AskRequest, AskResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("fitmecoach")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup: load the AI models now, not on the first user's request
    if settings.warmup_models:
        from app.embeddings import get_model
        from app.retrieval import get_reranker
        logger.info("Loading models...")
        get_model()
        get_reranker()
        logger.info("Models ready")
    yield


app = FastAPI(title="Fit Me Coach API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "db": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    start = time.perf_counter()
    try:
        result = run_agent(req.question, settings.demo_user_id, req.conversation_id)
    except Exception:
        # Full error goes to the logs; the user gets a clean message
        logger.exception("Agent failed")
        raise HTTPException(status_code=503, detail="The coach is temporarily unavailable. Please try again.")

    latency_ms = int((time.perf_counter() - start) * 1000)
    # Never log the question: it's private health information
    logger.info("ask safety=%s tools=%d latency_ms=%d", result["safety"], len(result["tool_calls"]), latency_ms)
    return AskResponse(**result, latency_ms=latency_ms)

@app.get("/dashboard")
def dashboard(days: int = Query(14, ge=1, le=30)):
    user_id = settings.demo_user_id
    args = {"days": days}
    with get_conn() as conn:
        return {
            "profile": get_user_profile(conn, user_id, {}),
            "sleep": get_sleep(conn, user_id, args),
            "metrics": get_daily_metrics(conn, user_id, args),
            "workouts": get_workouts(conn, user_id, args),
        }