from app.agent import run_agent
from app.db import get_conn
from app.memory import load_memories

USER_ID = 1
conversation_id = None

print("Fit Me Coach. Commands: /new (new chat), /memories, /quit\n")
while True:
    question = input("You: ").strip()
    if not question:
        continue
    if question == "/quit":
        break
    if question == "/new":
        conversation_id = None
        print("(new conversation)\n")
        continue
    if question == "/memories":
        with get_conn() as conn:
            print(load_memories(conn, USER_ID) or "(nothing yet)", "\n")
        continue

    result = run_agent(question, USER_ID, conversation_id)
    conversation_id = result["conversation_id"]       # keep chatting in the same conversation
    print(f"\nCoach: {result['answer']}")
    for s in result["sources"]:
        print(f"  [{s['n']}] {s['title']}, page {s['page']}")
    print(f"  (tools: {[c['tool'] for c in result['tool_calls']]})\n")