"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { ask, type AskResponse } from "@/lib/api";

type Turn = { id: number; question: string; response?: AskResponse; error?: string };

const MAX_QUESTION = 1000;

const STARTERS = [
  "Why am I so tired this week?",
  "Am I ready to train hard today?",
  "How much sleep should I be getting?",
];

const TOOL_TAGS: Record<string, string> = {
  get_sleep: "Sleep",
  get_recovery_summary: "Recovery",
  get_daily_metrics: "Heart & activity",
  get_workouts: "Workouts",
  get_user_profile: "Profile",
  search_guides: "Guidelines",
  remember: "Noted",
};

// "[2]" becomes a superscript citation, "**x**" becomes bold
function inline(text: string): ReactNode[] {
  return text.split(/(\s*\[\d+\]|\*\*[^*]+\*\*)/g).map((part, i) => {
    part = /^\s*\[\d+\]$/.test(part) ? part.trim() : part;
    if (/^\[\d+\]$/.test(part)) return <sup key={i}>{part.slice(1, -1)}</sup>;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    return part;
  });
}

function Answer({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (!bullets.length) return;
    blocks.push(<ul key={blocks.length}>{bullets.map((b, i) => <li key={i}>{inline(b)}</li>)}</ul>);
    bullets = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (bullet) { bullets.push(bullet[1]); continue; }
    flush();
    if (line) blocks.push(<p key={blocks.length}>{inline(line.replace(/^#+\s*/, ""))}</p>);
  }
  flush();
  return <>{blocks}</>;
}

function Reply({ response }: { response: AskResponse }) {
  const tags = [...new Set(response.tool_calls.map((t) => TOOL_TAGS[t.tool] ?? t.tool))];
  const redFlag = response.safety === "red_flag";
  return (
    <div className={redFlag ? "answer is-safety" : "answer"}>
      {redFlag && <div className="safety-label">Safety</div>}
      <Answer text={response.answer} />
      {tags.length > 0 && (
        <ul className="tags" aria-label="Data used">
          {tags.map((t) => <li key={t}>{t}</li>)}
        </ul>
      )}
      {response.sources.length > 0 && (
        <ol className="sources" aria-label="Sources">
          {response.sources.map((s) => (
            <li key={s.n}>
              <span className="source-n">{s.n}</span>
              <span>
                {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> : s.title}
                {s.page != null && <span className="source-page"> · p. {s.page}</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function Chat({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  // Grow the input with its text, up to the max-height set in CSS
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
    // Only show a scrollbar once the text is taller than the max-height
    el.style.overflowY = el.scrollHeight > el.clientHeight ? "auto" : "hidden";
  }, [draft]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    const id = Date.now();
    setDraft("");
    setPending(true);
    setTurns((t) => [...t, { id, question }]);
    try {
      const response = await ask(question, conversationId);
      setConversationId(response.conversation_id);
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, response } : turn)));
    } catch (e) {
      const error = e instanceof Error && !(e instanceof TypeError) ? e.message : "Could not reach the coach. Is the API running?";
      setTurns((t) => t.map((turn) => (turn.id === id ? { ...turn, error } : turn)));
    } finally {
      setPending(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(draft);
    }
  }

  function reset() {
    setTurns([]);
    setConversationId(null);
  }

  return (
    <main className="coach">
      <div className="scroll">
        <div className="column">
          {children}

          {turns.length === 0 ? (
            <ul className="starters" aria-label="Suggested questions">
              {STARTERS.map((s) => (
                <li key={s}><button type="button" onClick={() => send(s)}>{s}</button></li>
              ))}
            </ul>
          ) : (
            <div className="thread">
              {turns.map((turn) => (
                <article key={turn.id} className="turn">
                  <p className="question">{turn.question}</p>
                  {turn.response ? (
                    <Reply response={turn.response} />
                  ) : turn.error ? (
                    <p className="answer-error">{turn.error}</p>
                  ) : (
                    <p className="answer-pending" role="status">Reading your data</p>
                  )}
                </article>
              ))}
              {!pending && (
                <button type="button" className="reset" onClick={reset}>Start a new conversation</button>
              )}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <div className="column">
          <div className="field">
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              maxLength={MAX_QUESTION}
              placeholder="Ask your coach"
              aria-label="Question for your coach"
            />
            <button type="submit" disabled={pending || !draft.trim()} aria-label="Send">
              <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
          <p className="fine">Cites published guidelines. Not medical advice.</p>
        </div>
      </form>
    </main>
  );
}
