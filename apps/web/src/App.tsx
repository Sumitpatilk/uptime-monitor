
import { useEffect, useState, type FormEvent } from "react";
import {
  getCurrentUser,
  login,
  logout,
  refreshSession,
  register,
  getProjects,
  createProject,
  getMonitors,
  getMonitorAnalytics,
  createMonitor,
  updateMonitor,
  deleteMonitor,
  getStatusPages,
  createStatusPage,
  updateStatusPage,
  deleteStatusPage,
  type User,
  type Project,
  type Monitor,
  type MonitorAnalytics,
  type StatusPage,
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
  const [success, setSuccess] = useState("");
  const [health, setHealth] = useState<Health | null>(null);

  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [statusPages, setStatusPages] = useState<StatusPage[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [selectedAnalyticsMonitorId, setSelectedAnalyticsMonitorId] = useState("");
  const [analyticsHours, setAnalyticsHours] = useState(24);
  const [monitorAnalytics, setMonitorAnalytics] = useState<MonitorAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsError, setAnalyticsError] = useState("");

  const [projectName, setProjectName] = useState("");
  const [monitorName, setMonitorName] = useState("");
  const [monitorUrl, setMonitorUrl] = useState("");
  const [monitorInterval, setMonitorInterval] = useState("60");
  const [statusSlug, setStatusSlug] = useState("");
  const [statusVisibility, setStatusVisibility] =
    useState<"public" | "private">("public");

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
        if (!response.ok) throw new Error("Readiness check failed");
        return (await response.json()) as Health;
      })
      .then((data) => {
        if (mounted) setHealth(data);
      })
      .catch(() => {
        if (mounted) setHealth(null);
      });

    async function loadProjects() {
      try {
        const data = await getProjects();
        if (!mounted) return;

        setProjects(data);
        setSelectedProjectId((current) => {
          if (current && data.some((project) => project.id === current)) {
            return current;
          }
          return data[0]?.id ?? "";
        });
      } catch (reason) {
        if (mounted) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load projects.",
          );
        }
      }
    }

    void loadProjects();

    return () => {
      mounted = false;
    };
  }, [user]);

  useEffect(() => {
    if (!selectedProjectId) {
      setMonitors([]);
      setStatusPages([]);
      setSelectedAnalyticsMonitorId("");
      setMonitorAnalytics(null);
      return;
    }

    let mounted = true;
    setSelectedAnalyticsMonitorId("");
    setDataLoading(true);

    async function loadProjectData() {
      try {
        const [monitorData, statusPageData] = await Promise.all([
          getMonitors(selectedProjectId),
          getStatusPages(selectedProjectId),
        ]);

        if (!mounted) return;

        setMonitors(monitorData);
        setStatusPages(statusPageData);
        setSelectedAnalyticsMonitorId((current) =>
          monitorData.some((monitor) => monitor.id === current)
            ? current
            : monitorData[0]?.id ?? "",
        );
      } catch (reason) {
        if (mounted) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load project data.",
          );
        }
      } finally {
        if (mounted) setDataLoading(false);
      }
    }

    void loadProjectData();

    return () => {
      mounted = false;
    };
  }, [selectedProjectId]);

  useEffect(() => {
    const monitorExists = monitors.some(
      (monitor) => monitor.id === selectedAnalyticsMonitorId,
    );

    if (!selectedProjectId || !selectedAnalyticsMonitorId || !monitorExists) {
      setMonitorAnalytics(null);
      setAnalyticsError("");
      setAnalyticsLoading(false);
      return;
    }

    let mounted = true;
    setAnalyticsLoading(true);
    setAnalyticsError("");

    getMonitorAnalytics(
      selectedProjectId,
      selectedAnalyticsMonitorId,
      analyticsHours,
    )
      .then((data) => {
        if (mounted) setMonitorAnalytics(data);
      })
      .catch((reason) => {
        if (mounted) {
          setMonitorAnalytics(null);
          setAnalyticsError(
            reason instanceof Error
              ? reason.message
              : "Could not load monitor analytics.",
          );
        }
      })
      .finally(() => {
        if (mounted) setAnalyticsLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [
    selectedProjectId,
    selectedAnalyticsMonitorId,
    analyticsHours,
    monitors,
  ]);

  async function reloadProjects() {
    const data = await getProjects();
    setProjects(data);
    return data;
  }

  async function reloadProjectData() {
    if (!selectedProjectId) return;

    const [monitorData, statusPageData] = await Promise.all([
      getMonitors(selectedProjectId),
      getStatusPages(selectedProjectId),
    ]);

    setMonitors(monitorData);
    setStatusPages(statusPageData);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
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
      setProjects([]);
      setMonitors([]);
      setStatusPages([]);
      setSelectedProjectId("");
      setEmail("");
      setPassword("");
      setMode("login");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Logout failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);

    try {
      const project = await createProject(projectName);
      const data = await reloadProjects();

      setSelectedProjectId(project.id);
      setProjectName("");
      setSuccess(`Project "${project.name}" created successfully.`);
      if (!data.some((item) => item.id === project.id)) {
        setProjects((current) => [project, ...current]);
      }
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Project creation failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateMonitor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;

    setError("");
    setSuccess("");
    setBusy(true);

    try {
      await createMonitor(selectedProjectId, {
        name: monitorName,
        url: monitorUrl,
        interval_seconds: Number(monitorInterval),
        timeout_seconds: 10,
        expected_status: 200,
        enabled: true,
      });

      await reloadProjectData();
      setMonitorName("");
      setMonitorUrl("");
      setMonitorInterval("60");
      setSuccess("Monitor created successfully.");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Monitor creation failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleMonitorToggle(monitor: Monitor) {
    if (!selectedProjectId) return;

    setError("");
    setSuccess("");

    try {
      await updateMonitor(selectedProjectId, monitor.id, {
        enabled: !monitor.enabled,
      });
      await reloadProjectData();
      setSuccess("Monitor status updated.");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Monitor update failed.",
      );
    }
  }

  async function handleDeleteMonitor(monitor: Monitor) {
    if (!selectedProjectId) return;
    if (!window.confirm(`Delete monitor "${monitor.name}"?`)) return;

    setError("");
    setSuccess("");

    try {
      await deleteMonitor(selectedProjectId, monitor.id);
      await reloadProjectData();
      setSuccess("Monitor deleted.");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Monitor deletion failed.",
      );
    }
  }

  async function handleCreateStatusPage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;

    setError("");
    setSuccess("");
    setBusy(true);

    try {
      const page = await createStatusPage(selectedProjectId, {
        slug: statusSlug,
        visibility: statusVisibility,
        enabled: false,
      });

      await reloadProjectData();
      setStatusSlug("");
      setSuccess(`Status page "${page.slug}" created. Enable it to publish.`);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Status page creation failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleStatusPageToggle(page: StatusPage) {
    if (!selectedProjectId) return;

    setError("");
    setSuccess("");

    try {
      await updateStatusPage(selectedProjectId, page.id, {
        enabled: !page.enabled,
      });
      await reloadProjectData();
      setSuccess("Status page updated.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Status page update failed.",
      );
    }
  }

  async function handleVisibilityToggle(page: StatusPage) {
    if (!selectedProjectId) return;

    setError("");
    setSuccess("");

    try {
      await updateStatusPage(selectedProjectId, page.id, {
        visibility: page.visibility === "public" ? "private" : "public",
      });
      await reloadProjectData();
      setSuccess("Status page visibility updated.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Visibility update failed.",
      );
    }
  }

  async function handleDeleteStatusPage(page: StatusPage) {
    if (!selectedProjectId) return;
    if (!window.confirm(`Delete status page "${page.slug}"?`)) return;

    setError("");
    setSuccess("");

    try {
      await deleteStatusPage(selectedProjectId, page.id);
      await reloadProjectData();
      setSuccess("Status page deleted.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Status page deletion failed.",
      );
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
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-slate-700">
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
              <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={mode === "register" ? 12 : 1}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={mode === "register" ? "At least 12 characters" : "Enter your password"}
                className="w-full rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
            </div>

            {error && <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-600">
            {mode === "login" ? "Don't have an account?" : "Already have an account?"}{" "}
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

  const selectedProject = projects.find(
    (project) => project.id === selectedProjectId,
  );

  const enabledMonitors = monitors.filter((monitor) => monitor.enabled).length;

  const latencyChecks = (monitorAnalytics?.checks ?? []).filter(
    (check) => check.latency_ms !== null,
  );
  const latencyValues = latencyChecks.map((check) => check.latency_ms as number);
  const chartMin = Math.min(...latencyValues, 0);
  const chartMax = Math.max(...latencyValues, 1);
  const chartRange = Math.max(chartMax - chartMin, 1);
  const chartPoints = latencyChecks
    .map((check, index) => {
      const x =
        latencyChecks.length === 1
          ? 300
          : (index / (latencyChecks.length - 1)) * 580 + 10;
      const y = 150 - ((check.latency_ms as number) - chartMin) / chartRange * 130;
      return `${x},${y}`;
    })
    .join(" ");

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
          <div className="flex items-center gap-4">
            <span className="hidden text-sm text-slate-600 sm:block">{user.email}</span>
            <button onClick={handleLogout} disabled={busy} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60">
              {busy ? "Please wait..." : "Logout"}
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl space-y-8 px-6 py-10">
        <div>
          <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-blue-600">Dashboard</p>
          <h1 className="text-3xl font-bold tracking-tight">Monitoring Overview</h1>
          <p className="mt-2 text-sm text-slate-600">Manage your projects, monitors and public status pages.</p>
        </div>

        {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        {success && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</div>}

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">Projects</p>
            <p className="mt-2 text-3xl font-bold">{projects.length}</p>
          </article>
          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">Total Monitors</p>
            <p className="mt-2 text-3xl font-bold">{monitors.length}</p>
          </article>
          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">Enabled Monitors</p>
            <p className="mt-2 text-3xl font-bold">{enabledMonitors}</p>
          </article>
          <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">API / Database</p>
            <p className="mt-2 text-lg font-bold">{health?.status ?? "Unavailable"}</p>
            <p className="mt-1 text-xs text-slate-500">{health?.database ?? "Database status unavailable"}</p>
          </article>
        </div>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-5">
            <h2 className="text-lg font-semibold">Projects</h2>
            <p className="mt-1 text-sm text-slate-500">Create a project or select one to manage its resources.</p>
          </div>

          <form onSubmit={handleCreateProject} className="mb-6 flex flex-col gap-3 sm:flex-row">
            <input
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              required
              maxLength={150}
              placeholder="New project name"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
            />
            <button disabled={busy} className="rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
              Create Project
            </button>
          </form>

          {projects.length === 0 ? (
            <p className="rounded-lg bg-slate-50 p-5 text-sm text-slate-500">No projects yet. Create your first project above.</p>
          ) : (
            <div>
              <label htmlFor="project-select" className="mb-2 block text-sm font-medium text-slate-700">Selected project</label>
              <select
                id="project-select"
                value={selectedProjectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm sm:max-w-md"
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </select>
              {selectedProject && <p className="mt-2 text-xs text-slate-500">Plan: {selectedProject.plan}</p>}
            </div>
          )}
        </section>

        {selectedProjectId && (
          <>
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-5">
                <h2 className="text-lg font-semibold">Monitors</h2>
                <p className="mt-1 text-sm text-slate-500">Add websites or APIs to monitor.</p>
              </div>

              <form onSubmit={handleCreateMonitor} className="mb-7 grid gap-3 md:grid-cols-4">
                <input
                  value={monitorName}
                  onChange={(event) => setMonitorName(event.target.value)}
                  required
                  maxLength={150}
                  placeholder="Monitor name"
                  className="rounded-lg border border-slate-300 px-4 py-3 text-sm"
                />
                <input
                  type="url"
                  value={monitorUrl}
                  onChange={(event) => setMonitorUrl(event.target.value)}
                  required
                  maxLength={2048}
                  placeholder="https://example.com"
                  className="rounded-lg border border-slate-300 px-4 py-3 text-sm"
                />
                <select value={monitorInterval} onChange={(event) => setMonitorInterval(event.target.value)} className="rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm">
                  <option value="30">Every 30 seconds</option>
                  <option value="60">Every 1 minute</option>
                  <option value="300">Every 5 minutes</option>
                  <option value="600">Every 10 minutes</option>
                  <option value="1800">Every 30 minutes</option>
                  <option value="3600">Every 1 hour</option>
                </select>
                <button disabled={busy} className="rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">Add Monitor</button>
              </form>

              {dataLoading ? (
                <p className="text-sm text-slate-500">Loading monitors...</p>
              ) : monitors.length === 0 ? (
                <p className="rounded-lg bg-slate-50 p-5 text-sm text-slate-500">No monitors in this project yet.</p>
              ) : (
                <div className="space-y-3">
                  {monitors.map((monitor) => (
                    <article key={monitor.id} className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold">{monitor.name}</h3>
                          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${monitor.enabled ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                            {monitor.enabled ? "Enabled" : "Disabled"}
                          </span>
                        </div>
                        <p className="mt-1 break-all text-sm text-slate-500">{monitor.url}</p>
                        <p className="mt-1 text-xs text-slate-500">Interval: {monitor.interval_seconds}s · Expected HTTP: {monitor.expected_status}</p>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button onClick={() => void handleMonitorToggle(monitor)} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold hover:bg-slate-50">
                          {monitor.enabled ? "Disable" : "Enable"}
                        </button>
                        <button onClick={() => void handleDeleteMonitor(monitor)} className="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50">Delete</button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                <div>
                  <h2 className="text-lg font-semibold">Monitor Analytics</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Uptime and response-time performance for your monitors.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:min-w-72">
                  <select
                    aria-label="Select monitor for analytics"
                    value={selectedAnalyticsMonitorId}
                    onChange={(event) => setSelectedAnalyticsMonitorId(event.target.value)}
                    disabled={monitors.length === 0}
                    className="min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                  >
                    {monitors.length === 0 && <option value="">No monitors</option>}
                    {monitors.map((monitor) => (
                      <option key={monitor.id} value={monitor.id}>{monitor.name}</option>
                    ))}
                  </select>
                  <select
                    aria-label="Analytics time range"
                    value={analyticsHours}
                    onChange={(event) => setAnalyticsHours(Number(event.target.value))}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                  >
                    <option value={24}>Last 24 hours</option>
                    <option value={168}>Last 7 days</option>
                    <option value={720}>Last 30 days</option>
                  </select>
                </div>
              </div>

              {analyticsLoading ? (
                <p className="rounded-lg bg-slate-50 p-5 text-sm text-slate-500">
                  Loading monitor analytics...
                </p>
              ) : analyticsError ? (
                <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
                  {analyticsError}
                </p>
              ) : monitors.length === 0 ? (
                <p className="rounded-lg bg-slate-50 p-5 text-sm text-slate-500">
                  Add a monitor to view uptime and latency analytics.
                </p>
              ) : !monitorAnalytics || monitorAnalytics.total_checks === 0 ? (
                <p className="rounded-lg bg-slate-50 p-5 text-sm text-slate-500">
                  No check data available for this time range yet. Analytics will appear after the monitor runs its checks.
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                    <article className="rounded-xl border border-slate-200 p-4">
                      <p className="text-xs font-medium text-slate-500">Uptime</p>
                      <p className="mt-2 text-2xl font-bold text-slate-900">
                        {monitorAnalytics.uptime_percentage === null
                          ? "—"
                          : `${monitorAnalytics.uptime_percentage.toFixed(2)}%`}
                      </p>
                    </article>
                    <article className="rounded-xl border border-slate-200 p-4">
                      <p className="text-xs font-medium text-slate-500">Total Checks</p>
                      <p className="mt-2 text-2xl font-bold text-slate-900">
                        {monitorAnalytics.total_checks}
                      </p>
                    </article>
                    <article className="rounded-xl border border-slate-200 p-4">
                      <p className="text-xs font-medium text-slate-500">Average Latency</p>
                      <p className="mt-2 text-2xl font-bold text-slate-900">
                        {monitorAnalytics.average_latency_ms === null
                          ? "—"
                          : `${monitorAnalytics.average_latency_ms.toFixed(0)} ms`}
                      </p>
                    </article>
                    <article className="rounded-xl border border-slate-200 p-4">
                      <p className="text-xs font-medium text-slate-500">Failed Checks</p>
                      <p className="mt-2 text-2xl font-bold text-red-600">
                        {monitorAnalytics.down_checks}
                      </p>
                    </article>
                  </div>

                  <div className="mt-6 rounded-xl border border-slate-200 p-4">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="font-semibold">Response Time</h3>
                        <p className="text-xs text-slate-500">
                          Recent check latency · milliseconds
                        </p>
                      </div>
                      <p className="text-xs text-slate-500">
                        Min: {monitorAnalytics.min_latency_ms === null
                          ? "—"
                          : `${monitorAnalytics.min_latency_ms.toFixed(0)} ms`}
                        {" · "}
                        Max: {monitorAnalytics.max_latency_ms === null
                          ? "—"
                          : `${monitorAnalytics.max_latency_ms.toFixed(0)} ms`}
                      </p>
                    </div>

                    {latencyChecks.length === 0 ? (
                      <p className="py-8 text-center text-sm text-slate-500">
                        No latency measurements available.
                      </p>
                    ) : (
                      <svg
                        viewBox="0 0 600 170"
                        role="img"
                        aria-label="Response time line chart"
                        className="h-48 w-full overflow-visible"
                        preserveAspectRatio="none"
                      >
                        {[20, 85, 150].map((y) => (
                          <line
                            key={y}
                            x1="10"
                            y1={y}
                            x2="590"
                            y2={y}
                            stroke="#e2e8f0"
                            strokeDasharray="4 4"
                          />
                        ))}
                        {latencyChecks.length > 1 && (
                          <polyline
                            points={chartPoints}
                            fill="none"
                            stroke="#2563eb"
                            strokeWidth="3"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        )}
                        {latencyChecks.map((check, index) => {
                          const x =
                            latencyChecks.length === 1
                              ? 300
                              : (index / (latencyChecks.length - 1)) * 580 + 10;
                          const y =
                            150 -
                            ((check.latency_ms as number) - chartMin) /
                              chartRange *
                              130;
                          return (
                            <circle
                              key={check.id}
                              cx={x}
                              cy={y}
                              r="3.5"
                              fill="#2563eb"
                            >
                              <title>
                                {new Date(check.checked_at).toLocaleString()}: {check.latency_ms} ms
                              </title>
                            </circle>
                          );
                        })}
                      </svg>
                    )}
                    <div className="mt-2 flex justify-between text-xs text-slate-400">
                      <span>Older checks</span>
                      <span>Recent checks</span>
                    </div>
                  </div>

                  <div className="mt-5 flex flex-wrap gap-4 text-xs text-slate-600">
                    <span>
                      <span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />
                      Successful: {monitorAnalytics.up_checks}
                    </span>
                    <span>
                      <span className="mr-1 inline-block h-2 w-2 rounded-full bg-red-500" />
                      Failed: {monitorAnalytics.down_checks}
                    </span>
                    <span>
                      <span className="mr-1 inline-block h-2 w-2 rounded-full bg-blue-500" />
                      Latency samples: {latencyChecks.length}
                    </span>
                  </div>
                </>
              )}
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="mb-5">
                <h2 className="text-lg font-semibold">Status Pages</h2>
                <p className="mt-1 text-sm text-slate-500">Create a public or private status page for this project.</p>
              </div>

              <form onSubmit={handleCreateStatusPage} className="mb-7 grid gap-3 md:grid-cols-3">
                <input
                  value={statusSlug}
                  onChange={(event) => setStatusSlug(event.target.value)}
                  required
                  minLength={3}
                  maxLength={100}
                  pattern="[A-Za-z0-9]+(-[A-Za-z0-9]+)*"
                  placeholder="status-page-slug"
                  className="rounded-lg border border-slate-300 px-4 py-3 text-sm"
                />
                <select value={statusVisibility} onChange={(event) => setStatusVisibility(event.target.value as "public" | "private")} className="rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm">
                  <option value="public">Public</option>
                  <option value="private">Private</option>
                </select>
                <button disabled={busy} className="rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">Create Status Page</button>
              </form>

              {dataLoading ? (
                <p className="text-sm text-slate-500">Loading status pages...</p>
              ) : statusPages.length === 0 ? (
                <p className="rounded-lg bg-slate-50 p-5 text-sm text-slate-500">No status pages created yet.</p>
              ) : (
                <div className="space-y-3">
                  {statusPages.map((page) => (
                    <article key={page.id} className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center">
                      <div className="min-w-0">
                        <h3 className="font-semibold">{page.slug}</h3>
                        <p className="mt-1 text-xs text-slate-500">Visibility: {page.visibility} · {page.enabled ? "Published" : "Disabled"}</p>
                        {page.enabled && page.visibility === "public" && (
                          <a href={`/api/status/${encodeURIComponent(page.slug)}`} target="_blank" rel="noreferrer" className="mt-2 inline-block break-all text-sm font-medium text-blue-600 hover:underline">
                            Open public status API
                          </a>
                        )}
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        <button onClick={() => void handleStatusPageToggle(page)} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold hover:bg-slate-50">
                          {page.enabled ? "Disable" : "Enable"}
                        </button>
                        <button onClick={() => void handleVisibilityToggle(page)} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-semibold hover:bg-slate-50">
                          Make {page.visibility === "public" ? "Private" : "Public"}
                        </button>
                        <button onClick={() => void handleDeleteStatusPage(page)} className="rounded-lg border border-red-200 px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-50">Delete</button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </>
        )}

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Authentication</h2>
          <p className="mt-2 text-sm text-emerald-700">Authenticated using secure HttpOnly cookies.</p>
        </section>
      </section>
    </main>
  );
}
