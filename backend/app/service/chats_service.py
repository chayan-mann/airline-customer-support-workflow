"""Business logic behind the /chats routes."""

from sqlalchemy.orm import Session

from app.models import Chat, User
from app.schema.chats import ChatOut


def _to_chat_out(chat: Chat) -> ChatOut:
    return ChatOut(
        id=str(chat.id), title=chat.title, created_at=chat.created_at, updated_at=chat.updated_at
    )


def list_user_chats(db: Session, user: User) -> list[ChatOut]:
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc())
        .all()
    )
    return [_to_chat_out(c) for c in chats]


def create_chat(db: Session, user: User, title: str | None) -> ChatOut:
    chat = Chat(user_id=user.id, title=title or "New Chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return _to_chat_out(chat)
