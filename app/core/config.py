import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "0"))
    IS_BOT_PRIVATE = os.getenv("IS_BOT_PRIVATE", "True").lower() == "true"
    # Local Bot API Server base URL, e.g., http://localhost:8081/bot
    BOT_API_BASE_URL = os.getenv("BOT_API_BASE_URL")
    # Persistence file path
    PERSISTENCE_PATH = os.getenv("PERSISTENCE_PATH", "data/persistence")
    
config = Config()
