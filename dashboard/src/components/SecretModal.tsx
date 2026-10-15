import { Alert, Button, CopyButton, Group, Modal, Stack, Text, TextInput } from "@mantine/core";

/** Shows a secret exactly once (tokens cannot be recovered later). */
export function SecretModal({ secret, onClose, title = "Copy your token now" }: { secret: string | null; onClose: () => void; title?: string }) {
  return (
    <Modal opened={secret !== null} onClose={onClose} title={title} centered closeOnClickOutside={false}>
      <Stack>
        <Alert color="yellow" title="Shown only once">
          Store it in a password manager or a CI secret. It cannot be displayed again - create a new one if you lose it.
        </Alert>
        <TextInput readOnly value={secret ?? ""} aria-label="Token" onFocus={(e) => e.currentTarget.select()} />
        <Group justify="space-between">
          <CopyButton value={secret ?? ""}>
            {({ copied, copy }) => (
              <Button variant="light" onClick={copy}>{copied ? "Copied" : "Copy to clipboard"}</Button>
            )}
          </CopyButton>
          <Button onClick={onClose}>I have saved it</Button>
        </Group>
        <Text size="xs" c="dimmed">Use it as <code>Authorization: Bearer &lt;token&gt;</code> or with <code>owl remote add NAME URL --token-env VAR</code>.</Text>
      </Stack>
    </Modal>
  );
}
