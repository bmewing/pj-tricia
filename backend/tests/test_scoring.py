import uuid

from app.game.scoring import max_wager, score
from app.game.steps import build_steps, problems
from app.models import Answer, Question, QuestionKind

EVENT = uuid.uuid4()
ALICE = uuid.uuid4()
BOB = uuid.uuid4()


def mc(round_: int, correct: int = 0, position: int = 1) -> Question:
    return Question(
        id=uuid.uuid4(),
        event_id=EVENT,
        round=round_,
        kind=QuestionKind.MC,
        position=position,
        text=f"Round {round_} q{position}",
        choices=["a", "b", "c", "d"],
        correct_choice=correct,
    )


def special(round_: int, kind: QuestionKind, answer: str = "yes", position: int = 0) -> Question:
    return Question(
        id=uuid.uuid4(),
        event_id=EVENT,
        round=round_,
        kind=kind,
        position=position,
        text=f"Round {round_} {kind}",
        answer_text=answer,
    )


def ans(
    question: Question,
    user: uuid.UUID,
    *,
    correct: bool | None = None,
    text: str | None = None,
    passed: bool = False,
    wager: int | None = None,
) -> Answer:
    if question.kind == QuestionKind.MC:
        choice = question.correct_choice if correct else ((question.correct_choice or 0) + 1) % 4
        return Answer(
            id=uuid.uuid4(),
            question_id=question.id,
            user_id=user,
            choice=choice,
            is_correct=bool(correct),
            passed=False,
        )
    return Answer(
        id=uuid.uuid4(),
        question_id=question.id,
        user_id=user,
        text=text if text is not None else (None if passed else "something"),
        passed=passed,
        wager=wager,
        is_correct=correct,
    )


def full_game() -> dict[str, list[Question]]:
    """Two multiple-choice questions in each of rounds 1-3, two free in round 4."""
    game: dict[str, list[Question]] = {}
    for r in (1, 2, 3):
        game[f"r{r}"] = [mc(r, position=1), mc(r, position=2)]
        game[f"dare{r}"] = [special(r, QuestionKind.DOUBLE_DARE)]
    game["r4"] = [
        special(4, QuestionKind.FREE, position=1),
        special(4, QuestionKind.FREE, position=2),
    ]
    game["final"] = [special(4, QuestionKind.FINAL)]
    return game


def everything(game: dict[str, list[Question]]) -> list[Question]:
    return [q for qs in game.values() for q in qs]


def test_mc_points_by_round() -> None:
    game = full_game()
    answers = [ans(q, ALICE, correct=True) for r in (1, 2, 3) for q in game[f"r{r}"]]
    answers.append(ans(game["r1"][0], BOB, correct=True))
    answers.append(ans(game["r1"][1], BOB, correct=False))
    teams = score(everything(game), answers, [ALICE, BOB])
    assert [r.points for r in teams[ALICE].rounds] == [10, 20, 30, 0]
    assert teams[ALICE].total == 60
    assert teams[BOB].total == 5


def test_double_dare_doubles_zeroes_or_keeps() -> None:
    game = full_game()
    answers = [ans(q, ALICE, correct=True) for r in (1, 2, 3) for q in game[f"r{r}"]]
    answers += [
        ans(game["dare1"][0], ALICE, correct=True),  # 10 -> 20
        ans(game["dare2"][0], ALICE, correct=False),  # 20 -> 0
        ans(game["dare3"][0], ALICE, passed=True),  # 30 stays
    ]
    team = score(everything(game), answers, [ALICE])[ALICE]
    assert [(r.base, r.dare, r.points) for r in team.rounds[:3]] == [
        (10, "right", 20),
        (20, "wrong", 0),
        (30, "passed", 30),
    ]
    assert team.total == 50


def test_ungraded_dare_leaves_points_and_counts_pending() -> None:
    game = full_game()
    answers = [ans(game["r1"][0], ALICE, correct=True), ans(game["dare1"][0], ALICE)]
    team = score(everything(game), answers, [ALICE])[ALICE]
    assert team.rounds[0].dare == "pending"
    assert team.rounds[0].points == 5
    assert team.pending == 1


