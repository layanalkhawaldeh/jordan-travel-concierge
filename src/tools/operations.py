import json
import uuid
from typing import Dict, Any, List
from src.database import SessionLocal, HotelModel, ActivityModel, TransportationModel, ConversationModel, SalesLeadModel
from src.tools.base import CalculateTripEstimateSchema, CreateTripProposalSchema, SubmitSalesLeadSchema, ToolValidationError, SimulateTripChangeSchema, OptimizeTripSchema


def calculate_trip_estimate(
    hotel_id: int, 
    duration_days: int, 
    travelers_count: int, 
    activities_ids: List[int], 
    transportation_type: str
) -> str:
    """
    Deterministically calculates the estimated cost of a trip based on database items.
    Does not allow LLM to perform calculations.
    Returns a JSON string containing the detailed cost breakdown.
    """
    try:
        validated = CalculateTripEstimateSchema(
            hotel_id=hotel_id,
            duration_days=duration_days,
            travelers_count=travelers_count,
            activities_ids=activities_ids,
            transportation_type=transportation_type
        )
    except ToolValidationError as ve:
        return json.dumps({"success": False, "error": str(ve)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Invalid arguments: {e}"}, ensure_ascii=False)

    db = SessionLocal()
    try:
        # 1. Fetch Hotel
        hotel = db.query(HotelModel).filter(HotelModel.id == validated.hotel_id).first()
        if not hotel:
            return json.dumps({"success": False, "error": f"Hotel with ID {validated.hotel_id} not found."}, ensure_ascii=False)
        
        # 2. Fetch Transportation
        transport = db.query(TransportationModel).filter(TransportationModel.type == validated.transportation_type).first()
        if not transport:
            return json.dumps({"success": False, "error": f"Transportation type '{validated.transportation_type}' not found."}, ensure_ascii=False)

        # 3. Fetch Activities
        activities = db.query(ActivityModel).filter(ActivityModel.id.in_(validated.activities_ids)).all()
        found_ids = {act.id for act in activities}
        missing_ids = [aid for aid in validated.activities_ids if aid not in found_ids]
        if missing_ids:
            return json.dumps({"success": False, "error": f"Activities with IDs {missing_ids} not found."}, ensure_ascii=False)

        # 4. Deterministic Calculations
        hotel_total = hotel.price_per_night * validated.duration_days
        transport_total = transport.price_per_day * validated.duration_days
        
        activities_total = sum(act.price for act in activities) * validated.travelers_count
        
        total_cost = hotel_total + transport_total + activities_total
        
        breakdown = {
            "hotel": {
                "name": hotel.name,
                "price_per_night": hotel.price_per_night,
                "nights": validated.duration_days,
                "total": hotel_total
            },
            "transportation": {
                "type": transport.type,
                "price_per_day": transport.price_per_day,
                "days": validated.duration_days,
                "total": transport_total
            },
            "activities": [
                {"id": act.id, "name": act.name, "price_per_person": act.price}
                for act in activities
            ],
            "activities_total": activities_total,
            "total_estimated_cost": total_cost,
            "currency": "USD" # default database currency is USD
        }
        
        return json.dumps({
            "success": True,
            "breakdown": breakdown
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Calculation failed: {str(e)}"}, ensure_ascii=False)
    finally:
        db.close()

def create_trip_proposal(
    conversation_id: str,
    hotel_id: int,
    activities_ids: List[int],
    transportation_type: str,
    duration_days: int,
    travelers_count: int
) -> str:
    """
    Prepares a structured trip proposal, runs constraint validation against traveler budget,
    automatically triggers replanning up to 3 attempts if over-budget, saves it, and returns the summary.
    """
    try:
        validated = CreateTripProposalSchema(
            conversation_id=conversation_id,
            hotel_id=hotel_id,
            activities_ids=activities_ids,
            transportation_type=transportation_type,
            duration_days=duration_days,
            travelers_count=travelers_count
        )
    except Exception as e:
        return json.dumps({"success": False, "error": f"Argument validation failed: {str(e)}"}, ensure_ascii=False)

    db = SessionLocal()
    try:
        # Check conversation exists
        conv = db.query(ConversationModel).filter(ConversationModel.id == validated.conversation_id).first()
        if not conv:
            return json.dumps({"success": False, "error": f"Conversation with ID '{validated.conversation_id}' not found."}, ensure_ascii=False)

        profile = conv.traveler_profile or {}
        budget_amt = profile.get("budget", {}).get("amount")
        budget_currency = profile.get("budget", {}).get("currency") or "USD"

        # 1. Run the initial deterministic cost calculation
        calc_result_json = calculate_trip_estimate(
            hotel_id=validated.hotel_id,
            duration_days=validated.duration_days,
            travelers_count=validated.travelers_count,
            activities_ids=validated.activities_ids,
            transportation_type=validated.transportation_type
        )
        
        calc_res = json.loads(calc_result_json)
        if not calc_res.get("success"):
            return json.dumps({"success": False, "error": f"Could not generate proposal: {calc_res.get('error')}"}, ensure_ascii=False)
        
        breakdown = calc_res["breakdown"]
        total_cost = breakdown["total_estimated_cost"]

        # 2. Constraint Check and Automatic Replanning (Parts 14, 15)
        replanning_notes = []
        is_replanned = False
        
        current_hotel_id = validated.hotel_id
        current_transport = validated.transportation_type
        current_activities = list(validated.activities_ids)

        if budget_amt and total_cost > budget_amt:
            replanning_notes.append(f"Initial estimate of ${total_cost} exceeded budget of ${budget_amt}. Triggering automatic replanning.")
            
            # --- ATTEMPT 1: Try a cheaper hotel in the same city ---
            initial_hotel = db.query(HotelModel).filter(HotelModel.id == current_hotel_id).first()
            if initial_hotel:
                cheaper_hotel = db.query(HotelModel).filter(
                    HotelModel.city == initial_hotel.city,
                    HotelModel.price_per_night < initial_hotel.price_per_night,
                    HotelModel.availability_status == True
                ).order_by(HotelModel.price_per_night.asc()).first()
                
                if cheaper_hotel:
                    current_hotel_id = cheaper_hotel.id
                    replanning_notes.append(f"Attempt 1: Swapped to cheaper hotel '{cheaper_hotel.name}' (${cheaper_hotel.price_per_night}/night).")
                    
                    # Recalculate cost
                    calc_res_temp = json.loads(calculate_trip_estimate(
                        hotel_id=current_hotel_id, duration_days=validated.duration_days,
                        travelers_count=validated.travelers_count, activities_ids=current_activities,
                        transportation_type=current_transport
                    ))
                    if calc_res_temp.get("success"):
                        breakdown = calc_res_temp["breakdown"]
                        total_cost = breakdown["total_estimated_cost"]
                        if total_cost <= budget_amt:
                            is_replanned = True

            # --- ATTEMPT 2: Swap to cheaper transportation option if still over budget ---
            if budget_amt and total_cost > budget_amt:
                active_transport = db.query(TransportationModel).filter(TransportationModel.type == current_transport).first()
                if active_transport:
                    cheaper_transport = db.query(TransportationModel).filter(
                        TransportationModel.price_per_day < active_transport.price_per_day
                    ).order_by(TransportationModel.price_per_day.asc()).first()
                    
                    if cheaper_transport:
                        current_transport = cheaper_transport.type
                        replanning_notes.append(f"Attempt 2: Swapped transport to '{cheaper_transport.type}' (${cheaper_transport.price_per_day}/day).")
                        
                        # Recalculate cost
                        calc_res_temp = json.loads(calculate_trip_estimate(
                            hotel_id=current_hotel_id, duration_days=validated.duration_days,
                            travelers_count=validated.travelers_count, activities_ids=current_activities,
                            transportation_type=current_transport
                        ))
                        if calc_res_temp.get("success"):
                            breakdown = calc_res_temp["breakdown"]
                            total_cost = breakdown["total_estimated_cost"]
                            if total_cost <= budget_amt:
                                is_replanned = True

            # --- ATTEMPT 3: Remove the most expensive activity if still over budget ---
            if budget_amt and total_cost > budget_amt and current_activities:
                db_activities = db.query(ActivityModel).filter(ActivityModel.id.in_(current_activities)).all()
                if db_activities:
                    # Sort by price descending
                    db_activities.sort(key=lambda x: x.price, reverse=True)
                    removed_act = db_activities[0]
                    current_activities.remove(removed_act.id)
                    replanning_notes.append(f"Attempt 3: Removed expensive activity '{removed_act.name}' (saved ${removed_act.price * validated.travelers_count}).")
                    
                    # Recalculate cost
                    calc_res_temp = json.loads(calculate_trip_estimate(
                        hotel_id=current_hotel_id, duration_days=validated.duration_days,
                        travelers_count=validated.travelers_count, activities_ids=current_activities,
                        transportation_type=current_transport
                    ))
                    if calc_res_temp.get("success"):
                        breakdown = calc_res_temp["breakdown"]
                        total_cost = breakdown["total_estimated_cost"]
                        if total_cost <= budget_amt:
                            is_replanned = True

        # 3. Build structured proposal data
        proposal_data = {
            "proposal_id": f"prop-{uuid.uuid4().hex[:8]}",
            "hotel_id": current_hotel_id,
            "hotel_name": breakdown["hotel"]["name"],
            "activities_ids": current_activities,
            "activities": [act["name"] for act in breakdown["activities"]],
            "transportation_type": current_transport,
            "duration_days": validated.duration_days,
            "travelers_count": validated.travelers_count,
            "total_cost": total_cost,
            "budget_status": "Within Budget" if (budget_amt and total_cost <= budget_amt) else ("Over Budget" if budget_amt else "Not Specified"),
            "replanned": is_replanned or len(replanning_notes) > 1,
            "replanning_log": replanning_notes,
            "breakdown": breakdown
        }

        # 4. Save proposal in traveler profile
        profile["current_proposal"] = proposal_data
        conv.traveler_profile = profile
        db.commit()

        message = "Proposal created successfully."
        if is_replanned:
            message = "Proposal created with automatic budget optimizations: " + " -> ".join(replanning_notes[1:])
        elif budget_amt and total_cost > budget_amt:
            message = "Proposal created but is OVER BUDGET. We attempted 3 replanning steps but couldn't fit the budget constraints."

        return json.dumps({
            "success": True,
            "message": message,
            "proposal": proposal_data
        }, ensure_ascii=False)

    except Exception as e:
        db.rollback()
        return json.dumps({"success": False, "error": f"Database operation failed: {str(e)}"}, ensure_ascii=False)
    finally:
        db.close()

def create_booking(conversation_id: str) -> str:
    """
    Pulls the active trip proposal from the conversation, and registers a direct 
    travel booking with status 'pending_payment'. Returns the booking ID.
    """
    db = SessionLocal()
    try:
        conv = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
        if not conv:
            return json.dumps({"success": False, "error": "Conversation not found."})

        profile = conv.traveler_profile or {}
        proposal = profile.get("current_proposal")
        if not proposal:
            return json.dumps({"success": False, "error": "No trip proposal found in traveler profile. Create a proposal first."})

        # Generate unique Booking ID
        booking_id = f"bk-{uuid.uuid4().hex[:8]}"
        
        # Save to Bookings database
        from src.database import BookingModel
        new_booking = BookingModel(
            booking_id=booking_id,
            conversation_id=conversation_id,
            traveler_profile=profile,
            hotel_name=proposal.get("hotel_name"),
            activities=proposal.get("activities"),
            transportation=proposal.get("transportation_type"),
            total_price=proposal.get("total_cost"),
            status="pending_payment"
        )
        db.add(new_booking)
        
        # Update traveler profile to include the active booking ID
        profile["active_booking_id"] = booking_id
        profile["booking_status"] = "pending_payment"
        conv.traveler_profile = profile
        
        db.commit()
        return json.dumps({
            "success": True,
            "message": "Direct travel booking created successfully in pending_payment state.",
            "booking_id": booking_id,
            "total_price": proposal.get("total_cost"),
            "status": "pending_payment"
        })
    except Exception as e:
        db.rollback()
        return json.dumps({"success": False, "error": f"Booking failed: {e}"})
    finally:
        db.close()

def confirm_booking_payment(booking_id: str) -> str:
    """
    Simulates secure payment gateway processing and confirms the booking.
    Updates booking status to 'booked' and issues confirmation.
    """
    db = SessionLocal()
    try:
        from src.database import BookingModel
        booking = db.query(BookingModel).filter(BookingModel.booking_id == booking_id).first()
        if not booking:
            return json.dumps({"success": False, "error": f"No booking found with ID '{booking_id}'."})

        if booking.status == "booked":
            return json.dumps({
                "success": True,
                "message": "Booking was already confirmed and paid.",
                "booking_id": booking_id,
                "status": "booked"
            })

        # Update booking status
        booking.status = "booked"
        
        # Also update corresponding conversation profile if it matches
        conv = db.query(ConversationModel).filter(ConversationModel.id == booking.conversation_id).first()
        if conv:
            profile = conv.traveler_profile or {}
            profile["booking_status"] = "booked"
            conv.traveler_profile = profile
            
        db.commit()
        return json.dumps({
            "success": True,
            "message": f"Payment processed successfully! Booking {booking_id} status updated to 'booked'.",
            "booking_id": booking_id,
            "status": "booked",
            "invoice_summary": {
                "hotel": booking.hotel_name,
                "activities_count": len(booking.activities or []),
                "transport": booking.transportation,
                "amount_paid": booking.total_price
            }
        })
    except Exception as e:
        db.rollback()
        return json.dumps({"success": False, "error": f"Payment confirmation failed: {e}"})
    finally:
        db.close()

def submit_sales_lead(conversation_id: str) -> str:
    """
    Submits the generated trip proposal as a qualified sales lead to the database.
    Enforces idempotency (duplicate check).
    """
    try:
        validated = SubmitSalesLeadSchema(conversation_id=conversation_id)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Argument validation failed: {str(e)}"}, ensure_ascii=False)

    db = SessionLocal()
    try:
        # 1. Fetch Conversation
        conv = db.query(ConversationModel).filter(ConversationModel.id == validated.conversation_id).first()
        if not conv:
            return json.dumps({"success": False, "error": f"Conversation '{validated.conversation_id}' not found."}, ensure_ascii=False)
            
        profile = conv.traveler_profile or {}
        proposal = profile.get("current_proposal")
        if not proposal:
            return json.dumps({
                "success": False, 
                "error": "No trip proposal found in traveler profile. Please create a trip proposal first using create_trip_proposal."
            }, ensure_ascii=False)

        # 2. Idempotency Check (Duplicate Protection)
        # Check if a lead with this conversation_id already exists in the database
        existing_lead = db.query(SalesLeadModel).filter(SalesLeadModel.conversation_id == validated.conversation_id).first()
        if existing_lead:
            return json.dumps({
                "success": True,
                "is_duplicate": True,
                "message": "A sales lead has already been submitted for this conversation.",
                "lead_id": existing_lead.lead_id,
                "status": existing_lead.status,
                "estimated_cost": existing_lead.estimated_cost
            }, ensure_ascii=False)#اذا الحدا كبس على سيند مرتين مثلا مش رح ينشئ سطر مكرر بالداتا بيس 

        # 3. Create new Sales Lead
        lead_id = f"lead-{uuid.uuid4().hex[:8]}"
        new_lead = SalesLeadModel(
            lead_id=lead_id,
            conversation_id=validated.conversation_id,
            traveler_profile=profile,
            selected_options={
                "hotel": proposal.get("hotel_name"),
                "activities": proposal.get("activities"),
                "transportation": proposal.get("transportation_type")
            },
            estimated_cost=proposal.get("total_cost", 0.0),
            status="pending"
        )
        
        db.add(new_lead)
        db.commit()
        
        return json.dumps({
            "success": True,
            "is_duplicate": False,
            "message": "Sales lead submitted successfully.",
            "lead_id": lead_id,
            "status": "pending"
        }, ensure_ascii=False)
    finally:
        db.close()

def simulate_trip_change(conversation_id: str, change_type: str, new_value: str) -> str:
    """
    Simulates changes to an existing trip proposal and displays price difference (savings or extra cost).
    Does not modify the saved proposal unless explicitly asked; just simulates.
    """
    db = SessionLocal()
    try:
        conv = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
        if not conv:
            return json.dumps({"success": False, "error": "Conversation not found."})
            
        profile = conv.traveler_profile or {}
        proposal = profile.get("current_proposal")
        if not proposal:
            return json.dumps({"success": False, "error": "No current trip proposal found to simulate changes. Create a proposal first."})
            
        breakdown = proposal["breakdown"]
        
        # Current values
        hotel_id = proposal["hotel_id"]
        duration_days = proposal["duration_days"]
        travelers_count = proposal["travelers_count"]
        activities_ids = proposal["activities_ids"]
        transportation_type = proposal["transportation_type"]
        current_total = proposal["total_cost"]
        
        # Apply change
        change_desc = ""
        if change_type == "hotel":
            new_hotel_id = int(new_value)
            hotel = db.query(HotelModel).filter(HotelModel.id == new_hotel_id).first()
            if not hotel:
                return json.dumps({"success": False, "error": f"Hotel ID {new_hotel_id} not found."})
            hotel_id = new_hotel_id
            change_desc = f"Change hotel to '{hotel.name}'"
        elif change_type == "transportation":                                         #بيتجاهل الاحرف عربي وانجليزي 
            transport = db.query(TransportationModel).filter(TransportationModel.type.ilike(new_value)).first()
            if not transport:
                return json.dumps({"success": False, "error": f"Transportation type '{new_value}' not found."})
            transportation_type = transport.type
            change_desc = f"Change transportation to '{transport.type}'"
        elif change_type == "remove_activity":
            act_id = int(new_value)
            if act_id in activities_ids:
                activities_ids = [aid for aid in activities_ids if aid != act_id]
                act = db.query(ActivityModel).filter(ActivityModel.id == act_id).first()
                change_desc = f"Remove activity '{act.name if act else act_id}'"
            else:
                return json.dumps({"success": False, "error": f"Activity ID {act_id} is not in the current proposal."})
        elif change_type == "add_activity":
            act_id = int(new_value)
            if act_id not in activities_ids:
                act = db.query(ActivityModel).filter(ActivityModel.id == act_id).first()
                if not act:
                    return json.dumps({"success": False, "error": f"Activity ID {act_id} not found."})
                activities_ids = list(activities_ids) + [act_id]
                change_desc = f"Add activity '{act.name}'"
            else:
                return json.dumps({"success": False, "error": f"Activity ID {act_id} is already in the current proposal."})
        elif change_type == "duration":
            new_dur = int(new_value)
            if new_dur < 1:
                return json.dumps({"success": False, "error": "Duration must be at least 1 day."})
            duration_days = new_dur
            change_desc = f"Change duration to {new_dur} days"
        else:
            return json.dumps({"success": False, "error": f"Unsupported change type '{change_type}'."})

        # Calculate new total
        hotel = db.query(HotelModel).filter(HotelModel.id == hotel_id).first()
        transport = db.query(TransportationModel).filter(TransportationModel.type == transportation_type).first()
        activities = db.query(ActivityModel).filter(ActivityModel.id.in_(activities_ids)).all()
        
        hotel_total = hotel.price_per_night * duration_days
        transport_total = transport.price_per_day * duration_days
        activities_total = sum(act.price for act in activities) * travelers_count
        new_total = hotel_total + transport_total + activities_total
        
        diff = current_total - new_total
        status = "saving" if diff > 0 else "extra_cost"
        
        return json.dumps({
            "success": True,
            "simulation": {
                "change_description": change_desc,
                "original_cost": current_total,
                "new_cost": new_total,
                "difference": abs(diff),
                "status": status,
                "explanation": f"Current proposal: {current_total} USD | Simulated proposal: {new_total} USD | Difference: Savings of {diff} USD" if diff > 0 else f"Current proposal: {current_total} USD | Simulated proposal: {new_total} USD | Difference: Extra cost of {abs(diff)} USD"
            }
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": f"Simulation failed: {str(e)}"})
    finally:
        db.close()

def optimize_trip(conversation_id: str) -> str:
    """
    Analyzes current traveler preferences and searches the database for the 
    best value combination (cheapest hotel with preferred star rating and cheapest transport)
    to save money for the client.
    """
    db = SessionLocal()
    try:
        conv = db.query(ConversationModel).filter(ConversationModel.id == conversation_id).first()
        if not conv:
            return json.dumps({"success": False, "error": "Conversation not found."})
            
        profile = conv.traveler_profile or {}
        proposal = profile.get("current_proposal")
        
        # Preferred parameters
        city = profile.get("destination", "Amman")
        duration_days = profile.get("duration_days") or 5
        travelers_count = (profile.get("travelers") or {}).get("adults") or 2
        hotel_pref = profile.get("hotel_preference")
        
        # Try to infer preferred stars
        stars = 5
        if hotel_pref:
            for s in ["2", "3", "4", "5"]:
                if s in str(hotel_pref):
                    stars = int(s)
                    break
        
        # Find cheapest hotel in the city with specified stars (or fallback to any hotel in city if none found)
        hotel = db.query(HotelModel).filter(
            HotelModel.city == city,
            HotelModel.stars == stars,
            HotelModel.availability_status == True
        ).order_by(HotelModel.price_per_night.asc()).first()
        
        if not hotel:
            hotel = db.query(HotelModel).filter(
                HotelModel.city == city,
                HotelModel.stars == (stars - 1),
                HotelModel.availability_status == True
            ).order_by(HotelModel.price_per_night.asc()).first()
            
        if not hotel:
            hotel = db.query(HotelModel).filter(
                HotelModel.city == city,
                HotelModel.availability_status == True
            ).order_by(HotelModel.price_per_night.asc()).first()
            
        if not hotel:
            return json.dumps({"success": False, "error": f"No available hotels found in '{city}' to optimize."})
            
        # Find cheapest transport
        transport = db.query(TransportationModel).order_by(TransportationModel.price_per_day.asc()).first()
        if not transport:
            return json.dumps({"success": False, "error": "No transportation options found in database."})
            
        # Select active activities
        activities = db.query(ActivityModel).filter(ActivityModel.city == city).order_by(ActivityModel.price.asc()).limit(2).all()
        activities_ids = [act.id for act in activities]
        
        # Calculations
        hotel_total = hotel.price_per_night * duration_days
        transport_total = transport.price_per_day * duration_days
        activities_total = sum(act.price for act in activities) * travelers_count
        optimized_total = hotel_total + transport_total + activities_total
        
        current_cost = proposal.get("total_cost") if proposal else (profile.get("budget") or {}).get("amount") or 2000.0
        savings = current_cost - optimized_total
        
        opt_package = {
            "hotel_id": hotel.id,
            "hotel_name": hotel.name,
            "hotel_stars": hotel.stars,
            "hotel_price_per_night": hotel.price_per_night,
            "transportation_type": transport.type,
            "transport_price_per_day": transport.price_per_day,
            "activities": [act.name for act in activities],
            "activities_ids": activities_ids,
            "total_cost": optimized_total,
            "savings": max(0.0, savings),
            "breakdown": {
                "hotel_total": hotel_total,
                "transport_total": transport_total,
                "activities_total": activities_total
            }
        }
        
        return json.dumps({
            "success": True,
            "optimized_package": opt_package,
            "explanation": f"Best value package suggestion: Hotel {hotel.name} ({hotel.stars}-star) with transportation {transport.type} and activities: {', '.join([act.name for act in activities])}. Total optimized cost: {optimized_total} USD. Expected savings: {max(0.0, savings)} USD!"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Optimization failed: {str(e)}"})
    finally:
        db.close()

