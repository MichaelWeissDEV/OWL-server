export type Role = "reader" | "publisher" | "admin";

export interface Registry {
  slug: string;
  name: string;
  description: string;
  visibility: "public" | "private";
  skills: number;
  role: Role | null;
  created_at: string;
}

export interface SkillSummary {
  author: string;
  name: string;
  version: string;
  description: string;
  tags: string[];
  topics: string[];
  sha256: string;
  updated_at: string | null;
}

export interface Skill extends SkillSummary {
  content: string;
  extra: Record<string, unknown>;
  files: Record<string, string>; // path -> base64
  created_at: string | null;
}

export interface VersionInfo {
  sha256: string;
  version: string;
  description: string;
  created_at: string;
  created_by: string;
  current: boolean;
}

export interface FileInfo {
  path: string;
  size: number;
  sha256: string;
  text: boolean;
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface Activity {
  ref: string;
  version: string;
  sha256: string;
  at: string;
  by: string;
  description: string;
  current: boolean;
}

export interface Stats {
  registry: string;
  skills: number;
  versions: number;
  last_update: string | null;
  by_author: Record<string, number>;
  by_tag: Record<string, number>;
  by_topic: Record<string, number>;
}

export interface Collection {
  name: string;
  description: string;
  skills: number;
}

export interface SsoProvider {
  id: string;
  type: string;
  label: string;
}

export interface AuthConfig {
  open: boolean;
  open_reason: string;
  mode: "public" | "private" | "mixed";
  local_accounts: boolean;
  ldap: { label: string } | null;
  proxy: boolean;
  providers: SsoProvider[];
}

export interface Me {
  authenticated: boolean;
  kind: "anonymous" | "open" | "bootstrap" | "user" | "service";
  username: string;
  is_admin: boolean;
  memberships: { registry: string; role: Role }[];
  token_role: Role | null;
}

export interface UserInfo {
  username: string;
  email: string | null;
  is_admin: boolean;
  active: boolean;
  provider: string;
  created_at: string;
  last_login: string | null;
  memberships: { registry: string; role: Role }[];
}

export interface TokenInfo {
  id: number;
  name: string;
  prefix: string;
  role: Role;
  registry: string | null;
  user?: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
}

export interface AuditEvent {
  id: number;
  at: string;
  actor: string;
  action: string;
  target: string;
  detail: string;
  ip: string;
}

export interface ServerInfo {
  version: string;
  mode: string;
  open: boolean;
  open_reason: string;
  default_registry: string;
  providers: Record<string, boolean>;
  oidc_issuer: string | null;
  ldap_url: string | null;
  counts: Record<string, number>;
  schema_revision: string | null;
  max_body_mb: number;
  session_ttl_hours: number;
}

export interface SetupStatus {
  open: boolean;
  reason: string;
  users: number;
  admins: number;
  providers: Record<string, boolean>;
  version: string;
}

export interface ImportReport {
  results: { name: string; path: string; status: string; ref?: string; problems?: string[] }[];
  imported: number;
  invalid: number;
}
