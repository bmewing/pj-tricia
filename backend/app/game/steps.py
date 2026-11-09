"""The shape of a game: the order the host walks through, and whether the questions are ready.

Rounds 1-3 are multiple choice, each ending in a double dare. Round 4 is free-form, then
teams wager and answer the final question.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.models import Question, QuestionKind

ROUNDS = (1, 2, 3, 4)
DARE_ROUNDS = (1, 2, 3)
# Points for each multiple-choice (rounds 1-3) or free-form (round 4) question.
ROUND_POINTS = {1: 5, 2: 10, 3: 15, 4: 20}
CHOICES = 4

StepType = Literal["question", "wager", "results"]


def kinds_for(round_: int) -> tuple[QuestionKind, QuestionKind]:
    """The regular and the special kind of question a round holds."""
    if round_ == 4:
        return QuestionKind.FREE, QuestionKind.FINAL
    return QuestionKind.MC, QuestionKind.DOUBLE_DARE


def points_for(question: Question) -> int | None:
    """What a correct answer is worth; None for the dare and the final, which instead
    change the round's points or stake a wager."""
    if question.kind in (QuestionKind.MC, QuestionKind.FREE):
        return ROUND_POINTS[question.round]
    return None


@dataclass(frozen=True)
class Step:
    type: StepType
    round: int
    question: Question | None = None
    # 1-based number among the round's regular questions; None for the special ones.
    number: int | None = None


def in_order(questions: Iterable[Question]) -> list[Question]:
    """Rounds in order; in each, the regular questions by position, then the special one."""
    return sorted(
        questions,
        key=lambda q: (
            q.round,
            q.kind in (QuestionKind.DOUBLE_DARE, QuestionKind.FINAL),
            q.position,
        ),
    )


def build_steps(questions: Iterable[Question]) -> list[Step]:
    steps: list[Step] = []
    number = 0
    current_round = 0
    for question in in_order(questions):
        if question.round != current_round:
            current_round, number = question.round, 0
        if question.kind == QuestionKind.FINAL:
            steps.append(Step("wager", 4, question))
            steps.append(Step("question", 4, question))
        elif question.kind == QuestionKind.DOUBLE_DARE:
            steps.append(Step("question", question.round, question))
        else:
            number += 1
            steps.append(Step("question", question.round, question, number))
    steps.append(Step("results", 4))
    return steps


def problems(questions: Sequence[Question]) -> list[str]:
    """What stops the game from starting. Empty: ready to play."""
    found: list[str] = []
    for round_ in ROUNDS:
        regular, special = kinds_for(round_)
        in_round = [q for q in questions if q.round == round_]
        if not any(q.kind == regular for q in in_round):
            what = "multiple-choice" if regular == QuestionKind.MC else "free-form"
            found.append(f"Round {round_} needs at least one {what} question.")
        if not any(q.kind == special for q in in_round):
            what = "double dare" if special == QuestionKind.DOUBLE_DARE else "final wager question"
            found.append(f"Round {round_} needs its {what}.")
    for question in questions:
        found.extend(question_problems(question))
    return found


def question_problems(question: Question) -> list[str]:
    label = f"Round {question.round}: “{_short(question.text)}”"
    found: list[str] = []
    if not question.text.strip():
        found.append(f"Round {question.round} has a question with no text.")
    if question.kind == QuestionKind.MC:
        choices = question.choices or []
        if len(choices) != CHOICES or not all(c.strip() for c in choices):
            found.append(f"{label} needs all four choices filled in.")
        if question.correct_choice is None or not 0 <= question.correct_choice < CHOICES:
            found.append(f"{label} needs a correct choice.")
    elif not (question.answer_text or "").strip():
        found.append(f"{label} needs an answer.")
    return found


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
