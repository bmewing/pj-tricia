"""A whole game through the API: host, three players and a spectator."""

from typing import Any

from httpx import AsyncClient

from tests.conftest import MakePerson, Person

CSV = """round,kind,question,A,B,C,D,answer
1,mc,R1 Q1,a,b,c,d,A
1,mc,R1 Q2,a,b,c,d,B
1,dare,Dare one,,,,,Paris
2,mc,R2 Q1,a,b,c,d,C
2,dare,Dare two,,,,,Blue
3,mc,R3 Q1,a,b,c,d,D
3,dare,Dare three,,,,,Seven
4,,Free one,,,,,The Beatles
4,free,Free two,,,,,Mars
4,final,Final,,,,,Everest
"""


async def setup_event(client: AsyncClient, person: MakePerson) -> dict[str, Any]:
    owner, host, ann, ben, cat = [await person(n) for n in ("Owner", "Hosty", "Ann", "Ben", "Cat")]
    group = (await client.post("/api/groups", json={"name": "Quiz"}, headers=owner.headers)).json()
    for member in (host, ann, ben):
        r = await client.post(f"/api/join/{group['invite_code']}", headers=member.headers)
        assert r.status_code == 200
    event = (
        await client.post(
            f"/api/groups/{group['id']}/events",
            json={"title": "Trivia", "starts_at": "2026-11-20T19:00:00-05:00"},
            headers=owner.headers,
        )
    ).json()
    eid = event["id"]
    for player, team in ((ann, "The Smiths"), (ben, None), (owner, None)):
        r = await client.put(
            f"/api/events/{eid}/rsvp",
            json={"response": "yes", "role": "player", "team_name": team},
            headers=player.headers,
        )
        assert r.status_code == 200
    # The owner plays too, so they can't see the questions.
    r = await client.post(f"/api/events/{eid}/host/volunteer", headers=host.headers)
    assert r.json()["host"]["id"] == host.id
    r = await client.post(
        f"/api/events/{eid}/questions/import", json={"csv": CSV}, headers=host.headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["problems"] == []
    # Cat isn't in the group: spectates by link.
    r = await client.post(f"/api/watch/{event['spectate_token']}", headers=cat.headers)
    assert r.json()["me"]["game_role"] == "spectator"
    return {"eid": eid, "owner": owner, "host": host, "ann": ann, "ben": ben, "cat": cat}


async def live(client: AsyncClient, eid: str, who: Person) -> dict[str, Any]:
    r = await client.get(f"/api/events/{eid}/live", headers=who.headers)
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


async def host_do(client: AsyncClient, eid: str, host: Person, action: str) -> dict[str, Any]:
    r = await client.post(f"/api/events/{eid}/live/{action}", headers=host.headers)
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


async def answer(client: AsyncClient, eid: str, who: Person, **body: Any) -> Any:
    state = await live(client, eid, who)
    question_id = state["question"]["id"] if state["question"] else state["wager_question_id"]
    body.pop("question_id", None)
    return await client.put(
        f"/api/events/{eid}/live/answer",
        json={"question_id": question_id, **body},
        headers=who.headers,
    )


def totals(state: dict[str, Any]) -> dict[str, int]:
    return {row["team"]["name"]: row["total"] for row in state["scoreboard"]}


async def test_full_game(client: AsyncClient, person: MakePerson) -> None:
    s = await setup_event(client, person)
    eid, host, ann, ben, owner, cat = s["eid"], s["host"], s["ann"], s["ben"], s["owner"], s["cat"]

    # Nobody but the host can read the questions before the game.
    r = await client.get(f"/api/events/{eid}/questions", headers=ann.headers)
    assert r.status_code == 403
    r = await client.get(f"/api/events/{eid}/questions", headers=host.headers)
    assert r.status_code == 200

    lobby = await live(client, eid, ann)
    assert lobby["step"] == "lobby"
    assert {t["name"] for t in lobby["teams"]} == {"The Smiths", "Ben", "Owner"}

    state = await host_do(client, eid, host, "start")
    assert state["step"] == "question" and state["question"]["text"] == "R1 Q1"
    assert state["reveal"]["correct_choice"] == 0  # the host sees the key

    # Players see the question but never the key while it's open.
    seen = await live(client, eid, ann)
    assert seen["reveal"] is None
    assert seen["question"]["choices"] == ["a", "b", "c", "d"]
    assert "correct_choice" not in str(seen["question"])

    # Spectators and the host can't answer.
    r = await answer(client, eid, cat, choice=0)
    assert r.status_code == 403
    r = await answer(client, eid, host, choice=0)
    assert r.status_code == 403

    # R1 Q1 (A): Ann right, Ben wrong, Owner right after changing their mind.
    await answer(client, eid, ann, choice=0)
    await answer(client, eid, ben, choice=3)
    await answer(client, eid, owner, choice=2)
    await answer(client, eid, owner, choice=0)
    # Scores don't move while the question is open, so they give nothing away.
    assert set(totals(await live(client, eid, ann)).values()) == {0}
    state = await host_do(client, eid, host, "close")
    seen = await live(client, eid, ann)
    assert seen["reveal"]["correct_choice"] == 0
    assert seen["my_answer"]["is_correct"] is True
    assert totals(seen) == {"The Smiths": 5, "Ben": 0, "Owner": 5}
    r = await answer(client, eid, ben, choice=0)
    assert r.status_code == 409  # locked

    # R1 Q2 (B): only Ann.
    await host_do(client, eid, host, "next")
    await answer(client, eid, ann, choice=1)
    # Dare one: Ann answers right, Ben passes, Owner answers wrong.
    state = await host_do(client, eid, host, "next")
    assert state["question"]["kind"] == "double_dare"
    await answer(client, eid, ann, text="paris!")  # auto-graded: exact apart from punctuation
    await answer(client, eid, ben, passed=True)
    await answer(client, eid, owner, text="London")
    state = await host_do(client, eid, host, "close")
    wrong = next(a for a in state["answers"] if a["team"]["name"] == "Owner")
    assert wrong["is_correct"] is None
    r = await client.put(
        f"/api/events/{eid}/live/answers/{wrong['id']}/grade",
        json={"is_correct": False},
        headers=host.headers,
    )
    assert totals(r.json()) == {"The Smiths": 20, "Ben": 0, "Owner": 0}

    # Round 2 (C) and its dare: Ben right on both; Ann misses.
    await host_do(client, eid, host, "next")
    await answer(client, eid, ben, choice=2)
    await answer(client, eid, ann, choice=0)
    await host_do(client, eid, host, "next")
    await answer(client, eid, ben, text="blue")
    # Round 3 (D): Owner right, no one dares.
    await host_do(client, eid, host, "next")
    await answer(client, eid, owner, choice=3)
    await host_do(client, eid, host, "next")
    await host_do(client, eid, host, "next")
    # Round 4: Ann's "Beatles" matches "The Beatles" without the host; Ben gets Mars.
    state = await live(client, eid, host)
    assert state["question"]["text"] == "Free one"
    await answer(client, eid, ann, text="Beatles")
    state = await live(client, eid, host)
    assert state["answers"][0]["is_correct"] is True
    await host_do(client, eid, host, "next")
    await answer(client, eid, ben, text="mars")
    state = await host_do(client, eid, host, "next")
    assert state["step"] == "wager"
    assert state["question"] is None  # the final stays hidden while wagering
    # Ann 20+20=40, Ben 0+20(dare doubled 10)+20=40, Owner 0+0+15=15.
    seen = await live(client, eid, ann)
    assert totals(seen) == {"The Smiths": 40, "Ben": 40, "Owner": 15}
    assert seen["max_wager"] == 40
    r = await answer(client, eid, owner, wager=16)
    assert r.status_code == 422
    await answer(client, eid, owner, wager=15)
    await answer(client, eid, ann, wager=30)
    await answer(client, eid, ben, wager=40)
    # Others' wagers stay hidden.
    seen = await live(client, eid, ann)
    wagers = {row["team"]["name"]: row["wager"] for row in seen["scoreboard"]}
    assert wagers == {"The Smiths": 30, "Ben": None, "Owner": None}

    state = await host_do(client, eid, host, "next")
    assert state["question"]["kind"] == "final"
    await answer(client, eid, ann, text="Mount Everest")
    await answer(client, eid, ben, text="K2")
    # Owner leaves it blank: counts as wrong once closed.
    state = await host_do(client, eid, host, "close")
    for row in state["answers"]:
        if row["team"]["name"] == "The Smiths":
            await client.put(
                f"/api/events/{eid}/live/answers/{row['id']}/grade",
                json={"is_correct": True},
                headers=host.headers,
            )
        elif row["team"]["name"] == "Ben":
            await client.put(
                f"/api/events/{eid}/live/answers/{row['id']}/grade",
                json={"is_correct": False},
                headers=host.headers,
            )
    state = await host_do(client, eid, host, "next")
    assert state["step"] == "results"
    assert state["ungraded"] == 0
    assert totals(state) == {"The Smiths": 70, "Ben": 0, "Owner": 0}
    assert state["scoreboard"][0]["team"]["name"] == "The Smiths"

    state = await host_do(client, eid, host, "end")
    assert state["step"] == "over"
    # Afterward everyone at the event can look back over the questions.
    r = await client.get(f"/api/events/{eid}/questions", headers=cat.headers)
    assert r.status_code == 200


async def test_poll_returns_204_when_unchanged(client: AsyncClient, person: MakePerson) -> None:
    s = await setup_event(client, person)
    eid, ann, host = s["eid"], s["ann"], s["host"]
    version = (await live(client, eid, ann))["version"]
    r = await client.get(f"/api/events/{eid}/live?since={version}", headers=ann.headers)
    assert r.status_code == 204
    await host_do(client, eid, host, "start")
    r = await client.get(f"/api/events/{eid}/live?since={version}", headers=ann.headers)
    assert r.status_code == 200


async def test_outsiders_cannot_see_event(client: AsyncClient, person: MakePerson) -> None:
    s = await setup_event(client, person)
    stranger = await person("Stranger")
    r = await client.get(f"/api/events/{s['eid']}/live", headers=stranger.headers)
    assert r.status_code == 404


async def test_only_host_runs_game(client: AsyncClient, person: MakePerson) -> None:
    s = await setup_event(client, person)
    r = await client.post(f"/api/events/{s['eid']}/live/start", headers=s["owner"].headers)
    assert r.status_code == 403


async def test_cannot_start_incomplete_game(client: AsyncClient, person: MakePerson) -> None:
    s = await setup_event(client, person)
    eid, host = s["eid"], s["host"]
    questions = (await client.get(f"/api/events/{eid}/questions", headers=host.headers)).json()
    dare = next(q for q in questions["questions"] if q["kind"] == "double_dare")
    await client.delete(f"/api/questions/{dare['id']}", headers=host.headers)
    r = await client.post(f"/api/events/{eid}/live/start", headers=host.headers)
    assert r.status_code == 409
    assert "double dare" in r.json()["detail"]


async def test_changing_host_asks_about_questions(client: AsyncClient, person: MakePerson) -> None:
    s = await setup_event(client, person)
    eid, owner, ann = s["eid"], s["owner"], s["ann"]
    r = await client.put(f"/api/events/{eid}/host", json={"user_id": ann.id}, headers=owner.headers)
    assert r.status_code == 409
    r = await client.put(
        f"/api/events/{eid}/host",
        json={"user_id": ann.id, "clear_questions": True},
        headers=owner.headers,
    )
    assert r.status_code == 200
    event = r.json()
    assert event["host"]["id"] == ann.id
    # The new host no longer plays.
    ann_row = next(a for a in event["attendees"] if a["person"]["id"] == ann.id)
    assert ann_row["role"] == "spectator"
    questions = (await client.get(f"/api/events/{eid}/questions", headers=ann.headers)).json()
    assert questions["questions"] == []
