import os
import time
import requests
import hashlib
import json
from abc import ABC, abstractmethod #Abstract Base Class
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.database import SessionLocal, HotelModel, ActivityModel, ApiCacheModel
import src.config as config

# Interface definitions
class HotelProvider(ABC):
    @abstractmethod
    def search_hotels(self, city: str, stars: Optional[int] = None, max_price: Optional[float] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_hotel_details(self, hotel_id: str) -> Optional[Dict[str, Any]]:
        pass
    """
    تخيلي لو إنتِ بدك توظفي ناس يشتغلوا عندك "موصلين طلبات"، عشان تضمن كل الموظفين يشتغلوا بنفس الطريقة، بتعمليلهم قانون موحد وبتحكيلهم: 
    "أي واحد بدو يشتغل عندي دليفري، غصباً عنه لازم يسوي شغلتين: يروح يستلم الطلب، ويسلم الطلب للزبون".

هاد الكلاس HotelProvider هو هاد القانون الموحد بالظبط!

هو بحد ذاته ما بعمل إشي وما بجيب فنادق (عشان هيك كاتبين جواه pass يعني مرقها بدون كود).
بس وظيفته يفرض شروط صارمة على الكلاسات الثانية اللي رح تعمل الشغل الحقيقي (مثل كود الـ OpenStreetMap أو كود الداتا بيس المحلية).
بفضل كلمة @abstractmethod، أي كلاس بنكتبه بعدين وبنحكي إنه برتبط بالـ HotelProvider (برث منه)، غصباً عنه لازم يبرمج ويكتب هدول الفنكشنين بالظبط وبنفس الأسماء! لو نسى المبرمج يكتب واحد منهم، البايثون رح يعصب ويعطي خطأ ويوقف البرنامج فوراً.

    """

# 1. Local Database Hotel Provider
class LocalDatabaseHotelProvider(HotelProvider):
    def search_hotels(self, city: str, stars: Optional[int] = None, max_price: Optional[float] = None) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            city_title = city.strip().title()
            query = db.query(HotelModel).filter(
                HotelModel.city == city_title,
                HotelModel.availability_status == True
            )
            if stars is not None:
                query = query.filter(HotelModel.stars == stars)
            if max_price is not None:
                query = query.filter(HotelModel.price_per_night <= max_price)
                
            hotels = query.all()
            return [
                {
                    "id": str(h.id),
                    "name": h.name,
                    "city": h.city,
                    "stars": h.stars,
                    "price_per_night": h.price_per_night,
                    "capacity": h.capacity,
                    "amenities": h.amenities,
                    "source": "local_database"
                } for h in hotels
            ]
        except Exception as e:
            print(f"[LocalHotelProvider] Error querying database: {e}")
            return []
        finally:
            db.close()

    def get_hotel_details(self, hotel_id: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            h = db.query(HotelModel).filter(HotelModel.id == int(hotel_id)).first()
            if h:
                return {
                    "id": str(h.id),
                    "name": h.name,
                    "city": h.city,
                    "stars": h.stars,
                    "price_per_night": h.price_per_night,
                    "capacity": h.capacity,
                    "amenities": h.amenities,
                    "source": "local_database"
                }
            return None
        except Exception as e:
            print(f"[LocalHotelProvider] Error getting hotel details: {e}")
            return None
        finally:
            db.close()

# 4. OpenStreetMap Nominatim Hotel Provider (Real-time Keyless Connection)
class NominatimHotelProvider(HotelProvider):
    def search_hotels(self, city: str, stars: Optional[int] = None, max_price: Optional[float] = None) -> List[Dict[str, Any]]:
        url = "https://nominatim.openstreetmap.org/search"
        city_title = city.strip().title()
        params = {
            "q": f"hotels in {city_title} Jordan",
            "format": "json",
            "addressdetails": "1",
            "limit": "5"
        }
        headers = {
            "User-Agent": "JordanTravelConcierge/2.0 (student project fallback)"
        }
        try:
            response = requests.get(url, params=params, headers=headers, timeout=8)
            normalized_hotels = []
            if response.status_code == 200:
                results = response.json()
                for idx, place in enumerate(results[:5]):
                    display_name = place.get("display_name", "")
                    name = display_name.split(",")[0]
                    h_stars = stars if stars is not None else ((idx % 3) + 3)
                    h_price = max_price if max_price is not None else (70.0 + (idx * 30.0))
                    
                    normalized_hotels.append({
                        "id": f"osm-hotel-{place.get('place_id')}",
                        "name": name,
                        "city": city_title,
                        "stars": h_stars,
                        "price_per_night": h_price,
                        "capacity": 2,
                        "amenities": ["Free WiFi", "Breakfast Included", "Air Conditioning"],
                        "source": "openstreetmap_nominatim_api"
                    })
            if normalized_hotels:
                return normalized_hotels
            return LocalDatabaseHotelProvider().search_hotels(city, stars, max_price)
        except Exception as e:
            print(f"[NominatimHotelProvider] Error: {e}")
            return LocalDatabaseHotelProvider().search_hotels(city, stars, max_price)

    def get_hotel_details(self, hotel_id: str) -> Optional[Dict[str, Any]]:
        if not hotel_id.startswith("osm-hotel-"):
            return LocalDatabaseHotelProvider().get_hotel_details(hotel_id)
        return {
            "id": hotel_id,
            "name": f"OSM Hotel Reference {hotel_id[-4:]}",
            "city": "Amman",
            "stars": 4,
            "price_per_night": 110.0,
            "capacity": 2,
            "amenities": ["Free WiFi", "Breakfast Included", "Air Conditioning"],
            "source": "openstreetmap_nominatim_api"
        }

# Provider Factory
class HotelProviderFactory:
    @staticmethod
    def get_provider() -> HotelProvider:
        return NominatimHotelProvider()
    


# 3. Google Places API Provider (with OSM Nominatim fallback)
class GooglePlacesProvider:
    def __init__(self):
        self.api_key = config.GOOGLE_PLACES_API_KEY
        self.base_url = "https://maps.googleapis.com/maps/api/place"

    def search_places(self, query: str) -> List[Dict[str, Any]]:
        if not self.api_key:
            return self._nominatim_search(query)

        # Check Cache
        cache_key = f"google_places_{query}"
        cached = get_cached_response(cache_key)
        if cached:
            return cached

        url = f"{self.base_url}/textsearch/json"
        params = {
            "query": f"{query} Jordan",
            "key": self.api_key
        }

        try:
            response = requests.get(url, params=params, timeout=8)
            if response.status_code == 200:
                results = response.json().get("results", [])
                normalized = []
                for place in results[:5]: # limit to 5
                    normalized.append({
                        "name": place.get("name"),
                        "address": place.get("formatted_address"),
                        "rating": place.get("rating", 0.0),
                        "place_id": place.get("place_id"),
                        "types": place.get("types", []),
                        "source": "google_places_api"
                    })
                set_cached_response(cache_key, normalized)
                return normalized
            else:
                return self._nominatim_search(query)
        except Exception as e:
            print(f"[GooglePlaces] Request failed: {e}")
            return self._nominatim_search(query)

    def _nominatim_search(self, query: str) -> List[Dict[str, Any]]:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": f"{query} Jordan",
            "format": "json",
            "addressdetails": "1",
            "limit": "5"
        }
        headers = {
            "User-Agent": "JordanTravelConcierge/2.0 (student project fallback)"
        }
        try:
            response = requests.get(url, params=params, headers=headers, timeout=8)
            normalized = []
            if response.status_code == 200:
                results = response.json()
                for place in results[:5]:
                    display_name = place.get("display_name", "")
                    name = display_name.split(",")[0]
                    normalized.append({
                        "name": name,
                        "address": display_name,
                        "rating": 4.5,
                        "place_id": f"osm-{place.get('place_id')}",
                        "types": [place.get("type", "monument"), "tourist_attraction"],
                        "source": "openstreetmap_nominatim_api"
                    })
            if normalized:
                return normalized
            return self._local_fallback(query)
        except Exception as e:
            print(f"[OSM Nominatim] Request failed: {e}")
            return self._local_fallback(query)

    def _local_fallback(self, query: str) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            acts = db.query(ActivityModel).filter(
                (ActivityModel.name.ilike(f"%{query}%")) | 
                (ActivityModel.description.ilike(f"%{query}%"))
            ).all()
            
            return [
                {
                    "name": a.name,
                    "address": f"{a.city}, Jordan",
                    "rating": 4.6,
                    "place_id": f"loc-act-{a.id}",
                    "types": [a.interest_type, "tourist_attraction"],
                    "source": "local_database_activities"
                } for a in acts
            ]
        except Exception as e:
            print(f"[GooglePlaces Fallback] Error: {e}")
            return []
        finally:
            db.close()


# Caching helpers
def get_cached_response(key: str) -> Optional[Any]:
    db = SessionLocal()
    try:
        hashed_key = hashlib.md5(key.encode("utf-8")).hexdigest()
        cache = db.query(ApiCacheModel).filter(ApiCacheModel.cache_key == hashed_key).first()
        if cache:
            # Cache is valid for 12 hours
            elapsed = time.time() - cache.created_at.timestamp()
            if elapsed < 43200:
                return cache.response_data
            else:
                db.delete(cache)
                db.commit()
        return None
    except Exception as e:
        print(f"[Cache] Read error: {e}")
        return None
    finally:
        db.close()

def set_cached_response(key: str, data: Any):
    db = SessionLocal()
    try:
        hashed_key = hashlib.md5(key.encode("utf-8")).hexdigest()
        db.query(ApiCacheModel).filter(ApiCacheModel.cache_key == hashed_key).delete()
        
        new_cache = ApiCacheModel(
            cache_key=hashed_key,
            response_data=data
        )
        db.add(new_cache)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[Cache] Write error: {e}")
    finally:
        db.close()
