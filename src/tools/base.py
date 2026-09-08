from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

class ToolValidationError(Exception):#(ال Inputs غلط)
    """Exception raised when tool arguments are invalid."""
    pass

class ToolExecutionError(Exception):#(ال Inputs صح بس التنفيذ غلط)
    """Exception raised when tool execution fails."""
    pass

# Helper cities list
#ليش ؟ لو الشركة قررت مستقبلاً تدعم السياحة بـ "مادبا"؛ المطور بس بضيف كلمة "Madaba" لهي القائمة وبكل سهولة السيستم كله بتعرف عليها!
SUPPORTED_CITIES = ["Amman", "Petra", "Dead Sea", "Wadi Rum", "Aqaba"]
SUPPORTED_INTERESTS = ["history", "adventure", "nature", "relaxation"]
SUPPORTED_TRANSPORTATION = ["Private Driver", "Rental Car", "Public Bus"]

class SearchHotelsSchema(BaseModel):
    city: str = Field(description="The city to search for hotels (e.g., Amman, Petra, Dead Sea, Wadi Rum, Aqaba).")
    stars: Optional[int] = Field(default=None, description="Preferred star rating of the hotel (between 2 and 5).")
    max_price: Optional[float] = Field(default=None, description="Maximum budget price per night (must be positive).")

    @field_validator("city")#بتفحصلي المدينة باذات
    @classmethod
    def validate_city(cls, v: str) -> str:
        city_title = v.strip().title()
        if city_title not in SUPPORTED_CITIES:
            raise ToolValidationError(f"City '{v}' is not supported. Supported cities are: {', '.join(SUPPORTED_CITIES)}")
        return city_title

    @field_validator("stars")
    @classmethod
    def validate_stars(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 2 or v > 5):
            raise ToolValidationError("Star rating must be between 2 and 5 stars.")
        return v

    @field_validator("max_price")
    @classmethod
    def validate_max_price(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ToolValidationError("Maximum price must be a positive number.")
        return v

class SearchActivitiesSchema(BaseModel):
    city: str = Field(description="The city to search for activities (e.g., Amman, Petra, Dead Sea, Wadi Rum, Aqaba).")
    interest_type: Optional[str] = Field(default=None, description="Type of interest (history, adventure, nature, relaxation).")

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        city_title = v.strip().title()
        if city_title not in SUPPORTED_CITIES:
            raise ToolValidationError(f"City '{v}' is not supported. Supported cities are: {', '.join(SUPPORTED_CITIES)}")
        return city_title

    @field_validator("interest_type")
    @classmethod
    def validate_interest(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            val = v.strip().lower()
            if val not in SUPPORTED_INTERESTS:
                raise ToolValidationError(f"Interest type '{v}' is not supported. Supported: {', '.join(SUPPORTED_INTERESTS)}")
            return val
        return v

class SearchTransportationSchema(BaseModel):
    transport_type: Optional[str] = Field(default=None, description="Optional transportation type (Private Driver, Rental Car, Public Bus).")

    @field_validator("transport_type")
    @classmethod
    def validate_transport_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            # Match case insensitive but return standardized string
            val = v.strip().lower()
            for supported in SUPPORTED_TRANSPORTATION:
                if val == supported.lower():
                    return supported
            raise ToolValidationError(f"Transportation type '{v}' is not supported. Supported: {', '.join(SUPPORTED_TRANSPORTATION)}")
        return v

class CalculateTripEstimateSchema(BaseModel):
    hotel_id: int = Field(description="The unique database ID of the selected hotel.")
    duration_days: int = Field(description="Length of the trip in days (must be at least 1).")
    travelers_count: int = Field(description="Number of travelers (must be at least 1).")
    activities_ids: List[int] = Field(default_factory=list, description="IDs of selected activities from search_activities.")
    transportation_type: str = Field(description="Standardized transportation type (Private Driver, Rental Car, Public Bus).")

    @field_validator("duration_days")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < 1:
            raise ToolValidationError("Duration of trip must be at least 1 day.")
        return v

    @field_validator("travelers_count")
    @classmethod
    def validate_travelers(cls, v: int) -> int:
        if v < 1:
            raise ToolValidationError("Travelers count must be at least 1.")
        return v

    @field_validator("transportation_type")
    @classmethod
    def validate_transportation(cls, v: str) -> str:
        val = v.strip().lower()
        for supported in SUPPORTED_TRANSPORTATION:
            if val == supported.lower():
                return supported
        raise ToolValidationError(f"Transportation type '{v}' is not supported. Supported: {', '.join(SUPPORTED_TRANSPORTATION)}")

class CreateTripProposalSchema(BaseModel):
    conversation_id: str = Field(description="The unique identifier of the active conversation.")
    hotel_id: int = Field(description="The unique database ID of the selected hotel.")
    activities_ids: List[int] = Field(default_factory=list, description="List of unique IDs of selected activities.")
    transportation_type: str = Field(description="Selected transportation type.")
    duration_days: int = Field(description="Duration of the trip in days.")
    travelers_count: int = Field(description="Number of travelers.")

class SubmitSalesLeadSchema(BaseModel):
    conversation_id: str = Field(description="The unique identifier of the active conversation.")

class GetSalesLeadStatusSchema(BaseModel):
    lead_id: str = Field(description="The unique lead ID returned when the lead was submitted (e.g. lead_xxxxx).")

class SimulateTripChangeSchema(BaseModel):
    conversation_id: str = Field(description="The unique identifier of the active conversation.")
    change_type: str = Field(description="The aspect to change: 'hotel' (change hotel), 'transportation' (change transport type), 'remove_activity' (remove an activity), 'add_activity' (add an activity), 'duration' (change duration in days).")
    new_value: str = Field(description="The new value for the change (e.g., ID of new hotel, new transport type, ID of activity to remove/add, or new number of days/travelers).")

class OptimizeTripSchema(BaseModel):
    conversation_id: str = Field(description="The unique identifier of the active conversation.")

class SearchWebSchema(BaseModel):
    query: str = Field(description="The search query term to look up on the web (e.g. 'Jordan weather October', 'Petra museum tickets').")

class SearchPlacesSchema(BaseModel):
    query: str = Field(description="The landmark, attraction, restaurant or place in Jordan to search (e.g. 'Petra', 'Amman Citadel').")

class SearchKnowledgeBaseSchema(BaseModel):
    query: str = Field(description="The policy or guide question to search (e.g. 'cancellation refund policy', 'visa cost').")

class CreateBookingSchema(BaseModel):
    conversation_id: str = Field(description="The unique identifier of the active conversation.")

class ConfirmBookingPaymentSchema(BaseModel):
    booking_id: str = Field(description="The unique booking ID to confirm and pay (e.g. bk-xxxxxx).")


