"""The game as it's played: the host walks through the steps, players answer, everyone polls.

Clients poll GET /events/{id}/live?since=<version>. The event's version goes up on every
change anyone could see, so an unchanged poll is a bare 204. What comes back depends on who
asks: players and spectators never get an answer key, or anything about a question, before
the host reaches it.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import EventAccess, GameRole, bump, event_access, is_player, require_host
from app.auth import CurrentUser
from app.db import SessionDep
from app.game.scoring import Outcome, TeamScore, max_wager, score
from app.game.steps import CHOICES, Step, StepType, build_steps, points_for, problems
from app.models import (
    Answer,
    Event,
    EventAttendee,
    EventStatus,
    Question,
    QuestionKind,
    StepPhase,
    User,
)

router = APIRouter(tags=["live"])

AnswerText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]

NOT_LIVE = HTTPException(status.HTTP_409_CONFLICT, "The game isn't on.")
CLOSED = HTTPException(status.HTTP_409_CONFLICT, "Answers are locked for this one.")
MOVED_ON = HTTPException(status.HTTP_409_CONFLICT, "The host has moved on to another question.")

LiveStep = Literal["lobby", "question", "wager", "results", "over"]


class TeamRef(BaseModel):
    user_id: uuid.UUID
    name: str


class LiveQuestion(BaseModel):
    id: uuid.UUID
    round: int
    kind: QuestionKind
    number: int | None  # among the round's regular questions
    points: int | None
    text: str
    choices: list[str] | None


class Reveal(BaseModel):
    correct_choice: int | None
    answer_text: str | None


class MyAnswer(BaseModel):
    choice: int | None
    text: str | None
    passed: bool
    wager: int | None
    is_correct: bool | None  # only once answers are locked


class HostAnswer(BaseModel):
    id: uuid.UUID
    team: TeamRef
    choice: int | None
    text: str | None
    passed: bool
    wager: int | None
    is_correct: bool | None
    submitted_at: datetime


class RoundRow(BaseModel):
    base: int
    dare: Outcome
    points: int


class ScoreRow(BaseModel):
    team: TeamRef
    rounds: list[RoundRow]
    wager: int | None  # others' wagers stay hidden until the final is revealed
    final: Outcome
    final_points: int
    total: int
    pending: int


class LiveState(BaseModel):
    version: int
    status: EventStatus
    role: GameRole
    step: LiveStep
    step_index: int | None
    step_count: int
    phase: StepPhase | None
    round: int | None
    question: LiveQuestion | None
    # During the wager: which question the wager is for (its text stays hidden).
    wager_question_id: uuid.UUID | None
    reveal: Reveal | None  # the host always; everyone else once locked
    my_answer: MyAnswer | None
    my_score: ScoreRow | None
    max_wager: int | None  # players, during the wager
    scoreboard: list[ScoreRow]
    teams: list[TeamRef]  # everyone playing
    answered: int  # teams that have answered the current step
    # The host only:
    answers: list[HostAnswer] | None
    ungraded: int | None  # free-form answers anywhere in the game still to grade
    next_label: str | None
    problems: list[str] | None


class Submit(BaseModel):
    question_id: uuid.UUID
    choice: Annotated[int, Field(ge=0, lt=CHOICES)] | None = None
    text: AnswerText | None = None
    passed: bool = False
    wager: Annotated[int, Field(ge=0)] | None = None


class Grade(BaseModel):
    is_correct: bool | None


def normalize(text: str) -> str:
    text = re.sub(r"[^\w\s]", "", text.lower())
    text = " ".join(text.split())
    return text.removeprefix("the ").removeprefix("a ").removeprefix("an ")


def auto_grade(question: Question, text: str) -> bool | None:
    """An exact match (ignoring case, punctuation and a leading article) counts as right;
    anything else waits for the host."""
    expected = normalize(question.answer_text or "")
    return True if expected and normalize(text) == expected else None


def step_label(step: Step) -> str:
    if step.type == "results":
        return "Final results"
    if step.type == "wager":
        return "Do or Die Dare wagers"
    assert step.question is not None
    kind = step.question.kind
    if kind == QuestionKind.DOUBLE_DARE:
        return f"Round {step.round} Double Down Dare"
    if kind == QuestionKind.FINAL:
        return "Do or Die Dare"
    return f"Round {step.round}, question {step.number}"


class Game:
    """Everything about one event's game, loaded once per request."""

    def __init__(
        self,
        event: Event,
        questions: list[Question],
        answers: list[Answer],
        attendees: list[EventAttendee],
        users: dict[uuid.UUID, User],
    ) -> None:
        self.event = event
        self.questions = questions
        self.answers = answers
        self.steps = build_steps(questions)
        self.attendees = {a.user_id: a for a in attendees}
        self.users = users
        players = {a.user_id for a in attendees if is_player(a)}
        players |= {a.user_id for a in answers}
        players.discard(event.host_user_id)
        self.players = players

    @property
    def step(self) -> Step | None:
        index = self.event.current_step
        return self.steps[index] if index is not None and index < len(self.steps) else None

    @property
    def open_question(self) -> Question | None:
        step = self.step
        if step and step.type == "question" and self.event.step_phase == StepPhase.OPEN:
            return step.question
        return None

    def final_closed(self) -> bool:
        index = self.event.current_step
        if index is None:
            return False
        if self.event.status == EventStatus.FINISHED:
            return True
        for i, step in enumerate(self.steps):
            if (
                step.type == "question"
                and step.question
                and step.question.kind == QuestionKind.FINAL
            ):
                return index > i or (index == i and self.event.step_phase == StepPhase.CLOSED)
        return False

    def scores(self) -> dict[uuid.UUID, TeamScore]:
        hidden = [self.open_question.id] if self.open_question else []
        return score(
            self.questions,
            self.answers,
            self.players,
            hidden=hidden,
            final_closed=self.final_closed(),
        )

    def team(self, user_id: uuid.UUID) -> TeamRef:
        attendee = self.attendees.get(user_id)
        user = self.users.get(user_id)
        name = (attendee.team_name if attendee else None) or (user.display_name if user else "?")
        return TeamRef(user_id=user_id, name=name)

    def answers_to(self, question: Question) -> list[Answer]:
        return [a for a in self.answers if a.question_id == question.id]


