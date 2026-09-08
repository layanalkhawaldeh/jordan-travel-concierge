import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from src.database import ConversationModel


def generate_conversation_id() -> str:
    return f"conv-{uuid.uuid4().hex[:12]}"


def create_conversation(db: Session) -> ConversationModel:
    conversation = ConversationModel(
        id=generate_conversation_id(),
        title="New Conversation",
        messages=[],
        traveler_profile={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


def get_conversation(db: Session, conversation_id: str):
    return (
        db.query(ConversationModel)
        .filter(ConversationModel.id == conversation_id)
        .first()
    )


def list_conversations(db: Session):
    return (
        db.query(ConversationModel)
        .order_by(ConversationModel.updated_at.desc())
        .all()
    )


def delete_conversation(db: Session, conversation_id: str) -> bool:
    conversation = get_conversation(db, conversation_id)

    if not conversation:
        return False

    db.delete(conversation)
    db.commit()

    return True


def generate_conversation_title(message: str) -> str:
    clean_message = " ".join(message.split())

    if len(clean_message) <= 45:
        return clean_message

    return clean_message[:45] + "..."


def append_message(
    db: Session,
    conversation: ConversationModel,
    role: str,
    content: str,
):
    messages = list(conversation.messages or [])

    messages.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    conversation.messages = messages
    conversation.updated_at = datetime.now(timezone.utc)

    if conversation.title == "New Conversation" and role == "user":
        conversation.title = generate_conversation_title(content)

    db.commit()
    db.refresh(conversation)