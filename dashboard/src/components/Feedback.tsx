import { Alert, Center, Loader, Skeleton, Stack, Text, Title } from "@mantine/core";
import { IconAlertCircle, IconInbox } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { ApiError } from "../api/client";

export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <Stack gap="sm" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={28} radius="sm" />
      ))}
    </Stack>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <Center py="xl" role="status" aria-label={label}>
      <Loader />
    </Center>
  );
}

export function ErrorBlock({ error, title = "Something went wrong" }: { error: unknown; title?: string }) {
  const err = error as Error;
  const hint =
    err instanceof ApiError && err.status === 401
      ? "You need to sign in to see this."
      : err instanceof ApiError && err.status === 404
        ? "It does not exist or you do not have access."
        : undefined;
  return (
    <Alert color="red" icon={<IconAlertCircle aria-hidden />} title={title} role="alert">
      {err?.message ?? "Unknown error"}
      {hint && <Text size="sm" mt={4}>{hint}</Text>}
    </Alert>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <Center py="xl">
      <Stack align="center" gap="xs" maw={440} ta="center">
        <IconInbox size={40} stroke={1.2} aria-hidden />
        <Title order={4}>{title}</Title>
        {children && <Text c="dimmed" size="sm">{children}</Text>}
        {action}
      </Stack>
    </Center>
  );
}
