import json
import sys

from app.db import get_conn
from app.tools import run_tool

USER_ID = 1  

name = sys.argv[1]
args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}

with get_conn() as conn:
    result = run_tool(conn, USER_ID, name, args)
    print(json.dumps(json.loads(result), indent=2))