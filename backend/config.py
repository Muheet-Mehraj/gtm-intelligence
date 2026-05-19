import os
from dotenv import load_dotenv

load_dotenv()

DEBUG       = os.getenv("DEBUG", "false").lower() == "true"
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

if not GROQ_API_KEY:
    import logging
    logging.getLogger("gtm.config").warning("GROQ_API_KEY not set — all agents will use heuristic fallback")