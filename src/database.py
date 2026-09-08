import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get database URL from environment, fallback to a local sqlite database for local testing if DB not run yet
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tourism_local.db")
#بحاول يقرأ ال داتا بيس من ال POSTGRESQL ولو مو موجود بينشئ وحدة باسم التوريزم 

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                            #عشان ما يحفظ كلشي 
Base = declarative_base()

class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, index=True)

    title = Column(String, nullable=False, default="New conversation")
    status = Column(String, nullable=False, default="active")

    messages = Column(JSON, default=list)
    traveler_profile = Column(JSON, default=dict)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
class HotelModel(Base):
    __tablename__ = "hotels"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False) # Amman, Petra, Dead Sea, Wadi Rum, Aqaba
    stars = Column(Integer, nullable=False)
    price_per_night = Column(Float, nullable=False)
    capacity = Column(Integer, nullable=False)
    amenities = Column(JSON, default=list)
    availability_status = Column(Boolean, default=True)

class ActivityModel(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    price = Column(Float, nullable=False) # Cost per person
    interest_type = Column(String, nullable=False) # history, adventure, nature, relaxation
    description = Column(String, nullable=True)

class TransportationModel(Base):
    __tablename__ = "transportation"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    type = Column(String, nullable=False, unique=True) # Private Driver, Rental Car, Public Bus
    price_per_day = Column(Float, nullable=False)
    description = Column(String, nullable=True)

class SalesLeadModel(Base):
    __tablename__ = "sales_leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id = Column(String, unique=True, index=True, nullable=False)
    conversation_id = Column(String, nullable=False)
    traveler_profile = Column(JSON, nullable=False)
    selected_options = Column(JSON, nullable=False) # {"hotel": {...}, "activities": [...], "transportation": {...}}
    estimated_cost = Column(Float, nullable=False)
    status = Column(String, default="pending") # pending, approved, rejected, modified
    reviewer_comments = Column(String, nullable=True)
    reviewer_name = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class BookingModel(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    booking_id = Column(String, unique=True, index=True, nullable=False)
    conversation_id = Column(String, nullable=False)
    traveler_profile = Column(JSON, nullable=False)
    hotel_name = Column(String, nullable=True)
    activities = Column(JSON, default=list)
    transportation = Column(String, nullable=True)
    total_price = Column(Float, nullable=False)
    status = Column(String, default="pending_payment") # pending_payment, booked, cancelled
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"
    #    # 2. اسم الملف الأصلي الذي أخذنا منه المقطع (مثلاً: cancellation_policy.txt)


    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_name = Column(String, nullable=False)
    text = Column(String, nullable=False)#النص الحقيقي المقتطع من الملف 
    embedding = Column(JSON, nullable=False) # JSON array of floats
    metadata_info = Column(JSON, default=dict) # Metadata info (e.g. source, page)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ApiCacheModel(Base):
    __tablename__ = "api_cache"#api History 

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cache_key = Column(String, unique=True, index=True, nullable=False) # md5 hash of query/url
    response_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AgentExecutionLogModel(Base):
    __tablename__ = "agent_execution_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    conversation_id = Column(String, nullable=False)
    user_request = Column(String, nullable=False)
    iterations = Column(Integer, nullable=False)
    steps = Column(JSON, default=list) # List of tool calls & outputs
    latency_seconds = Column(Float, nullable=False)
    token_usage = Column(JSON, default=dict) # {"input_tokens": x, "output_tokens": y, "total_tokens": z}
    estimated_cost_usd = Column(Float, nullable=False)
    status = Column(String, nullable=False) # completed, failed, error
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class PromptModel(Base):
    __tablename__ = "prompts"

    id = Column(String, primary_key=True, index=True) # e.g. 'profile_extraction', 'system_instruction'
    prompt_data = Column(String, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
