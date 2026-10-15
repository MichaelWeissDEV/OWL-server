import { Alert, Button, Group, Modal, PasswordInput, Select, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { api, API } from "../api/client";
import { useAction, useMyTokens, useRegistries } from "../api/hooks";
import type { Role, TokenInfo } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { SecretModal } from "../components/SecretModal";
import { TokenTable } from "./TokensPage";

export function ProfilePage() {
  const { me } = useAuth();
  const tokens = useMyTokens();
  const registries = useRegistries();
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const pw = useForm({
    initialValues: { old: "", next: "", again: "" },
    validate: { next: (v) => (v.length >= 12 ? null : "At least 12 characters"), again: (v, vals) => (v === vals.next ? null : "The passwords do not match") },
  });
  const change = useAction((v: { old: string; next: string }) => api(`${API}/auth/password`, { method: "POST", json: { old: v.old, new: v.next } }),
    { success: "Password changed - other sessions were signed out", onSuccess: () => pw.reset() });
  const form = useForm({ initialValues: { name: "", registry: "", role: "reader" as Role }, validate: { name: (v) => (v.trim() ? null : "Give the token a name") } });
  const create = useAction((v: typeof form.values) => api<{ token: string }>(`${API}/auth/tokens`, { method: "POST", json: { name: v.name, role: v.role, registry: v.registry || undefined } }),
    { invalidate: [["tokens"]], onSuccess: (r) => { setSecret(r.token); setCreating(false); form.reset(); } });
  const revoke = useAction((t: TokenInfo) => api(`${API}/auth/tokens/${t.id}`, { method: "DELETE" }), { invalidate: [["tokens"]], success: "Token revoked" });
  if (!me?.authenticated || me.kind !== "user") {
    return <EmptyState title="Profile">Profiles exist for signed-in accounts. {me?.kind === "open" ? "The server is open, so nobody is signed in." : ""}</EmptyState>;
  }
  return (
    <Stack>
      <Title order={2}>{me.username}</Title>
      <Text size="sm" c="dimmed">{me.is_admin ? "Server administrator" : "User"}{me.memberships.length ? ` - ${me.memberships.map((m) => `${m.registry}: ${m.role}`).join(", ")}` : ""}</Text>

      <Title order={4} mt="md">Change password</Title>
      <form onSubmit={pw.onSubmit((v) => change.mutate({ old: v.old, next: v.next }))}>
        <Stack maw={380}>
          <PasswordInput label="Current password" autoComplete="current-password" {...pw.getInputProps("old")} />
          <PasswordInput label="New password" autoComplete="new-password" {...pw.getInputProps("next")} />
          <PasswordInput label="Repeat new password" autoComplete="new-password" {...pw.getInputProps("again")} />
          <Group><Button type="submit" loading={change.isPending}>Change password</Button></Group>
        </Stack>
      </form>
      <Alert color="gray" variant="light" maw={520}>Accounts managed by an identity provider have no password here.</Alert>

      <Group justify="space-between" mt="md">
        <Title order={4}>Personal API tokens</Title>
        <Button size="sm" leftSection={<IconPlus size={14} aria-hidden />} onClick={() => setCreating(true)}>New token</Button>
      </Group>
      <Text size="sm" c="dimmed">For the OWL CLI: <code>owl remote add NAME URL --token-env OWL_TOKEN</code>. A token can never do more than you can.</Text>
      {tokens.isLoading ? <LoadingBlock rows={2} /> : tokens.error ? <ErrorBlock error={tokens.error} /> : (tokens.data ?? []).length === 0 ? <Text c="dimmed" size="sm">You have no tokens.</Text> : <TokenTable tokens={tokens.data!} onRevoke={(t) => revoke.mutate(t)} />}
      <Modal opened={creating} onClose={() => setCreating(false)} title="New personal token" centered>
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack>
            <TextInput label="Name" placeholder="laptop-cli" data-autofocus {...form.getInputProps("name")} />
            <Select label="Registry" description="Empty = all registries you can access" clearable placeholder="All" data={(registries.data ?? []).map((r) => r.slug)} {...form.getInputProps("registry")} />
            <Select label="Role" allowDeselect={false} data={["reader", "publisher", "admin"]} {...form.getInputProps("role")} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" loading={create.isPending}>Create token</Button></Group>
          </Stack>
        </form>
      </Modal>
      <SecretModal secret={secret} onClose={() => setSecret(null)} />
    </Stack>
  );
}
