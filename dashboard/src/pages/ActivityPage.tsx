import { Anchor, Badge, Stack, Table, Title } from "@mantine/core";
import { Link, useParams } from "react-router-dom";
import { useActivity } from "../api/hooks";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { shortDate } from "../lib";

export function ActivityPage() {
  const { registry = "default" } = useParams();
  const activity = useActivity(registry, 100);
  return (
    <Stack>
      <Title order={2}>Activity</Title>
      {activity.isLoading ? <LoadingBlock rows={5} /> : activity.error ? <ErrorBlock error={activity.error} /> : (activity.data ?? []).length === 0 ? (
        <EmptyState title="Nothing has happened yet">New skill versions show up here.</EmptyState>
      ) : (
        <Table.ScrollContainer minWidth={560}>
          <Table aria-label="Recent versions">
            <Table.Thead><Table.Tr><Table.Th>When</Table.Th><Table.Th>Skill</Table.Th><Table.Th>Version</Table.Th><Table.Th>By</Table.Th><Table.Th>Hash</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {activity.data!.map((a) => (
                <Table.Tr key={a.sha256 + a.ref}>
                  <Table.Td>{shortDate(a.at)}</Table.Td>
                  <Table.Td><Anchor component={Link} to={`/r/${registry}/skills/${a.ref}`}>{a.ref}</Anchor></Table.Td>
                  <Table.Td><Badge variant={a.current ? "filled" : "outline"}>{a.version}</Badge></Table.Td>
                  <Table.Td>{a.by || "-"}</Table.Td>
                  <Table.Td><code>{a.sha256.slice(0, 10)}</code></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  );
}
