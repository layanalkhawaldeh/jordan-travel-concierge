import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from database import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String, default="active")  # active / completed
    created_at = Column(DateTime, default=datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(datetime.timezone.utc), onupdate=datetime.now(datetime.timezone.utc))

    # Relationships
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    traveler_profile = relationship("TravelerProfile", uselist=False, back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now(datetime.timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

class TravelerProfile(Base):
    __tablename__ = "traveler_profiles"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    destination = Column(String, nullable=True)
    adults = Column(Integer, nullable=True)
    children = Column(Integer, nullable=True)
    budget = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    duration_days = Column(Integer, nullable=True)
    travel_dates = Column(String, nullable=True)
    hotel_preference = Column(String, nullable=True)
    transportation_preference = Column(String, nullable=True)
    
    interests = Column(JSON, default=list)  # list of strings
    accessibility_requirements = Column(JSON, default=list)  # list of strings
    special_requests = Column(JSON, default=list)  # list of strings
    
    lead_status = Column(String, default="Incomplete")  # Incomplete / Ready for Sales / Out of Scope
    completeness_score = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.now(datetime.timezone.utc), onupdate=datetime.now(datetime.timezone.utc))

    # Relationships
    conversation = relationship("Conversation", back_populates="traveler_profile")
