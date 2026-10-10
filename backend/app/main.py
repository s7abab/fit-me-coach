import logging
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.agent import run_agent
from app.auth import current_user
from app.config import settings
from app.db import get_conn
from app.health_sync import claim_sync, connection_state, save_connection, sync_user
from app.overview import get_overview
from app.schema import AskRequest, AskResponse, GoogleHealthTokens
from app.tools import get_daily_metrics, get_sleep, get_user_profile, get_workouts

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


@app.put("/connections/google-health")
def connect_google_health(tokens: GoogleHealthTokens, user_id: int = Depends(current_user)):
    """Called by the Next.js server right after Google sign-in, with the refresh token Google issued."""
    with get_conn() as conn:
        connected = save_connection(conn, user_id, tokens.refresh_token, tokens.scope.split())
    return {"connected": connected}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, user_id: int = Depends(current_user)):
    start = time.perf_counter()
    try:
        result = run_agent(req.question, user_id, req.conversation_id)
    except Exception:
        # Full error goes to the logs; the user gets a clean message
        logger.exception("Agent failed")
        raise HTTPException(status_code=503, detail="The coach is temporarily unavailable. Please try again.")

    latency_ms = int((time.perf_counter() - start) * 1000)
    # Never log the question: it's private health information
    logger.info("ask safety=%s tools=%d latency_ms=%d", result["safety"], len(result["tool_calls"]), latency_ms)
    return AskResponse(**result, latency_ms=latency_ms)


@app.get("/dashboard")
def dashboard(background: BackgroundTasks, days: int = Query(14, ge=1, le=30), user_id: int = Depends(current_user)):
    args = {"days": days}
    with get_conn() as conn:
        # Opening the dashboard is what keeps the data fresh
        sync_days = claim_sync(conn, user_id)
        if sync_days is not None:
            if connection_state(conn, user_id)["status"] == "syncing":
                background.add_task(sync_user, user_id, sync_days)   # first import is slow: the app polls
            else:
                sync_user(user_id, sync_days)                        # a few recent days: quick enough to wait for
        return {
            "connection": connection_state(conn, user_id),
            "overview": get_overview(conn, user_id),
            "profile": get_user_profile(conn, user_id, {}),
            "sleep": get_sleep(conn, user_id, args),
            "metrics": get_daily_metrics(conn, user_id, args),
            "workouts": get_workouts(conn, user_id, args),
        }
