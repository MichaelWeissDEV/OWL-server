import { Anchor, Badge, Button, Group, MultiSelect, Pagination, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { IconPlus, IconSearch } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useFacets, useRegistry, useSkills } from "../api/hooks";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { SkillImportModal } from "../components/SkillImport";
import { canWrite, shortDate } from "../lib";

const PAGE = 25;

export function SkillsPage() {
  const { registry = "default" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const reg = useRegistry(registry);
  const [adding, setAdding] = useState(false);
  const q = params.get("q") ?? "";
  const author = params.get("author") ?? "";
  const tags = params.getAll("tag");
  const page = Math.max(1, Number(params.get("page") ?? 1));
  const [text, setText] = useState(q);
  // Keep the box in sync with the URL (back/forward) without overwriting what the user is typing.
  const submitted = useRef(q);
  useEffect(() => {
    if (q !== submitted.current) {
      submitted.current = q;
      setText(q);
    }
  }, [q]);

  const skills = useSkills(registry, { q, author: author || undefined, tags, limit: PAGE + 1, offset: (page - 1) * PAGE });
  const authors = useFacets(registry, "author");
  const tagFacets = useFacets(registry, "tag");

  const update = (changes: Record<string, string | string[] | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      next.delete(k);
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
      else if (v) next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  };

  const rows = (skills.data ?? []).slice(0, PAGE);
  const hasMore = (skills.data?.length ?? 0) > PAGE;
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Skills{reg.data ? ` - ${reg.data.name || reg.data.slug}` : ""}</Title>
        {canWrite(reg.data) && <Button leftSection={<IconPlus size={16} aria-hidden />} onClick={() => setAdding(true)}>Add skill</Button>}
      </Group>
      <form role="search" onSubmit={(e) => { e.preventDefault(); submitted.current = text.trim(); update({ q: text.trim() || null }); }}>
        <Group align="flex-end" wrap="wrap">
          <TextInput label="Search" placeholder="name, description, tags, text..." leftSection={<IconSearch size={16} aria-hidden />}
            value={text} onChange={(e) => setText(e.currentTarget.value)} style={{ flex: 1, minWidth: 220 }} />
          <Select label="Author" placeholder="Any" clearable searchable value={author || null}
            data={(authors.data ?? []).map((f) => ({ value: f.value, label: `${f.value} (${f.count})` }))}
            onChange={(v) => update({ author: v })} w={190} />
          <MultiSelect label="Tags" placeholder={tags.length ? undefined : "Any"} searchable clearable value={tags}
            data={(tagFacets.data ?? []).map((f) => ({ value: f.value, label: `${f.value} (${f.count})` }))}
            onChange={(v) => update({ tag: v })} w={260} />
          <Button type="submit" variant="light">Search</Button>
        </Group>
      </form>

      {skills.isLoading ? <LoadingBlock rows={6} /> : skills.error ? <ErrorBlock error={skills.error} /> : rows.length === 0 ? (
        <EmptyState title={q || author || tags.length ? "No skills match" : "No skills yet"}
          action={canWrite(reg.data) && !q ? <Button onClick={() => setAdding(true)}>Add the first skill</Button> : undefined}>
          {q || author || tags.length ? "Try other words or clear the filters." : "Skills you publish with the OWL CLI or add here will appear in this list."}
        </EmptyState>
      ) : (
        <>
          <Table.ScrollContainer minWidth={640}>
            <Table highlightOnHover verticalSpacing="sm" aria-label="Skills">
              <Table.Thead>
                <Table.Tr><Table.Th>Skill</Table.Th><Table.Th>Version</Table.Th><Table.Th>Description</Table.Th><Table.Th>Tags</Table.Th><Table.Th>Updated</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((s) => (
                  <Table.Tr key={`${s.author}/${s.name}`} onDoubleClick={() => navigate(`/r/${registry}/skills/${s.author}/${s.name}`)}>
                    <Table.Td><Anchor component={Link} to={`/r/${registry}/skills/${s.author}/${s.name}`} fw={600}>{s.author}/{s.name}</Anchor></Table.Td>
                    <Table.Td><Badge variant="outline">{s.version}</Badge></Table.Td>
                    <Table.Td><Text size="sm" lineClamp={2} maw={420}>{s.description}</Text></Table.Td>
                    <Table.Td><Group gap={4}>{s.tags.slice(0, 4).map((t) => <Badge key={t} size="sm" variant="light">{t}</Badge>)}</Group></Table.Td>
                    <Table.Td><Text size="sm" c="dimmed">{shortDate(s.updated_at)}</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {(page > 1 || hasMore) && (
            <Group justify="center">
              <Pagination total={hasMore ? page + 1 : page} value={page} onChange={(p) => update({ page: String(p) })} aria-label="Pages" />
            </Group>
          )}
        </>
      )}
      <SkillImportModal registry={registry} opened={adding} onClose={() => setAdding(false)} onDone={(ref) => ref && navigate(`/r/${registry}/skills/${ref}`)} />
    </Stack>
  );
}
