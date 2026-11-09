import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  Modal,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { ApiError, api, call, type EventRead } from '../api/client'
import { keys, useApi, useEvent, useGroup } from '../api/queries'
import { CopyLink, ErrorNote, Loading } from '../components/common'
import { formatWhen } from '../components/format'

function icsFor(event: EventRead): string {
  const stamp = (d: Date) =>
    d
      .toISOString()
      .replace(/[-:]/g, '')
      .replace(/\.\d{3}/, '')
  const start = new Date(event.starts_at)
  const end = new Date(start.getTime() + event.duration_minutes * 60000)
  const escape = (s: string) => s.replace(/[\\;,]/g, (c) => `\\${c}`).replace(/\n/g, '\\n')
  const url = `${window.location.origin}/events/${event.id}/play`
  return [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//PJ Tricia//EN',
    'BEGIN:VEVENT',
    `UID:${event.id}@pjtricia`,
    `DTSTAMP:${stamp(new Date())}`,
    `DTSTART:${stamp(start)}`,
    `DTEND:${stamp(end)}`,
    `SUMMARY:${escape(`${event.title} (${event.group_name})`)}`,
    `DESCRIPTION:${escape(`${event.notes ? `${event.notes}\n\n` : ''}Play: ${url}`)}`,
    `URL:${url}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\r\n')
}

function downloadIcs(event: EventRead) {
  const blob = new Blob([icsFor(event)], { type: 'text/calendar' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'trivia.ics'
  link.click()
  URL.revokeObjectURL(link.href)
}

function RsvpCard({ event }: { event: EventRead }) {
  const mine = event.me.attendee
  const [response, setResponse] = useState<'yes' | 'maybe' | 'no'>(mine?.response ?? 'yes')
  const [role, setRole] = useState<'player' | 'spectator'>(mine?.role ?? 'player')
  const [team, setTeam] = useState(mine?.team_name ?? '')
  const save = useApi(
    () =>
      call(
        api.PUT('/api/events/{event_id}/rsvp', {
          params: { path: { event_id: event.id } },
          body: { response, role, team_name: team || null },
        }),
      ),
    { invalidate: [keys.event(event.id), keys.group(event.group_id), keys.live(event.id)] },
  )
  const isHost = event.me.game_role === 'host'
  if (isHost || event.status === 'finished' || event.status === 'cancelled') return null
  return (
    <Card>
      <Stack>
        <Title order={4}>{mine ? 'Your RSVP' : 'Are you coming?'}</Title>
        <SegmentedControl
          value={response}
          onChange={(v) => setResponse(v as typeof response)}
          data={[
            { value: 'yes', label: 'Yes' },
            { value: 'maybe', label: 'Maybe' },
            { value: 'no', label: 'No' },
          ]}
        />
        {response !== 'no' && event.me.is_member && (
          <SegmentedControl
            value={role}
            onChange={(v) => setRole(v as typeof role)}
            data={[
              { value: 'player', label: 'Playing' },
              { value: 'spectator', label: 'Just watching' },
            ]}
          />
        )}
        {response !== 'no' && role === 'player' && (
          <TextInput
            label="Team name (optional)"
            description="Playing as a couple? Name your team. Otherwise your name is used."
            placeholder="The Smiths"
            value={team}
            maxLength={60}
            onChange={(e) => setTeam(e.currentTarget.value)}
          />
        )}
        <Button w="fit-content" loading={save.isPending} onClick={() => save.mutate(undefined)}>
          {mine ? 'Update' : 'Save'}
        </Button>
        <ErrorNote error={save.error} />
      </Stack>
    </Card>
  )
}

type HostAction =
  | { kind: 'assign'; userId: string }
  | { kind: 'random' }
  | { kind: 'clear' }
  | { kind: 'volunteer' }

function HostCard({ event }: { event: EventRead }) {
  const { data: group } = useGroup(event.group_id)
  const [pick, setPick] = useState<string | null>(null)
  const [askAbout, setAskAbout] = useState<HostAction | null>(null)
  const invalidate = [keys.event(event.id), keys.group(event.group_id), keys.live(event.id)]
  const change = useApi(
    ({ action, clear }: { action: HostAction; clear: boolean | null }) => {
      const path = { params: { path: { event_id: event.id } } }
      const body = { clear_questions: clear }
      switch (action.kind) {
        case 'volunteer':
          return call(api.POST('/api/events/{event_id}/host/volunteer', path))
        case 'assign':
          return call(
            api.PUT('/api/events/{event_id}/host', {
              ...path,
              body: { ...body, user_id: action.userId },
            }),
          )
        case 'random':
          return call(api.POST('/api/events/{event_id}/host/random', { ...path, body }))
        case 'clear':
          return call(api.POST('/api/events/{event_id}/host/clear', { ...path, body }))
      }
    },
    { invalidate },
  )
  const run = (action: HostAction, clear: boolean | null = null) =>
    change.mutate(
      { action, clear },
      {
        onSuccess: () => setAskAbout(null),
        onError: (error) => {
          if (
            error instanceof ApiError &&
            error.status === 409 &&
            /keep them/.test(error.message)
          ) {
            setAskAbout(action)
          }
        },
      },
    )

  const scheduled = event.status === 'scheduled'
  const isHost = event.me.game_role === 'host'
  const yesPlayers = event.attendees.filter((a) => a.response === 'yes' && a.role === 'player')
  return (
    <Card>
      <Stack>
        <Title order={4}>Host</Title>
        {event.host ? (
          <Text>
            <Text span fw={700}>
              {event.host.display_name}
            </Text>{' '}
            is hosting{isHost ? ' (that’s you!)' : ''}.
          </Text>
        ) : (
          <Text c="dimmed">Nobody's hosting yet.</Text>
        )}
        {scheduled && !event.host && event.me.is_member && (
          <Button
            w="fit-content"
            onClick={() => run({ kind: 'volunteer' })}
            loading={change.isPending}
          >
            I'll host
          </Button>
        )}
        {scheduled && isHost && (
          <Group>
            <Button component={Link} to={`/events/${event.id}/questions`}>
              Write the questions
            </Button>
            <Button variant="subtle" color="red" onClick={() => run({ kind: 'clear' })}>
              Step down
            </Button>
          </Group>
        )}
        {scheduled && event.me.can_manage && (
          <Group align="end">
            <Select
              label="Choose a host"
              placeholder="Pick a member"
              data={(group?.members ?? []).map((m) => ({
                value: m.person.id,
                label: m.person.display_name,
              }))}
              value={pick}
              onChange={setPick}
              searchable
            />
            <Button
              variant="light"
              disabled={!pick}
              onClick={() => pick && run({ kind: 'assign', userId: pick })}
            >
              Assign
            </Button>
            <Button
              variant="light"
              disabled={yesPlayers.length === 0}
              onClick={() => run({ kind: 'random' })}
            >
              Pick at random
            </Button>
            {event.host && !isHost && (
              <Button variant="subtle" color="red" onClick={() => run({ kind: 'clear' })}>
                Remove host
              </Button>
            )}
          </Group>
        )}
        {change.error && !askAbout && <ErrorNote error={change.error} />}
      </Stack>
      <Modal
        opened={askAbout !== null}
        onClose={() => setAskAbout(null)}
        title="Questions already written"
      >
        <Stack>
          <Text>
            {event.host?.display_name ?? 'The current host'} has already written questions for this
            game. Keep them for the new host, or clear them so whoever wrote them can play?
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAskAbout(null)}>
              Cancel
            </Button>
            <Button variant="light" onClick={() => askAbout && run(askAbout, false)}>
              Keep them
            </Button>
            <Button color="red" onClick={() => askAbout && run(askAbout, true)}>
              Clear them
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  )
}

function ManageCard({ event }: { event: EventRead }) {
  const navigate = useNavigate()
  const invalidate = [keys.event(event.id), keys.group(event.group_id), keys.groups]
  const cancel = useApi(
    (cancelled: boolean) =>
      call(
        api.PATCH('/api/events/{event_id}', {
          params: { path: { event_id: event.id } },
          body: { cancelled },
        }),
      ),
    { invalidate },
  )
  const remove = useApi(
    () => call(api.DELETE('/api/events/{event_id}', { params: { path: { event_id: event.id } } })),
    { invalidate: [keys.group(event.group_id), keys.groups] },
  )
  if (!event.me.can_manage || event.status === 'live') return null
  return (
    <Group>
      {event.status === 'scheduled' && (
        <Button variant="subtle" color="red" onClick={() => cancel.mutate(true)}>
          Cancel this game
        </Button>
      )}
      {event.status === 'cancelled' && (
        <Button variant="subtle" onClick={() => cancel.mutate(false)}>
          Un-cancel
        </Button>
      )}
      <Button
        variant="subtle"
        color="red"
        onClick={() => {
          if (window.confirm('Delete this event and everything in it?')) {
            remove.mutate(undefined, { onSuccess: () => navigate(`/groups/${event.group_id}`) })
          }
        }}
      >
        Delete
      </Button>
      <ErrorNote error={cancel.error ?? remove.error} />
    </Group>
  )
}

export function EventPage() {
  const { eventId = '' } = useParams()
  const { data: event, isLoading, error } = useEvent(eventId)
  if (isLoading) return <Loading />
  if (!event) return <ErrorNote error={error} />
  const players = event.attendees.filter((a) => a.role === 'player' && a.response !== 'no')
  const watching = event.attendees.filter((a) => a.role === 'spectator' && a.response !== 'no')
  const declined = event.attendees.filter((a) => a.response === 'no')
  return (
    <Stack gap="lg">
      <div>
        <Text component={Link} to={`/groups/${event.group_id}`} c="dimmed" size="sm">
          ← {event.group_name}
        </Text>
        <Group gap="sm" align="center">
          <Title order={1}>{event.title}</Title>
          {event.status !== 'scheduled' && (
            <Badge color={event.status === 'live' ? 'red' : 'gray'} size="lg">
              {event.status}
            </Badge>
          )}
        </Group>
        <Text>
          {formatWhen(event.starts_at)} · {event.duration_minutes} min
        </Text>
        {event.notes && (
          <Text mt="xs" style={{ whiteSpace: 'pre-wrap' }}>
            {event.notes}
          </Text>
        )}
      </div>

      <Group>
        {event.status !== 'cancelled' && (
          <Button
            component={Link}
            to={`/events/${event.id}/play`}
            size="md"
            color="gold"
            c="dark.9"
          >
            {event.status === 'live'
              ? 'Join the game'
              : event.status === 'finished'
                ? 'See the results'
                : 'Open the game room'}
          </Button>
        )}
        {event.status === 'scheduled' && (
          <Button variant="light" onClick={() => downloadIcs(event)}>
            Add to calendar
          </Button>
        )}
      </Group>

      {event.me.game_role === 'host' && event.problems && event.problems.length > 0 && (
        <Alert color="gold" variant="light" title={`Questions: ${event.question_count} written`}>
          <List size="sm">
            {event.problems.slice(0, 5).map((p) => (
              <List.Item key={p}>{p}</List.Item>
            ))}
          </List>
          {event.problems.length > 5 && (
            <Text size="sm">…and {event.problems.length - 5} more</Text>
          )}
        </Alert>
      )}
      {event.me.game_role === 'host' && event.problems?.length === 0 && (
        <Alert color="green" variant="light">
          {event.question_count} questions written. You're ready to start the game.
        </Alert>
      )}

      <RsvpCard key={JSON.stringify(event.me.attendee)} event={event} />
      <HostCard event={event} />

      <Card>
        <Stack gap="xs">
          <Title order={4}>Playing ({players.length})</Title>
          {players.length === 0 && <Text c="dimmed">No teams yet.</Text>}
          {players.map((a) => (
            <Text key={a.person.id}>
              {a.team_name ? `${a.team_name} (${a.person.display_name})` : a.person.display_name}
              {a.response === 'maybe' && (
                <Badge ml="xs" size="sm" variant="light">
                  maybe
                </Badge>
              )}
            </Text>
          ))}
          {watching.length > 0 && (
            <Text size="sm" c="dimmed">
              Watching: {watching.map((a) => a.person.display_name).join(', ')}
            </Text>
          )}
          {declined.length > 0 && (
            <Text size="sm" c="dimmed">
              Can't make it: {declined.map((a) => a.person.display_name).join(', ')}
            </Text>
          )}
        </Stack>
      </Card>

      {event.spectate_token && event.status !== 'cancelled' && (
        <Card>
          <CopyLink
            label="Spectator link: anyone can watch (they won't play)"
            path={`/watch/${event.spectate_token}`}
          />
        </Card>
      )}

      <ManageCard event={event} />
    </Stack>
  )
}
