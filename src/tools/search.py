import json
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
from src.database import SessionLocal, HotelModel, ActivityModel, TransportationModel, SalesLeadModel
from src.tools.base import SearchHotelsSchema, SearchActivitiesSchema, SearchTransportationSchema, GetSalesLeadStatusSchema, ToolValidationError, SearchWebSchema


def search_hotels(city: str, stars: Optional[int] = None, max_price: Optional[float] = None) -> str:
    """
    Search available hotels in a specific city with optional stars and max price.
    Returns a JSON string containing the list of matching hotels.
    """
    # 1. Validate parameters using schema
    try:
        validated = SearchHotelsSchema(city=city, stars=stars, max_price=max_price)
    except ToolValidationError as ve:
        return json.dumps({"success": False, "error": str(ve)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Invalid arguments: {e}"}, ensure_ascii=False)

    db = SessionLocal()
    try:
        query = db.query(HotelModel).filter(
            HotelModel.city == validated.city,
            HotelModel.availability_status == True# متاحة للحجز
        )
        if validated.stars is not None:
            query = query.filter(HotelModel.stars == validated.stars)
        if validated.max_price is not None:
            query = query.filter(HotelModel.price_per_night <= validated.max_price)
            
        hotels = query.all()
        
        result_list = []
        for h in hotels:
            result_list.append({
                "id": h.id,
                "name": h.name,
                "city": h.city,
                "stars": h.stars,
                "price_per_night": h.price_per_night,
                "capacity": h.capacity,
                "amenities": h.amenities#["Pool", "Gym", "Spa", "Free WiFi"]
            })
            
        return json.dumps({
            "success": True,
            "count": len(result_list),
            "hotels": result_list
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Database query failed: {str(e)}"}, ensure_ascii=False)
    finally:
        db.close()

def search_activities(city: str, interest_type: Optional[str] = None) -> str:
    """
    Search activities and attractions in a specific city with optional interest category.
    Returns a JSON string containing the matching activities.
    """
    try:
        validated = SearchActivitiesSchema(city=city, interest_type=interest_type)
    except ToolValidationError as ve:
        return json.dumps({"success": False, "error": str(ve)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Invalid arguments: {e}"}, ensure_ascii=False)

    db = SessionLocal()
    try:
        query = db.query(ActivityModel).filter(ActivityModel.city == validated.city)
        if validated.interest_type is not None:
            query = query.filter(ActivityModel.interest_type == validated.interest_type)
            
        activities = query.all()
        
        result_list = []
        for act in activities:
            result_list.append({
                "id": act.id,
                "name": act.name,
                "city": act.city,
                "price": act.price,
                "interest_type": act.interest_type,
                "description": act.description
            })
            
        return json.dumps({
            "success": True,
            "count": len(result_list),
            "activities": result_list
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Database query failed: {str(e)}"}, ensure_ascii=False)
    finally:
        db.close()

def search_transportation(transport_type: Optional[str] = None) -> str:
    """
    Search available transportation options and their pricing.
    Returns a JSON string containing the transportation options.
    """
    try:
        validated = SearchTransportationSchema(transport_type=transport_type)
    except ToolValidationError as ve:
        return json.dumps({"success": False, "error": str(ve)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Invalid arguments: {e}"}, ensure_ascii=False)

    db = SessionLocal()
    try:
        query = db.query(TransportationModel)
        if validated.transport_type is not None:
            query = query.filter(TransportationModel.type == validated.transport_type)
            
        options = query.all()
        
        result_list = []
        for opt in options:
            result_list.append({
                "id": opt.id,
                "type": opt.type,
                "price_per_day": opt.price_per_day,
                "description": opt.description
            })
            
        return json.dumps({
            "success": True,
            "count": len(result_list),
            "transportation_options": result_list
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Database query failed: {str(e)}"}, ensure_ascii=False)
    finally:
        db.close()

def get_sales_lead_status(lead_id: str) -> str:
    """
    Check the status of an existing sales lead submission.
    Returns a JSON string containing lead status.
    """
    try:
        validated = GetSalesLeadStatusSchema(lead_id=lead_id)
    except ToolValidationError as ve:
        return json.dumps({"success": False, "error": str(ve)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Invalid arguments: {e}"}, ensure_ascii=False)

    db = SessionLocal()
    try:
        lead = db.query(SalesLeadModel).filter(SalesLeadModel.lead_id == validated.lead_id).first()
        if not lead:
            return json.dumps({
                "success": False,
                "error": f"No sales lead found with ID '{validated.lead_id}'."
            }, ensure_ascii=False)
            
        return json.dumps({
            "success": True,
            "lead_id": lead.lead_id,
            "conversation_id": lead.conversation_id,
            "status": lead.status,
            "created_at": lead.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "estimated_cost": lead.estimated_cost
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Database query failed: {str(e)}"}, ensure_ascii=False)
    finally:
        db.close()

def search_web_for_tourism(query: str) -> str:
    """
    Searches the web for tourism info, flight prices, travel reviews, attractions, or general up-to-date Jordan travel data.
    Returns a JSON string containing search result snippets.
    """
    try:
        validated = SearchWebSchema(query=query)
    except ToolValidationError as ve:
        return json.dumps({"success": False, "error": str(ve)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Invalid arguments: {e}"}, ensure_ascii=False)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    url = f"https://html.duckduckgo.com/html/?q={validated.query}+jordan+tourism"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return json.dumps({"success": False, "error": f"Search engine returned status code {r.status_code}."})
        
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.find_all("a", class_="result__snippet")[:3]:
            results.append(a.text.strip())
            
        if not results:
            return json.dumps({"success": True, "results": ["No matching results found on the web."]}, ensure_ascii=False)
            
        return json.dumps({"success": True, "results": results}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

def search_places(query: str) -> str:
    """
    Search interesting places, tourist attractions, landmarks, restaurants, 
    or sites in Jordan using Google Places API (with local fallback).
    """
    try:
        from src.services.providers import GooglePlacesProvider
        provider = GooglePlacesProvider()
        results = provider.search_places(query)
        return json.dumps({
            "success": True,
            "count": len(results),
            "places": results
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Places search failed: {e}"}, ensure_ascii=False)

def search_knowledge_base(query: str) -> str:
    """
    Search company policies, guides, visa requirements, tipping rules, 
    FAQs, and regulations. Essential for answering policy questions.
    """
    try:
        from src.services.rag_service import retrieve_relevant_knowledge
        results = retrieve_relevant_knowledge(query, limit=3)
        return json.dumps({
            "success": True,
            "count": len(results),
            "results": results
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"RAG query failed: {e}"}, ensure_ascii=False)
