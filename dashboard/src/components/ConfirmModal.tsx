import { Button, Group, Modal, Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";

export function ConfirmModal({
  opened, onClose, onConfirm, title, children, confirmLabel = "Confirm", danger = true, loading = false,
}: {
  opened: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title={title} centered>
      <Stack>
        <Text size="sm">{children}</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button color={danger ? "red" : undefined} onClick={onConfirm} loading={loading}>{confirmLabel}</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
