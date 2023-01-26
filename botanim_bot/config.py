import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

BASE_DIR = Path(__file__).resolve().parent
SQLITE_DB_FILE = BASE_DIR / "db.sqlite3"
DATE_FORMAT = "%d.%m.%Y"
VOTE_ELEMENTS_COUNT = 3

ALL_BOOKS_CALLBACK_PATTERN = "all_books_"
VOTE_BOOKS_CALLBACK_PATTERN = "vote_"