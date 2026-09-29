"""
Konbit — Notifikasyon (klòch nan ba anlè a)
Chemen: backend/app/routers/notifications.py

    GET  /api/notifications             Dènye notifikasyon mwen yo (+ konbyen m poko li)
    GET  /api/notifications/count       Konbyen m poko li (pou ti chif wouj la)
    POST /api/notifications/{id}/read   Make youn kòm li
    POST /api/notifications/read-all    Make tout kòm li

Lòt router yo KREYE notifikasyon (pewòl peye, chanjman peman, konje,
fòmasyon, rekritman...). Isit la moun nan LI pa l sèlman: chak rekèt
filtre sou user_id moun ki konekte a — pèsonn pa wè notifikasyon yon lòt.
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func

from ..deps import CurrentUser, DbSession
from ..models import Notification

router = APIRouter()


def _mine(db, user):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if user.organization_id is not None:
        q = q.filter(Notification.organization_id == user.organization_id)
    return q


class NotificationOut(BaseModel):
    id: int
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    category: Optional[str] = None
    is_read: bool
    created_at: datetime


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationOut]


class UnreadCount(BaseModel):
    unread: int


def _unread(db, user) -> int:
    return _mine(db, user).filter(Notification.is_read.is_(False)).with_entities(
        func.count(Notification.id)).scalar() or 0


@router.get("", response_model=NotificationList)
def list_notifications(user: CurrentUser, db: DbSession,
                       limit: Annotated[int, Query(ge=1, le=50)] = 20,
                       unread_only: bool = False):
    q = _mine(db, user)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.id.desc()).limit(limit).all()
    return NotificationList(
        unread=_unread(db, user),
        items=[NotificationOut(
            id=n.id, title=n.title, body=n.body, link_url=n.link_url, category=n.category,
            is_read=bool(n.is_read), created_at=n.created_at,
        ) for n in rows],
    )


@router.get("/count", response_model=UnreadCount)
def unread_count(user: CurrentUser, db: DbSession):
    return UnreadCount(unread=_unread(db, user))


@router.post("/read-all", response_model=UnreadCount)
def read_all(user: CurrentUser, db: DbSession):
    now = datetime.now(timezone.utc)
    for n in _mine(db, user).filter(Notification.is_read.is_(False)).all():
        n.is_read = True
        n.read_at = now
    db.commit()
    return UnreadCount(unread=0)


@router.post("/{notification_id}/read", response_model=UnreadCount)
def read_one(notification_id: int, user: CurrentUser, db: DbSession):
    n = _mine(db, user).filter(Notification.id == notification_id).first()
    if n is None:
        # Pa di si notifikasyon an egziste pou yon lòt moun.
        raise HTTPException(status_code=404)
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    return UnreadCount(unread=_unread(db, user))