import { Alert, Badge, Button, Checkbox, Group, Modal, PasswordInput, Select, Stack, Switch, Table, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconPlus } from "@tabler/icons-react";
import { useState } from "react";
import { api, API, enc } from "../api/client";
import { useAction, useRegistries, useUsers } from "../api/hooks";
import type { Role, UserInfo } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { ConfirmModal } from "../components/ConfirmModal";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { shortDate } from "../lib";

const PROVIDER_COLOR: Record<string, string> = { local: "gray", oidc: "blue", oauth: "indigo", ldap: "grape", proxy: "cyan" };

function EditUser({ user, onClose }: { user: UserInfo; onClose: () => void }) {
  const { me, config } = useAuth();
  const registries = useRegistries();
  const [password, setPassword] = useState("");
  const [slug, setSlug] = useState<string | null>(null);
  const [role, setRole] = useState<Role>("reader");
  const self = me?.username === user.username;
  const patch = useAction((body: Record<string, unknown>) => api(`${API}/admin/users/${enc(user.username)}`, { method: "PATCH", json: body }),
    { invalidate: [["users"]], success: "Saved" });
  const setMember = useAction((v: { registry: string; role: Role | null }) =>
    v.role ? api(`${API}/registries/${enc(v.registry)}/members/${enc(user.username)}`, { method: "PUT", json: { role: v.role } })
      : api(`${API}/registries/${enc(v.registry)}/members/${enc(user.username)}`, { method: "DELETE" }),
  { invalidate: [["users"], ["members"]], success: "Membership saved", onSuccess: () => setSlug(null) });
  const external = user.provider !== "local";
  return (
    <Modal opened onClose={onClose} title={`Edit ${user.username}`} size="lg" centered>
      <Stack>
        <Group gap="xs"><Badge color={PROVIDER_COLOR[user.provider] ?? "gray"} variant="light">{user.provider}</Badge>{user.email && <Text size="sm" c="dimmed">{user.email}</Text>}</Group>
        <Switch label="Active" description="Disabled users cannot sign in and their sessions end immediately" checked={user.active} disabled={self}
          onChange={(e) => patch.mutate({ active: e.currentTarget.checked })} />
        <Switch label="Server administrator" description={external ? "Managed by the identity provider if admin groups are configured there" : "Can manage registries, users, tokens and settings"}
          checked={user.is_admin} disabled={self} onChange={(e) => patch.mutate({ is_admin: e.currentTarget.checked })} />
        {!external && (
          <Group align="flex-end">
            <PasswordInput label="Reset password" description="At least 12 characters; ends all sessions of the user" value={password} onChange={(e) => setPassword(e.currentTarget.value)} style={{ flex: 1 }} autoComplete="new-password" />
            <Button disabled={password.length < 12} loading={patch.isPending} onClick={() => patch.mutate({ password }, { onSuccess: () => setPassword("") })}>Set</Button>
          </Group>
        )}
        <Title order={5}>Registry access</Title>
        {user.memberships.length === 0 ? <Text size="sm" c="dimmed">No registry memberships.{user.is_admin ? " Administrators can access everything." : ""}</Text> : (
          <Table aria-label="Memberships"><Table.Tbody>
            {user.memberships.map((m) => (
              <Table.Tr key={m.registry}><Table.Td>{m.registry}</Table.Td>
                <Table.Td><Select size="xs" w={130} allowDeselect={false} aria-label={`Role in ${m.registry}`} value={m.role} data={["reader", "publisher", "admin"]} onChange={(v) => v && setMember.mutate({ registry: m.registry, role: v as Role })} /></Table.Td>
                <Table.Td><Button size="compact-sm" variant="subtle" color="red" onClick={() => setMember.mutate({ registry: m.registry, role: null })}>Remove</Button></Table.Td></Table.Tr>
            ))}
          </Table.Tbody></Table>
        )}
        <Group align="flex-end">
          <Select label="Add to registry" placeholder="Registry" value={slug} onChange={setSlug} data={(registries.data ?? []).filter((r) => !user.memberships.some((m) => m.registry === r.slug)).map((r) => r.slug)} w={200} />
          <Select label="Role" allowDeselect={false} value={role} onChange={(v) => v && setRole(v as Role)} data={["reader", "publisher", "admin"]} w={130} />
          <Button disabled={!slug} onClick={() => slug && setMember.mutate({ registry: slug, role })}>Add</Button>
        </Group>
        {config && external && <Alert color="blue" variant="light">Memberships of registries named in the identity provider's group mapping are re-synchronised at every login.</Alert>}
      </Stack>
    </Modal>
  );
}

export function UsersPage() {
  const { config, me } = useAuth();
  const users = useUsers();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const form = useForm({
    initialValues: { username: "", password: "", is_admin: false },
    validate: {
      username: (v) => (/^[A-Za-z0-9._@-]{2,100}$/.test(v) ? null : "2-100 characters: letters, digits and . _ - @"),
      password: (v) => (v.length >= 12 ? null : "At least 12 characters"),
    },
  });
  const create = useAction((v: typeof form.values) => api(`${API}/admin/users`, { method: "POST", json: v }),
    { invalidate: [["users"]], success: "User created", onSuccess: () => { setCreating(false); form.reset(); } });
  const remove = useAction((u: string) => api(`${API}/admin/users/${enc(u)}`, { method: "DELETE" }),
    { invalidate: [["users"]], success: "User deleted", onSuccess: () => setDeleting(null) });
  const editUser = (users.data ?? []).find((u) => u.username === editing);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Users</Title>
        {config?.local_accounts && <Button leftSection={<IconPlus size={16} aria-hidden />} onClick={() => setCreating(true)}>New user</Button>}
      </Group>
      <Text size="sm" c="dimmed">Accounts are created here (local, password hashed with Argon2id) or appear on first sign-in through an identity provider.</Text>
      {users.isLoading ? <LoadingBlock rows={4} /> : users.error ? <ErrorBlock error={users.error} /> : (users.data ?? []).length === 0 ? (
        <EmptyState title="No users yet">{config?.open ? "The server is open - nobody needs an account. Create users, then secure the server in Settings." : "Create the first user."}</EmptyState>
      ) : (
        <Table.ScrollContainer minWidth={700}>
          <Table highlightOnHover aria-label="Users">
            <Table.Thead><Table.Tr><Table.Th>User</Table.Th><Table.Th>Source</Table.Th><Table.Th>Role</Table.Th><Table.Th>Registries</Table.Th><Table.Th>Last sign-in</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {users.data!.map((u) => (
                <Table.Tr key={u.username} style={{ opacity: u.active ? 1 : 0.55 }}>
                  <Table.Td><Text fw={600}>{u.username}</Text>{u.email && <Text size="xs" c="dimmed">{u.email}</Text>}</Table.Td>
                  <Table.Td><Badge variant="light" color={PROVIDER_COLOR[u.provider] ?? "gray"}>{u.provider}</Badge></Table.Td>
                  <Table.Td>{u.is_admin ? <Badge>admin</Badge> : <Text size="sm" c="dimmed">user</Text>}{!u.active && <Badge color="red" variant="light" ml={6}>disabled</Badge>}</Table.Td>
                  <Table.Td><Text size="sm">{u.memberships.map((m) => `${m.registry}: ${m.role}`).join(", ") || "-"}</Text></Table.Td>
                  <Table.Td>{shortDate(u.last_login)}</Table.Td>
                  <Table.Td><Group gap="xs" justify="flex-end">
                    <Button size="compact-sm" variant="light" onClick={() => setEditing(u.username)}>Edit</Button>
                    <Button size="compact-sm" variant="subtle" color="red" disabled={u.username === me?.username} onClick={() => setDeleting(u.username)}>Delete</Button>
                  </Group></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Modal opened={creating} onClose={() => setCreating(false)} title="New user" centered>
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack>
            <TextInput label="Username" data-autofocus autoComplete="off" {...form.getInputProps("username")} />
            <PasswordInput label="Initial password" description="The user can change it in their profile" autoComplete="new-password" {...form.getInputProps("password")} />
            <Checkbox label="Server administrator" {...form.getInputProps("is_admin", { type: "checkbox" })} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" loading={create.isPending}>Create user</Button></Group>
          </Stack>
        </form>
      </Modal>
      {editUser && <EditUser user={editUser} onClose={() => setEditing(null)} />}
      <ConfirmModal opened={deleting !== null} onClose={() => setDeleting(null)} onConfirm={() => deleting && remove.mutate(deleting)} loading={remove.isPending} title="Delete user?" confirmLabel="Delete user">
        {deleting} loses access, their tokens and memberships are removed. Skills they published stay. To keep the account but block it, disable it instead.
      </ConfirmModal>
    </Stack>
  );
}
