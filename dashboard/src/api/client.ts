/** Thin fetch wrapper: bearer token from sessionStorage, readable errors, no hidden retries. */

const TOKEN_KEY = "owl.token";

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const tokenStore = {
  get(): string | null {
    try {
      return window.sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null): void {
    try {
      if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
      else window.sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage blocked: the session just will not survive a reload */
    }
  },
};

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
export function onUnauthorized(listener: Listener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

export interface RequestOptions {
  method?: string;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  /** Do not treat 401 as "session expired" (used by the login form itself). */
  quiet401?: boolean;
}

async function raise(response: Response): Promise<never> {
  let detail = response.statusText || `HTTP ${response.status}`;
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") detail = data.detail;
    else if (Array.isArray(data?.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).join("; ");
  } catch {
    /* not JSON */
  }
  throw new ApiError(response.status, detail);
}

export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.form) {
    body = options.form;
  }
  let response: Response;
  try {
    response = await fetch(path, { method: options.method ?? "GET", headers, body, signal: options.signal });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "The server cannot be reached");
  }
  if (response.status === 401 && !options.quiet401 && token) {
    tokenStore.set(null);
    unauthorizedListeners.forEach((l) => l());
  }
  if (!response.ok) await raise(response);
  return response;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function apiText(path: string, options: RequestOptions = {}): Promise<string> {
  return (await request(path, options)).text();
}

/** Download a protected file: fetch with the token, then hand the blob to the browser. */
export async function download(path: string, filename: string): Promise<void> {
  const blob = await (await request(path)).blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export const enc = encodeURIComponent;

/** URL prefix of one registry's API. */
export const reg = (slug: string) => `/r/${enc(slug)}/api/v1`;
export const API = "/api/v1";
