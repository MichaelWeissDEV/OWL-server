import { Anchor, Button, Group, Modal, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconPlus } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, enc, reg } from "../api/client";
import { useAction, useCollections, useRegistry, useSkills } from "../api/hooks";
import { ConfirmModal } from "../components/ConfirmModal";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { canWrite } from "../lib";

function Members({ registry, name, writable }: { registry: string; name: string; writable: boolean }) {
  const members = useQuery({ queryKey: ["collection", registry, name], queryFn: () => api<{ skills: string[] }>(`${reg(registry)}/collections/${enc(name)}`) });
  const skills = useSkills(registry, { limit: 200 });
  const [pick, setPick] = useState<string | null>(null);
  const refresh = [["collection", registry, name], ["collections", registry]];
  const add = useAction((ref: string) => api(`${reg(registry)}/collections/${enc(name)}/skills/${ref.split("/").map(enc).join("/")}`, { method: "PUT" }), { invalidate: refresh, success: "Added", onSuccess: () => setPick(null) });
  const remove = useAction((ref: string) => api(`${reg(registry)}/collections/${enc(name)}/skills/${ref.split("/").map(enc).join("/")}`, { method: "DELETE" }), { invalidate: refresh, success: "Removed" });
  if (members.isLoading) return <LoadingBlock rows={2} />;
  if (members.error) return <ErrorBlock error={members.error} />;
  const list = members.data!.skills;
  return (
    <Stack>
      {list.length === 0 ? <Text c="dimmed" size="sm">This collection is empty.</Text> : (
        <Table aria-label={`Skills in ${name}`}><Table.Tbody>
          {list.map((ref) => (
            <Table.Tr key={ref}>
              <Table.Td><Anchor component={Link} to={`/r/${registry}/skills/${ref}`}>{ref}</Anchor></Table.Td>
              <Table.Td>{writable && <Button size="compact-sm" color="red" variant="subtle" onClick={() => remove.mutate(ref)}>Remove</Button>}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody></Table>
      )}
      {writable && (
        <Group align="flex-end">
          <Select label="Add a skill" searchable placeholder="Search skills" value={pick} onChange={setPick} w={320}
            data={(skills.data ?? []).map((s) => `${s.author}/${s.name}`).filter((r) => !list.includes(r))} />
          <Button disabled={!pick} onClick={() => pick && add.mutate(pick)} loading={add.isPending}>Add</Button>
        </Group>
      )}
    </Stack>
  );
}

export function CollectionsPage() {
  const { registry = "default" } = useParams();
  const reg_ = useRegistry(registry);
  const collections = useCollections(registry);
  const writable = canWrite(reg_.data);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [del, setDel] = useState<string | null>(null);
  const form = useForm({ initialValues: { name: "", description: "" }, validate: { name: (v) => (v.trim() && !v.includes("/") ? null : "Enter a name without '/'") } });
  const create = useAction((v: typeof form.values) => api(`${reg(registry)}/collections`, { method: "POST", json: v }), {
    invalidate: [["collections", registry]], success: "Collection created", onSuccess: () => { setCreating(false); form.reset(); },
  });
  const remove = useAction((name: string) => api(`${reg(registry)}/collections/${enc(name)}`, { method: "DELETE" }), {
    invalidate: [["collections", registry]], success: "Collection deleted", onSuccess: () => { setDel(null); setOpen(null); },
  });
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Collections</Title>
        {writable && <Button leftSection={<IconPlus size={16} aria-hidden />} onClick={() => setCreating(true)}>New collection</Button>}
      </Group>
      <Text size="sm" c="dimmed">Group skills that belong together, for example everything for security reviews.</Text>
      {collections.isLoading ? <LoadingBlock /> : collections.error ? <ErrorBlock error={collections.error} /> : (collections.data ?? []).length === 0 ? (
        <EmptyState title="No collections yet">{writable ? "Create a collection and add skills to it." : "Nobody has created a collection here."}</EmptyState>
      ) : (
        <Table highlightOnHover aria-label="Collections">
          <Table.Thead><Table.Tr><Table.Th>Name</Table.Th><Table.Th>Skills</Table.Th><Table.Th>Description</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {collections.data!.map((c) => (
              <Table.Tr key={c.name}>
                <Table.Td><Anchor component="button" type="button" onClick={() => setOpen(open === c.name ? null : c.name)} fw={600} aria-expanded={open === c.name}>{c.name}</Anchor></Table.Td>
                <Table.Td>{c.skills}</Table.Td><Table.Td>{c.description}</Table.Td>
                <Table.Td>{writable && <Button size="compact-sm" color="red" variant="subtle" onClick={() => setDel(c.name)}>Delete</Button>}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {open && <Stack><Title order={4}>{open}</Title><Members registry={registry} name={open} writable={writable} /></Stack>}
      <Modal opened={creating} onClose={() => setCreating(false)} title="New collection" centered>
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack><TextInput label="Name" data-autofocus {...form.getInputProps("name")} /><TextInput label="Description" {...form.getInputProps("description")} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" loading={create.isPending}>Create</Button></Group></Stack>
        </form>
      </Modal>
      <ConfirmModal opened={del !== null} onClose={() => setDel(null)} onConfirm={() => del && remove.mutate(del)} loading={remove.isPending} title="Delete collection?" confirmLabel="Delete">
        The collection {del} is removed. The skills in it are not touched.
      </ConfirmModal>
    </Stack>
  );
}
