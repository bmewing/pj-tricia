import { useKindeAuth } from '@kinde-oss/kinde-auth-react'
import { Button, Card, Stack, Text, TextInput, Title } from '@mantine/core'
import { useState } from 'react'

import { api, call } from '../api/client'
import { keys, useApi, useMe } from '../api/queries'
import { ErrorNote, Loading } from '../components/common'

export function ProfilePage() {
  const { logout } = useKindeAuth()
  const { data: me, isLoading } = useMe()
  const [edited, setName] = useState<string | null>(null)
  const name = edited ?? me?.display_name ?? ''
  const save = useApi(() => call(api.PATCH('/api/me', { body: { display_name: name } })), {
    invalidate: [keys.me],
  })
  const remove = useApi(() => call(api.DELETE('/api/me')))
  if (isLoading || !me) return <Loading />
  return (
    <Stack gap="lg" maw={480}>
      <Title order={1}>Profile</Title>
      <Card>
        <Stack>
          <TextInput
            label="Display name"
            description="Your team name unless you set one for a game"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
          />
          <Text size="sm" c="dimmed">
            {me.email}
          </Text>
          <Button
            w="fit-content"
            disabled={!name.trim() || name === me.display_name}
            loading={save.isPending}
            onClick={() => save.mutate(undefined)}
          >
            Save
          </Button>
          <ErrorNote error={save.error} />
        </Stack>
      </Card>
      <Card>
        <Stack>
          <Title order={4}>Delete account</Title>
          <Text size="sm">
            Removes your groups' memberships and answers here. Groups you own pass to another
            member.
          </Text>
          <Button
            color="red"
            variant="light"
            w="fit-content"
            onClick={() => {
              if (window.confirm('Delete your account? This cannot be undone.')) {
                remove.mutate(undefined, { onSuccess: () => void logout() })
              }
            }}
          >
            Delete my account
          </Button>
        </Stack>
      </Card>
    </Stack>
  )
}
