import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { LiveState } from '../api/client'
import { pollInterval } from '../api/queries'
import { mockApi, signIn } from '../test/mocks'
import { renderWithProviders } from '../test/render'
import { LivePage } from './LivePage'

const EVENT = '11111111-1111-4111-8111-111111111111'
const ME = '22222222-2222-4222-8222-222222222222'
const OTHER = '33333333-3333-4333-8333-333333333333'

function row(id: string, name: string, total: number) {
  return {
    team: { user_id: id, name },
    rounds: [1, 2, 3, 4].map(() => ({ base: 0, dare: 'none' as const, points: 0 })),
    wager: null,
    final: 'none' as const,
    final_points: 0,
    total,
    pending: 0,
  }
}

function state(overrides: Partial<LiveState> = {}): LiveState {
  return {
    version: 3,
    status: 'live',
    role: 'player',
    step: 'question',
    step_index: 0,
    step_count: 12,
    phase: 'open',
    round: 1,
    question: {
      id: '44444444-4444-4444-8444-444444444444',
      round: 1,
      kind: 'mc',
      number: 1,
      points: 5,
      text: 'Which planet is closest to the sun?',
      choices: ['Venus', 'Mercury', 'Mars', 'Earth'],
    },
    wager_question_id: null,
    reveal: null,
    my_answer: null,
    my_score: row(ME, 'The Smiths', 0),
    max_wager: null,
    scoreboard: [row(ME, 'The Smiths', 0), row(OTHER, 'Ben', 0)],
    teams: [
      { user_id: OTHER, name: 'Ben' },
      { user_id: ME, name: 'The Smiths' },
    ],
    answered: 0,
    answers: null,
    ungraded: null,
    next_label: null,
    problems: null,
    ...overrides,
  }
}

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })

function renderLive() {
  return renderWithProviders(
    <Routes>
      <Route path="/events/:eventId/play" element={<LivePage />} />
    </Routes>,
    { route: `/events/${EVENT}/play` },
  )
}

describe('LivePage', () => {
  it('lets a player pick a choice and sends it to the server', async () => {
    signIn()
    let sent: unknown = null
    mockApi({
      [`GET /api/events/${EVENT}`]: () => json({ title: 'Trivia' }),
      [`GET /api/events/${EVENT}/live`]: () => json(state()),
      [`PUT /api/events/${EVENT}/live/answer`]: async (request) => {
        sent = await request.json()
        return json(
          state({
            my_answer: { choice: 1, text: null, passed: false, wager: null, is_correct: null },
          }),
        )
      },
    })
    renderLive()
    await userEvent.click(await screen.findByRole('button', { name: /Mercury/ }))
    await waitFor(() =>
      expect(sent).toEqual({
        passed: false,
        question_id: '44444444-4444-4444-8444-444444444444',
        choice: 1,
      }),
    )
    expect(screen.getByText('Round 1 · Question 1 · 5 pts')).toBeInTheDocument()
  })

  it('offers a double dare pass and shows the round points at stake', async () => {
    signIn()
    const dare = state({
      question: {
        id: '55555555-5555-4555-8555-555555555555',
        round: 2,
        kind: 'double_dare',
        number: null,
        points: null,
        text: 'Capital of Australia?',
        choices: null,
      },
      my_score: {
        ...row(ME, 'The Smiths', 20),
        rounds: [
          { base: 0, dare: 'none', points: 0 },
          { base: 20, dare: 'none', points: 20 },
          { base: 0, dare: 'none', points: 0 },
          { base: 0, dare: 'none', points: 0 },
        ],
      },
    })
    mockApi({
      [`GET /api/events/${EVENT}`]: () => json({ title: 'Trivia' }),
      [`GET /api/events/${EVENT}/live`]: () => json(dare),
    })
    renderLive()
    expect(await screen.findByRole('button', { name: 'Pass' })).toBeInTheDocument()
    expect(screen.getByText(/Your round 2 points/)).toHaveTextContent('20')
  })

  it('shows the host the answer key and grading buttons', async () => {
    signIn()
    const hosting = state({
      role: 'host',
      question: {
        id: '66666666-6666-4666-8666-666666666666',
        round: 4,
        kind: 'free',
        number: 1,
        points: 20,
        text: 'Who painted the Mona Lisa?',
        choices: null,
      },
      reveal: { correct_choice: null, answer_text: 'Leonardo da Vinci' },
      answers: [
        {
          id: '77777777-7777-4777-8777-777777777777',
          team: { user_id: OTHER, name: 'Ben' },
          choice: null,
          text: 'da Vinci',
          passed: false,
          wager: null,
          is_correct: null,
          submitted_at: '2026-11-20T00:00:00Z',
        },
      ],
      answered: 1,
      next_label: 'Round 4, question 2',
      my_score: null,
    })
    mockApi({
      [`GET /api/events/${EVENT}`]: () => json({ title: 'Trivia' }),
      [`GET /api/events/${EVENT}/live`]: () => json(hosting),
    })
    renderLive()
    expect(await screen.findByText('Leonardo da Vinci')).toBeInTheDocument()
    expect(screen.getByText('da Vinci')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark right' })).toBeInTheDocument()
    expect(screen.getByText(/Waiting on: The Smiths/)).toBeInTheDocument()
  })
})

describe('pollInterval', () => {
  it('polls faster for a host taking answers and slowly once the game is over', () => {
    expect(pollInterval(state({ role: 'host', phase: 'open' }))).toBe(1500)
    expect(pollInterval(state())).toBe(2000)
    expect(pollInterval(state({ status: 'finished' }))).toBe(15000)
  })
})
