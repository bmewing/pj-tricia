"""The host's questions: writing, ordering and importing them before the game.

Nobody but the host reads them until the game is over; during the game each question
reaches players only through the live state, one step at a time.
"""

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import EventAccess, event_access, require_host
from app.auth import CurrentUser
from app.db import SessionDep
from app.game.steps import CHOICES, in_order, kinds_for, points_for, problems
from app.models import EventStatus, Question, QuestionKind, User

router = APIRouter(tags=["questions"])

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
Choice = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
AnswerText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Round = Annotated[int, Field(ge=1, le=4)]
ChoiceIndex = Annotated[int, Field(ge=0, lt=CHOICES)]

LOCKED = HTTPException(status.HTTP_409_CONFLICT, "Questions can't change once the game starts.")
QUESTION_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")


class QuestionRead(BaseModel):
    id: uuid.UUID
    round: int
    kind: QuestionKind
    position: int
    text: str
    choices: list[str] | None
    correct_choice: int | None
    answer_text: str | None
    points: int | None  # null for the double dare and the final

    @classmethod
    def of(cls, question: Question) -> "QuestionRead":
        return cls(
            id=question.id,
            round=question.round,
            kind=question.kind,
            position=question.position,
            text=question.text,
            choices=question.choices,
            correct_choice=question.correct_choice,
            answer_text=question.answer_text,
            points=points_for(question),
        )


class QuestionsRead(BaseModel):
    questions: list[QuestionRead]  # in game order
    problems: list[str]  # empty: ready to start


class QuestionCreate(BaseModel):
    round: Round
    kind: QuestionKind
    text: Text = ""
    choices: Annotated[list[Choice], Field(min_length=CHOICES, max_length=CHOICES)] | None = None
    correct_choice: ChoiceIndex | None = None
    answer_text: AnswerText | None = None


class QuestionUpdate(BaseModel):
    text: Text | None = None
    choices: Annotated[list[Choice], Field(min_length=CHOICES, max_length=CHOICES)] | None = None
    correct_choice: ChoiceIndex | None = None
    answer_text: AnswerText | None = None


class Reorder(BaseModel):
    round: Round
    ids: list[uuid.UUID]


class CsvImport(BaseModel):
    csv: Annotated[str, StringConstraints(max_length=200_000)]
    replace: bool = False  # true: clear existing questions first


async def _questions(session: AsyncSession, event_id: uuid.UUID) -> list[Question]:
    return in_order(await session.scalars(select(Question).where(Question.event_id == event_id)))


async def _read(session: AsyncSession, event_id: uuid.UUID) -> QuestionsRead:
    questions = await _questions(session, event_id)
    return QuestionsRead(
        questions=[QuestionRead.of(q) for q in questions], problems=problems(questions)
    )


async def _host_editing(session: AsyncSession, event_id: uuid.UUID, user: User) -> EventAccess:
    access = await event_access(session, event_id, user)
    require_host(access)
    if access.event.status not in (EventStatus.SCHEDULED, EventStatus.CANCELLED):
        raise LOCKED
    return access


async def _host_question(session: AsyncSession, question_id: uuid.UUID, user: User) -> Question:
    question = await session.get(Question, question_id)
    if question is None:
        raise QUESTION_NOT_FOUND
    try:
        await _host_editing(session, question.event_id, user)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            raise
        raise QUESTION_NOT_FOUND from exc
    return question


def _check_kind(round_: int, kind: QuestionKind) -> None:
    if kind not in kinds_for(round_):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Rounds 1-3 hold multiple choice and a Double Down Dare; round 4 holds free-form "
            "questions and the Do or Die Dare.",
        )


def _fill(question: Question, body: QuestionCreate | QuestionUpdate) -> None:
    sent = body.model_fields_set
    if body.text is not None:
        question.text = body.text
    if question.kind == QuestionKind.MC:
        if body.choices is not None:
            question.choices = list(body.choices)
        if "correct_choice" in sent:
            question.correct_choice = body.correct_choice
        if question.choices is None:
            question.choices = [""] * CHOICES
    elif "answer_text" in sent:
        question.answer_text = body.answer_text or None


async def _add(session: AsyncSession, event_id: uuid.UUID, body: QuestionCreate) -> Question:
    _check_kind(body.round, body.kind)
    if body.kind in (QuestionKind.DOUBLE_DARE, QuestionKind.FINAL):
        taken = await session.scalar(
            select(Question.id).where(
                Question.event_id == event_id,
                Question.round == body.round,
                Question.kind == body.kind,
            )
        )
        if taken is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Round {body.round} already has that question."
            )
        position = 0
    else:
        last = await session.scalar(
            select(func.max(Question.position)).where(
                Question.event_id == event_id,
                Question.round == body.round,
                Question.kind == body.kind,
            )
        )
        position = (last or 0) + 1
    question = Question(
        event_id=event_id, round=body.round, kind=body.kind, position=position, text=""
    )
    _fill(question, body)
    session.add(question)
    await session.flush()
    return question


