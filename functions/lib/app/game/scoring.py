"""Points. This is the only place they're worked out; nothing a browser sends is trusted.

- Rounds 1-3: each correct multiple-choice answer earns the round's points (5, 10, 15).
  Then the double dare: pass and keep the round's points; answer right and they double;
  answer wrong and the round is worth nothing.
- Round 4: each correct free-form answer earns 20.
- Final: wager from 0 up to your total so far (never below 0), then win or lose that much.
  A blank answer once the final is closed counts as wrong.

Ungraded free-form answers count for nothing yet, and an ungraded dare or final leaves
points where they were, so scores only move when the host decides.
"""

import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Literal

from app.game.steps import DARE_ROUNDS, ROUNDS, points_for
from app.models import Answer, Question, QuestionKind

Outcome = Literal["none", "passed", "pending", "right", "wrong"]


@dataclass
class RoundScore:
    base: int = 0  # from the round's regular questions
    dare: Outcome = "none"  # rounds 1-3 only
    points: int = 0  # after the dare


@dataclass
class TeamScore:
    user_id: uuid.UUID
    rounds: list[RoundScore] = field(default_factory=lambda: [RoundScore() for _ in ROUNDS])
    wager: int | None = None  # as staked; the effective wager is capped by the total
    final: Outcome = "none"
    final_points: int = 0
    pending: int = 0  # answers waiting for the host

    @property
    def before_final(self) -> int:
        return sum(r.points for r in self.rounds)

    @property
    def total(self) -> int:
        return self.before_final + self.final_points


def max_wager(team: TeamScore) -> int:
    return max(0, team.before_final)


def score(
    questions: Iterable[Question],
    answers: Iterable[Answer],
    players: Iterable[uuid.UUID],
    *,
    hidden: Collection[uuid.UUID] = (),
    final_closed: bool = False,
) -> dict[uuid.UUID, TeamScore]:
    """Every player's score. Answers to `hidden` questions (the one still taking answers)
    are left out, so a score never gives away whether an answer was right."""
    by_id = {q.id: q for q in questions}
    teams = {user_id: TeamScore(user_id) for user_id in players}
    dares: dict[tuple[uuid.UUID, int], Answer] = {}
    finals: dict[uuid.UUID, Answer] = {}
    for answer in answers:
        team = teams.get(answer.user_id)
        question = by_id.get(answer.question_id)
        if team is None or question is None:
            continue
        if question.kind == QuestionKind.FINAL:
            # The wager counts from the wager step on; the answer only once it's revealed.
            finals[answer.user_id] = answer
            continue
        if question.id in hidden:
            continue
        if question.kind == QuestionKind.DOUBLE_DARE:
            dares[(answer.user_id, question.round)] = answer
            continue
        if answer.is_correct is None and question.kind == QuestionKind.FREE:
            team.pending += 1
        if answer.is_correct:
            team.rounds[question.round - 1].base += points_for(question) or 0

    final_question = next((q for q in by_id.values() if q.kind == QuestionKind.FINAL), None)
    final_hidden = final_question is not None and final_question.id in hidden
    for team in teams.values():
        for round_ in DARE_ROUNDS:
            result = team.rounds[round_ - 1]
            result.dare = _dare_outcome(dares.get((team.user_id, round_)))
            if result.dare == "pending":
                team.pending += 1
            result.points = {"right": result.base * 2, "wrong": 0}.get(result.dare, result.base)
        team.rounds[3].points = team.rounds[3].base

        final = finals.get(team.user_id)
        team.wager = final.wager if final else None
        stake = min(team.wager or 0, max_wager(team))
        if final is None or final_hidden:
            continue
        if final.text and final.text.strip():
            team.final = _graded(final.is_correct)
        elif final_closed:
            team.final = "wrong"
        if team.final == "pending":
            team.pending += 1
        team.final_points = {"right": stake, "wrong": -stake}.get(team.final, 0)
    return teams


def _dare_outcome(answer: Answer | None) -> Outcome:
    if answer is None:
        return "none"
    if answer.passed or not (answer.text or "").strip():
        return "passed"
    return _graded(answer.is_correct)


def _graded(is_correct: bool | None) -> Outcome:
    if is_correct is None:
        return "pending"
    return "right" if is_correct else "wrong"
