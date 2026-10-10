import { signInWithGoogle } from "@/app/actions";
import { ok, type Connection, type Dashboard } from "@/lib/api";
import { buildStatus } from "@/lib/status";
import Overview from "./Overview";

const CONNECT: Partial<Record<Connection["status"], { headline: string; detail: string }>> = {
  none: {
    headline: "Connect Google Health",
    detail: "Share your sleep, heart and activity data so your coach can work from your real numbers.",
  },
  expired: {
    headline: "Reconnect Google Health",
    detail: "Access to your Google Health data has ended. Sign in again to pick up where you left off.",
  },
  error: {
    headline: "Couldn't read Google Health",
    detail: "We'll try again in a few minutes. If it keeps happening, reconnect and allow access to your health data.",
  },
};

function Connect({ status }: { status: Connection["status"] }) {
  const copy = CONNECT[status];
  if (!copy) return null;
  return (
    <section className="brief">
      <div className="brief-label tone-amber"><i />Google Health</div>
      <h1>{copy.headline}</h1>
      <p className="brief-detail">{copy.detail}</p>
      <form action={signInWithGoogle}>
        <button type="submit" className="button">{status === "none" ? "Connect" : "Reconnect"} with Google</button>
      </form>
    </section>
  );
}

export default function Brief({ data, error }: { data: Dashboard | null; error: string | null }) {
  if (error) return <section className="brief"><p className="brief-detail">{error}</p></section>;
  if (!data) return <section className="brief"><p className="brief-detail">Reading your data</p></section>;

  const { status: connection } = data.connection;
  if (connection === "syncing") {
    return (
      <section className="brief">
        <h1>Importing your Google Health data</h1>
        <p className="brief-detail answer-pending" role="status">This takes a moment the first time</p>
      </section>
    );
  }
  if (connection !== "ready") return <Connect status={connection} />;

  const status = buildStatus(ok(data.sleep), ok(data.metrics));

  return (
    <section className="brief">
      <div className={`brief-label tone-${status.tone}`}><i />{status.label}</div>
      <h1>{status.headline}</h1>
      {status.detail && <p className="brief-detail">{status.detail}</p>}
      <Overview overview={data.overview} />
    </section>
  );
}
