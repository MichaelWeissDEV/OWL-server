import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../App";
import { adminMe, anonMe, mockFetch, openConfig, readerMe, registry, renderApp, securedConfig, status } from "../test/utils";

const skill = (name: string, over: object = {}) => ({
  author: "alice", name, version: "1.0.0", description: `The ${name} skill`, tags: ["git"], topics: [], sha256: "a".repeat(64), updated_at: "2026-02-01T10:00:00+00:00", ...over,
});
const fullSkill = (name: string) => ({ ...skill(name), content: `---\nname: ${name}\ndescription: The ${name} skill\n---\n# ${name} heading\n\nBody text.\n`, extra: {}, files: {}, created_at: "2026-01-01T00:00:00+00:00" });

const base = (me: object, config: object, role: string | null = "admin") => ({
  "GET /api/v1/auth/config": config,
  "GET /api/v1/auth/me": me,
  "GET /api/v1/registries": [registry(role)],
  "GET /api/v1/registries/default": registry(role),
  "GET /r/default/api/v1/stats": { registry: "default", skills: 2, versions: 3, last_update: "2026-02-01T10:00:00+00:00", by_author: {}, by_tag: { git: 2 }, by_topic: {} },
  "GET /r/default/api/v1/activity": [],
});

describe("layout and open mode", () => {
  it("warns loudly in open mode and points to Settings", async () => {
    mockFetch(base({ ...adminMe, kind: "open", username: "open-mode" }, openConfig));
    renderApp(<App />, "/");
    expect(await screen.findByText(/Open mode: no login required/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Secure this server" })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("button", { name: "Account menu" })).toBeNull(); // nobody is signed in
  });

  it("shows administration only to administrators", async () => {
    mockFetch(base(readerMe, securedConfig, "reader"));
    renderApp(<App />, "/", { token: "t" });
    expect(await screen.findByRole("link", { name: "Skills" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Audit log" })).toBeNull();
  });

  it("shows administration to admins and lets them open Users", async () => {
    mockFetch({ ...base(adminMe, securedConfig), "GET /api/v1/admin/users": [] });
    renderApp(<App />, "/", { token: "t" });
    await userEvent.click(await screen.findByRole("link", { name: "Users" }));
    expect(await screen.findByRole("heading", { name: "Users" })).toBeInTheDocument();
    expect(await screen.findByText("No users yet")).toBeInTheDocument();
  });

  it("keeps non-admins out of admin pages", async () => {
    mockFetch(base(readerMe, securedConfig, "reader"));
    renderApp(<App />, "/admin/users", { token: "t" });
    expect(await screen.findByText(/Only server administrators/)).toBeInTheDocument();
  });

  it("sends signed-out visitors of a secured server to the login page", async () => {
    mockFetch({ ...base(anonMe, securedConfig), "GET /api/v1/auth/me": status(401, { detail: "no" }) });
    renderApp(<App />, "/admin/users");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("login", () => {
  it("validates, signs in and reports wrong passwords", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    mockFetch({
      "GET /api/v1/auth/config": securedConfig,
      "GET /api/v1/auth/me": () => (attempts > 1 ? adminMe : status(401, { detail: "x" })),
      "POST /api/v1/auth/login": () => { attempts += 1; return attempts === 1 ? status(401, { detail: "Wrong username or password" }) : { token: "owl_t" }; },
      "GET /api/v1/registries": [],
    });
    renderApp(<App />, "/login");
    await user.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your username")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Username"), "boss");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong username or password");
    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "right-password-123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(window.sessionStorage.getItem("owl.token")).toBe("owl_t"));
  });

  it("offers single sign-on buttons and starts the redirect", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: "http://localhost" });
    mockFetch({
      "GET /api/v1/auth/config": { ...securedConfig, local_accounts: false, providers: [{ id: "oidc", type: "oidc", label: "Sign in with Keycloak" }] },
      "GET /api/v1/auth/me": status(401, { detail: "x" }),
      "GET /api/v1/auth/sso/oidc/login": { authorization_url: "https://idp.example.com/auth?x=1" },
    });
    renderApp(<App />, "/login");
    expect(screen.queryByLabelText("Password")).toBeNull(); // no password login configured
    await userEvent.click(await screen.findByRole("button", { name: "Sign in with Keycloak" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://idp.example.com/auth?x=1"));
    expect(window.sessionStorage.getItem("owl.sso.provider")).toBe("oidc");
  });

  it("labels directory login", async () => {
    mockFetch({ "GET /api/v1/auth/config": { ...securedConfig, local_accounts: false, ldap: { label: "Corporate directory" } }, "GET /api/v1/auth/me": status(401, { detail: "x" }) });
    renderApp(<App />, "/login");
    expect(await screen.findByLabelText(/Corporate directory/)).toBeInTheDocument();
  });
});

describe("skills list", () => {
  const routes = (role: string | null, rows: object[]) => ({
    ...base(adminMe, securedConfig, role),
    "GET /r/default/api/v1/skills": rows,
    "GET /r/default/api/v1/facets/author": [{ value: "alice", count: 2 }],
    "GET /r/default/api/v1/facets/tag": [{ value: "git", count: 2 }],
  });

  it("lists skills with versions and tags", async () => {
    mockFetch(routes("reader", [skill("git-helper"), skill("sql-tuner", { version: "2.1.0" })]));
    renderApp(<App />, "/r/default/skills", { token: "t" });
    const table = await screen.findByRole("table", { name: "Skills" });
    expect(within(table).getByRole("link", { name: "alice/git-helper" })).toHaveAttribute("href", "/r/default/skills/alice/git-helper");
    expect(within(table).getByText("2.1.0")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add skill/ })).toBeNull(); // readers cannot add
  });

  it("lets publishers add skills", async () => {
    mockFetch(routes("publisher", [skill("a")]));
    renderApp(<App />, "/r/default/skills", { token: "t" });
    expect(await screen.findByRole("button", { name: /Add skill/ })).toBeInTheDocument();
  });

  it("sends the search text to the server", async () => {
    const { calls } = mockFetch(routes("reader", [skill("git-helper")]));
    renderApp(<App />, "/r/default/skills", { token: "t" });
    await screen.findByRole("table", { name: "Skills" });
    await userEvent.type(screen.getByLabelText("Search"), "commit message{enter}");
    await waitFor(() => expect(calls.some((c) => c.url.includes("q=commit+message"))).toBe(true));
  });

  it("explains an empty registry", async () => {
    mockFetch(routes("publisher", []));
    renderApp(<App />, "/r/default/skills", { token: "t" });
    expect(await screen.findByText("No skills yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add the first skill" })).toBeInTheDocument();
  });

  it("shows server errors instead of an empty page", async () => {
    mockFetch({ ...routes("reader", []), "GET /r/default/api/v1/skills": status(500, { detail: "database is down" }) });
    renderApp(<App />, "/r/default/skills", { token: "t" });
    expect(await screen.findByRole("alert")).toHaveTextContent("database is down");
  });
});

describe("skill detail", () => {
  const detail = (role: string | null) => ({
    ...base(adminMe, securedConfig, role),
    "GET /r/default/api/v1/skills/alice/pdf": fullSkill("pdf"),
    "GET /r/default/api/v1/skills/alice/pdf/versions": [
      { sha256: "b".repeat(64), version: "2.0.0", description: "new", created_at: "2026-02-01T00:00:00+00:00", created_by: "bob", current: true },
      { sha256: "c".repeat(64), version: "1.0.0", description: "old", created_at: "2026-01-01T00:00:00+00:00", created_by: "alice", current: false },
    ],
    "GET /r/default/api/v1/skills/alice/pdf/files": [{ path: "SKILL.md", size: 80, sha256: "d".repeat(64), text: true }, { path: "blob.bin", size: 9, sha256: "e".repeat(64), text: false }],
  });

  it("shows the rendered SKILL.md, versions and files", async () => {
    mockFetch(detail("reader"));
    renderApp(<App />, "/r/default/skills/alice/pdf", { token: "t" });
    expect(await screen.findByRole("heading", { name: "alice/pdf" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "pdf heading" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Manage" })).toBeNull(); // readers cannot manage
    await userEvent.click(screen.getByRole("tab", { name: /Versions/ }));
    const versions = await screen.findByRole("table", { name: "Versions" });
    expect(within(versions).getByText(/2.0.0/)).toBeInTheDocument();
    expect(within(versions).queryByRole("button", { name: "Make current" })).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: /Files/ }));
    expect(await screen.findByText("blob.bin")).toBeInTheDocument();
    expect(screen.getByText("binary")).toBeInTheDocument();
  });

  it("lets a publisher restore an old version and delete the skill after confirming", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({
      ...detail("publisher"),
      ["GET /r/default/api/v1/skills/alice/pdf?version=" + "c".repeat(64)]: fullSkill("pdf"),
      "PUT /r/default/api/v1/skills/alice/pdf": {},
      "DELETE /r/default/api/v1/skills/alice/pdf": { deleted: true },
      "GET /r/default/api/v1/skills": [],
      "GET /r/default/api/v1/facets/author": [], "GET /r/default/api/v1/facets/tag": [],
    });
    renderApp(<App />, "/r/default/skills/alice/pdf", { token: "t" });
    await screen.findByRole("heading", { name: "alice/pdf" });
    await user.click(screen.getByRole("tab", { name: /Versions/ }));
    await user.click(await screen.findByRole("button", { name: "Make current" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));

    await user.click(screen.getByRole("button", { name: "Manage" }));
    await user.click(await screen.findByRole("menuitem", { name: /Delete skill/ }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false); // not before confirming
    await user.click(await screen.findByRole("button", { name: /Delete skill and all versions/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });
});

describe("users", () => {
  const users = [
    { username: "boss", email: null, is_admin: true, active: true, provider: "local", created_at: "", last_login: null, memberships: [] },
    { username: "ldapuser", email: "l@corp.example", is_admin: false, active: true, provider: "ldap", created_at: "", last_login: "2026-02-01T10:00:00+00:00", memberships: [{ registry: "default", role: "publisher" }] },
  ];

  it("shows where accounts come from and prevents deleting yourself", async () => {
    mockFetch({ ...base(adminMe, securedConfig), "GET /api/v1/admin/users": users });
    renderApp(<App />, "/admin/users", { token: "t" });
    const table = await screen.findByRole("table", { name: "Users" });
    expect(within(table).getByText("ldap")).toBeInTheDocument();
    expect(within(table).getByText("default: publisher")).toBeInTheDocument();
    const rows = within(table).getAllByRole("row");
    expect(within(rows[1]).getByRole("button", { name: "Delete" })).toBeDisabled(); // boss is signed in
    expect(within(rows[2]).getByRole("button", { name: "Delete" })).toBeEnabled();
  });

  it("validates and creates a user", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ ...base(adminMe, securedConfig), "GET /api/v1/admin/users": users, "POST /api/v1/admin/users": status(201, {}) });
    renderApp(<App />, "/admin/users", { token: "t" });
    await user.click(await screen.findByRole("button", { name: /New user/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Username"), "x");
    await user.type(within(dialog).getByLabelText(/Initial password/), "short");
    await user.click(within(dialog).getByRole("button", { name: "Create user" }));
    expect(await within(dialog).findByText("At least 12 characters")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.clear(within(dialog).getByLabelText("Username"));
    await user.type(within(dialog).getByLabelText("Username"), "carol");
    await user.clear(within(dialog).getByLabelText(/Initial password/));
    await user.type(within(dialog).getByLabelText(/Initial password/), "correct-horse-battery-9");
    await user.click(within(dialog).getByRole("button", { name: "Create user" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ username: "carol", password: "correct-horse-battery-9", is_admin: false }));
  });
});

describe("settings: secure this server", () => {
  const info = (open: boolean) => ({
    version: "0.1.0", mode: "mixed", open, open_reason: open ? "default: nothing to authenticate with is configured yet" : "set in the dashboard", default_registry: "default",
    providers: { local_accounts: true, oidc: false, oauth: false, ldap: true, proxy: false, admin_token: false }, oidc_issuer: null, ldap_url: "ldaps://dc.corp.example",
    counts: { registries: 1, skills: 4, versions: 6, users: 0, tokens: 0 }, schema_revision: "0003", max_body_mb: 40, session_ttl_hours: 12,
  });

  it("requires matching strong passwords before securing", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({
      ...base({ ...adminMe, kind: "open", username: "open-mode" }, openConfig), "GET /api/v1/admin/server": info(true),
      "POST /api/v1/setup/secure": status(201, { token: "owl_new", user: { username: "root", is_admin: true } }),
    });
    renderApp(<App />, "/settings");
    expect(await screen.findByText("Open - no login")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Administrator username"), "root");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery-9");
    await user.type(screen.getByLabelText("Repeat password"), "something-else-1234");
    await user.click(screen.getByRole("button", { name: "Secure this server" }));
    expect(await screen.findByText("The passwords do not match")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await user.clear(screen.getByLabelText("Repeat password"));
    await user.type(screen.getByLabelText("Repeat password"), "correct-horse-battery-9");
    await user.click(screen.getByRole("button", { name: "Secure this server" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ username: "root", password: "correct-horse-battery-9" }));
    await waitFor(() => expect(window.sessionStorage.getItem("owl.token")).toBe("owl_new"));
  });

  it("lists which sign-in methods are enabled", async () => {
    mockFetch({ ...base(adminMe, securedConfig), "GET /api/v1/admin/server": info(false) });
    renderApp(<App />, "/settings", { token: "t" });
    const table = await screen.findByRole("table", { name: "Sign-in methods" });
    const ldap = within(table).getByText("LDAP / Active Directory").closest("tr")!;
    expect(within(ldap).getByText("enabled")).toBeInTheDocument();
    const oidc = within(table).getByText("OpenID Connect").closest("tr")!;
    expect(within(oidc).getByText("off")).toBeInTheDocument();
    expect(screen.getByText("Secured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Switch back to open mode/ })).toBeInTheDocument();
  });

  it("asks for confirmation before re-opening", async () => {
    const user = userEvent.setup();
    const { calls } = mockFetch({ ...base(adminMe, securedConfig), "GET /api/v1/admin/server": info(false), "PUT /api/v1/admin/security": { open: true } });
    renderApp(<App />, "/settings", { token: "t" });
    await user.click(await screen.findByRole("button", { name: /Switch back to open mode/ }));
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    await user.click(await screen.findByRole("button", { name: "Yes, open the server" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ open: true, confirm: true }));
  });
});

describe("tokens", () => {
  it("shows a new token once and never lists secrets", async () => {
    const user = userEvent.setup();
    mockFetch({
      ...base(adminMe, securedConfig), "GET /api/v1/admin/tokens": [],
      "POST /api/v1/admin/tokens": status(201, { token: "owl_SECRETVALUE", id: 1, prefix: "owl_SECRETV", role: "publisher", registry: "default", expires_at: null }),
    });
    renderApp(<App />, "/admin/tokens", { token: "t" });
    await user.click(await screen.findByRole("button", { name: /New token/ }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "ci");
    await user.click(within(dialog).getByRole("textbox", { name: "Registry" }));
    await user.click(await screen.findByText("default", { selector: "[role=option] *, [role=option]" }));
    await user.click(within(dialog).getByRole("button", { name: "Create token" }));
    const secret = await screen.findByLabelText("Token");
    expect(secret).toHaveValue("owl_SECRETVALUE");
    await user.click(screen.getByRole("button", { name: "I have saved it" }));
    await waitFor(() => expect(screen.queryByLabelText("Token")).toBeNull());
    expect(screen.queryByText(/owl_SECRETVALUE/)).toBeNull();
  });
});
