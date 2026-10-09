import sys
from app.coach import answer

result = answer(sys.argv[1])
print(result["answer"])
print(f"\n(safety: {result['safety']})")
for s in result["sources"]:
    print(f"[{s['n']}] {s['title']}, page {s['page']}")