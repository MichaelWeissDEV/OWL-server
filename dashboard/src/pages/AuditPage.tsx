import { Group, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { useAudit } from "../api/hooks";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { shortDate } from "../lib";

const FILTERS = [
  { value: "", label: "Everything" }, { value: "auth.", label: "Sign-ins" }, { value: "skill.", label: "Skills" },
  { value: "user.", label: "Users" }, { value: "token.", label: "Tokens" }, { value: "registry.", label: "Registries" }, { value: "server.", label: "Server" },
];

export function AuditPage() {
  const [action, setAction] = useState("");
  const [limit, setLimit] = useState("100");
  const audit = useAudit(action, Number(limit));
  return (
    <Stack>
      <Title order={2}>Audit log</Title>
      <Text size="sm" c="dimmed">Who did what and when. Passwords, tokens and request headers are never recorded.</Text>
      <Group>
        <Select label="Show" allowDeselect={false} data={FILTERS} value={action} onChange={(v) => setAction(v ?? "")} w={200} />
        <Select label="Entries" allowDeselect={false} data={["50", "100", "250", "500"]} value={limit} onChange={(v) => setLimit(v ?? "100")} w={110} />
      </Group>
      {audit.isLoading ? <LoadingBlock rows={6} /> : audit.error ? <ErrorBlock error={audit.error} /> : (audit.data ?? []).length === 0 ? <EmptyState title="No events" /> : (
        <Table.ScrollContainer minWidth={720}>
          <Table aria-label="Audit events" verticalSpacing={4}>
            <Table.Thead><Table.Tr><Table.Th>Time</Table.Th><Table.Th>Actor</Table.Th><Table.Th>Action</Table.Th><Table.Th>Target</Table.Th><Table.Th>Detail</Table.Th><Table.Th>IP</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {audit.data!.map((e) => (
                <Table.Tr key={e.id}>
                  <Table.Td>{shortDate(e.at)}</Table.Td><Table.Td>{e.actor}</Table.Td><Table.Td><code>{e.action}</code></Table.Td>
                  <Table.Td>{e.target}</Table.Td><Table.Td><Text size="xs" c="dimmed" lineClamp={2}>{e.detail}</Text></Table.Td><Table.Td>{e.ip}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  );
}
