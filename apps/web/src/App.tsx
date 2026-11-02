
import { useEffect, useState, type FormEvent } from "react";
import {
  getCurrentUser,
  login,
  logout,
  refreshSession,
  register,
  type User,
} from "./auth";

type Health = {
  status: string;
  database?: string;
};

type AuthMode = "login" | "register";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let mounted = true;

    async function checkSession() {
      try {
        let currentUser: User;

        try {
          currentUser = await getCurrentUser();
        } catch {
          await refreshSession();
          currentUser = await getCurrentUser();
        }

        if (mounted) setUser(currentUser);
      } catch {
        if (mounted) setUser(null);
      } finally {
        if (mounted) setAuthLoading(false);
      }
    }

    void checkSession();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!user) return;

    let mounted = true;

    fetch("/health/ready")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("API readiness check failed");
        }
        return (await response.json()) as Health;
      })
      .then((data) => {
        if (mounted) setHealth(data);
      })
      .catch(() => {
        if (mounted) setHealth(null);
      });

    return () => {
      mounted = false;
    };
  }, [user]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);

    try {
      if (mode === "register") {
        await register({ email, password });
      }

      const authenticatedUser = await login({ email, password });
      setUser(authenticatedUser);
      setPassword("");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Authentication failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setError("");
    setBusy(true);

    try {
      await logout();
      setUser(null);
      setEmail("");
      setPassword("");
      setMode("login");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Logout failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (authLoading) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50">
        <p className="text-sm font-medium text-slate-600">
          Checking your session...
        </p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
        <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-8 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-blue-600 text-xl font-bold text-white">
              U
            </div>
            <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">
              Uptime Monitor
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              {mode === "login"
                ? "Sign in to your monitoring dashboard"
                : "Create your monitoring account"}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="email"
                className="mb-2 block text-sm font-medium text-slate-700"
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                maxLength={254}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-2 block text-sm font-medium text-slate-700"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                required
                minLength={mode === "register" ? 12 : 1}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={
                  mode === "register"
                    ? "At least 12 characters"
                    : "Enter your password"
                }
                className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy
                ? "Please wait..."
                : mode === "login"
                  ? "Sign in"
                  : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-600">
            {mode === "login"
              ? "Don't have an account?"
              : "Already have an account?"}{" "}
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
              className="font-semibold text-blue-600 hover:text-blue-700"
            >
              {mode === "login" ? "Register" : "Sign in"}
            </button>
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-blue-600 text-lg font-bold text-white">
              U
            </div>
            <div>
              <p className="text-lg font-bold tracking-tight">
                Uptime Monitor
              </p>
              <p className="text-xs text-slate-500">
                Website & API monitoring platform
              </p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            disabled={busy}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            {busy ? "Please wait..." : "Logout"}
          </button>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-14">
        <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-blue-600">
          Dashboard
        </p>

        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Welcome back!
        </h1>

        <p className="mt-3 text-slate-600">
          Signed in as <strong>{user.email}</strong>
        </p>

        {error && (
          <p role="alert" className="mt-4 text-sm text-red-600">
            {error}
          </p>
        )}

        <div className="mt-10 grid gap-5 md:grid-cols-3">
          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Frontend</p>
            <p className="mt-2 text-2xl font-bold">React + Vite</p>
            <p className="mt-2 text-sm text-emerald-700">
              Application loaded
            </p>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Backend API</p>
            <p className="mt-2 text-2xl font-bold">FastAPI</p>
            <p className="mt-2 text-sm text-slate-600">
              {health?.status ?? "Checking or unavailable"}
            </p>
          </article>

          <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <p className="text-sm font-medium text-slate-500">Database</p>
            <p className="mt-2 text-2xl font-bold">PostgreSQL</p>
            <p className="mt-2 text-sm text-slate-600">
              {health?.database ?? "Status unavailable"}
            </p>
          </article>
        </div>

        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-semibold">Authentication status</h2>
          <p className="mt-2 text-sm text-emerald-700">
            You are authenticated. Your session is managed using HttpOnly
            cookies.
          </p>
        </div>
      </section>
    </main>
  );
}
