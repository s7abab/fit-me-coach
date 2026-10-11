"""The coach's data tools as an MCP server.

In production it is part of the API (app/main.py serves it at /mcp) and every request carries a
token that says which user it is for (app/mcp_auth.py). For local use, backend/mcp_server.py runs
the same tools over stdin/stdout for a single user.
"""
import logging
import time
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from app import mcp_auth
from app.db import get_conn
from app.tools import run_tool

logger = logging.getLogger("fitmecoach.mcp")

# Only set by backend/mcp_server.py. Over HTTP the user always comes from the token.
LOCAL_USER_ID = None

mcp = MCPServer(
    "fit-me-coach",
    instructions=("Read-only access to the signed-in user's health data (profile, sleep, activity, heart, workouts) "
                  "and a search over trusted health guidelines. Use search_guides before giving health advice, "
                  "and cite the guide title and page."),
    auth_server_provider=mcp_auth.CoachOAuthProvider(),
    auth=AuthSettings(
        issuer_url=mcp_auth.PUBLIC_URL,
        resource_server_url=mcp_auth.RESOURCE_URL,
        validate_token_resource=True,
        required_scopes=[mcp_auth.SCOPE],
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=[mcp_auth.SCOPE], default_scopes=[mcp_auth.SCOPE]),
        revocation_options=RevocationOptions(enabled=True),
    ),
)
mcp.custom_route("/oauth/google/callback", methods=["GET"])(mcp_auth.google_callback)
mcp.custom_route("/oauth/consent", methods=["POST"])(mcp_auth.consent)

READ_ONLY = ToolAnnotations(read_only_hint=True)


def _user_id():
    token = get_access_token()
    if token is not None:
        return int(token.subject)
    if LOCAL_USER_ID is not None:
        return LOCAL_USER_ID
    raise RuntimeError("No signed-in user")


def _run(name, args):
    user_id = _user_id()
    start = time.perf_counter()
    with get_conn() as conn:
        result = run_tool(conn, user_id, name, args)
    # Never log the arguments or the result: they are private health information
    logger.info("mcp tool=%s user=%s latency_ms=%d", name, user_id, (time.perf_counter() - start) * 1000)
    return result


@mcp.tool(annotations=READ_ONLY)
def get_user_profile() -> str:
    """The user's profile: age, sex, height, weight and fitness goal."""
    return _run("get_user_profile", {})


@mcp.tool(annotations=READ_ONLY)
def get_recovery_summary(days: int = 7) -> str:
    """Sleep plus resting heart rate and HRV for the last N days (1-30), each compared with the
    user's normal baseline. Use for questions about tiredness, energy or recovery."""
    return _run("get_recovery_summary", {"days": days})


@mcp.tool(annotations=READ_ONLY)
def get_sleep(days: int = 7) -> str:
    """The user's sleep for the last N nights (1-30): hours, bedtime, wake time, deep and REM sleep,
    plus averages and their normal baseline."""
    return _run("get_sleep", {"days": days})


@mcp.tool(annotations=READ_ONLY)
def get_daily_metrics(days: int = 7) -> str:
    """The user's daily steps, active minutes, resting heart rate and HRV for the last N days (1-30),
    plus their normal baseline."""
    return _run("get_daily_metrics", {"days": days})


@mcp.tool(annotations=READ_ONLY)
def get_workouts(days: int = 14) -> str:
    """The user's workouts for the last N days (1-30): name, type, duration and average heart rate."""
    return _run("get_workouts", {"days": days})


@mcp.tool(annotations=READ_ONLY)
def search_guides(query: str) -> str:
    """Search trusted health guidelines (WHO, US Physical Activity Guidelines, ICMR-NIN diet,
    NHLBI sleep). Each result includes the guide title and page, for citing."""
    return _run("search_guides", {"query": query})


def http_app():
    """The MCP endpoint plus its OAuth routes, as an app that app/main.py mounts.

    Stateless: nothing is kept in memory between requests, so a redeploy or a second instance
    never breaks a connected client.
    """
    return mcp.streamable_http_app(stateless_http=True, json_response=True,
                                   host=urlparse(mcp_auth.PUBLIC_URL).hostname)
