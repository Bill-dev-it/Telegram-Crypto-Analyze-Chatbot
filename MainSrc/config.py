# config.py
import os
from dotenv import load_dotenv

load_dotenv()           # looks for .env file in same folder

API_ID = int(os.getenv("API_ID") or "0")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")     # optional
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")       # optional

# Optional — if you want to keep using Mongo
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/chatbot_db")

# Quick validation
if not all([API_ID, API_HASH, BOT_TOKEN]):
    missing = [k for k,v in {"API_ID":API_ID, "API_HASH":API_HASH, "BOT_TOKEN":BOT_TOKEN}.items() if not v]
    raise ValueError(f"Missing required env variables: {', '.join(missing)}")