import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import { theme } from "../theme";

export type Handler = (request: { url: string; method: string; body: unknown; headers: Record<string, string> }) => unknown;
export interface MockResponse { status?: number; body?: unknown }

/** Route table: key is "METHOD /path" (query string ignored unless the key contains '?'). */
export type Routes = Record<string, Handler | unknown>;

export function mockFetch(routes: Routes) {
  const calls: { method: string; url: string; body: unknown; headers: Record<string, string> }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = (init?.headers ?? {}) as Record<string, string>;
    let body: unknown = init?.body;
    if (typeof body === "string") {
      try { body = JSON.parse(body); } catch { /* keep text */ }
    }
    calls.push({ method, url, body, headers });
    const path = url.split("?")[0];
    const key = Object.keys(routes).find((k) => k === `${method} ${url}` || k === `${method} ${path}`);
    if (!key) return new Response(JSON.stringify({ detail: `unmocked ${method} ${url}` }), { status: 599 });
    const entry = routes[key];
    const result = typeof entry === "function" ? (entry as Handler)({ url, method, body, headers }) : entry;
    const mock: MockResponse = result && typeof result === "object" && "__status" in (result as object)
      ? { status: (result as { __status: number }).__status, body: (result as { body?: unknown }).body }
      : { body: result };
    const status = mock.status ?? (result as { __status?: number })?.__status ?? 200;
    const text = mock.body === undefined ? "" : typeof mock.body === "string" ? mock.body : JSON.stringify(mock.body);
    return new Response(status === 204 ? null : text, { status, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export const status = (code: number, body?: unknown) => ({ __status: code, body });

export const openConfig = {
  open: true, open_reason: "default", mode: "mixed", local_accounts: true, ldap: null, proxy: false, providers: [],
};
export const securedConfig = { ...openConfig, open: false, open_reason: "configured" };
export const adminMe = { authenticated: true, kind: "user", username: "boss", is_admin: true, memberships: [], token_role: null };
export const readerMe = { authenticated: true, kind: "user", username: "rita", is_admin: false, memberships: [{ registry: "default", role: "reader" }], token_role: null };
export const anonMe = { authenticated: false, kind: "anonymous", username: "anonymous", is_admin: false, memberships: [], token_role: null };
export const registry = (role: string | null = "admin", slug = "default") => ({
  slug, name: slug === "default" ? "Default registry" : slug, description: "d", visibility: "private", skills: 2, role, created_at: "2026-01-01T00:00:00+00:00",
});

export function renderApp(ui: ReactElement, route = "/", { token }: { token?: string } = {}): RenderResult {
  if (token) window.sessionStorage.setItem("owl.token", token);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(
    <MantineProvider theme={theme} defaultColorScheme="light">
      <Notifications />
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>{ui}</AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}
