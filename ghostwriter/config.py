"""Environment configuration for Ghostwriter."""
import os
from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    val = os.getenv(name)
    try:
        return int(val) if val else default
    except ValueError:
        return default


class Config:
    CASPIAN_API_KEY = os.getenv("CASPIAN_API_KEY")
    CASPIAN_BASE_URL = os.getenv("CASPIAN_BASE_URL", "https://api.trycaspianai.com")
    CASPIAN_EMAIL_USERNAME = os.getenv("CASPIAN_EMAIL_USERNAME", "ghostwriter")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    # AI_PROVIDER: "groq" (free, no credit card) or "anthropic" (paid, needs credit)
    AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-4-5")

    UNANSWERED_THRESHOLD_SECONDS = _int_env("UNANSWERED_THRESHOLD_SECONDS", 14400)
    WATCH_INTERVAL_SECONDS = _int_env("WATCH_INTERVAL_SECONDS", 30)
    TRUST_AUTO_SEND_THRESHOLD = _int_env("TRUST_AUTO_SEND_THRESHOLD", 5)

    CONTACTS_FILE = os.getenv("CONTACTS_FILE", "contacts.json")
    STATE_FILE = os.getenv("STATE_FILE", "state.json")
    SENT_EXAMPLES_FILE = os.getenv("SENT_EXAMPLES_FILE", "demo/sent_examples.txt")

    def validate(self):
        required = ["CASPIAN_API_KEY", "TELEGRAM_BOT_TOKEN"]
        if self.AI_PROVIDER == "anthropic":
            required.append("ANTHROPIC_API_KEY")
        else:
            required.append("GROQ_API_KEY")
        missing = [name for name in required if not getattr(self, name)]
        if missing:
            raise RuntimeError(
                f"Missing required env vars: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in."
            )


config = Config()
