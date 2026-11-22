import os
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()


def env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} має бути цілим числом") from exc


API_ID = env_int("API_ID")
API_HASH = os.getenv("API_HASH", "").strip()
PHONE = os.getenv("PHONE", "").strip()
NOTIFY_CHAT_ID = env_int("NOTIFY_CHAT_ID")
TRANSLATION_URL = os.getenv("TRANSLATION_URL", "https://libretranslate.com/translate").strip()
TRANSLATION_API_KEY = os.getenv("TRANSLATION_API_KEY", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/userbot.sqlite3").strip()
SESSION_PATH = os.getenv("SESSION_PATH", "data/telegram_session").strip()

TRACK_CHAT_IDS = {
    int(value.strip())
    for value in os.getenv("TRACK_CHAT_IDS", "").split(",")
    if value.strip()
}

if not API_ID or API_ID == 123456:
    raise RuntimeError(
        "Вкажіть справжній API_ID у .env (отримайте його на https://my.telegram.org/apps)"
    )
if not API_HASH or API_HASH == "replace_me":
    raise RuntimeError(
        "Вкажіть справжній API_HASH у .env (отримайте його на https://my.telegram.org/apps)"
    )

Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(SESSION_PATH).parent.mkdir(parents=True, exist_ok=True)
