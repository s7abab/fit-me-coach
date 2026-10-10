"use client";

import { useEffect, useState } from "react";
import { signOutOfApp } from "@/app/actions";
import { getDashboard, type Dashboard } from "@/lib/api";
import { headerDate } from "@/lib/format";
import Brief from "./Brief";
import Chat from "./Chat";
import Trends from "./Trends";

type Tab = "coach" | "trends";

const SYNC_POLL_MS = 4000;

export default function App() {
  const [tab, setTab] = useState<Tab>("coach"); // phones show one pane at a time
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
    <div className="app" data-tab={tab}>
      <header className="top">
        <span className="wordmark">fit me<i /></span>
        <nav className="tabs" aria-label="View">
          <button type="button" aria-pressed={tab === "coach"} onClick={() => setTab("coach")}>Coach</button>
          <button type="button" aria-pressed={tab === "trends"} onClick={() => setTab("trends")}>Trends</button>
        </nav>
        <div className="top-end">
          <span className="top-date">{today}</span>
          <form action={signOutOfApp}>
            <button type="submit" className="signout">Sign out</button>
          </form>
        </div>
      </header>

      <Chat>
        <Brief data={data} error={error} />
      </Chat>

      <Trends data={data} days={days} onDays={setDays} />
    </div>
  );
}