@router.get("/events/{event_id}/questions")
async def list_questions(
    event_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> QuestionsRead:
    """The host's questions, with what's missing before the game can start. Once the game
    is over, everyone at the event can look back over them."""
    access = await event_access(session, event_id, user)
    if not access.is_host and access.event.status != EventStatus.FINISHED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the host sees the questions.")
    return await _read(session, event_id)


@router.post("/events/{event_id}/questions", status_code=status.HTTP_201_CREATED)
async def create_question(
    event_id: uuid.UUID, body: QuestionCreate, user: CurrentUser, session: SessionDep
) -> QuestionRead:
    await _host_editing(session, event_id, user)
    question = await _add(session, event_id, body)
    await session.commit()
    return QuestionRead.of(question)


@router.patch("/questions/{question_id}")
async def update_question(
    question_id: uuid.UUID, body: QuestionUpdate, user: CurrentUser, session: SessionDep
) -> QuestionRead:
    question = await _host_question(session, question_id, user)
    _fill(question, body)
    await session.commit()
    return QuestionRead.of(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    question = await _host_question(session, question_id, user)
    await session.delete(question)
    await session.commit()


@router.post("/events/{event_id}/questions/reorder")
async def reorder_questions(
    event_id: uuid.UUID, body: Reorder, user: CurrentUser, session: SessionDep
) -> QuestionsRead:
    """Put a round's regular questions in this order (every one of them, once)."""
    await _host_editing(session, event_id, user)
    regular, _special = kinds_for(body.round)
    questions = {
        q.id: q
        for q in await session.scalars(
            select(Question).where(
                Question.event_id == event_id,
                Question.round == body.round,
                Question.kind == regular,
            )
        )
    }
    if sorted(map(str, body.ids)) != sorted(map(str, questions)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "List each of the round's questions once."
        )
    for position, question_id in enumerate(body.ids, start=1):
        questions[question_id].position = position
    await session.commit()
    return await _read(session, event_id)


KIND_NAMES = {
    "mc": QuestionKind.MC,
    "multiple choice": QuestionKind.MC,
    "dare": QuestionKind.DOUBLE_DARE,
    "double dare": QuestionKind.DOUBLE_DARE,
    "double_dare": QuestionKind.DOUBLE_DARE,
    "double down dare": QuestionKind.DOUBLE_DARE,
    "free": QuestionKind.FREE,
    "final": QuestionKind.FINAL,
    "wager": QuestionKind.FINAL,
    "do or die": QuestionKind.FINAL,
    "do or die dare": QuestionKind.FINAL,
}
LETTERS = "ABCD"


def parse_csv(text: str) -> list[QuestionCreate]:
    """Rows of round, kind, question, A, B, C, D, answer (a header row is optional).

    Kind is mc, dare, free or final; left blank it's mc in rounds 1-3 and free in round 4.
    For multiple choice the answer is the letter (or the text) of the right choice; the
    choice columns are left blank for the others.
    """
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    parsed: list[QuestionCreate] = []
    errors: list[str] = []
    for line, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row] + [""] * 8
        if not any(cells):
            continue
        if line == 1 and cells[0].lower() == "round":
            continue
        try:
            round_ = int(cells[0])
            if not 1 <= round_ <= 4:
                raise ValueError
        except ValueError:
            errors.append(f"Line {line}: round must be 1, 2, 3 or 4.")
            continue
        kind_name = cells[1].lower()
        if kind_name:
            kind = KIND_NAMES.get(kind_name)
            if kind is None:
                errors.append(f"Line {line}: kind must be mc, dare, free or final.")
                continue
        else:
            kind = kinds_for(round_)[0]
        if kind not in kinds_for(round_):
            errors.append(f"Line {line}: round {round_} can't hold a {kind_name} question.")
            continue
        question, choices, answer = cells[2], cells[3:7], cells[7]
        if kind == QuestionKind.MC:
            correct = None
            if len(answer) == 1 and answer.upper() in LETTERS:
                correct = LETTERS.index(answer.upper())
            elif answer:
                lowered = [c.lower() for c in choices]
                correct = lowered.index(answer.lower()) if answer.lower() in lowered else None
            if correct is None:
                errors.append(f"Line {line}: the answer should be A, B, C or D.")
                continue
            parsed.append(
                QuestionCreate(
                    round=round_, kind=kind, text=question, choices=choices, correct_choice=correct
                )
            )
        else:
            parsed.append(
                QuestionCreate(round=round_, kind=kind, text=question, answer_text=answer)
            )
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, " ".join(errors[:10]))
    return parsed


@router.post("/events/{event_id}/questions/import")
async def import_questions(
    event_id: uuid.UUID, body: CsvImport, user: CurrentUser, session: SessionDep
) -> QuestionsRead:
    await _host_editing(session, event_id, user)
    parsed = parse_csv(body.csv)
    if body.replace:
        await session.execute(delete(Question).where(Question.event_id == event_id))
    for question in parsed:
        await _add(session, event_id, question)
    await session.commit()
    return await _read(session, event_id)
