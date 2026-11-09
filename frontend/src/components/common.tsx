import { Alert, Button, CopyButton, Center, Group, Loader, Text, TextInput } from '@mantine/core'

export function Loading() {
  return (
    <Center mt="xl">
      <Loader />
    </Center>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <Alert color="red" variant="light" mt="sm">
      {error instanceof Error ? error.message : 'Something went wrong.'}
    </Alert>
  )
}

export function CopyLink({ label, path }: { label: string; path: string }) {
  const url = `${window.location.origin}${path}`
  return (
    <div>
      <Text size="sm" fw={600} mb={4}>
        {label}
      </Text>
      <Group gap="xs" wrap="nowrap">
        <TextInput
          value={url}
          readOnly
          style={{ flex: 1 }}
          onFocus={(e) => e.currentTarget.select()}
        />
        <CopyButton value={url}>
          {({ copied, copy }) => (
            <Button variant="light" onClick={copy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          )}
        </CopyButton>
      </Group>
    </div>
  )
}
