import { Alert, Badge, Button, Card, Code, Group, PasswordInput, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconCheck, IconShieldLock, IconX } from "@tabler/icons-react";
import { useState } from "react";
import { api, API } from "../api/client";
import { useAction, useServerInfo } from "../api/hooks";
import { useAuth } from "../auth/AuthProvider";
import { ConfirmModal } from "../components/ConfirmModal";
import { ErrorBlock, LoadingBlock } from "../components/Feedback";

const PROVIDERS: { key: string; label: string; help: string }[] = [
  { key: "local_accounts", label: "Local accounts", help: "Users managed in this dashboard (Argon2id passwords). OWL_SERVER_LOCAL_ACCOUNTS" },
  { key: "oidc", label: "OpenID Connect", help: "Keycloak, Authentik, Microsoft Entra ID, Okta, Google, ... OWL_SERVER_OIDC_*" },
  { key: "oauth", label: "OAuth 2.0", help: "GitHub or any OAuth 2.0 provider with a user-info endpoint. OWL_SERVER_OAUTH_*" },
  { key: "ldap", label: "LDAP / Active Directory", help: "Password login checked against your directory. OWL_SERVER_LDAP_*" },
  { key: "proxy", label: "Proxy authentication", help: "Kerberos/SPNEGO, SAML, oauth2-proxy, Authelia behind a reverse proxy. OWL_SERVER_PROXY_*" },
  { key: "admin_token", label: "Bootstrap admin token", help: "A fixed token for setup and emergencies. OWL_SERVER_ADMIN_TOKEN" },
];

function SecureCard({ open, reason }: { open: boolean; reason: string }) {
  const { acceptToken, config } = useAuth();
  const [reopen, setReopen] = useState(false);
  const form = useForm({
    initialValues: { username: "", password: "", confirm: "" },
    validate: {
      username: (v) => (/^[A-Za-z0-9._@-]{2,100}$/.test(v) ? null : "2-100 characters: letters, digits and . _ - @"),
      password: (v) => (v.length >= 12 ? null : "At least 12 characters"),
      confirm: (v, values) => (v === values.password ? null : "The passwords do not match"),
    },
  });
  const secure = useAction((v: { username: string; password: string }) => api<{ token: string }>(`${API}/setup/secure`, { method: "POST", json: v }),
    { success: "The server is now secured. You are signed in as the new administrator.", onSuccess: (r) => void acceptToken(r.token) });
  const toggle = useAction((v: { open: boolean; confirm?: boolean }) => api(`${API}/admin/security`, { method: "PUT", json: v }),
    { invalidate: [["server"]], success: "Saved", onSuccess: () => { setReopen(false); window.location.reload(); } });
  return (
    <Card withBorder>
      <Group justify="space-between" mb="xs">
        <Group gap="xs"><IconShieldLock aria-hidden /><Title order={4}>Access control</Title></Group>
        <Badge size="lg" color={open ? "yellow" : "teal"} variant="light">{open ? "Open - no login" : "Secured"}</Badge>
      </Group>
      <Text size="sm" c="dimmed" mb="sm">{reason}</Text>
      {open ? (
        <Stack>
          <Alert color="yellow" title="Everyone is an administrator right now">
            That is fine for localhost or a trusted network. To require sign-in, create the first administrator account.
          </Alert>
          {config?.local_accounts ? (
            <form onSubmit={form.onSubmit((v) => secure.mutate({ username: v.username, password: v.password }))}>
              <Stack maw={420}>
                <TextInput label="Administrator username" autoComplete="username" {...form.getInputProps("username")} />
                <PasswordInput label="Password" autoComplete="new-password" {...form.getInputProps("password")} />
                <PasswordInput label="Repeat password" autoComplete="new-password" {...form.getInputProps("confirm")} />
                <Button type="submit" loading={secure.isPending}>Secure this server</Button>
              </Stack>
            </form>
          ) : <Text size="sm">Local accounts are disabled. Configure an identity provider and set <Code>OWL_SERVER_OPEN=false</Code>.</Text>}
        </Stack>
      ) : (
        <Stack>
          <Text size="sm">Every request needs authentication. Public registries stay readable by anyone if the server mode allows it.</Text>
          <Group><Button color="red" variant="light" onClick={() => setReopen(true)}>Switch back to open mode...</Button></Group>
        </Stack>
      )}
      <ConfirmModal opened={reopen} onClose={() => setReopen(false)} loading={toggle.isPending} title="Remove all access control?" confirmLabel="Yes, open the server"
        onConfirm={() => toggle.mutate({ open: true, confirm: true })}>
        Anyone who can reach this server will be able to read, change and delete everything. Only do this on a closed network.
      </ConfirmModal>
    </Card>
  );
}

export function SettingsPage() {
  const info = useServerInfo();
  if (info.isLoading) return <LoadingBlock rows={6} />;
  if (info.error) return <ErrorBlock error={info.error} />;
  const s = info.data!;
  return (
    <Stack>
      <Title order={2}>Settings</Title>
      <SecureCard open={s.open} reason={s.open_reason} />

      <Title order={4} mt="md">Sign-in methods</Title>
      <Text size="sm" c="dimmed">Identity providers are configured through environment variables (secrets never pass through the browser). Restart the server after changing them.</Text>
      <Table aria-label="Sign-in methods">
        <Table.Thead><Table.Tr><Table.Th>Method</Table.Th><Table.Th>Status</Table.Th><Table.Th>How to configure</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {PROVIDERS.map((p) => (
            <Table.Tr key={p.key}>
              <Table.Td>{p.label}</Table.Td>
              <Table.Td>{s.providers[p.key] ? <Badge color="teal" leftSection={<IconCheck size={12} aria-hidden />}>enabled</Badge> : <Badge color="gray" variant="light" leftSection={<IconX size={12} aria-hidden />}>off</Badge>}</Table.Td>
              <Table.Td><Text size="sm" c="dimmed">{p.help}</Text></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {(s.oidc_issuer || s.ldap_url) && <Text size="sm">{s.oidc_issuer && <>OIDC issuer: <Code>{s.oidc_issuer}</Code> </>}{s.ldap_url && <>Directory: <Code>{s.ldap_url}</Code></>}</Text>}

      <Title order={4} mt="md">Server</Title>
      <Table aria-label="Server information"><Table.Tbody>
        <Table.Tr><Table.Th w={220}>Version</Table.Th><Table.Td>{s.version}</Table.Td></Table.Tr>
        <Table.Tr><Table.Th>Mode</Table.Th><Table.Td>{s.mode}</Table.Td></Table.Tr>
        <Table.Tr><Table.Th>Default registry</Table.Th><Table.Td>{s.default_registry}</Table.Td></Table.Tr>
        <Table.Tr><Table.Th>Database schema</Table.Th><Table.Td>{s.schema_revision ?? "-"}</Table.Td></Table.Tr>
        <Table.Tr><Table.Th>Session lifetime</Table.Th><Table.Td>{s.session_ttl_hours} h</Table.Td></Table.Tr>
        <Table.Tr><Table.Th>Upload limit</Table.Th><Table.Td>{s.max_body_mb} MiB</Table.Td></Table.Tr>
        {Object.entries(s.counts).map(([k, v]) => <Table.Tr key={k}><Table.Th>{k}</Table.Th><Table.Td>{v}</Table.Td></Table.Tr>)}
      </Table.Tbody></Table>
    </Stack>
  );
}
