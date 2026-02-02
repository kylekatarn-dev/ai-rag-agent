import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()


def get_secret(key: str, default: str = None) -> str | None:
    """Get secret from Streamlit secrets or environment variables.

    Priority: Streamlit secrets > Environment variables > Default
    """
    # Try Streamlit secrets first (for Streamlit Cloud deployment)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    # Fall back to environment variable
    return os.getenv(key, default)

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
CHROMA_DIR = BASE_DIR / get_secret("CHROMA_PERSIST_DIR", "./chroma_db")

# OpenAI
OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
OPENAI_MODEL = get_secret("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = get_secret("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# ChromaDB
CHROMA_COLLECTION_NAME = "properties"

# Property types
PROPERTY_TYPES = {
    "warehouse": "sklad",
    "office": "kancelář"
}

# Location mappings for normalization
LOCATION_REGIONS = {
    "praha": ["praha", "průhonice", "hostivice", "říčany"],
    "brno": ["brno"],
    "ostrava": ["ostrava"],
    "plzeň": ["plzeň"],
    "olomouc": ["olomouc"],
    "liberec": ["liberec"],
    "hradec králové": ["hradec králové"],
    "kladno": ["kladno"],
}

# Market averages (Kč/m²/month) for realism scoring
MARKET_AVERAGES = {
    "warehouse": {
        "praha": 110,
        "brno": 85,
        "ostrava": 75,
        "other": 85,
    },
    "office": {
        "praha": 320,
        "brno": 220,
        "ostrava": 150,
        "other": 200,
    }
}

# Lead scoring weights
SCORING_WEIGHTS = {
    "completeness": 30,
    "realism": 30,
    "match_quality": 25,
    "engagement": 15,
}

# RAG Configuration
# Enhanced RAG features (can be toggled in UI)
RAG_USE_HYBRID_SEARCH = get_secret("RAG_USE_HYBRID_SEARCH", "true").lower() == "true"
RAG_USE_QUERY_EXPANSION = get_secret("RAG_USE_QUERY_EXPANSION", "true").lower() == "true"
RAG_USE_RERANKING = get_secret("RAG_USE_RERANKING", "true").lower() == "true"

# Lead quality thresholds
LEAD_QUALITY_THRESHOLDS = {
    "hot": 70,
    "warm": 40,
    "cold": 0,
}

# Scheduling configuration
# Mode: "simulated", "calendly", or "google"
SCHEDULING_MODE = get_secret("SCHEDULING_MODE", "simulated")

# Calendly settings (if using Calendly mode)
# Get your link from: https://calendly.com/app/settings/link
CALENDLY_URL = get_secret("CALENDLY_URL", "https://calendly.com/your-username")
CALENDLY_EVENT_TYPES = {
    "call": "/15min",      # 15-minute phone call
    "video": "/30min",     # 30-minute video call
    "meeting": "/60min",   # 60-minute in-person meeting
}

# Google Calendar settings (if using Google mode)
# 1. Create Google Cloud project: https://console.cloud.google.com/
# 2. Enable Calendar API
# 3. Create Service Account and download JSON key
# 4. Share broker's calendar with the service account email
GOOGLE_CALENDAR_ENABLED = get_secret("GOOGLE_CALENDAR_ENABLED", "false").lower() == "true"
GOOGLE_SERVICE_ACCOUNT_FILE = get_secret("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
GOOGLE_CALENDAR_ID = get_secret("GOOGLE_CALENDAR_ID", "primary")  # or specific calendar ID

# Broker contact info
BROKER_EMAIL = get_secret("BROKER_EMAIL", "broker@example.com")
BROKER_NAME = get_secret("BROKER_NAME", "Jan Novák")
