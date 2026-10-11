"""Run the MCP server on this machine, over stdin/stdout, for one user. No sign-in.

The deployed server is the same tools behind OAuth: see app/mcp_server.py.
"""
import os

import app.mcp_server as server

if __name__ == "__main__":
    server.LOCAL_USER_ID = int(os.environ.get("FITME_USER_ID", "1"))   # whose data this server can read
    server.mcp.run()   # talks to the client over stdin/stdout
