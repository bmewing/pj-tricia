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
import { HouseRules } from '../components/HouseRules'
import { formatWhen } from '../components/format'

function Landing() {
  const { login, register } = useKindeAuth()
  return (
    <Stack gap="xl" mt="lg">
      <img
        src="/logo.png"
        alt="PJ Tricia"
        style={{ width: 'min(100%, 480px)', height: 'auto', display: 'block' }}
      />
      <Title order={1} fz={{ base: 32, sm: 46 }} lh={1.15} className="gold-title">
        Trivia night, from the couch.
      </Title>
      <Text size="lg" maw={640}>
        Make a group, schedule a game, and let someone host. Everyone plays from home on their
        phone; the scores keep themselves.
      </Text>
      <List spacing="xs" maw={640}>
        <List.Item>Round 1, 2 and 3: multiple choice worth 5, 10 and 15 a question</List.Item>
        <List.Item>
          A <b>Double Down Dare</b> after each one: double the round, or lose it
        </List.Item>
        <List.Item>
          Round 4 is free-form, then the <b>Do or Die Dare</b>: wager it all
        </List.Item>
      </List>
      <Group>
        <Button size="md" onClick={() => void register()}>
          Get started
        </Button>
        <Button size="md" variant="light" onClick={() => void login()}>
          Sign in
        </Button>
      </Group>
      <HouseRules />
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
