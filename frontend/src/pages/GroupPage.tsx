import {
  Badge,
  Button,
  Card,
  Group,
  Menu,
  NumberInput,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { api, call, type EventBrief, type GroupRead } from '../api/client'
import { keys, useApi, useGroup, useMe } from '../api/queries'
import { CopyLink, ErrorNote, Loading } from '../components/common'
import { formatWhen, localInputToIso } from '../components/format'

function EventRow({ event }: { event: EventBrief }) {
  return (
    <Card component={Link} to={`/events/${event.id}`} padding="sm">
      <Group justify="space-between" wrap="nowrap">
        <div>
          <Text fw={700}>{event.title}</Text>
          <Text size="sm" c="dimmed">
            {formatWhen(event.starts_at)} · {event.players} playing
            {event.host ? ` · hosted by ${event.host.display_name}` : ' · needs a host'}
          </Text>
        </div>
        {event.status !== 'scheduled' && (
          <Badge color={event.status === 'live' ? 'red' : 'gray'}>{event.status}</Badge>
        )}
      </Group>
    </Card>
  )
}

function NewEvent({ group }: { group: GroupRead }) {
  const navigate = useNavigate()
  const [title, setTitle] = useState('Trivia Night')
  const [when, setWhen] = useState('')
  const [duration, setDuration] = useState<number>(120)
  const [notes, setNotes] = useState('')
  const create = useApi(
    () =>
      call(
        api.POST('/api/groups/{group_id}/events', {
          params: { path: { group_id: group.id } },
          body: {
            title,
            starts_at: localInputToIso(when),
            duration_minutes: duration,
            notes: notes || null,
          },
        }),
      ),
    { invalidate: [keys.group(group.id), keys.groups] },
  )
  return (
    <Card>
      <Stack>
        <Title order={4}>Schedule a game</Title>
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
        <TextInput
          type="datetime-local"
          label="When"
          value={when}
          onChange={(e) => setWhen(e.currentTarget.value)}
        />
        <NumberInput
          label="Length (minutes)"
          min={15}
          max={720}
          step={15}
          value={duration}
          onChange={(v) => setDuration(Number(v) || 120)}
        />
        <Textarea
          label="Notes (optional)"
          placeholder="Video call link, theme, anything else"
          value={notes}
          onChange={(e) => setNotes(e.currentTarget.value)}
          autosize
          minRows={2}
        />
        <Button
          disabled={!title.trim() || !when}
          loading={create.isPending}
          onClick={() =>
            create.mutate(undefined, { onSuccess: (e) => navigate(`/events/${e.id}`) })
          }
        >
          Schedule
        </Button>
        <ErrorNote error={create.error} />
      </Stack>
    </Card>
  )
}

function Members({ group }: { group: GroupRead }) {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const invalidate = [keys.group(group.id), keys.groups]
  const setRole = useApi(
    ({ userId, role }: { userId: string; role: 'owner' | 'admin' | 'member' }) =>
      call(
        api.PATCH('/api/groups/{group_id}/members/{user_id}', {
          params: { path: { group_id: group.id, user_id: userId } },
          body: { role },
        }),
      ),
    { invalidate },
  )
  const remove = useApi(
    (userId: string) =>
      call(
        api.DELETE('/api/groups/{group_id}/members/{user_id}', {
          params: { path: { group_id: group.id, user_id: userId } },
        }),
      ),
    { invalidate },
  )
  const isOwner = group.my_role === 'owner'
  return (
    <Card>
      <Title order={4} mb="sm">
        Members
      </Title>
      <Stack gap="xs">
        {group.members.map((m) => {
          const isMe = m.person.id === me?.id
          const canRemove = !isMe && (isOwner || (group.my_role === 'admin' && m.role === 'member'))
          return (
            <Group key={m.person.id} justify="space-between">
              <Group gap="xs">
                <Text>{m.person.display_name}</Text>
                {m.role !== 'member' && (
                  <Badge size="sm" variant="light">
                    {m.role}
                  </Badge>
                )}
              </Group>
              {(isOwner && !isMe) || canRemove || (isMe && !isOwner) ? (
                <Menu position="bottom-end">
                  <Menu.Target>
                    <Button size="xs" variant="subtle">
                      ⋯
                    </Button>
                  </Menu.Target>
                  <Menu.Dropdown>
                    {isOwner && !isMe && m.role === 'member' && (
                      <Menu.Item
                        onClick={() => setRole.mutate({ userId: m.person.id, role: 'admin' })}
                      >
                        Make admin
                      </Menu.Item>
                    )}
                    {isOwner && !isMe && m.role === 'admin' && (
                      <Menu.Item
                        onClick={() => setRole.mutate({ userId: m.person.id, role: 'member' })}
                      >
                        Make member
                      </Menu.Item>
                    )}
                    {isOwner && !isMe && (
                      <Menu.Item
                        onClick={() => {
                          if (window.confirm(`Hand the group to ${m.person.display_name}?`)) {
                            setRole.mutate({ userId: m.person.id, role: 'owner' })
                          }
                        }}
                      >
                        Hand over the group
                      </Menu.Item>
                    )}
                    {canRemove && (
                      <Menu.Item color="red" onClick={() => remove.mutate(m.person.id)}>
                        Remove
                      </Menu.Item>
                    )}
                    {isMe && !isOwner && (
                      <Menu.Item
                        color="red"
                        onClick={() =>
                          remove.mutate(m.person.id, { onSuccess: () => navigate('/') })
                        }
                      >
                        Leave group
                      </Menu.Item>
                    )}
                  </Menu.Dropdown>
                </Menu>
              ) : null}
            </Group>
          )
        })}
      </Stack>
      <ErrorNote error={setRole.error ?? remove.error} />
    </Card>
  )
}

export function GroupPage() {
  const { groupId = '' } = useParams()
  const { data: group, isLoading, error } = useGroup(groupId)
  const runner = group?.my_role === 'owner' || group?.my_role === 'admin'
  const newCode = useApi(
    () =>
      call(
        api.POST('/api/groups/{group_id}/invite-code', { params: { path: { group_id: groupId } } }),
      ),
    { invalidate: [keys.group(groupId)] },
  )
  if (isLoading) return <Loading />
  if (!group) return <ErrorNote error={error} />
  return (
    <Stack gap="lg">
      <div>
        <Title order={1}>{group.name}</Title>
        {group.description && <Text c="dimmed">{group.description}</Text>}
      </div>

      <Stack gap="xs">
        <Title order={3}>Coming up</Title>
        {group.upcoming.length === 0 && <Text c="dimmed">Nothing scheduled yet.</Text>}
        {group.upcoming.map((e) => (
          <EventRow key={e.id} event={e} />
        ))}
      </Stack>

      {runner && <NewEvent group={group} />}

      <Card>
        <Stack>
          <CopyLink
            label="Invite link: anyone who opens it can join"
            path={`/join/${group.invite_code}`}
          />
          {runner && (
            <Button
              variant="subtle"
              size="xs"
              w="fit-content"
              loading={newCode.isPending}
              onClick={() => {
                if (window.confirm('Make a new link? The current one will stop working.')) {
                  newCode.mutate(undefined)
                }
              }}
            >
              Make a new link
            </Button>
          )}
        </Stack>
      </Card>

      <Members group={group} />

      {group.recent.length > 0 && (
        <Stack gap="xs">
          <Title order={3}>Past games</Title>
          {group.recent.map((e) => (
            <EventRow key={e.id} event={e} />
          ))}
        </Stack>
      )}
    </Stack>
  )
}
