
export type User = {
  id: string;
  email: string;
  created_at: string;
};

export type AuthCredentials = {
  email: string;
  password: string;
};

type AuthErrorResponse = {
  detail?: string;
};

const API_BASE = "/api/auth";

async function authRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
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
      const errorData = (await response.json()) as AuthErrorResponse;
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

export function register(credentials: AuthCredentials): Promise<User> {
  return authRequest<User>("/register", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function login(credentials: AuthCredentials): Promise<User> {
  return authRequest<User>("/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function getCurrentUser(): Promise<User> {
  return authRequest<User>("/me", {
    method: "GET",
  });
}

export function refreshSession(): Promise<{ message: string }> {
  return authRequest<{ message: string }>("/refresh", {
    method: "POST",
  });
}

export function logout(): Promise<{ message: string }> {
  return authRequest<{ message: string }>("/logout", {
    method: "POST",
  });
}
