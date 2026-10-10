"use client";

import { useEffect, useState } from "react";
import { signOutOfApp } from "@/app/actions";
import { getDashboard, type Dashboard } from "@/lib/api";
import { headerDate } from "@/lib/format";
import { buildStarters } from "@/lib/status";
import Brief from "./Brief";
import Chat from "./Chat";
import Trends from "./Trends";

const SYNC_POLL_MS = 4000;

export default function App() {
  const [coachOpen, setCoachOpen] = useState(false); // phones: the coach opens over the dashboard
  const [days, setDays] = useState(14);
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [today, setToday] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => setToday(headerDate(new Date())), []);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    getDashboard(days, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name === "AbortError") return;
        setError(e instanceof Error && !(e instanceof TypeError) ? e.message : "Could not load your data. Is the API running?");
      });
    return () => controller.abort();
  }, [days, reload]);

  // The first import from Google Health runs in the background: keep checking until it lands
  const syncing = data?.connection.status === "syncing";
  useEffect(() => {
    if (!syncing) return;
    const timer = setTimeout(() => setReload((n) => n + 1), SYNC_POLL_MS);
    return () => clearTimeout(timer);
  }, [syncing, data]);

  return (
    <div className="app">
      <header className="top">
        <span className="wordmark">fit me<i /></span>
        <div className="top-end">
          <span className="top-date">{today}</span>
          <form action={signOutOfApp}>
            <button type="submit" className="signout">Sign out</button>
          </form>
        </div>
      </header>

      <main className="dash">
        <div className="dash-inner">
          <Brief data={data} error={error} />
          <Trends data={data} days={days} onDays={setDays} />
        </div>
      </main>

      <Chat
        starters={buildStarters(data?.connection.status === "ready" ? data.overview : null)}
        open={coachOpen} onClose={() => setCoachOpen(false)}
      />

      {/* Phones only: the way into the coach */}
      <button type="button" className="ask-ai" onClick={() => setCoachOpen(true)}>
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path d="M10 2.5l1.7 4.3a2 2 0 0 0 1.1 1.1L17.5 10l-4.7 2.1a2 2 0 0 0-1.1 1.1L10 17.5l-1.7-4.3a2 2 0 0 0-1.1-1.1L2.5 10l4.7-2.1a2 2 0 0 0 1.1-1.1L10 2.5z" fill="currentColor" />
        </svg>
        Ask AI
      </button>
    </div>
  );
}
