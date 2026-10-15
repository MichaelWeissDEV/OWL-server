import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { api, API, enc, reg } from "./client";
import type {
  Activity, AuditEvent, Collection, FacetValue, FileInfo, ImportReport, Registry, ServerInfo, Skill,
  SkillSummary, Stats, TokenInfo, UserInfo, VersionInfo,
} from "./types";

export interface SkillQuery {
  q?: string;
  author?: string;
  tags?: string[];
  topics?: string[];
  limit?: number;
  offset?: number;
}

export function searchParams(q: SkillQuery): string {
  const p = new URLSearchParams();
  if (q.q) p.set("q", q.q);
  if (q.author) p.set("author", q.author);
  q.tags?.forEach((t) => p.append("tag", t));
  q.topics?.forEach((t) => p.append("topic", t));
  p.set("limit", String(q.limit ?? 25));
  p.set("offset", String(q.offset ?? 0));
  return p.toString();
}

export const useRegistries = () =>
  useQuery({ queryKey: ["registries"], queryFn: () => api<Registry[]>(`${API}/registries`) });

export const useRegistry = (slug: string) =>
  useQuery({ queryKey: ["registry", slug], queryFn: () => api<Registry>(`${API}/registries/${enc(slug)}`) });

export const useStats = (slug: string) =>
  useQuery({ queryKey: ["stats", slug], queryFn: () => api<Stats>(`${reg(slug)}/stats`) });

export const useSkills = (slug: string, q: SkillQuery) =>
  useQuery({
    queryKey: ["skills", slug, q],
    queryFn: () => api<SkillSummary[]>(`${reg(slug)}/skills?${searchParams(q)}`),
    placeholderData: (previous) => previous,
  });

export const useFacets = (slug: string, kind: "author" | "tag" | "topic") =>
  useQuery({ queryKey: ["facets", slug, kind], queryFn: () => api<FacetValue[]>(`${reg(slug)}/facets/${kind}`) });

export const useSkill = (slug: string, author: string, name: string) =>
  useQuery({
    queryKey: ["skill", slug, author, name],
    queryFn: () => api<Skill>(`${reg(slug)}/skills/${enc(author)}/${enc(name)}`),
  });

export const useVersions = (slug: string, author: string, name: string) =>
  useQuery({
    queryKey: ["versions", slug, author, name],
    queryFn: () => api<VersionInfo[]>(`${reg(slug)}/skills/${enc(author)}/${enc(name)}/versions`),
  });

export const useFiles = (slug: string, author: string, name: string, version?: string) =>
  useQuery({
    queryKey: ["files", slug, author, name, version],
    queryFn: () =>
      api<FileInfo[]>(`${reg(slug)}/skills/${enc(author)}/${enc(name)}/files${version ? `?version=${version}` : ""}`),
  });

export const useActivity = (slug: string, limit = 30) =>
  useQuery({ queryKey: ["activity", slug, limit], queryFn: () => api<Activity[]>(`${reg(slug)}/activity?limit=${limit}`) });

export const useCollections = (slug: string) =>
  useQuery({ queryKey: ["collections", slug], queryFn: () => api<Collection[]>(`${reg(slug)}/collections`) });

export const useUsers = (enabled = true) =>
  useQuery({ queryKey: ["users"], queryFn: () => api<UserInfo[]>(`${API}/admin/users`), enabled });

export const useServiceTokens = () =>
  useQuery({ queryKey: ["tokens", "service"], queryFn: () => api<TokenInfo[]>(`${API}/admin/tokens`) });

export const useMyTokens = () =>
  useQuery({ queryKey: ["tokens", "mine"], queryFn: () => api<TokenInfo[]>(`${API}/auth/tokens`) });

export const useAudit = (action: string, limit: number) =>
  useQuery({
    queryKey: ["audit", action, limit],
    queryFn: () => api<AuditEvent[]>(`${API}/admin/audit?limit=${limit}${action ? `&action=${enc(action)}` : ""}`),
  });

export const useServerInfo = () =>
  useQuery({ queryKey: ["server"], queryFn: () => api<ServerInfo>(`${API}/admin/server`) });

/** A mutation that reports success/failure as a notification and refreshes the listed queries. */
export function useAction<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  options: { invalidate?: string[][]; success?: string | ((r: TResult) => string); onSuccess?: (r: TResult) => void } = {},
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      for (const key of options.invalidate ?? []) await queryClient.invalidateQueries({ queryKey: key });
      if (options.success) {
        const message = typeof options.success === "function" ? options.success(result) : options.success;
        notifications.show({ color: "teal", message });
      }
      options.onSuccess?.(result);
    },
    onError: (error: Error) => notifications.show({ color: "red", title: "That did not work", message: error.message }),
  });
}

export function importSkill(
  slug: string, body: { content: string; author?: string; files?: Record<string, string>; overrides?: Record<string, unknown> },
) {
  return api<Skill & { outcome: string }>(`${reg(slug)}/skills/import`, { method: "POST", json: body });
}

export function importZip(slug: string, file: File, author: string) {
  const form = new FormData();
  form.append("file", file);
  if (author) form.append("author", author);
  return api<ImportReport>(`${reg(slug)}/import-zip`, { method: "POST", form });
}
