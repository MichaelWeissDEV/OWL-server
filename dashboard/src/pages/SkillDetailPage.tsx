import { Alert, Badge, Button, Code, Group, Menu, Modal, Select, Stack, Table, Tabs, Text, Textarea, Title } from "@mantine/core";
import { IconDownload, IconEdit, IconTrash } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, apiText, download, enc, reg } from "../api/client";
import { importSkill, useAction, useFiles, useRegistry, useSkill, useVersions } from "../api/hooks";
import type { Skill } from "../api/types";
import { ConfirmModal } from "../components/ConfirmModal";
import { DiffView } from "../components/DiffView";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { MarkdownView } from "../components/MarkdownView";
import { bytes, canWrite, shortDate } from "../lib";

function FilePreview({ registry, author, name, path, version }: { registry: string; author: string; name: string; path: string; version?: string }) {
  const text = useQuery({
    queryKey: ["file", registry, author, name, path, version],
    queryFn: () => apiText(`${reg(registry)}/skills/${enc(author)}/${enc(name)}/files/${path.split("/").map(enc).join("/")}${version ? `?version=${version}` : ""}`),
  });
  if (text.isLoading) return <LoadingBlock rows={2} />;
  if (text.error) return <ErrorBlock error={text.error} />;
  return <Code block data-testid="file-content" style={{ maxHeight: 420, overflow: "auto", whiteSpace: "pre-wrap" }}>{text.data}</Code>;
}

