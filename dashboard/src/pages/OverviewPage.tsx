import { Anchor, Badge, Card, Group, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";
import { useActivity, useRegistries, useStats } from "../api/hooks";
import { EmptyState, ErrorBlock, LoadingBlock } from "../components/Feedback";
import { shortDate } from "../lib";
import { useCurrentRegistry } from "../registry";
import { useAuth } from "../auth/AuthProvider";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Card withBorder padding="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{label}</Text>
      <Text fz={28} fw={700}>{value}</Text>
    </Card>
  );
}

export function OverviewPage() {
  const { config, signedIn } = useAuth();
  const registries = useRegistries();
  const { slug } = useCurrentRegistry();
  const stats = useStats(slug ?? "");
  const activity = useActivity(slug ?? "", 6);

  if (registries.isLoading) return <LoadingBlock rows={4} />;
  if (registries.error) return <ErrorBlock error={registries.error} />;
  const list = registries.data ?? [];
  if (list.length === 0) {
    return (
      <EmptyState title="No registries to show" action={!signedIn && !config?.open ? <Anchor component={Link} to="/login">Sign in</Anchor> : undefined}>
        {config?.open || signedIn ? "Create the first registry on the Registries page." : "Private registries are only visible after you sign in."}
      </EmptyState>
    );
  }
  const topTags = Object.entries(stats.data?.by_tag ?? {}).slice(0, 12);
  return (
    <Stack>
      <Title order={2}>Overview</Title>
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Stat label="Registries" value={list.length} />
        <Stat label="Skills (this registry)" value={stats.data?.skills ?? "-"} />
        <Stat label="Versions" value={stats.data?.versions ?? "-"} />
        <Stat label="Last update" value={stats.data?.last_update ? shortDate(stats.data.last_update) : "-"} />
      </SimpleGrid>

      <Title order={4} mt="md">Registries</Title>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {list.map((r) => (
          <Card key={r.slug} withBorder padding="md" component={Link} to={`/r/${r.slug}/skills`} style={{ textDecoration: "none", color: "inherit" }}>
            <Group justify="space-between">
              <Text fw={600}>{r.name || r.slug}</Text>
              <Badge variant="light" color={r.visibility === "public" ? "teal" : "gray"}>{r.visibility}</Badge>
            </Group>
            <Text size="sm" c="dimmed" lineClamp={2}>{r.description || "No description"}</Text>
            <Text size="sm" mt="xs">{r.skills} {r.skills === 1 ? "skill" : "skills"}{r.role ? ` - you are ${r.role}` : ""}</Text>
          </Card>
        ))}
      </SimpleGrid>

      {topTags.length > 0 && (
        <>
          <Title order={4} mt="md">Top tags</Title>
          <Group gap="xs">
            {topTags.map(([tag, n]) => (
              <Badge key={tag} component={Link} to={`/r/${slug}/skills?tag=${encodeURIComponent(tag)}`} variant="light" style={{ cursor: "pointer" }}>
                {tag} ({n})
              </Badge>
            ))}
          </Group>
        </>
      )}

      <Title order={4} mt="md">Recent versions</Title>
      {activity.isLoading ? <LoadingBlock rows={3} /> : activity.error ? <ErrorBlock error={activity.error} /> : (activity.data ?? []).length === 0 ? (
        <Text c="dimmed" size="sm">Nothing published yet.</Text>
      ) : (
        <Stack gap={6}>
          {activity.data!.map((a) => (
            <Group key={a.sha256 + a.ref} gap="sm">
              <Anchor component={Link} to={`/r/${slug}/skills/${a.ref}`}>{a.ref}</Anchor>
              <Badge variant="outline" size="sm">{a.version}</Badge>
              <Text size="sm" c="dimmed">{shortDate(a.at)} by {a.by || "unknown"}</Text>
            </Group>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