async def load_game(session: AsyncSession, event: Event) -> Game:
    # Fresh from the database, not what this session saw earlier in the request.
    fresh = {"populate_existing": True}
    questions = list(
        await session.scalars(
            select(Question).where(Question.event_id == event.id).execution_options(**fresh)
        )
    )
    answers = list(
        await session.scalars(
            select(Answer)
            .where(Answer.event_id == event.id)
            .order_by(Answer.submitted_at)
            .execution_options(**fresh)
        )
    )
    attendees = list(
        await session.scalars(
            select(EventAttendee)
            .where(EventAttendee.event_id == event.id)
            .execution_options(**fresh)
        )
    )
    ids = {a.user_id for a in attendees} | {a.user_id for a in answers}
    users = {u.id: u for u in await session.scalars(select(User).where(User.id.in_(ids)))}
    return Game(event, questions, answers, attendees, users)


def build_state(game: Game, access: EventAccess) -> LiveState:
    event = game.event
    role = access.game_role
    me = access.user.id
    is_host = role == "host"
    step = game.step
    phase = event.step_phase
    question = step.question if step else None
    on_step: StepType | None = step.type if step else None
    if event.status == EventStatus.SCHEDULED or event.status == EventStatus.CANCELLED:
        live_step: LiveStep = "lobby"
    elif event.status == EventStatus.FINISHED:
        live_step = "over"
    else:
        live_step = on_step or "lobby"

    shown_question = None
    reveal = None
    if question is not None and on_step == "question":
        shown_question = LiveQuestion(
            id=question.id,
            round=question.round,
            kind=question.kind,
            number=step.number if step else None,
            points=points_for(question),
            text=question.text,
            choices=question.choices if question.kind == QuestionKind.MC else None,
        )
        if is_host or phase == StepPhase.CLOSED:
            reveal = Reveal(
                correct_choice=question.correct_choice, answer_text=question.answer_text
            )

    scores = game.scores()
    final_shown = game.final_closed()

    def row(team: TeamScore) -> ScoreRow:
        return ScoreRow(
            team=game.team(team.user_id),
            rounds=[RoundRow(base=r.base, dare=r.dare, points=r.points) for r in team.rounds],
            wager=team.wager if (is_host or final_shown or team.user_id == me) else None,
            final=team.final,
            final_points=team.final_points,
            total=team.total,
            pending=team.pending,
        )

    board = sorted(scores.values(), key=lambda t: (-t.total, game.team(t.user_id).name.lower()))
    scoreboard = [row(t) for t in board]

    my_answer = None
    answered = 0
    current_answers: list[Answer] = []
    if question is not None and on_step in ("question", "wager"):
        current_answers = game.answers_to(question)
        if on_step == "wager":
            current_answers = [a for a in current_answers if a.wager is not None]
        else:
            current_answers = [
                a for a in current_answers if a.choice is not None or a.text or a.passed
            ]
        answered = len(current_answers)
        mine = next((a for a in game.answers_to(question) if a.user_id == me), None)
        if mine is not None:
            my_answer = MyAnswer(
                choice=mine.choice,
                text=mine.text,
                passed=mine.passed,
                wager=mine.wager,
                is_correct=mine.is_correct if phase == StepPhase.CLOSED else None,
            )

    next_label = None
    if is_host and event.current_step is not None and event.current_step + 1 < len(game.steps):
        next_label = step_label(game.steps[event.current_step + 1])

    return LiveState(
        version=event.version,
        status=event.status,
        role=role,
        step=live_step,
        step_index=event.current_step,
        step_count=len(game.steps),
        phase=phase,
        round=step.round if step else None,
        question=shown_question,
        wager_question_id=question.id if question is not None and on_step == "wager" else None,
        reveal=reveal,
        my_answer=my_answer,
        my_score=row(scores[me]) if me in scores else None,
        max_wager=max_wager(scores[me])
        if role == "player" and on_step == "wager" and me in scores
        else None,
        scoreboard=scoreboard,
        teams=sorted((game.team(p) for p in game.players), key=lambda t: t.name.lower()),
        answered=answered,
        answers=[
            HostAnswer(
                id=a.id,
                team=game.team(a.user_id),
                choice=a.choice,
                text=a.text,
                passed=a.passed,
                wager=a.wager,
                is_correct=a.is_correct,
                submitted_at=a.submitted_at,
            )
            for a in current_answers
        ]
        if is_host
        else None,
        ungraded=sum(t.pending for t in scores.values()) if is_host else None,
        next_label=next_label,
        problems=problems(game.questions) if is_host and live_step == "lobby" else None,
    )


