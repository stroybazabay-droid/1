from dotenv import load_dotenv

# Ключи из .env нужны до импорта бота: клиент Claude и список доступа читают их при импорте.
load_dotenv()

from .bot import run  # noqa: E402

run()
