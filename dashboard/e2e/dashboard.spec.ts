import { expect, test, type Page } from "@playwright/test";

const SKILL = (description: string, version = "1.0.0") => `---
name: pdf-tools
description: ${description}
tags: [pdf, office]
version: ${version}
---

# PDF tools

Extract text from PDFs.

<script>window.__pwned = true</script>
`;

const ADMIN_PASSWORD = "correct-horse-battery-9";

async function fillEditor(page: Page, text: string) {
  const box = page.getByRole("dialog").getByRole("textbox", { name: "SKILL.md" });
  await box.fill(text);
}

// The tests share one server and tell one story: open -> add content -> secure -> manage users.
test.describe.serial("OWL dashboard", () => {
  test("an open server needs no login and says so", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Open mode: no login required")).toBeVisible();
    await expect(page.getByRole("link", { name: "Skills", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Users", exact: true })).toBeVisible(); // everyone is an admin while open
    await expect(page.locator("header img").first()).toBeVisible(); // the logo
  });

  test("create a registry, add a skill, edit it and compare versions", async ({ page }) => {
    await page.goto("/registries");
    await page.getByRole("button", { name: "New registry" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Slug").fill("team");
    await dialog.getByLabel("Name").fill("Team skills");
    await dialog.getByRole("button", { name: "Create" }).click();
    await expect(page.getByRole("heading", { name: "Team skills" })).toBeVisible();

    await page.goto("/r/team/skills");
    await expect(page.getByText("No skills yet")).toBeVisible();
    await page.getByRole("button", { name: "Add the first skill" }).click();
    await fillEditor(page, SKILL("Extract text from PDF files"));
    await page.getByRole("button", { name: "Save skill" }).click();

    await expect(page.getByRole("heading", { name: "open-mode/pdf-tools" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "PDF tools", level: 1 })).toBeVisible();
    // untrusted markdown never runs
    expect(await page.evaluate(() => (window as unknown as { __pwned?: boolean }).__pwned)).toBeUndefined();
    await expect(page.locator("[data-testid=markdown] script")).toHaveCount(0);

    await page.getByRole("button", { name: "Manage" }).click();
    await page.getByRole("menuitem", { name: /Edit SKILL.md/ }).click();
    await page.getByRole("dialog").getByRole("textbox", { name: "SKILL.md" }).fill(SKILL("Extract text and tables from PDF files", "1.1.0"));
    await page.getByRole("button", { name: "Save new version" }).click();
    await expect(page.getByText("Saved as a new version")).toBeVisible();

    await page.getByRole("tab", { name: /Versions/ }).click();
    await expect(page.getByRole("table", { name: "Versions" }).getByRole("row")).toHaveCount(3); // header + 2
    await page.getByRole("tab", { name: "Compare" }).click();
    await page.getByRole("button", { name: "Compare" }).click();
    const diff = page.getByTestId("diff");
    await expect(diff).toContainText("+ description: Extract text and tables from PDF files");
    await expect(diff).toContainText("- description: Extract text from PDF files");
  });

  test("search finds the skill and filters narrow it down", async ({ page }) => {
    await page.goto("/r/team/skills");
    await page.getByLabel("Search").fill("tables");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByRole("link", { name: "open-mode/pdf-tools" })).toBeVisible();
    await page.getByLabel("Search").fill("nothing-like-this");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByText("No skills match")).toBeVisible();
  });

  test("securing the server creates the first admin and requires sign-in", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("Open - no login")).toBeVisible();
    await page.getByLabel("Administrator username").fill("root");
    await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
    await page.getByLabel("Repeat password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Secure this server" }).click();
    await expect(page.getByText("Secured", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Account menu" })).toContainText("root");
    await expect(page.getByText("Open mode: no login required")).toHaveCount(0);

    // signed out: login required, wrong password is refused, correct one works
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.getByLabel("Username").fill("root");
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert")).toContainText("Wrong username or password");
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("button", { name: "Account menu" })).toContainText("root");
  });

  test("an admin creates a reader; the reader sees a read-only view", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill("root");
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByRole("link", { name: "Users", exact: true }).click();
    await page.getByRole("button", { name: "New user" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Username").fill("rita");
    await dialog.getByLabel(/Initial password/).fill(ADMIN_PASSWORD);
    await dialog.getByRole("button", { name: "Create user" }).click();
    const row = page.getByRole("row", { name: /rita/ });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Edit" }).click();
    const edit = page.getByRole("dialog");
    await edit.getByRole("textbox", { name: "Registry", exact: false }).first().click();
    await page.getByRole("option", { name: "team" }).click();
    await edit.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText("Membership saved")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();

    await page.getByLabel("Username").fill("rita");
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("button", { name: "Account menu" })).toContainText("rita");
    await expect(page.getByRole("link", { name: "Users", exact: true })).toHaveCount(0);
    await page.goto("/r/team/skills");
    await expect(page.getByRole("link", { name: "open-mode/pdf-tools" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Add skill/ })).toHaveCount(0);
    await page.goto("/admin/users");
    await expect(page.getByText("Only server administrators")).toBeVisible();
    // the API refuses too (the UI is not a security boundary)
    const response = await page.request.get("/api/v1/admin/users", { headers: { Authorization: `Bearer ${await page.evaluate(() => sessionStorage.getItem("owl.token"))}` } });
    expect(response.status()).toBe(403);
  });

  test("dark mode, keyboard skip link and mobile navigation", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Username").fill("root");
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("button", { name: "Account menu" })).toBeVisible();

    await page.getByRole("button", { name: "Switch to dark mode" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", "dark");
    await page.getByRole("button", { name: "Switch to light mode" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-mantine-color-scheme", "light");

    await page.goto("/"); // a fresh page: the skip link is the first thing a keyboard user reaches
    await expect(page.getByRole("button", { name: "Account menu" })).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();

    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Skills", exact: true })).not.toBeInViewport();
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    await expect(page.getByRole("link", { name: "Skills", exact: true })).toBeVisible();
  });
});
