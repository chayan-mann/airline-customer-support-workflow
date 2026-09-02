"""Business logic behind the /chats routes."""

from sqlalchemy.orm import Session

from app.agentic_ai.graph import checkpointer
from app.models import Chat, User
from app.schema.chats import ChatOut
from app.service.conversation_service import get_owned_chat


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


def rename_chat(chat_id: str, title: str, user: User, db: Session) -> ChatOut:
    chat = get_owned_chat(chat_id, user, db)
    chat.title = title.strip() or "New Chat"
    db.commit()
    db.refresh(chat)
    return _to_chat_out(chat)


def delete_chat(chat_id: str, user: User, db: Session) -> None:
    chat = get_owned_chat(chat_id, user, db)
    # Chat.id doubles as the LangGraph thread_id (see Chat's docstring) —
    # clean up its checkpointed conversation state too, or it lingers in
    # Postgres forever with nothing pointing back at it.
    checkpointer.delete_thread(chat_id)
    db.delete(chat)
    db.commit()
