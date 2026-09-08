from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class TravelerProfileSchema(BaseModel):
    is_tourism_related: Optional[bool] = Field(default=True, description="Whether the request is tourism related.")
    destination: Optional[str] = Field(default=None, description="Country or city destination.")
    adults: Optional[int] = Field(default=None, description="Number of adult travelers.")
    children: Optional[int] = Field(default=None, description="Number of child travelers.")
    budget: Optional[float] = Field(default=None, description="Estimated budget amount.")
    currency: Optional[str] = Field(default=None, description="Currency code (e.g., USD, EUR).")
    duration_days: Optional[int] = Field(default=None, description="Duration of the trip in days.")
    travel_dates: Optional[str] = Field(default=None, description="Approximate or exact travel dates/period.")
    hotel_preference: Optional[str] = Field(default=None, description="Hotel stars or accommodation preference.")
    transportation_preference: Optional[str] = Field(default=None, description="Rental car, private driver, public transport, etc.")
    interests: List[str] = Field(default_factory=list, description="List of activities or places of interest.")
    accessibility_requirements: List[str] = Field(default_factory=list, description="Wheelchair, dietary, or elderly needs.")
    special_requests: List[str] = Field(default_factory=list, description="Other custom special requests.")
    customer_intent: Optional[str] = Field(default=None, description="Intent e.g. booking, information, out of scope.")

class MessageCreate(BaseModel):
    content: str = Field(..., description="Message text content.")

class MessageSchema(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

class TravelerProfileSummary(BaseModel):
    destination: Optional[str]
    adults: Optional[int]
    children: Optional[int]
    budget: Optional[float]
    currency: Optional[str]
    duration_days: Optional[int]
    travel_dates: Optional[str]
    hotel_preference: Optional[str]
    transportation_preference: Optional[str]
    interests: List[str]
    accessibility_requirements: List[str]
    special_requests: List[str]
    lead_status: str
    completeness_score: float

    class Config:
        from_attributes = True

class ConversationSchema(BaseModel):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    traveler_profile: Optional[TravelerProfileSummary] = None

    class Config:
        from_attributes = True

class SalesLeadSummary(BaseModel):
    profile: TravelerProfileSummary
    missing_fields: List[str]
    completeness_score: float
    lead_status: str
    recommended_next_action: str