@router.get(
    "/events/{event_id}/live",
    responses={204: {"description": "Nothing changed since that version"}},
)
async def read_live(
    event_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    response: Response,
    since: int | None = None,
) -> LiveState | None:
    access = await event_access(session, event_id, user)
    response.headers["Cache-Control"] = "no-store"
    if since is not None and since == access.event.version:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    game = await load_game(session, access.event)
    return build_state(game, access)


async def _hosting(session: AsyncSession, event_id: uuid.UUID, user: User) -> EventAccess:
    access = await event_access(session, event_id, user)
    require_host(access)
    return access


async def _respond(session: AsyncSession, access: EventAccess) -> LiveState:
    await bump(session, access.event.id)
    await session.commit()
    await session.refresh(access.event)
    return build_state(await load_game(session, access.event), access)


@router.post("/events/{event_id}/live/start")
async def start_game(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> LiveState:
    access = await _hosting(session, event_id, user)
    event = access.event
    if event.status != EventStatus.SCHEDULED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This game can't be started.")
    game = await load_game(session, event)
    found = problems(game.questions)
    if found:
        raise HTTPException(status.HTTP_409_CONFLICT, found[0])
    event.status = EventStatus.LIVE
    event.current_step = 0
    event.step_phase = StepPhase.OPEN
    event.started_at = datetime.now(UTC)
    return await _respond(session, access)


def _live(access: EventAccess) -> None:
    if access.event.status != EventStatus.LIVE:
        raise NOT_LIVE


@router.post("/events/{event_id}/live/close")
async def close_answers(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> LiveState:
    """Lock answers and show everyone the right one."""
    access = await _hosting(session, event_id, user)
    _live(access)
    access.event.step_phase = StepPhase.CLOSED
    return await _respond(session, access)


@router.post("/events/{event_id}/live/reopen")
async def reopen_answers(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> LiveState:
    access = await _hosting(session, event_id, user)
    _live(access)
    game = await load_game(session, access.event)
    if game.step is None or game.step.type == "results":
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing to reopen here.")
    access.event.step_phase = StepPhase.OPEN
    return await _respond(session, access)


@router.post("/events/{event_id}/live/next")
async def next_step(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> LiveState:
    """Lock the current step (if it isn't already) and open the next one."""
    access = await _hosting(session, event_id, user)
    _live(access)
    event = access.event
    game = await load_game(session, event)
    index = event.current_step or 0
    if index + 1 >= len(game.steps):
        raise HTTPException(status.HTTP_409_CONFLICT, "That was the last step. End the game.")
    event.current_step = index + 1
    following = game.steps[index + 1]
    event.step_phase = None if following.type == "results" else StepPhase.OPEN
    return await _respond(session, access)


@router.post("/events/{event_id}/live/back")
async def previous_step(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> LiveState:
    """Go back a step, with its answers locked (reopen them if needed)."""
    access = await _hosting(session, event_id, user)
    _live(access)
    event = access.event
    if not event.current_step:
        raise HTTPException(status.HTTP_409_CONFLICT, "This is the first step.")
    event.current_step -= 1
    event.step_phase = StepPhase.CLOSED
    return await _respond(session, access)


@router.post("/events/{event_id}/live/end")
async def end_game(event_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> LiveState:
    access = await _hosting(session, event_id, user)
    _live(access)
    game = await load_game(session, access.event)
    access.event.status = EventStatus.FINISHED
    access.event.finished_at = datetime.now(UTC)
    access.event.current_step = len(game.steps) - 1
    access.event.step_phase = None
    return await _respond(session, access)


@router.put("/events/{event_id}/live/answers/{answer_id}/grade")
async def grade_answer(
    event_id: uuid.UUID,
    answer_id: uuid.UUID,
    body: Grade,
    user: CurrentUser,
    session: SessionDep,
) -> LiveState:
    """Mark an answer right or wrong (null: ungraded). Any answer, until the game ends."""
    access = await _hosting(session, event_id, user)
    _live(access)
    answer = await session.get(Answer, answer_id)
    if answer is None or answer.event_id != event_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found")
    answer.is_correct = body.is_correct
    return await _respond(session, access)


@router.put("/events/{event_id}/live/answer")
async def submit_answer(
    event_id: uuid.UUID, body: Submit, user: CurrentUser, session: SessionDep
) -> LiveState:
    """Answer the open question, or stake the wager. You can change it until it locks."""
    access = await event_access(session, event_id, user)
    _live(access)
    if access.game_role != "player":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only players can answer.")
    event = access.event
    game = await load_game(session, event)
    step = game.step
    if step is None or step.question is None:
        raise MOVED_ON
    question = step.question
    if body.question_id != question.id:
        raise MOVED_ON
    if event.step_phase != StepPhase.OPEN:
        raise CLOSED

    answer = next((a for a in game.answers_to(question) if a.user_id == user.id), None)
    if answer is None:
        answer = Answer(event_id=event.id, question_id=question.id, user_id=user.id, passed=False)
        session.add(answer)

    if step.type == "wager":
        if body.wager is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "How much are you wagering?")
        limit = max_wager(game.scores()[user.id]) if user.id in game.players else 0
        if body.wager > limit:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"You can wager at most {limit}."
            )
        answer.wager = body.wager
    elif question.kind == QuestionKind.MC:
        if body.choice is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick an answer.")
        answer.choice = body.choice
        answer.is_correct = body.choice == question.correct_choice
    elif question.kind == QuestionKind.DOUBLE_DARE and body.passed:
        answer.passed = True
        answer.text = None
        answer.is_correct = None
    else:
        if not body.text:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Type an answer.")
        answer.passed = False
        answer.text = body.text
        answer.is_correct = auto_grade(question, body.text)
    return await _respond(session, access)
