import { useKindeAuth } from '@kinde-oss/kinde-auth-react'
import {
  Badge,
  Button,
  Card,
  Group,
  List,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { api, call } from '../api/client'
import { keys, useApi, useGroups } from '../api/queries'
import { ErrorNote, Loading } from '../components/common'
import { formatWhen } from '../components/format'

function Landing() {
  const { login, register } = useKindeAuth()
  return (
    <Stack gap="xl" mt="xl" maw={640}>
      <Title order={1} fz={{ base: 36, sm: 52 }} lh={1.1}>
        Trivia night,{' '}
        <Text span inherit c="gold.4">
          from the couch.
        </Text>
      </Title>
      <Text size="lg">
        Make a group, schedule a game, and let someone host. Everyone plays from home on their
        phone; the scores keep themselves.
      </Text>
      <List spacing="xs">
        <List.Item>Three multiple-choice rounds worth 5, 10 and 15 a question</List.Item>
        <List.Item>A double dare after each one: double the round, or lose it</List.Item>
        <List.Item>A free-form fourth round, then wager it all on the final</List.Item>
      </List>
      <Group>
        <Button size="md" onClick={() => void register()}>
          Get started
        </Button>
        <Button size="md" variant="light" onClick={() => void login()}>
          Sign in
        </Button>
      </Group>
    </Stack>
  )
}

function NewGroup() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const create = useApi(
    () => call(api.POST('/api/groups', { body: { name, description: description || null } })),
    { invalidate: [keys.groups] },
  )
  return (
    <Card>
      <Stack>
        <Title order={4}>Start a group</Title>
        <TextInput
          label="Name"
          placeholder="Thursday Night Trivia"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
        />
        <Textarea
          label="About (optional)"
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Button
          disabled={!name.trim()}
          loading={create.isPending}
          onClick={() =>
            create.mutate(undefined, { onSuccess: (group) => navigate(`/groups/${group.id}`) })
          }
        >
          Create group
        </Button>
        <ErrorNote error={create.error} />
      </Stack>
    </Card>
  )
}

function MyGroups() {
  const { data: groups, isLoading, error } = useGroups()
  if (isLoading) return <Loading />
  return (
    <Stack gap="lg">
      <Title order={2}>Your groups</Title>
      <ErrorNote error={error} />
      {groups?.length === 0 && (
        <Text c="dimmed">
          You're not in a group yet. Start one below, or open an invite link from a friend.
        </Text>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {groups?.map((group) => (
          <Card key={group.id} component={Link} to={`/groups/${group.id}`}>
            <Group justify="space-between" mb="xs">
              <Text fw={700} ff="heading" fz="lg">
                {group.name}
              </Text>
              <Badge variant="light">{group.member_count} members</Badge>
            </Group>
            {group.next_event ? (
              <Text size="sm">
                Next:{' '}
                <Text span fw={600}>
                  {group.next_event.title}
                </Text>{' '}
                · {formatWhen(group.next_event.starts_at)}
                {group.next_event.status === 'live' && (
                  <Badge ml="xs" color="red">
                    Live
                  </Badge>
                )}
              </Text>
            ) : (
              <Text size="sm" c="dimmed">
                Nothing scheduled
              </Text>
            )}
          </Card>
        ))}
      </SimpleGrid>
      <NewGroup />
    </Stack>
  )
}

export function HomePage() {
  const { isAuthenticated, isLoading } = useKindeAuth()
  if (isLoading) return <Loading />
  return isAuthenticated ? <MyGroups /> : <Landing />
}
