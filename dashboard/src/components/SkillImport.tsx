import { Alert, Button, FileInput, Group, List, Modal, Stack, Tabs, Text, TextInput, Textarea } from "@mantine/core";
import { useState } from "react";
import { importSkill, importZip, useAction } from "../api/hooks";
import type { ImportReport } from "../api/types";
import { SKILL_TEMPLATE } from "../lib";

/** Create or upload skills. Parsing and validation happen on the server with OWL's own rules. */
export function SkillImportModal({ registry, opened, onClose, onDone }: { registry: string; opened: boolean; onClose: () => void; onDone?: (ref?: string) => void }) {
  const [text, setText] = useState(SKILL_TEMPLATE);
  const [author, setAuthor] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = [["skills", registry], ["facets", registry], ["stats", registry], ["activity", registry], ["registries"]];
  const fromText = useAction(() => importSkill(registry, { content: text, author: author || undefined }), {
    invalidate: refresh,
    success: (r) => `${r.outcome === "created" ? "Created" : r.outcome === "unchanged" ? "Already up to date:" : "New version of"} ${r.author}/${r.name}`,
    onSuccess: (r) => {
      setError(null);
      onDone?.(`${r.author}/${r.name}`);
      onClose();
    },
  });
  const fromFile = useAction(
    async () => {
      if (!file) throw new Error("Choose a file first");
      if (file.name.toLowerCase().endsWith(".zip")) return { zip: await importZip(registry, file, author) };
      const content = await file.text();
      return { single: await importSkill(registry, { content, author: author || undefined }) };
    },
    {
      invalidate: refresh,
      onSuccess: (r) => {
        setError(null);
        if ("zip" in r && r.zip) setReport(r.zip);
        else {
          onDone?.();
          onClose();
        }
      },
    },
  );

  return (
    <Modal opened={opened} onClose={onClose} title="Add a skill" size="xl" centered>
      <Tabs defaultValue="write">
        <Tabs.List>
          <Tabs.Tab value="write">Write SKILL.md</Tabs.Tab>
          <Tabs.Tab value="upload">Upload file or zip</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="write" pt="md">
          <Stack>
            <Textarea label="SKILL.md" description="Frontmatter needs name and description. Saving an existing name creates a new version."
              value={text} onChange={(e) => setText(e.currentTarget.value)} autosize minRows={12} maxRows={24}
              styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }} />
            <TextInput label="Author (optional)" description="Defaults to your username" value={author} onChange={(e) => setAuthor(e.currentTarget.value)} />
            {error && <Alert color="red">{error}</Alert>}
            <Group justify="flex-end">
              <Button variant="default" onClick={onClose}>Cancel</Button>
              <Button onClick={() => fromText.mutate(undefined)} loading={fromText.isPending}>Save skill</Button>
            </Group>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="upload" pt="md">
          <Stack>
            <FileInput label="SKILL.md or a .zip with skill folders" accept=".md,.markdown,.zip" value={file} onChange={setFile} clearable />
            <TextInput label="Author (optional)" value={author} onChange={(e) => setAuthor(e.currentTarget.value)} />
            {report && (
              <Alert color={report.invalid ? "yellow" : "teal"} title={`${report.imported} imported, ${report.invalid} with problems`}>
                <List size="sm" spacing={4}>
                  {report.results.map((r) => (
                    <List.Item key={r.path}>
                      <Text span fw={600}>{r.name}</Text>: {r.status}
                      {r.problems && <Text size="xs" c="red">{r.problems.join("; ")}</Text>}
                    </List.Item>
                  ))}
                </List>
              </Alert>
            )}
            <Group justify="flex-end">
              <Button variant="default" onClick={onClose}>{report ? "Close" : "Cancel"}</Button>
              {!report && <Button onClick={() => fromFile.mutate(undefined)} loading={fromFile.isPending} disabled={!file}>Upload</Button>}
            </Group>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Modal>
  );
}
