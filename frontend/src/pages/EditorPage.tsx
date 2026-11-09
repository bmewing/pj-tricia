import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Code,
  Group,
  List,
  Modal,
  Radio,
  Stack,
  Tabs,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { api, call, type QuestionRead, type QuestionsRead } from '../api/client'
import { keys, useApi, useEvent, useQuestions } from '../api/queries'
import { ErrorNote, Loading } from '../components/common'
import { LETTERS } from '../components/format'

type Kind = QuestionRead['kind']
const ROUNDS = [1, 2, 3, 4] as const
const POINTS: Record<number, number> = { 1: 5, 2: 10, 3: 15, 4: 20 }

function kindsFor(round: number): { regular: Kind; special: Kind } {
  return round === 4
    ? { regular: 'free', special: 'final' }
    : { regular: 'mc', special: 'double_dare' }
}

function QuestionCard({
  question,
  eventId,
  label,
  onMove,
}: {
  question: QuestionRead
  eventId: string
  label: string
  onMove?: (direction: -1 | 1) => void
}) {
  const [text, setText] = useState(question.text)
  const [choices, setChoices] = useState(question.choices ?? ['', '', '', ''])
  const [correct, setCorrect] = useState<number | null>(question.correct_choice)
  const [answer, setAnswer] = useState(question.answer_text ?? '')
  const invalidate = [keys.questions(eventId), keys.event(eventId)]
  const save = useApi(
    () =>
      call(
        api.PATCH('/api/questions/{question_id}', {
          params: { path: { question_id: question.id } },
          body:
            question.kind === 'mc'
              ? { text, choices, correct_choice: correct }
              : { text, answer_text: answer || null },
        }),
      ),
    { invalidate },
  )
  const remove = useApi(
    () =>
      call(
        api.DELETE('/api/questions/{question_id}', {
          params: { path: { question_id: question.id } },
        }),
      ),
    { invalidate },
  )
  const dirty =
    text !== question.text ||
    (question.kind === 'mc'
      ? JSON.stringify(choices) !== JSON.stringify(question.choices ?? ['', '', '', '']) ||
        correct !== question.correct_choice
      : answer !== (question.answer_text ?? ''))

  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="xs">
            <Text fw={700}>{label}</Text>
            {question.points != null && <Badge variant="light">{question.points} pts</Badge>}
          </Group>
          <Group gap={4}>
            {onMove && (
              <>
                <ActionIcon variant="subtle" aria-label="Move up" onClick={() => onMove(-1)}>
                  ↑
                </ActionIcon>
                <ActionIcon variant="subtle" aria-label="Move down" onClick={() => onMove(1)}>
                  ↓
                </ActionIcon>
              </>
            )}
            <ActionIcon
              variant="subtle"
              color="red"
              aria-label="Delete question"
              onClick={() => {
                if (window.confirm('Delete this question?')) remove.mutate(undefined)
              }}
            >
              ✕
            </ActionIcon>
          </Group>
        </Group>
        <Textarea
          placeholder="The question"
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          autosize
          minRows={2}
        />
        {question.kind === 'mc' ? (
          <Radio.Group
            value={correct === null ? '' : String(correct)}
            onChange={(v) => setCorrect(Number(v))}
            label="Choices (pick the right one)"
          >
            <Stack gap={6} mt={4}>
              {LETTERS.map((letter, i) => (
                <Group key={letter} gap="xs" wrap="nowrap">
                  <Radio value={String(i)} aria-label={`${letter} is correct`} />
                  <TextInput
                    style={{ flex: 1 }}
                    leftSection={<Text fw={700}>{letter}</Text>}
                    value={choices[i]}
                    onChange={(e) => {
                      const value = e.currentTarget.value
                      setChoices((old) => old.map((c, j) => (j === i ? value : c)))
                    }}
                  />
                </Group>
              ))}
            </Stack>
          </Radio.Group>
        ) : (
          <TextInput
            label="Answer"
            description="You'll see this next to each team's answer. Exact matches are marked right for you."
            value={answer}
            onChange={(e) => setAnswer(e.currentTarget.value)}
          />
        )}
        {dirty && (
          <Button w="fit-content" loading={save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        )}
        <ErrorNote error={save.error ?? remove.error} />
      </Stack>
    </Card>
  )
}

function RoundPanel({
  round,
  data,
  eventId,
}: {
  round: number
  data: QuestionsRead
  eventId: string
}) {
  const { regular, special } = kindsFor(round)
  const inRound = data.questions.filter((q) => q.round === round)
  const regulars = inRound.filter((q) => q.kind === regular)
  const specialQ = inRound.find((q) => q.kind === special)
  const invalidate = [keys.questions(eventId), keys.event(eventId)]
  const add = useApi(
    (kind: Kind) =>
      call(
        api.POST('/api/events/{event_id}/questions', {
          params: { path: { event_id: eventId } },
          body: { round, kind, text: '' },
        }),
      ),
    { invalidate },
  )
  const reorder = useApi(
    (ids: string[]) =>
      call(
        api.POST('/api/events/{event_id}/questions/reorder', {
          params: { path: { event_id: eventId } },
          body: { round, ids },
        }),
      ),
    { invalidate },
  )
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= regulars.length) return
    const ids = regulars.map((q) => q.id)
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorder.mutate(ids)
  }
  const specialName = special === 'final' ? 'Do or Die Dare' : 'Double Down Dare'
  return (
    <Stack mt="md">
      <Text c="dimmed" size="sm">
        {round === 4
          ? 'Free-form questions worth 20 each. You mark each answer right or wrong. Then the Do or Die Dare: teams wager up to their total before they see it.'
          : `Multiple choice, ${POINTS[round]} points each. Then the Double Down Dare: a free-form question teams can pass on. Right doubles the round's points; wrong loses them.`}
      </Text>
      {regulars.map((q, i) => (
        <QuestionCard
          key={JSON.stringify(q)}
          question={q}
          eventId={eventId}
          label={`Question ${i + 1}`}
          onMove={(d) => move(i, d)}
        />
      ))}
      <Button
        variant="light"
        w="fit-content"
        onClick={() => add.mutate(regular)}
        loading={add.isPending}
      >
        Add a {regular === 'mc' ? 'multiple-choice' : 'free-form'} question
      </Button>
      {specialQ ? (
        <QuestionCard
          key={JSON.stringify(specialQ)}
          question={specialQ}
          eventId={eventId}
          label={specialName}
        />
      ) : (
        <Button variant="outline" w="fit-content" color="gold" onClick={() => add.mutate(special)}>
          Add the {specialName}
        </Button>
      )}
      <ErrorNote error={add.error ?? reorder.error} />
    </Stack>
  )
}