def test_dare_on_zero_point_round_does_nothing() -> None:
    game = full_game()
    answers = [ans(game["dare1"][0], ALICE, correct=True)]
    assert score(everything(game), answers, [ALICE])[ALICE].total == 0


def test_round_four_free_answers_need_grading() -> None:
    game = full_game()
    answers = [
        ans(game["r4"][0], ALICE, correct=True),
        ans(game["r4"][1], ALICE),  # waiting for the host
    ]
    team = score(everything(game), answers, [ALICE])[ALICE]
    assert team.rounds[3].points == 20
    assert team.pending == 1


def test_final_wager_won_and_lost() -> None:
    game = full_game()
    base = [ans(q, u, correct=True) for u in (ALICE, BOB) for q in game["r1"]]  # 10 each
    final = game["final"][0]
    answers = [
        *base,
        ans(final, ALICE, wager=10, correct=True),
        ans(final, BOB, wager=7, correct=False),
    ]
    teams = score(everything(game), answers, [ALICE, BOB], final_closed=True)
    assert teams[ALICE].total == 20
    assert teams[BOB].total == 3


def test_wager_is_capped_by_total_and_never_negative() -> None:
    game = full_game()
    final = game["final"][0]
    answers = [
        ans(game["r1"][0], ALICE, correct=True),  # 5
        ans(game["dare1"][0], ALICE, correct=False),  # round 1 -> 0
        ans(final, ALICE, wager=50, correct=False),
    ]
    team = score(everything(game), answers, [ALICE], final_closed=True)[ALICE]
    assert max_wager(team) == 0
    assert team.final_points == 0
    assert team.total == 0


def test_blank_final_counts_wrong_only_once_closed() -> None:
    game = full_game()
    final = game["final"][0]
    answers = [
        *(ans(q, ALICE, correct=True) for q in game["r1"]),
        ans(final, ALICE, wager=4, text=""),
    ]
    still_open = score(everything(game), answers, [ALICE])[ALICE]
    assert still_open.final == "none"
    assert still_open.total == 10
    closed = score(everything(game), answers, [ALICE], final_closed=True)[ALICE]
    assert closed.final == "wrong"
    assert closed.total == 6


def test_no_wager_means_nothing_at_stake() -> None:
    game = full_game()
    final = game["final"][0]
    answers = [ans(game["r1"][0], ALICE, correct=True), ans(final, ALICE, correct=False)]
    team = score(everything(game), answers, [ALICE], final_closed=True)[ALICE]
    assert team.final == "wrong"
    assert team.total == 5


def test_hidden_question_does_not_count() -> None:
    game = full_game()
    question = game["r1"][0]
    answers = [ans(question, ALICE, correct=True)]
    assert score(everything(game), answers, [ALICE], hidden=[question.id])[ALICE].total == 0


def test_hidden_final_keeps_wager_out_of_play() -> None:
    game = full_game()
    final = game["final"][0]
    answers = [ans(game["r1"][0], ALICE, correct=True), ans(final, ALICE, wager=5, correct=True)]
    team = score(everything(game), answers, [ALICE], hidden=[final.id])[ALICE]
    assert team.wager == 5
    assert team.total == 5


def test_steps_order() -> None:
    game = full_game()
    steps = build_steps(reversed(everything(game)))
    labels = [(s.type, s.round, s.question.kind if s.question else None, s.number) for s in steps]
    assert labels[:3] == [
        ("question", 1, QuestionKind.MC, 1),
        ("question", 1, QuestionKind.MC, 2),
        ("question", 1, QuestionKind.DOUBLE_DARE, None),
    ]
    assert labels[-5:] == [
        ("question", 4, QuestionKind.FREE, 1),
        ("question", 4, QuestionKind.FREE, 2),
        ("wager", 4, QuestionKind.FINAL, None),
        ("question", 4, QuestionKind.FINAL, None),
        ("results", 4, None, None),
    ]
    assert len(steps) == 3 * 3 + 2 + 2 + 1


def test_problems() -> None:
    assert problems(everything(full_game())) == []
    found = problems([mc(1)])
    assert "Round 1 needs its Double Down Dare." in found
    assert "Round 4 needs its Do or Die Dare." in found
    broken = mc(1)
    broken.correct_choice = None
    assert any("correct choice" in p for p in problems([broken]))
