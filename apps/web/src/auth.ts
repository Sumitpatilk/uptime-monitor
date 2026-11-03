
export type User = {
  id: string;
  email: string;
  created_at: string;
};

export type AuthCredentials = {
  email: string;
  password: string;
};

export type Project = {
  id: string;
  owner_id: string;
  name: string;
  plan: string;
  created_at: string;
};

export type Monitor = {
  id: string;
  project_id: string;
  name: string;
  url: string;
  interval_seconds: number;
  timeout_seconds: number;
  expected_status: number;
  enabled: boolean;
  created_at: string;
};

export type MonitorCreate = {
  name: string;
  url: string;
  interval_seconds?: number;
  timeout_seconds?: number;
  expected_status?: number;
  enabled?: boolean;
};

export type MonitorUpdate = Partial<MonitorCreate>;

export type MonitorAnalyticsCheck = {
  id: string;
  checked_at: string;
  status: string;
  latency_ms: number | null;
};

export type MonitorAnalytics = {
  monitor_id: string;
  window_hours: number;
  since: string;
  total_checks: number;
  up_checks: number;
  down_checks: number;
  uptime_percentage: number | null;
  average_latency_ms: number | null;
  min_latency_ms: number | null;
  max_latency_ms: number | null;
  checks: MonitorAnalyticsCheck[];
};

export type StatusPage = {
  id: string;
  project_id: string;
  slug: string;
  visibility: "public" | "private";
  enabled: boolean;
};

export type StatusPageCreate = {
  slug: string;
  visibility?: "public" | "private";
  enabled?: boolean;
};

export type StatusPageUpdate = Partial<StatusPageCreate>;

export type PublicMonitorStatus = {
  name: string;
  status: string;
  last_checked_at: string | null;
  latency_ms: number | null;
};

export type PublicIncidentStatus = {
  started_at: string;
  resolved_at: string | null;
  state: string;
};

export type PublicStatusPage = {
  slug: string;
  overall_status: string;
  monitors: PublicMonitorStatus[];
  incidents: PublicIncidentStatus[];
};

type ApiErrorResponse = {
  detail?: string;
};

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(endpoint, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    let message = "Something went wrong. Please try again.";

    try {
      const errorData = (await response.json()) as ApiErrorResponse;
      if (errorData.detail) {
        message = errorData.detail;
      }
    } catch {
      // Keep the default error message.
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

// Authentication

export function register(credentials: AuthCredentials): Promise<User> {
  return apiRequest<User>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function login(credentials: AuthCredentials): Promise<User> {
  return apiRequest<User>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function getCurrentUser(): Promise<User> {
  return apiRequest<User>("/api/auth/me");
}

export function refreshSession(): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/api/auth/refresh", {
    method: "POST",
  });
}

export function logout(): Promise<{ message: string }> {
  return apiRequest<{ message: string }>("/api/auth/logout", {
    method: "POST",
  });
}

// Projects

export function getProjects(): Promise<Project[]> {
  return apiRequest<Project[]>("/api/projects");
}

export function createProject(name: string): Promise<Project> {
  return apiRequest<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function updateProject(
  projectId: string,
  name: string,
): Promise<Project> {
  return apiRequest<Project>(`/api/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteProject(projectId: string): Promise<void> {
  return apiRequest<void>(`/api/projects/${projectId}`, {
    method: "DELETE",
  });
}

// Monitors
export function getMonitorAnalytics(
  projectId: string,
  monitorId: string,
  hours = 24,
): Promise<MonitorAnalytics> {
  return apiRequest<MonitorAnalytics>(
    `/api/projects/${projectId}/monitors/${monitorId}/analytics?hours=${hours}`,
  );
}

export function getMonitors(projectId: string): Promise<Monitor[]> {
  return apiRequest<Monitor[]>(`/api/projects/${projectId}/monitors`);
}

export function createMonitor(
  projectId: string,
  payload: MonitorCreate,
): Promise<Monitor> {
  return apiRequest<Monitor>(`/api/projects/${projectId}/monitors`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateMonitor(
  projectId: string,
  monitorId: string,
  payload: MonitorUpdate,
): Promise<Monitor> {
  return apiRequest<Monitor>(
    `/api/projects/${projectId}/monitors/${monitorId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteMonitor(
  projectId: string,
  monitorId: string,
): Promise<void> {
  return apiRequest<void>(
    `/api/projects/${projectId}/monitors/${monitorId}`,
    {
      method: "DELETE",
    },
  );
}

// Status Pages

export function getStatusPages(projectId: string): Promise<StatusPage[]> {
  return apiRequest<StatusPage[]>(
    `/api/projects/${projectId}/status-pages`,
  );
}

export function createStatusPage(
  projectId: string,
  payload: StatusPageCreate,
): Promise<StatusPage> {
  return apiRequest<StatusPage>(
    `/api/projects/${projectId}/status-pages`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function updateStatusPage(
  projectId: string,
  statusPageId: string,
  payload: StatusPageUpdate,
): Promise<StatusPage> {
  return apiRequest<StatusPage>(
    `/api/projects/${projectId}/status-pages/${statusPageId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteStatusPage(
  projectId: string,
  statusPageId: string,
): Promise<void> {
  return apiRequest<void>(
    `/api/projects/${projectId}/status-pages/${statusPageId}`,
    {
      method: "DELETE",
    },
  );
}

// Public Status Page

export function getPublicStatusPage(
  slug: string,
): Promise<PublicStatusPage> {
  return apiRequest<PublicStatusPage>(
    `/api/status/${encodeURIComponent(slug)}`,
  );
}
