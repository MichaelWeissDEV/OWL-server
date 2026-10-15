import { Badge, Button, Group, Modal, NumberInput, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { api, API } from "../api/client";
import { useAction, useRegistries, useServiceTokens } from "../api/hooks";
import type { Role, TokenInfo } from "../api/types";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { SecretModal } from "../components/SecretModal";
import { shortDate } from "../lib";

export function TokenTable({ tokens, onRevoke, showUser }: { tokens: TokenInfo[]; onRevoke: (t: TokenInfo) => void; showUser?: boolean }) {
  return (
    <Table.ScrollContainer minWidth={640}>
      <Table aria-label="Tokens">
        <Table.Thead><Table.Tr><Table.Th>Name</Table.Th><Table.Th>Token</Table.Th><Table.Th>Role</Table.Th><Table.Th>Registry</Table.Th>{showUser && <Table.Th>User</Table.Th>}<Table.Th>Expires</Table.Th><Table.Th>Last used</Table.Th><Table.Th /></Table.Tr></Table.Thead>
        <Table.Tbody>
          {tokens.map((t) => (
            <Table.Tr key={t.id} style={{ opacity: t.revoked_at ? 0.5 : 1 }}>
              <Table.Td>{t.name}</Table.Td>
              <Table.Td><code>{t.prefix}...</code></Table.Td>
              <Table.Td><Badge variant="light">{t.role}</Badge></Table.Td>
              <Table.Td>{t.registry ?? "all"}</Table.Td>
              {showUser && <Table.Td>{t.user ?? "-"}</Table.Td>}
              <Table.Td>{t.revoked_at ? <Badge color="red" variant="light">revoked</Badge> : t.expires_at ? shortDate(t.expires_at) : "never"}</Table.Td>
              <Table.Td>{shortDate(t.last_used_at)}</Table.Td>
              <Table.Td>{!t.revoked_at && <Button size="compact-sm" color="red" variant="subtle" onClick={() => onRevoke(t)}>Revoke</Button>}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

export function TokensPage() {
  const tokens = useServiceTokens();
  const registries = useRegistries();
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const form = useForm({
    initialValues: { name: "", registry: "", role: "publisher" as Role, ttl_hours: "" as number | "" },
    validate: { name: (v) => (v.trim() ? null : "Give the token a name"), registry: (v) => (v ? null : "Choose a registry") },
  });
  const create = useAction((v: typeof form.values) => api<{ token: string }>(`${API}/admin/tokens`, { method: "POST", json: { ...v, ttl_hours: v.ttl_hours || undefined } }),
    { invalidate: [["tokens"]], onSuccess: (r) => { setSecret(r.token); setCreating(false); form.reset(); } });
  const revoke = useAction((t: TokenInfo) => api(`${API}/admin/tokens/${t.id}`, { method: "DELETE" }), { invalidate: [["tokens"]], success: "Token revoked" });
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Service tokens</Title>
        <Button leftSection={<IconPlus size={16} aria-hidden />} onClick={() => setCreating(true)}>New token</Button>
      </Group>
      <Text size="sm" c="dimmed">Tokens for automation (CI, scripts, the OWL CLI). Each is limited to one registry and a role. Users create their own personal tokens in their profile.</Text>
      {tokens.isLoading ? <LoadingBlock /> : tokens.error ? <ErrorBlock error={tokens.error} /> : (tokens.data ?? []).length === 0 ? (
        <EmptyState title="No tokens yet">Create one for a CI job that publishes skills.</EmptyState>
      ) : <TokenTable tokens={tokens.data!} onRevoke={(t) => revoke.mutate(t)} showUser />}
      <Modal opened={creating} onClose={() => setCreating(false)} title="New service token" centered>
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack>
            <TextInput label="Name" placeholder="ci-publisher" data-autofocus {...form.getInputProps("name")} />
            <Select label="Registry" placeholder="Choose" data={(registries.data ?? []).map((r) => r.slug)} {...form.getInputProps("registry")} />
            <Select label="Role" allowDeselect={false} data={["reader", "publisher", "admin"]} {...form.getInputProps("role")} />
            <NumberInput label="Valid for (hours)" description="Empty = does not expire" min={1} {...form.getInputProps("ttl_hours")} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" loading={create.isPending}>Create token</Button></Group>
          </Stack>
        </form>
      </Modal>
      <SecretModal secret={secret} onClose={() => setSecret(null)} />
      <Text size="xs" c="dimmed">The server also accepts the environment bootstrap token (OWL_SERVER_ADMIN_TOKEN) - it is not listed here.</Text>
    </Stack>
  );
}
