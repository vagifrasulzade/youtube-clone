"""Comments and replies (docs/api.md § Comments, acceptance C2 and D2)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Comment, ModerationAction, User, Video, VideoPermission
from app.models.enums import ModerationActionType, RoleName, VideoStatus, Visibility
from app.services import comments as comment_service
from tests.factories import auth_headers, create_user, create_video

API = "/api/v1"


def _video(db: Session, **fields: Any) -> tuple[Video, User]:
    owner = create_user(db)
    fields.setdefault("visibility", Visibility.PUBLIC)
    return create_video(db, owner.channel, status=VideoStatus.READY, **fields), owner


def _comment(client: TestClient, video: Video, user: User, body: str = "Nice", **extra: Any):
    response = client.post(
        f"{API}/videos/{video.id}/comments",
        json={"body": body, **extra},
        headers=auth_headers(user),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assert_counters_match_rows(db: Session, video: Video) -> None:
    db.expire_all()
    fresh = db.get(Video, video.id)
    assert fresh is not None
    assert fresh.comment_count == db.scalar(
        select(func.count()).select_from(Comment).where(Comment.video_id == video.id)
    )
    for parent in db.scalars(select(Comment).where(Comment.video_id == video.id)):
        replies = db.scalar(
            select(func.count()).select_from(Comment).where(Comment.parent_id == parent.id)
        )
        assert parent.reply_count == replies


def _audits(db: Session, comment_id: str) -> list[ModerationAction]:
    return list(
        db.scalars(
            select(ModerationAction).where(
                ModerationAction.target_id == comment_id,
                ModerationAction.action == ModerationActionType.DELETE_COMMENT,
            )
        )
    )


# --- create and list --------------------------------------------------------------


def test_comment_is_created_and_listed(client: TestClient, db_session: Session) -> None:
    video, owner = _video(db_session)
    author = create_user(db_session)

    created = _comment(client, video, author, "  First!  ")

    assert created["body"] == "First!"
    assert created["author"]["handle"] == author.channel.handle
    assert created["is_video_owner"] is False
    assert created["can_edit"] is True
    assert created["can_delete"] is True
    assert created["reply_count"] == 0
    assert created["edited_at"] is None

    anonymous = client.get(f"{API}/videos/{video.id}/comments")
    assert anonymous.status_code == 200
    [item] = anonymous.json()["items"]
    assert item["id"] == created["id"]
    assert (item["can_edit"], item["can_delete"]) == (False, False)
    _assert_counters_match_rows(db_session, video)

    as_owner = client.get(f"{API}/videos/{video.id}/comments", headers=auth_headers(owner))
    assert as_owner.json()["items"][0]["can_delete"] is True  # D2: the video owner


def test_creator_comment_gets_the_owner_badge(client: TestClient, db_session: Session) -> None:
    video, owner = _video(db_session)

    assert _comment(client, video, owner)["is_video_owner"] is True


def test_replies_are_one_level_and_counted(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    top = _comment(client, video, user, "Question?")
    first = _comment(client, video, user, "Answer 1", parent_id=top["id"])
    second = _comment(client, video, user, "Answer 2", parent_id=top["id"])

    listed = client.get(f"{API}/videos/{video.id}/comments").json()["items"]
    assert [c["id"] for c in listed] == [top["id"]]  # top level only
    assert listed[0]["reply_count"] == 2

    replies = client.get(f"{API}/comments/{top['id']}/replies").json()["items"]
    assert [r["id"] for r in replies] == [first["id"], second["id"]]  # oldest first
    assert all(r["parent_id"] == top["id"] for r in replies)

    reply_to_reply = client.post(
        f"{API}/videos/{video.id}/comments",
        json={"body": "Nested", "parent_id": first["id"]},
        headers=auth_headers(user),
    )
    assert reply_to_reply.status_code == 404
    assert reply_to_reply.json()["error"]["code"] == "parent_comment_not_found"
    _assert_counters_match_rows(db_session, video)


def test_reply_must_target_a_comment_of_the_same_video(
    client: TestClient, db_session: Session
) -> None:
    video, _ = _video(db_session)
    other_video, _ = _video(db_session)
    user = create_user(db_session)
    elsewhere = _comment(client, other_video, user)

    response = client.post(
        f"{API}/videos/{video.id}/comments",
        json={"body": "Wrong thread", "parent_id": elsewhere["id"]},
        headers=auth_headers(user),
    )

    assert response.status_code == 404
    _assert_counters_match_rows(db_session, video)
    _assert_counters_match_rows(db_session, other_video)


def test_pagination_and_sort(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    ids = [_comment(client, video, user, f"Comment {i}")["id"] for i in range(3)]
    url = f"{API}/videos/{video.id}/comments"

    first = client.get(url, params={"limit": 2}).json()
    assert [c["id"] for c in first["items"]] == [ids[2], ids[1]]  # newest first
    second = client.get(url, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [c["id"] for c in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None

    oldest = client.get(url, params={"sort": "oldest"}).json()["items"]
    assert [c["id"] for c in oldest] == ids

    assert client.get(url, params={"cursor": "not-a-cursor"}).status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"body": ""},
        {"body": "   "},
        {"body": "x" * 10_001},
        {"body": "bell\x07"},
        {"body": "ok", "author_id": "00000000-0000-0000-0000-000000000000"},
        {"body": "ok", "reply_count": 99},
    ],
)
def test_invalid_bodies_are_rejected(
    client: TestClient, db_session: Session, body: dict[str, Any]
) -> None:
    video, _ = _video(db_session)

    response = client.post(
        f"{API}/videos/{video.id}/comments",
        json=body,
        headers=auth_headers(create_user(db_session)),
    )

    assert response.status_code == 422


def test_comment_rate_limit(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    headers = auth_headers(create_user(db_session))
    url = f"{API}/videos/{video.id}/comments"

    codes = [
        client.post(url, json={"body": f"c{i}"}, headers=headers).status_code for i in range(21)
    ]

    assert codes[:20] == [201] * 20
    assert codes[20] == 429


# --- authentication and visibility (C2) -----------------------------------------


def test_writes_require_authentication(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    comment = _comment(client, video, create_user(db_session))

    assert client.post(f"{API}/videos/{video.id}/comments", json={"body": "x"}).status_code == 401
    assert client.patch(f"{API}/comments/{comment['id']}", json={"body": "x"}).status_code == 401
    assert client.delete(f"{API}/comments/{comment['id']}").status_code == 401


def test_private_video_comments_are_404_without_access(
    client: TestClient, db_session: Session
) -> None:
    video, owner = _video(db_session, visibility=Visibility.PRIVATE)
    top = _comment(client, video, owner, "Owner note")
    outsider = auth_headers(create_user(db_session))

    assert client.get(f"{API}/videos/{video.id}/comments").status_code == 404
    assert client.get(f"{API}/videos/{video.id}/comments", headers=outsider).status_code == 404
    assert client.get(f"{API}/comments/{top['id']}/replies", headers=outsider).status_code == 404
    post = client.post(f"{API}/videos/{video.id}/comments", json={"body": "hi"}, headers=outsider)
    assert post.status_code == 404
    edit = client.patch(f"{API}/comments/{top['id']}", json={"body": "x"}, headers=outsider)
    assert edit.status_code == 404  # not 403: existence is not revealed
    assert client.delete(f"{API}/comments/{top['id']}", headers=outsider).status_code == 404
    _assert_counters_match_rows(db_session, video)


def test_granted_viewer_can_comment_until_the_grant_is_revoked(
    client: TestClient, db_session: Session
) -> None:
    video, _ = _video(db_session, visibility=Visibility.PRIVATE)
    friend = create_user(db_session)
    grant = VideoPermission(video_id=video.id, user_id=friend.id)
    db_session.add(grant)
    db_session.flush()
    comment = _comment(client, video, friend, "Thanks for sharing")

    db_session.delete(grant)
    db_session.flush()

    headers = auth_headers(friend)
    assert client.get(f"{API}/videos/{video.id}/comments", headers=headers).status_code == 404
    edit = client.patch(f"{API}/comments/{comment['id']}", json={"body": "x"}, headers=headers)
    assert edit.status_code == 404


def test_hidden_video_comments_are_404_for_viewers(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    _comment(client, video, user)
    video.is_hidden = True
    db_session.flush()

    listed = client.get(f"{API}/videos/{video.id}/comments", headers=auth_headers(user))

    assert listed.status_code == 404


def test_unknown_ids_are_404(client: TestClient, db_session: Session) -> None:
    headers = auth_headers(create_user(db_session))
    missing = "00000000-0000-4000-8000-000000000000"

    assert client.get(f"{API}/videos/AAAAAAAAAAA/comments").status_code == 404
    assert client.get(f"{API}/comments/{missing}/replies").status_code == 404
    assert (
        client.patch(f"{API}/comments/{missing}", json={"body": "x"}, headers=headers).status_code
        == 404
    )
    assert client.delete(f"{API}/comments/{missing}", headers=headers).status_code == 404


# --- edit ----------------------------------------------------------------------------


def test_only_the_author_can_edit(client: TestClient, db_session: Session) -> None:
    video, owner = _video(db_session)
    author = create_user(db_session)
    comment = _comment(client, video, author, "Typo")
    url = f"{API}/comments/{comment['id']}"

    for other in (owner, create_user(db_session), create_user(db_session, role=RoleName.MODERATOR)):
        response = client.patch(url, json={"body": "Hijacked"}, headers=auth_headers(other))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_author"

    edited = client.patch(url, json={"body": "Fixed"}, headers=auth_headers(author))
    assert edited.status_code == 200
    assert edited.json()["body"] == "Fixed"
    assert edited.json()["edited_at"] is not None


# --- delete (D2) -----------------------------------------------------------------------


def test_a_stranger_cannot_delete(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    comment = _comment(client, video, create_user(db_session))

    response = client.delete(
        f"{API}/comments/{comment['id']}", headers=auth_headers(create_user(db_session))
    )

    assert response.status_code == 403
    _assert_counters_match_rows(db_session, video)


@pytest.mark.parametrize("who", ["author", "video_owner", "moderator", "admin"])
def test_allowed_roles_can_delete(client: TestClient, db_session: Session, who: str) -> None:
    video, owner = _video(db_session)
    author = create_user(db_session)
    comment = _comment(client, video, author)
    deleter = {
        "author": author,
        "video_owner": owner,
        "moderator": create_user(db_session, role=RoleName.MODERATOR),
        "admin": create_user(db_session, role=RoleName.ADMIN),
    }[who]

    response = client.delete(f"{API}/comments/{comment['id']}", headers=auth_headers(deleter))

    assert response.status_code == 204
    assert client.get(f"{API}/videos/{video.id}/comments").json()["items"] == []
    _assert_counters_match_rows(db_session, video)
    audits = _audits(db_session, comment["id"])
    if who in ("moderator", "admin"):  # moderation actions are audited
        [entry] = audits
        assert entry.actor_id == deleter.id
        assert entry.details["author_id"] == str(author.id)
    else:
        assert audits == []


def test_deleting_a_thread_removes_its_replies(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    top = _comment(client, video, user)
    for i in range(2):
        _comment(client, video, user, f"reply {i}", parent_id=top["id"])
    other = _comment(client, video, user, "Separate thread")

    response = client.delete(f"{API}/comments/{top['id']}", headers=auth_headers(user))

    assert response.status_code == 204
    remaining = client.get(f"{API}/videos/{video.id}/comments").json()["items"]
    assert [c["id"] for c in remaining] == [other["id"]]
    assert client.get(f"{API}/comments/{top['id']}/replies").status_code == 404
    _assert_counters_match_rows(db_session, video)
    assert db_session.get(Video, video.id).comment_count == 1


def test_deleting_a_reply_updates_both_counters(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    top = _comment(client, video, user)
    reply = _comment(client, video, user, "reply", parent_id=top["id"])

    response = client.delete(f"{API}/comments/{reply['id']}", headers=auth_headers(user))

    assert response.status_code == 204
    listed = client.get(f"{API}/videos/{video.id}/comments").json()["items"]
    assert listed[0]["reply_count"] == 0
    _assert_counters_match_rows(db_session, video)
    again = client.delete(f"{API}/comments/{reply['id']}", headers=auth_headers(user))
    assert again.status_code == 404


# --- review follow-ups ----------------------------------------------------------------


def test_lone_surrogates_are_rejected_not_a_500(client: TestClient, db_session: Session) -> None:
    video, _ = _video(db_session)
    headers = {**auth_headers(create_user(db_session)), "Content-Type": "application/json"}

    response = client.post(
        f"{API}/videos/{video.id}/comments",
        content=rb'{"body": "a\ud800b"}',  # JSON escape of a lone surrogate
        headers=headers,
    )

    assert response.status_code == 422


def test_emoji_sequences_with_zero_width_joiners_are_allowed(
    client: TestClient, db_session: Session
) -> None:
    video, _ = _video(db_session)
    family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"

    assert _comment(client, video, create_user(db_session), f"Love it {family}")["body"].endswith(
        family
    )


def test_replies_paginate_and_a_reply_has_no_replies(
    client: TestClient, db_session: Session
) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    top = _comment(client, video, user)
    ids = [_comment(client, video, user, f"r{i}", parent_id=top["id"])["id"] for i in range(3)]
    url = f"{API}/comments/{top['id']}/replies"

    first = client.get(url, params={"limit": 2}).json()
    second = client.get(url, params={"limit": 2, "cursor": first["next_cursor"]}).json()

    assert [r["id"] for r in first["items"] + second["items"]] == ids
    assert second["next_cursor"] is None
    assert client.get(f"{API}/comments/{ids[0]}/replies").status_code == 404


def test_moderator_thread_deletion_is_audited_with_the_reply_count(
    client: TestClient, db_session: Session
) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    top = _comment(client, video, user)
    for i in range(2):
        _comment(client, video, create_user(db_session), f"r{i}", parent_id=top["id"])
    moderator = create_user(db_session, role=RoleName.MODERATOR)

    response = client.delete(f"{API}/comments/{top['id']}", headers=auth_headers(moderator))

    assert response.status_code == 204
    [entry] = _audits(db_session, top["id"])
    assert entry.details["replies_removed"] == 2
    _assert_counters_match_rows(db_session, video)


def test_staff_can_moderate_comments_on_a_private_video(
    client: TestClient, db_session: Session
) -> None:
    video, owner = _video(db_session, visibility=Visibility.PRIVATE)
    comment = _comment(client, video, owner, "Private note")
    moderator = auth_headers(create_user(db_session, role=RoleName.MODERATOR))

    listed = client.get(f"{API}/videos/{video.id}/comments", headers=moderator)
    assert [c["id"] for c in listed.json()["items"]] == [comment["id"]]
    assert client.delete(f"{API}/comments/{comment['id']}", headers=moderator).status_code == 204


def test_former_grantee_cannot_delete_their_comment(
    client: TestClient, db_session: Session
) -> None:
    video, _ = _video(db_session, visibility=Visibility.PRIVATE)
    friend = create_user(db_session)
    grant = VideoPermission(video_id=video.id, user_id=friend.id)
    db_session.add(grant)
    db_session.flush()
    comment = _comment(client, video, friend)
    db_session.delete(grant)
    db_session.flush()

    response = client.delete(f"{API}/comments/{comment['id']}", headers=auth_headers(friend))

    assert response.status_code == 404


def _stale(db: Session, comment_id: str) -> tuple[Comment, Video]:
    """What a request that loaded the comment just before another one deleted it holds."""
    comment = db.get(Comment, uuid.UUID(comment_id))
    assert comment is not None
    video = db.get(Video, comment.video_id)
    assert video is not None
    return comment, video


def test_losing_a_race_to_delete_the_last_reply_is_a_404(
    db_session: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review: the second of two concurrent deletes used to break reply_count >= 0 (500)."""
    video, _ = _video(db_session)
    user = create_user(db_session)
    top = _comment(client, video, user)
    reply = _comment(client, video, user, "only reply", parent_id=top["id"])
    stale = _stale(db_session, reply["id"])
    # The winning request: reply removed and both counters decremented.
    assert (
        client.delete(f"{API}/comments/{reply['id']}", headers=auth_headers(user)).status_code
        == 204
    )
    monkeypatch.setattr(comment_service, "get_viewable_comment_or_404", lambda *_a: stale)

    with pytest.raises(NotFoundError):
        comment_service.remove(db_session, user, uuid.UUID(reply["id"]))

    _assert_counters_match_rows(db_session, video)


def test_editing_a_comment_deleted_meanwhile_is_a_404(
    db_session: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    video, _ = _video(db_session)
    user = create_user(db_session)
    comment = _comment(client, video, user)
    stale = _stale(db_session, comment["id"])
    assert (
        client.delete(f"{API}/comments/{comment['id']}", headers=auth_headers(user)).status_code
        == 204
    )
    monkeypatch.setattr(comment_service, "get_viewable_comment_or_404", lambda *_a: stale)

    with pytest.raises(NotFoundError):
        comment_service.edit(db_session, user, uuid.UUID(comment["id"]), "too late")
