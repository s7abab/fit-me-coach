import os

from mcp.server.mcpserver import MCPServer

from app.db import get_conn
from app.tools import run_tool

USER_ID = int(os.environ.get("FITME_USER_ID", "1"))   # whose data this server can read

mcp = MCPServer("fit-me-coach")


def _run(name, args):
    with get_conn() as conn:
        return run_tool(conn, USER_ID, name, args)


@mcp.tool()
def get_user_profile() -> str:
    """The user's profile: age, sex, height, weight and fitness goal."""
    return _run("get_user_profile", {})


@mcp.tool()
def get_recovery_summary(days: int = 7) -> str:
    """Sleep plus resting heart rate and HRV for the last N days (1-30), each compared with the
    user's normal baseline. Use for questions about tiredness, energy or recovery."""
    return _run("get_recovery_summary", {"days": days})


@mcp.tool()
def get_sleep(days: int = 7) -> str:
    """The user's sleep for the last N nights (1-30): hours, bedtime, wake time, deep and REM sleep,
    plus averages and their normal baseline."""
    return _run("get_sleep", {"days": days})


@mcp.tool()
def get_daily_metrics(days: int = 7) -> str:
    """The user's daily steps, active minutes, resting heart rate and HRV for the last N days (1-30),
    plus their normal baseline."""
    return _run("get_daily_metrics", {"days": days})


@mcp.tool()
def get_workouts(days: int = 14) -> str:
    """The user's workouts for the last N days (1-30): name, type, duration and average heart rate."""
    return _run("get_workouts", {"days": days})


@mcp.tool()
def search_guides(query: str) -> str:
    """Search trusted health guidelines (WHO, US Physical Activity Guidelines, ICMR-NIN diet,
    NHLBI sleep). Each result includes the guide title and page, for citing."""
    return _run("search_guides", {"query": query})


if __name__ == "__main__":
    mcp.run()   # talks to the client over stdin/stdout