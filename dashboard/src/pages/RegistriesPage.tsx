import { Anchor, Badge, Button, Group, Modal, Select, Stack, Table, Text, TextInput, Textarea, Title, Card, SimpleGrid } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconDownload, IconPlus, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, API, download, enc, reg as regApi } from "../api/client";
import { useAction, useRegistries, useRegistry, useStats, useUsers } from "../api/hooks";
import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { ConfirmModal } from "../components/ConfirmModal";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { canAdmin, shortDate } from "../lib";
import { useQuery } from "@tanstack/react-query";

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function RegistriesPage() {
  const { isAdmin, config } = useAuth();
  const registries = useRegistries();
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const form = useForm({
    initialValues: { slug: "", name: "", description: "", visibility: "private" as "public" | "private" },
    validate: { slug: (v) => (SLUG.test(v) && v.length <= 64 ? null : "Lower-case letters, digits and single hyphens") },
  });
  const create = useAction(
    (v: typeof form.values) => api(`${API}/registries`, { method: "POST", json: { ...v, name: v.name || v.slug } }),
    { invalidate: [["registries"]], success: "Registry created", onSuccess: () => { setCreating(false); navigate(`/registries/${form.values.slug}`); form.reset(); } },
  );
  const forced = config?.mode === "public" ? "public" : config?.mode === "private" ? "private" : null;

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Registries</Title>
        {isAdmin && <Button leftSection={<IconPlus size={16} aria-hidden />} onClick={() => { form.setFieldValue("visibility", forced ?? "private"); setCreating(true); }}>New registry</Button>}
      </Group>
      {registries.isLoading ? <LoadingBlock /> : registries.error ? <ErrorBlock error={registries.error} /> : (registries.data ?? []).length === 0 ? (
        <EmptyState title="No registries">{isAdmin ? "Create one to start publishing skills." : "You do not have access to any registry yet."}</EmptyState>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          {registries.data!.map((r) => (
            <Card key={r.slug} withBorder>
              <Group justify="space-between">
                <Anchor component={Link} to={`/registries/${r.slug}`} fw={600}>{r.name || r.slug}</Anchor>
                <Badge variant="light" color={r.visibility === "public" ? "teal" : "gray"}>{r.visibility}</Badge>
              </Group>
              <Text size="sm" c="dimmed" lineClamp={2} mt={4}>{r.description || "No description"}</Text>
              <Group justify="space-between" mt="sm">
                <Text size="sm">{r.skills} {r.skills === 1 ? "skill" : "skills"}</Text>
                <Anchor component={Link} to={`/r/${r.slug}/skills`} size="sm">Browse skills</Anchor>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}
      <Modal opened={creating} onClose={() => setCreating(false)} title="New registry" centered>
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack>
            <TextInput label="Slug" description="Used in URLs: /r/<slug>" required {...form.getInputProps("slug")} data-autofocus />
            <TextInput label="Name" {...form.getInputProps("name")} />
            <Textarea label="Description" autosize minRows={2} {...form.getInputProps("description")} />
            <Select label="Visibility" allowDeselect={false} data={[{ value: "private", label: "Private - members only" }, { value: "public", label: "Public - anyone can read" }]}
              disabled={forced !== null} description={forced ? `Fixed by the server mode (${forced})` : undefined} {...form.getInputProps("visibility")} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" loading={create.isPending}>Create</Button></Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}

interface Member { username: string; role: Role }

export function RegistryDetailPage() {
  const { slug = "" } = useParams();
  const { isAdmin, config } = useAuth();
  const navigate = useNavigate();
  const registry = useRegistry(slug);
  const stats = useStats(slug);
  const admin = canAdmin(registry.data);
  const members = useQuery({ queryKey: ["members", slug], queryFn: () => api<Member[]>(`${API}/registries/${enc(slug)}/members`), enabled: admin });
  const users = useUsers(admin && isAdmin);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [newUser, setNewUser] = useState("");
  const [newRole, setNewRole] = useState<Role>("reader");
  const forced = config?.mode === "public" ? "public" : config?.mode === "private" ? "private" : null;
  const form = useForm({ initialValues: { name: "", description: "", visibility: "private" as "public" | "private" } });

  const save = useAction((v: typeof form.values) => api(`${API}/registries/${enc(slug)}`, { method: "PATCH", json: isAdmin ? v : { name: v.name, description: v.description } }),
    { invalidate: [["registry", slug], ["registries"]], success: "Registry updated" });
  const setMember = useAction((v: { username: string; role: Role }) => api(`${API}/registries/${enc(slug)}/members/${enc(v.username)}`, { method: "PUT", json: { role: v.role } }),
    { invalidate: [["members", slug], ["users"]], success: "Member saved", onSuccess: () => setNewUser("") });
  const removeMember = useAction((username: string) => api(`${API}/registries/${enc(slug)}/members/${enc(username)}`, { method: "DELETE" }),
    { invalidate: [["members", slug], ["users"]], success: "Member removed" });
  const remove = useAction(() => api(`${API}/registries/${enc(slug)}?force=true`, { method: "DELETE" }),
    { invalidate: [["registries"]], success: "Registry deleted", onSuccess: () => navigate("/registries") });

  if (registry.isLoading) return <LoadingBlock rows={5} />;
  if (registry.error) return <ErrorBlock error={registry.error} title="Registry not found" />;
  const r = registry.data!;
  if (form.values.name === "" && form.values.description === "" && !form.isTouched()) form.setValues({ name: r.name, description: r.description, visibility: r.visibility });

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{r.name || r.slug}</Title>
        <Group>
          <Button component={Link} to={`/r/${slug}/skills`} variant="default">Browse skills</Button>
          <Button variant="default" leftSection={<IconDownload size={16} aria-hidden />} onClick={() => void download(`${regApi(slug)}/export`, `${slug}.zip`)}>Export as git registry</Button>
        </Group>
      </Group>
      <Group gap="xs"><Badge variant="light" color={r.visibility === "public" ? "teal" : "gray"}>{r.visibility}</Badge><Text size="sm" c="dimmed">created {shortDate(r.created_at)} - you are {r.role}</Text></Group>
      <Text size="sm">{stats.data ? `${stats.data.skills} skills, ${stats.data.versions} versions` : ""}</Text>
      <Text size="sm" c="dimmed">OWL CLI remote URL: <code>{window.location.origin}{slug === "default" ? "" : `/r/${slug}`}</code></Text>

      {admin && (
        <>
          <Title order={4} mt="md">Settings</Title>
          <form onSubmit={form.onSubmit((v) => save.mutate(v))}>
            <Stack maw={520}>
              <TextInput label="Name" {...form.getInputProps("name")} />
              <Textarea label="Description" autosize minRows={2} {...form.getInputProps("description")} />
              <Select label="Visibility" allowDeselect={false} disabled={!isAdmin || forced !== null}
                description={forced ? `Fixed by the server mode (${forced})` : !isAdmin ? "Only a server administrator can change this" : undefined}
                data={[{ value: "private", label: "Private" }, { value: "public", label: "Public" }]} {...form.getInputProps("visibility")} />
              <Group><Button type="submit" loading={save.isPending}>Save</Button>
                {isAdmin && slug !== "default" && <Button color="red" variant="light" leftSection={<IconTrash size={16} aria-hidden />} onClick={() => setConfirmDelete(true)}>Delete registry</Button>}</Group>
            </Stack>
          </form>

          <Title order={4} mt="md">Members</Title>
          <Text size="sm" c="dimmed">reader = read, publisher = also upload and delete skills, admin = also manage members.</Text>
          {members.isLoading ? <LoadingBlock rows={2} /> : members.error ? <ErrorBlock error={members.error} /> : (
            <Table maw={640} aria-label="Members">
              <Table.Thead><Table.Tr><Table.Th>User</Table.Th><Table.Th>Role</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(members.data ?? []).length === 0 && <Table.Tr><Table.Td colSpan={3}><Text c="dimmed" size="sm">No members yet.</Text></Table.Td></Table.Tr>}
                {members.data!.map((m) => (
                  <Table.Tr key={m.username}>
                    <Table.Td>{m.username}</Table.Td>
                    <Table.Td>
                      <Select aria-label={`Role of ${m.username}`} size="xs" w={140} allowDeselect={false} value={m.role} data={["reader", "publisher", "admin"]}
                        onChange={(v) => v && setMember.mutate({ username: m.username, role: v as Role })} />
                    </Table.Td>
                    <Table.Td><Button size="compact-sm" color="red" variant="subtle" onClick={() => removeMember.mutate(m.username)}>Remove</Button></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          <Group align="flex-end">
            {isAdmin ? (
              <Select label="Add user" placeholder="Choose a user" searchable value={newUser || null} onChange={(v) => setNewUser(v ?? "")} w={240}
                data={(users.data ?? []).filter((u) => !(members.data ?? []).some((m) => m.username === u.username)).map((u) => u.username)} />
            ) : (
              <TextInput label="Add user" placeholder="username" value={newUser} onChange={(e) => setNewUser(e.currentTarget.value)} w={240} />
            )}
            <Select label="Role" allowDeselect={false} value={newRole} onChange={(v) => v && setNewRole(v as Role)} data={["reader", "publisher", "admin"]} w={140} />
            <Button disabled={!newUser} loading={setMember.isPending} onClick={() => setMember.mutate({ username: newUser, role: newRole })}>Add</Button>
          </Group>
        </>
      )}
      <ConfirmModal opened={confirmDelete} onClose={() => setConfirmDelete(false)} onConfirm={() => remove.mutate(undefined)} loading={remove.isPending}
        title={`Delete ${r.slug}?`} confirmLabel="Delete registry and all skills">All skills, versions and memberships of this registry are removed. This cannot be undone.</ConfirmModal>
    </Stack>
  );
}
