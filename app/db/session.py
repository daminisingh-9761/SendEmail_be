from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

settings = get_settings()

client = AsyncIOMotorClient(settings.mongodb_url)
db = client[settings.mongodb_db_name]

async def get_db():
    yield db
