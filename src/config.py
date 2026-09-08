import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Default model choice - Gemini 3.6 Flash is recommended
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-3.5-flash")
# Alternative model choice - Gemini 3.6 Pro
PRO_MODEL = os.getenv("PRO_MODEL", "gemini-3.5-pro")

# Amadeus API credentials
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")

# Google Places API key
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

# PostgreSQL / database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tourism_local.db")

if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY is not set in the environment or .env file.")
