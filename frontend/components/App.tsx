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
      <button type="button" className="ask-bar" onClick={() => setCoachOpen(true)}>
        Ask your coach
        <span aria-hidden="true">
          <svg viewBox="0 0 16 16" width="16" height="16">
            <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>
    </div>
  );
}
