import { useEffect, useState } from "react";

type Health = { status: string; database?: string };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetch("/health/ready")
      .then(async (response) => {
        if (!response.ok) throw new Error("API readiness check failed");
        return (await response.json()) as Health;
      })
      .then((data) => { if (mounted) setHealth(data); })
      .catch((reason: unknown) => {
        if (mounted) setError(reason instanceof Error ? reason.message : "Cannot reach API");
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-600 text-lg font-bold text-white">U</div>
            <div>
              <p className="text-lg font-bold tracking-tight">Uptime Monitor</p>
              <p className="text-xs text-slate-500">Website & API monitoring platform</p>
            </div>
          </div>
          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">Phase 1 · Foundation</span>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-14">
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-blue-600">Project 11</p>
        <h1 className="max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">Know when your website is down.</h1>
        <p className="mt-5 max-w-3xl text-lg leading-8 text-slate-600">
          A developer-focused platform for checking website and API availability, tracking response times, and detecting incidents.
        </p>

        <div className="mt-10 grid gap-5 md:grid-cols-3">
          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Frontend</p>
            <p className="mt-2 text-2xl font-bold">React + Vite</p>
            <p className="mt-2 text-sm text-emerald-700">Application shell loaded</p>
          </article>
          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Backend API</p>
            <p className="mt-2 text-2xl font-bold">FastAPI</p>
            <p className={`mt-2 text-sm ${error ? "text-red-600" : "text-emerald-700"}`}>
              {loading ? "Checking API..." : error || `API: ${health?.status ?? "unknown"}`}
            </p>
          </article>
          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Database</p>
            <p className="mt-2 text-2xl font-bold">PostgreSQL</p>
            <p className="mt-2 text-sm text-slate-600">{health?.database ?? "Connection verified by API readiness check"}</p>
          </article>
        </div>

        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-semibold">Foundation milestone</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            The web app, API, PostgreSQL database, Docker Compose environment and initial database schema are connected.
            Monitor creation and scheduled checks will be implemented in later phases.
          </p>
          <a className="mt-5 inline-flex rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-700"
             href="http://localhost:8000/docs" target="_blank" rel="noreferrer">Open API documentation</a>
        </div>
      </section>
    </main>
  );
}
