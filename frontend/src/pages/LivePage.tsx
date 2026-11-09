import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  NumberInput,
  Paper,
  Progress,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { api, call, type HostAnswer, type LiveState, type ScoreRow } from '../api/client'
import { keys, useApi, useEvent, useLive } from '../api/queries'
import { ErrorNote, Loading } from '../components/common'
import { LETTERS } from '../components/format'

type Question = NonNullable<LiveState['question']>

function stepTitle(state: LiveState): string {
  const q = state.question
  if (state.step === 'wager') return 'Final wager'
  if (state.step === 'results' || state.step === 'over') return 'Final results'
  if (!q) return ''
  if (q.kind === 'double_dare') return `Round ${q.round} · Double dare`
  if (q.kind === 'final') return 'Final question'
  return `Round ${q.round} · Question ${q.number} · ${q.points} pts`
}

const DARE_MARK: Record<string, string> = {
  right: '×2',
  wrong: '✕',
  pending: '…',
  passed: '',
  none: '',
}

function Scoreboard({ state, compact = false }: { state: LiveState; compact?: boolean }) {
  if (state.scoreboard.length === 0) return null
  const mine = state.my_score?.team.user_id
  const showFinal =
    state.step === 'results' ||
    state.step === 'over' ||
    state.scoreboard.some((r) => r.final !== 'none')
  return (
    <Card padding="sm">
      <Title order={4} mb="xs">
        Scores
      </Title>
      <Table.ScrollContainer minWidth={compact ? 0 : 420}>
        <Table striped highlightOnHover verticalSpacing={4}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>Team</Table.Th>
              {!compact && [1, 2, 3, 4].map((r) => <Table.Th key={r}>R{r}</Table.Th>)}
              {!compact && showFinal && <Table.Th>Final</Table.Th>}
              <Table.Th ta="right">Total</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {state.scoreboard.map((row, i) => (
              <Table.Tr key={row.team.user_id} fw={row.team.user_id === mine ? 700 : undefined}>
                <Table.Td>{rank(state.scoreboard, i)}</Table.Td>
                <Table.Td>
                  {row.team.name}
                  {row.pending > 0 && (
                    <Text span c="dimmed" size="xs">
                      {' '}
                      ({row.pending} to grade)
                    </Text>
                  )}
                </Table.Td>
                {!compact &&
                  row.rounds.map((r, j) => (
                    <Table.Td key={j}>
                      {r.points}
                      {DARE_MARK[r.dare] && (
                        <Text
                          span
                          size="xs"
                          c={r.dare === 'right' ? 'green' : r.dare === 'wrong' ? 'red' : 'dimmed'}
                        >
                          {' '}
                          {DARE_MARK[r.dare]}
                        </Text>
                      )}
                    </Table.Td>
                  ))}
                {!compact && showFinal && (
                  <Table.Td>
                    {row.final === 'none' || row.final === 'pending'
                      ? row.wager != null
                        ? `bet ${row.wager}`
                        : '–'
                      : `${row.final_points >= 0 ? '+' : ''}${row.final_points}`}
                  </Table.Td>
                )}
                <Table.Td ta="right" fw={800}>
                  {row.total}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  )
}

function rank(rows: ScoreRow[], index: number): number {
  let place = index
  while (place > 0 && rows[place - 1].total === rows[index].total) place--
  return place + 1
}

function QuestionView({ question, state }: { question: Question; state: LiveState }) {
  const reveal = state.reveal
  return (
    <Stack gap="sm">
      <Text className="question-text">{question.text}</Text>
      {question.kind !== 'mc' && reveal?.answer_text && (
        <Paper p="sm" bg="green.9" c="white" radius="md">
          <Text size="sm" fw={700}>
            Answer
          </Text>
          <Text fz="lg">{reveal.answer_text}</Text>
        </Paper>
      )}
    </Stack>
  )
}

function Choices({
  question,
  state,
  onPick,
  busy,
}: {
  question: Question
  state: LiveState
  onPick?: (choice: number) => void
  busy?: boolean
}) {
  const picked = state.my_answer?.choice
  const correct = state.reveal?.correct_choice
  const open = state.phase === 'open'
  return (
    <Stack gap="xs">
      {(question.choices ?? []).map((choice, i) => {
        const isCorrect = correct === i
        const isPicked = picked === i
        const color =
          isCorrect && !open ? 'green' : isCorrect ? 'green' : isPicked ? 'gold' : 'midnight'
        return (
          <Button
            key={i}
            className="choice-button"
            size="lg"
            fullWidth
            variant={
              isPicked || (isCorrect && (!open || state.role === 'host')) ? 'filled' : 'light'
            }
            color={color}
            c={isPicked && !isCorrect ? 'dark.9' : undefined}
            disabled={!onPick || !open}
            loading={busy && isPicked}
            onClick={() => onPick?.(i)}
            styles={{ root: { opacity: 1 } }}
          >
            <span className="letter">{LETTERS[i]}</span>
            {choice}
          </Button>
        )
      })}
    </Stack>
  )
}

function PlayerInput({ state, eventId }: { state: LiveState; eventId: string }) {
  const question = state.question
  const mine = state.my_answer
  const [text, setText] = useState(mine?.text ?? '')
  const [wager, setWager] = useState<number>(mine?.wager ?? 0)
  const submit = useApi(
    (body: {
      question_id: string
      choice?: number
      text?: string
      passed?: boolean
      wager?: number
    }) =>
      call(
        api.PUT('/api/events/{event_id}/live/answer', {
          params: { path: { event_id: eventId } },
          body: { passed: false, ...body },
        }),
      ),
    { liveFor: eventId },
  )
  const open = state.phase === 'open'

  if (state.step === 'wager') {
    // The final question's id isn't sent during the wager; the server takes it from the step.
    return (
      <Card>
        <Stack>
          <Title order={3}>Place your wager</Title>
          <Text>
            You have <b>{state.my_score?.total ?? 0}</b> points. Wager up to{' '}
            <b>{state.max_wager ?? 0}</b>. Get the final right to win that much, wrong to lose it.
          </Text>
          <NumberInput
            size="lg"
            min={0}
            max={state.max_wager ?? 0}
            value={wager}
            onChange={(v) => setWager(Math.max(0, Math.min(Number(v) || 0, state.max_wager ?? 0)))}
            disabled={!open}
          />
          <Button
            size="lg"
            disabled={!open}
            loading={submit.isPending}
            onClick={() => submit.mutate({ question_id: state.wager_question_id ?? '', wager })}
          >
            {mine?.wager != null ? `Change wager (now ${mine.wager})` : 'Lock in wager'}
          </Button>
          {!open && <Text c="dimmed">Wagers are locked.</Text>}
          <ErrorNote error={submit.error} />
        </Stack>
      </Card>
    )
  }

  if (!question) return null

  if (question.kind === 'mc') {
    return (
      <Stack>
        <Choices
          question={question}
          state={state}
          busy={submit.isPending}
          onPick={(choice) => submit.mutate({ question_id: question.id, choice })}
        />
        <ErrorNote error={submit.error} />
      </Stack>
    )
  }

  const dare = question.kind === 'double_dare'
  const submitted = mine?.text || mine?.passed
  return (
    <Card>
      <Stack>
        {dare && (
          <Text size="sm">
            Your round {question.round} points:{' '}
            <b>{state.my_score?.rounds[question.round - 1].base ?? 0}</b>. Answer right to double
            them, wrong to lose them, or pass to keep them.
          </Text>
        )}
        {question.kind === 'final' && mine?.wager != null && (
          <Text size="sm">
            You wagered <b>{mine.wager}</b>.
          </Text>
        )}
        <TextInput
          size="lg"
          placeholder="Your answer"
          value={text}
          maxLength={500}
          disabled={!open}
          onChange={(e) => setText(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && text.trim() && open) {
              submit.mutate({ question_id: question.id, text: text.trim() })
            }
          }}
        />
        <Group grow>
          <Button
            size="lg"
            disabled={!open || !text.trim()}
            loading={submit.isPending}
            onClick={() => submit.mutate({ question_id: question.id, text: text.trim() })}
          >
            {mine?.text ? 'Change answer' : 'Submit'}
          </Button>
          {dare && (
            <Button
              size="lg"
              variant={mine?.passed ? 'filled' : 'outline'}
              color="gray"
              disabled={!open}
              onClick={() => submit.mutate({ question_id: question.id, passed: true })}
            >
              {mine?.passed ? 'Passed' : 'Pass'}
            </Button>
          )}
        </Group>
        {submitted && open && (
          <Text c="dimmed" size="sm">
            {mine?.passed ? "You're sitting this one out." : `Locked in: “${mine?.text}”`}. You can
            change it until the host closes answers.
          </Text>
        )}
        {!open && <Verdict state={state} />}
        <ErrorNote error={submit.error} />
      </Stack>
    </Card>
  )
}

function Verdict({ state }: { state: LiveState }) {
  const mine = state.my_answer
  if (!mine) return <Text c="dimmed">You didn't answer this one.</Text>
  if (mine.passed) return <Text c="dimmed">You passed.</Text>
  if (mine.is_correct === true)
    return (
      <Text c="green" fw={700}>
        Correct!
      </Text>
    )
  if (mine.is_correct === false)
    return (
      <Text c="red" fw={700}>
        Not quite.
      </Text>
    )
  return <Text c="dimmed">Waiting for the host to grade your answer.</Text>
}

function GradeButtons({ answer, eventId }: { answer: HostAnswer; eventId: string }) {
  const grade = useApi(
    (is_correct: boolean | null) =>
      call(
        api.PUT('/api/events/{event_id}/live/answers/{answer_id}/grade', {
          params: { path: { event_id: eventId, answer_id: answer.id } },
          body: { is_correct },
        }),
      ),
    { liveFor: eventId },
  )
  return (
    <Group gap={6} wrap="nowrap">
      <Button
        size="xs"
        color="green"
        variant={answer.is_correct === true ? 'filled' : 'outline'}
        onClick={() => grade.mutate(answer.is_correct === true ? null : true)}
        aria-label="Mark right"
      >
        ✓
      </Button>
      <Button
        size="xs"
        color="red"
        variant={answer.is_correct === false ? 'filled' : 'outline'}
        onClick={() => grade.mutate(answer.is_correct === false ? null : false)}
        aria-label="Mark wrong"
      >
        ✕
      </Button>
    </Group>
  )
}

function HostAnswers({ state, eventId }: { state: LiveState; eventId: string }) {
  const answers = state.answers ?? []
  const question = state.question
  const waiting = state.teams.filter((t) => !answers.some((a) => a.team.user_id === t.user_id))
  return (
    <Card>
      <Group justify="space-between" mb="xs">
        <Title order={4}>
          {state.step === 'wager' ? 'Wagers' : 'Answers'} ({state.answered}/{state.teams.length})
        </Title>
      </Group>
      <Progress
        value={state.teams.length ? (100 * state.answered) / state.teams.length : 0}
        mb="sm"
      />
      <Stack gap={6}>
        {answers.map((a) => (
          <Group key={a.id} justify="space-between" wrap="nowrap">
            <div style={{ minWidth: 0 }}>
              <Text size="sm" c="dimmed">
                {a.team.name}
              </Text>
              <Text fw={600} style={{ overflowWrap: 'anywhere' }}>
                {state.step === 'wager'
                  ? `wagers ${a.wager}`
                  : a.passed
                    ? 'Passed'
                    : a.choice != null
                      ? `${LETTERS[a.choice]}. ${question?.choices?.[a.choice] ?? ''}`
                      : a.text}
              </Text>
            </div>
            {state.step === 'question' && question?.kind !== 'mc' && !a.passed && (
              <GradeButtons answer={a} eventId={eventId} />
            )}
            {question?.kind === 'mc' && (
              <Badge color={a.is_correct ? 'green' : 'red'} variant="light">
                {a.is_correct ? 'right' : 'wrong'}
              </Badge>
            )}
          </Group>
        ))}
        {waiting.length > 0 && (
          <Text size="sm" c="dimmed">
            Waiting on: {waiting.map((t) => t.name).join(', ')}
          </Text>
        )}
      </Stack>
    </Card>
  )
}

function HostControls({ state, eventId }: { state: LiveState; eventId: string }) {
  const action = useApi(
    (name: 'close' | 'reopen' | 'next' | 'back' | 'end') => {
      const path = { params: { path: { event_id: eventId } } }
      switch (name) {
        case 'close':
          return call(api.POST('/api/events/{event_id}/live/close', path))
        case 'reopen':
          return call(api.POST('/api/events/{event_id}/live/reopen', path))
        case 'next':
          return call(api.POST('/api/events/{event_id}/live/next', path))
        case 'back':
          return call(api.POST('/api/events/{event_id}/live/back', path))
        case 'end':
          return call(api.POST('/api/events/{event_id}/live/end', path))
      }
    },
    { liveFor: eventId, invalidate: [keys.event(eventId)] },
  )
  const open = state.phase === 'open'
  const ungradedHere = (state.answers ?? []).some(
    (a) => a.is_correct === null && !a.passed && state.question?.kind !== 'mc',
  )
  const last = state.step === 'results'
  return (
    <Card>
      <Stack gap="xs">
        <Group grow>
          {open ? (
            <Button
              size="md"
              color="gold"
              c="dark.9"
              onClick={() => action.mutate('close')}
              loading={action.isPending}
            >
              Close answers &amp; reveal
            </Button>
          ) : (
            !last && (
              <Button size="md" variant="light" onClick={() => action.mutate('reopen')}>
                Reopen answers
              </Button>
            )
          )}
          {!last && (
            <Button
              size="md"
              onClick={() => {
                if (
                  ungradedHere &&
                  !window.confirm('Some answers here aren’t graded yet. Move on anyway?')
                )
                  return
                action.mutate('next')
              }}
              loading={action.isPending}
            >
              Next: {state.next_label}
            </Button>
          )}
          {last && (
            <Button
              size="md"
              color="red"
              onClick={() => {
                if (
                  (state.ungraded ?? 0) > 0 &&
                  !window.confirm(`${state.ungraded} answers aren't graded. End anyway?`)
                )
                  return
                action.mutate('end')
              }}
            >
              End the game
            </Button>
          )}
        </Group>
        <Group justify="space-between">
          <Button
            size="xs"
            variant="subtle"
            disabled={!state.step_index}
            onClick={() => action.mutate('back')}
          >
            ← Back a step
          </Button>
          {(state.ungraded ?? 0) > 0 && (
            <Text size="xs" c="gold">
              {state.ungraded} answers still to grade in this game
            </Text>
          )}
          {!last && (
            <Button
              size="xs"
              variant="subtle"
              color="red"
              onClick={() => {
                if (window.confirm('End the game now? Scores will be final.')) action.mutate('end')
              }}
            >
              End early
            </Button>
          )}
        </Group>
        <ErrorNote error={action.error} />
      </Stack>
    </Card>
  )
}

function Lobby({ state, eventId }: { state: LiveState; eventId: string }) {
  const start = useApi(
    () =>
      call(
        api.POST('/api/events/{event_id}/live/start', { params: { path: { event_id: eventId } } }),
      ),
    { liveFor: eventId, invalidate: [keys.event(eventId)] },
  )
  return (
    <Stack>
      <Card>
        <Stack>
          <Title order={3}>Teams ({state.teams.length})</Title>
          {state.teams.length === 0 ? (
            <Text c="dimmed">No one has said they're playing yet.</Text>
          ) : (
            <Group gap="xs">
              {state.teams.map((t) => (
                <Badge key={t.user_id} size="lg" variant="light">
                  {t.name}
                </Badge>
              ))}
            </Group>
          )}
          {state.status === 'cancelled' && <Alert color="red">This game was cancelled.</Alert>}
          {state.role === 'host' && state.status === 'scheduled' && (
            <>
              {state.problems && state.problems.length > 0 ? (
                <Alert color="gold" variant="light" title="Finish the questions first">
                  <List size="sm">
                    {state.problems.slice(0, 5).map((p) => (
                      <List.Item key={p}>{p}</List.Item>
                    ))}
                  </List>
                  <Button component={Link} to={`/events/${eventId}/questions`} mt="sm" size="xs">
                    Edit questions
                  </Button>
                </Alert>
              ) : (
                <Button
                  size="lg"
                  color="gold"
                  c="dark.9"
                  onClick={() => start.mutate(undefined)}
                  loading={start.isPending}
                >
                  Start the game
                </Button>
              )}
              <ErrorNote error={start.error} />
            </>
          )}
          {state.role !== 'host' && state.status === 'scheduled' && (
            <Text>
              {state.role === 'player'
                ? "You're in. This page updates by itself when the host starts."
                : "You're watching. This page updates by itself when the host starts."}
            </Text>
          )}
        </Stack>
      </Card>
    </Stack>
  )
}

function Results({ state }: { state: LiveState }) {
  const top = state.scoreboard[0]
  const winners = state.scoreboard.filter((r) => top && r.total === top.total)
  return (
    <Stack>
      {top && (
        <Card ta="center" p="xl">
          <Text c="dimmed">{winners.length > 1 ? 'A tie at the top!' : 'The winner is'}</Text>
          <Title order={1} c="gold.4">
            {winners.map((w) => w.team.name).join(' & ')}
          </Title>
          <Text fz="xl" fw={800}>
            {top.total} points
          </Text>
        </Card>
      )}
      <Scoreboard state={state} />
    </Stack>
  )
}

export function LivePage() {
  const { eventId = '' } = useParams()
  const { data: event } = useEvent(eventId)
  const { data: state, isLoading, error } = useLive(eventId)
  if (isLoading) return <Loading />
  if (!state) return <ErrorNote error={error} />
  const isHost = state.role === 'host'
  const question = state.question
  const playing = state.status === 'live' && (state.step === 'question' || state.step === 'wager')
  return (
    <Stack gap="md">
      <div>
        <Text component={Link} to={`/events/${eventId}`} c="dimmed" size="sm">
          ← {event?.title ?? 'Event'}
        </Text>
        <Group justify="space-between" align="center">
          <Title order={2}>{state.step === 'lobby' ? 'Game room' : stepTitle(state)}</Title>
          <Group gap="xs">
            <Badge variant="light">{state.role}</Badge>
            {state.status === 'live' && state.phase && (
              <Badge color={state.phase === 'open' ? 'green' : 'gray'}>
                {state.phase === 'open' ? 'answers open' : 'locked'}
              </Badge>
            )}
          </Group>
        </Group>
        {state.status === 'live' && state.step_index != null && (
          <Progress value={(100 * (state.step_index + 1)) / state.step_count} size="sm" mt={6} />
        )}
      </div>
      <ErrorNote error={error} />

      {state.step === 'lobby' && <Lobby state={state} eventId={eventId} />}

      {playing && isHost && <HostControls state={state} eventId={eventId} />}

      {playing && question && (
        <Card>
          <QuestionView question={question} state={state} />
          {question.kind === 'mc' && (isHost || state.role === 'spectator') && (
            <div style={{ marginTop: 12 }}>
              <Choices question={question} state={state} />
            </div>
          )}
        </Card>
      )}
      {playing && !question && state.step === 'wager' && !isHost && state.role === 'spectator' && (
        <Card>
          <Text>Teams are placing their wagers on the final question…</Text>
        </Card>
      )}
      {playing && isHost && state.step === 'wager' && (
        <Card>
          <Text>
            Teams are wagering. The final question stays hidden until you move on. Their total so
            far is the most they can stake.
          </Text>
        </Card>
      )}

      {playing && state.role === 'player' && (
        <PlayerInput
          // A new question, or a saved answer, starts the inputs over from the server's copy.
          key={`${state.step}:${question?.id}:${state.my_answer?.text}:${state.my_answer?.wager}`}
          state={state}
          eventId={eventId}
        />
      )}
      {playing &&
        state.role === 'player' &&
        question?.kind === 'mc' &&
        state.phase === 'closed' && <Verdict state={state} />}
      {playing && isHost && <HostAnswers state={state} eventId={eventId} />}

      {state.step === 'results' && isHost && <HostControls state={state} eventId={eventId} />}
      {(state.step === 'results' || state.step === 'over') && <Results state={state} />}
      {playing && <Scoreboard state={state} compact={!isHost} />}
    </Stack>
  )
}
