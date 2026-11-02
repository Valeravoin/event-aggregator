import os

from dotenv import load_dotenv

load_dotenv()

EVENTS_PROVIDER_BASE_URL = os.getenv("EVENTS_PROVIDER_BASE_URL")
EVENTS_PROVIDER_API_KEY = os.getenv("EVENTS_PROVIDER_API_KEY")

