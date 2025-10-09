from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.db.database import init_db

from app.core.config import settings
from app.api.routes import router as api_router
from app.api.chat import router as chat_router
from app.api.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    await init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


app.include_router(api_router)
app.include_router(chat_router)
app.include_router(users_router)
