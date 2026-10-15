import { api, ApiError, onUnauthorized, tokenStore } from "./client";
import { mockFetch, status } from "../test/utils";

describe("api client", () => {
  it("sends the bearer token and parses JSON", async () => {
    tokenStore.set("owl_secret");
    const { calls } = mockFetch({ "GET /api/v1/x": { ok: true } });
    expect(await api("/api/v1/x")).toEqual({ ok: true });
    expect(calls[0].headers.Authorization).toBe("Bearer owl_secret");
  });

  it("sends no Authorization header without a token", async () => {
    const { calls } = mockFetch({ "GET /api/v1/x": {} });
    await api("/api/v1/x");
    expect(calls[0].headers.Authorization).toBeUndefined();
  });

  it("turns error responses into readable ApiErrors", async () => {
    mockFetch({ "POST /api/v1/x": status(422, { detail: "name is invalid" }) });
    await expect(api("/api/v1/x", { method: "POST", json: {} })).rejects.toMatchObject({ status: 422, message: "name is invalid" });
  });

  it("explains unreachable servers", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    await expect(api("/api/v1/x")).rejects.toThrow("cannot be reached");
  });

  it("clears the token and notifies on 401 for an authenticated session", async () => {
    tokenStore.set("stale");
    mockFetch({ "GET /api/v1/x": status(401, { detail: "expired" }) });
    const listener = vi.fn();
    const off = onUnauthorized(listener);
    await expect(api("/api/v1/x")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalled();
    expect(tokenStore.get()).toBeNull();
    off();
  });

  it("does not treat a failed login (quiet401) as an expired session", async () => {
    tokenStore.set("still-valid");
    mockFetch({ "POST /api/v1/auth/login": status(401, { detail: "Wrong username or password" }) });
    const listener = vi.fn();
    const off = onUnauthorized(listener);
    await expect(api("/api/v1/auth/login", { method: "POST", json: {}, quiet401: true })).rejects.toThrow("Wrong username");
    expect(listener).not.toHaveBeenCalled();
    expect(tokenStore.get()).toBe("still-valid");
    off();
  });
});
