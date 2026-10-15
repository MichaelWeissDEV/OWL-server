import type { Registry, Role } from "./api/types";

export const ROLE_RANK: Record<Role, number> = { reader: 0, publisher: 1, admin: 2 };

export const canWrite = (r: Pick<Registry, "role"> | undefined | null): boolean =>
  !!r?.role && ROLE_RANK[r.role] >= ROLE_RANK.publisher;

export const canAdmin = (r: Pick<Registry, "role"> | undefined | null): boolean => r?.role === "admin";

export function shortDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

export function splitFrontmatter(text: string): { meta: Record<string, string>; body: string } {
  if (!text.startsWith("---")) return { meta: {}, body: text };
  const end = text.indexOf("\n---", 3);
  if (end === -1) return { meta: {}, body: text };
  const meta: Record<string, string> = {};
  for (const line of text.slice(3, end).split("\n")) {
    const m = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
    if (m) meta[m[1]] = m[2];
  }
  return { meta, body: text.slice(end + 4).replace(/^\n/, "") };
}

export const SKILL_TEMPLATE = `---
name: my-skill
description: Describe what this skill does and when an agent should use it.
tags: [example]
version: 0.1.0
---

# My skill

Instructions for the agent.
`;