const SAMPLE = `round,kind,question,A,B,C,D,answer
1,mc,Which planet is closest to the sun?,Venus,Mercury,Mars,Earth,B
1,dare,What is the capital of Australia?,,,,,Canberra
4,free,Who painted the Mona Lisa?,,,,,Leonardo da Vinci
4,final,What is the tallest mountain on Earth?,,,,,Everest`

function ImportModal({
  eventId,
  opened,
  onClose,
}: {
  eventId: string
  opened: boolean
  onClose: () => void
}) {
  const [csv, setCsv] = useState('')
  const [replace, setReplace] = useState(false)
  const run = useApi(
    () =>
      call(
        api.POST('/api/events/{event_id}/questions/import', {
          params: { path: { event_id: eventId } },
          body: { csv, replace },
        }),
      ),
    { invalidate: [keys.questions(eventId), keys.event(eventId)] },
  )
  return (
    <Modal opened={opened} onClose={onClose} title="Import from a spreadsheet" size="lg">
      <Stack>
        <Text size="sm">
          Paste CSV rows (or pick a .csv file) with columns{' '}
          <Code>round, kind, question, A, B, C, D, answer</Code>. Kind is <Code>mc</Code>,{' '}
          <Code>dare</Code> (the Double Down Dare), <Code>free</Code> or <Code>final</Code> (the Do
          or Die Dare). For multiple choice the answer is the letter.
        </Text>
        <Code block>{SAMPLE}</Code>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => {
            const file = e.currentTarget.files?.[0]
            if (file) void file.text().then(setCsv)
          }}
        />
        <Textarea
          value={csv}
          onChange={(e) => setCsv(e.currentTarget.value)}
          autosize
          minRows={6}
        />
        <Checkbox
          label="Replace the questions I already have"
          checked={replace}
          onChange={(e) => setReplace(e.currentTarget.checked)}
        />
        <Group justify="flex-end">
          <Button
            disabled={!csv.trim()}
            loading={run.isPending}
            onClick={() =>
              run.mutate(undefined, {
                onSuccess: () => {
                  setCsv('')
                  onClose()
                },
              })
            }
          >
            Import
          </Button>
        </Group>
        <ErrorNote error={run.error} />
      </Stack>
    </Modal>
  )
}

export function EditorPage() {
  const { eventId = '' } = useParams()
  const { data: event } = useEvent(eventId)
  const isHost = event?.me.game_role === 'host'
  const { data, isLoading, error } = useQuestions(eventId, isHost)
  const [importing, setImporting] = useState(false)
  if (!event || (isHost && isLoading)) return <Loading />
  if (!isHost) return <Alert color="red">Only the host can see the questions.</Alert>
  if (!data) return <ErrorNote error={error} />
  const locked = event.status !== 'scheduled' && event.status !== 'cancelled'
  return (
    <Stack gap="md">
      <div>
        <Text component={Link} to={`/events/${eventId}`} c="dimmed" size="sm">
          ← {event.title}
        </Text>
        <Group justify="space-between">
          <Title order={1}>Questions</Title>
          {!locked && (
            <Button variant="light" onClick={() => setImporting(true)}>
              Import CSV
            </Button>
          )}
        </Group>
        <Text size="sm" c="dimmed">
          Only you can see these. Players see each question when you reach it in the game.
        </Text>
      </div>
      {locked ? (
        <Alert color="gold">The game has started, so the questions are locked.</Alert>
      ) : data.problems.length > 0 ? (
        <Alert color="gold" variant="light" title="Before you can start">
          <List size="sm">
            {data.problems.slice(0, 8).map((p) => (
              <List.Item key={p}>{p}</List.Item>
            ))}
          </List>
        </Alert>
      ) : (
        <Alert color="green" variant="light">
          All set. Start the game from the game room when everyone's there.
        </Alert>
      )}
      <Tabs defaultValue="1" keepMounted={false}>
        <Tabs.List grow>
          {ROUNDS.map((r) => (
            <Tabs.Tab key={r} value={String(r)}>
              Round {r}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        {ROUNDS.map((r) => (
          <Tabs.Panel key={r} value={String(r)}>
            <RoundPanel round={r} data={data} eventId={eventId} />
          </Tabs.Panel>
        ))}
      </Tabs>
      <ImportModal eventId={eventId} opened={importing} onClose={() => setImporting(false)} />
    </Stack>
  )
}