export function SkillDetailPage() {
  const { registry = "default", author = "", name = "" } = useParams();
  const navigate = useNavigate();
  const registryInfo = useRegistry(registry);
  const skill = useSkill(registry, author, name);
  const versions = useVersions(registry, author, name);
  const [fileVersion, setFileVersion] = useState<string | undefined>();
  const files = useFiles(registry, author, name, fileVersion);
  const [openFile, setOpenFile] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [cmpA, setCmpA] = useState<string | null>(null);
  const [cmpB, setCmpB] = useState<string | null>(null);

  const writable = canWrite(registryInfo.data);
  const refresh = [["skill", registry, author, name], ["versions", registry, author, name], ["files", registry, author, name], ["skills", registry], ["activity", registry], ["stats", registry]];

  const remove = useAction(() => api(`${reg(registry)}/skills/${enc(author)}/${enc(name)}`, { method: "DELETE" }), {
    invalidate: [["skills", registry], ["stats", registry], ["registries"]], success: "Skill deleted", onSuccess: () => navigate(`/r/${registry}/skills`),
  });
  const save = useAction(
    () => importSkill(registry, { content: draft, author, files: (skill.data as Skill).files }),
    { invalidate: refresh, success: (r) => (r.outcome === "unchanged" ? "No changes to save" : "Saved as a new version"), onSuccess: () => setEditing(false) },
  );
  const restore = useAction(
    async (sha: string) => {
      const old = await api<Skill>(`${reg(registry)}/skills/${enc(author)}/${enc(name)}?version=${sha}`);
      return api(`${reg(registry)}/skills/${enc(author)}/${enc(name)}`, { method: "PUT", json: old });
    },
    { invalidate: refresh, success: "Version restored as current" },
  );

  const versionData = useQuery({
    queryKey: ["compare", registry, author, name, cmpA, cmpB],
    enabled: !!cmpA && !!cmpB,
    queryFn: async () => {
      const get = (sha: string) => api<Skill>(`${reg(registry)}/skills/${enc(author)}/${enc(name)}?version=${sha}`);
      const [a, b] = await Promise.all([get(cmpA!), get(cmpB!)]);
      return { a, b };
    },
  });

  if (skill.isLoading) return <LoadingBlock rows={6} />;
  if (skill.error) return <ErrorBlock error={skill.error} title="Skill not found" />;
  const s = skill.data!;
  const versionOptions = (versions.data ?? []).map((v) => ({ value: v.sha256, label: `${v.version} - ${shortDate(v.created_at)}${v.current ? " (current)" : ""}` }));

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <Stack gap={4}>
          <Title order={2}>{s.author}/{s.name}</Title>
          <Group gap="xs">
            <Badge variant="outline">v{s.version}</Badge>
            {s.tags.map((t) => <Badge key={t} variant="light">{t}</Badge>)}
            {s.topics.map((t) => <Badge key={t} variant="light" color="teal">{t}</Badge>)}
          </Group>
          <Text c="dimmed">{s.description}</Text>
        </Stack>
        <Group>
          <Button variant="default" leftSection={<IconDownload size={16} aria-hidden />}
            onClick={() => void download(`${reg(registry)}/skills/${enc(author)}/${enc(name)}/download`, `${s.name}.zip`)}>Download</Button>
          {writable && (
            <Menu withinPortal position="bottom-end">
              <Menu.Target><Button leftSection={<IconEdit size={16} aria-hidden />}>Manage</Button></Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconEdit size={14} />} onClick={() => { setDraft(s.content); setEditing(true); }}>Edit SKILL.md (new version)</Menu.Item>
                <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => setConfirmDelete(true)}>Delete skill</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          )}
        </Group>
      </Group>

      <Tabs defaultValue="readme" keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="readme">SKILL.md</Tabs.Tab>
          <Tabs.Tab value="files">Files ({files.data?.length ?? "..."})</Tabs.Tab>
          <Tabs.Tab value="versions">Versions ({versions.data?.length ?? "..."})</Tabs.Tab>
          <Tabs.Tab value="compare">Compare</Tabs.Tab>
          <Tabs.Tab value="details">Details</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="readme" pt="md"><MarkdownView source={s.content} /></Tabs.Panel>

        <Tabs.Panel value="files" pt="md">
          {files.isLoading ? <LoadingBlock /> : files.error ? <ErrorBlock error={files.error} /> : (
            <Stack>
              {fileVersion && <Alert color="blue">Showing the files of an older version. <Button variant="subtle" size="compact-sm" onClick={() => setFileVersion(undefined)}>Back to current</Button></Alert>}
              <Table aria-label="Files">
                <Table.Thead><Table.Tr><Table.Th>Path</Table.Th><Table.Th>Size</Table.Th><Table.Th>SHA-256</Table.Th><Table.Th /></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {files.data!.map((f) => (
                    <Table.Tr key={f.path}>
                      <Table.Td><Code>{f.path}</Code></Table.Td>
                      <Table.Td>{bytes(f.size)}</Table.Td>
                      <Table.Td><Text size="xs" c="dimmed" ff="monospace">{f.sha256.slice(0, 12)}</Text></Table.Td>
                      <Table.Td>
                        {f.text ? <Button size="compact-sm" variant="light" onClick={() => setOpenFile(openFile === f.path ? null : f.path)}>{openFile === f.path ? "Hide" : "View"}</Button>
                          : <Text size="xs" c="dimmed">binary</Text>}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {openFile && <FilePreview registry={registry} author={author} name={name} path={openFile} version={fileVersion} />}
            </Stack>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="versions" pt="md">
          {versions.isLoading ? <LoadingBlock /> : versions.error ? <ErrorBlock error={versions.error} /> : (
            <Table aria-label="Versions">
              <Table.Thead><Table.Tr><Table.Th>Version</Table.Th><Table.Th>Published</Table.Th><Table.Th>By</Table.Th><Table.Th>Hash</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {versions.data!.map((v) => (
                  <Table.Tr key={v.sha256}>
                    <Table.Td><Badge variant={v.current ? "filled" : "outline"}>{v.version}{v.current ? " - current" : ""}</Badge></Table.Td>
                    <Table.Td>{shortDate(v.created_at)}</Table.Td>
                    <Table.Td>{v.created_by || "-"}</Table.Td>
                    <Table.Td><Text size="xs" ff="monospace">{v.sha256.slice(0, 12)}</Text></Table.Td>
                    <Table.Td>
                      <Group gap="xs" justify="flex-end">
                        <Button size="compact-sm" variant="light" onClick={() => setFileVersion(v.sha256)}>Files</Button>
                        {writable && !v.current && <Button size="compact-sm" variant="light" loading={restore.isPending} onClick={() => restore.mutate(v.sha256)}>Make current</Button>}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="compare" pt="md">
          {(versions.data?.length ?? 0) < 2 ? <EmptyState title="Only one version">Publish a change to compare versions.</EmptyState> : (
            <Stack>
              <Group>
                <Select label="From" data={versionOptions} value={cmpA ?? versionOptions[1]?.value ?? null} onChange={setCmpA} allowDeselect={false} w={280} />
                <Select label="To" data={versionOptions} value={cmpB ?? versionOptions[0]?.value ?? null} onChange={setCmpB} allowDeselect={false} w={280} />
                <Button mt={24} variant="light" onClick={() => { setCmpA(cmpA ?? versionOptions[1]?.value ?? null); setCmpB(cmpB ?? versionOptions[0]?.value ?? null); }}>Compare</Button>
              </Group>
              {versionData.isLoading && <LoadingBlock rows={2} />}
              {versionData.error && <ErrorBlock error={versionData.error} />}
              {versionData.data && <DiffView before={versionData.data.a.content} after={versionData.data.b.content} labels={[`v${versionData.data.a.version}`, `v${versionData.data.b.version}`]} />}
            </Stack>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="details" pt="md">
          <Table aria-label="Details"><Table.Tbody>
            <Table.Tr><Table.Th w={160}>Author</Table.Th><Table.Td>{s.author}</Table.Td></Table.Tr>
            <Table.Tr><Table.Th>Version</Table.Th><Table.Td>{s.version}</Table.Td></Table.Tr>
            <Table.Tr><Table.Th>Registry</Table.Th><Table.Td>{registry}</Table.Td></Table.Tr>
            <Table.Tr><Table.Th>SHA-256</Table.Th><Table.Td><Code>{s.sha256}</Code></Table.Td></Table.Tr>
            <Table.Tr><Table.Th>Created</Table.Th><Table.Td>{shortDate(s.created_at)}</Table.Td></Table.Tr>
            <Table.Tr><Table.Th>Updated</Table.Th><Table.Td>{shortDate(s.updated_at)}</Table.Td></Table.Tr>
            {Object.entries(s.extra).map(([k, v]) => <Table.Tr key={k}><Table.Th>{k}</Table.Th><Table.Td>{String(v)}</Table.Td></Table.Tr>)}
          </Table.Tbody></Table>
          <Text size="xs" c="dimmed" mt="sm">Install with the OWL CLI: <Code>owl install {s.author}/{s.name} -r &lt;remote&gt;</Code></Text>
        </Tabs.Panel>
      </Tabs>

      <ConfirmModal opened={confirmDelete} onClose={() => setConfirmDelete(false)} onConfirm={() => remove.mutate(undefined)} loading={remove.isPending}
        title="Delete this skill?" confirmLabel="Delete skill and all versions">
        {s.author}/{s.name} and all of its versions will be removed from this registry. This cannot be undone.
      </ConfirmModal>
      <Modal opened={editing} onClose={() => setEditing(false)} title={`Edit ${s.name}`} size="xl" centered>
        <Stack>
          <Textarea label="SKILL.md" description="Saving creates a new immutable version; bundled files are kept." value={draft}
            onChange={(e) => setDraft(e.currentTarget.value)} autosize minRows={14} maxRows={26} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }} />
          <Group justify="flex-end"><Button variant="default" onClick={() => setEditing(false)}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate(undefined)}>Save new version</Button></Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
