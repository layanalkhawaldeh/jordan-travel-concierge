from schemas import TravelerProfileSchema, TravelerProfileSummary

ESSENTIAL_FIELDS = {
    "destination": "Destination Country/City",
    "adults": "Number of Travelers (Adults/Children)",
    "duration_days": "Trip Duration (Days)",
    "travel_dates": "Travel Dates/Period",
    "budget": "Trip Budget"
}

def calculate_completeness_and_status(profile: TravelerProfileSchema) -> tuple[float, str, list[str]]:
    """
    Deterministically computes traveler profile completeness score,
    lead qualification status, and lists missing fields.
    """
    # 1. Out of Scope Check
    # If the LLM flag or intent indicates it's not tourism related, it's immediately Out of Scope
    if profile.is_tourism_related is False or (profile.customer_intent and "out of scope" in profile.customer_intent.lower()):
        return 0.0, "Out of Scope", []

    # 2. Check essential fields
    missing_fields = []
    present_count = 0
    
    # Check Destination
    if profile.destination and profile.destination.strip().lower() not in ["none", "unknown", "null", ""]:
        present_count += 1
    else:
        missing_fields.append("destination")
        
    # Check Travelers
    if profile.adults is not None and profile.adults > 0:
        present_count += 1
    else:
        missing_fields.append("adults")
        
    # Check Duration
    if profile.duration_days is not None and profile.duration_days > 0:
        present_count += 1
    else:
        missing_fields.append("duration_days")
        
    # Check Travel Dates
    if profile.travel_dates and profile.travel_dates.strip().lower() not in ["none", "unknown", "null", ""]:
        present_count += 1
    else:
        missing_fields.append("travel_dates")
        
    # Check Budget
    if profile.budget is not None and profile.budget > 0:
        present_count += 1
    else:
        missing_fields.append("budget")

    # 3. Calculate completeness score based on these 5 essential fields
    completeness_score = (present_count / 5.0) * 100.0

    # 4. Lead Status
    if len(missing_fields) == 0:
        lead_status = "Ready for Sales"
    else:
        lead_status = "Incomplete"

    return completeness_score, lead_status, missing_fields

def get_recommended_next_action(lead_status: str, missing_fields: list[str]) -> str:
    """Returns a deterministic recommendation based on lead status."""
    if lead_status == "Out of Scope":
        return "Politely decline request and archive the conversation."
    elif lead_status == "Ready for Sales":
        return "IMMEDIATE ACTION: Hand over profile to senior travel advisor to prepare draft itinerary and price quote."
    else:
        # Convert keys to readable names
        readable_missing = [ESSENTIAL_FIELDS[f] for f in missing_fields]
        return f"Collect missing essential information: {', '.join(readable_missing)}."
