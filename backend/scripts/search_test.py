import sys
from app.db import get_conn
from app.retrieval import search

with get_conn() as conn:
    for c in search(conn, sys.argv[1]):
        print(f"score={c['score']:.2f} | {c['title']}, page {c['page']}")
        print(f"   {c['content'][:150]}...\n")