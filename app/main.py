from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.project_logging import setup_project_logging
from app.api.routes.chat import router as chat_router


setup_project_logging()


app = FastAPI(title='Chatbot API')


app.add_middleware(
CORSMiddleware,
allow_origins=["*"],
allow_credentials=True,
allow_methods=['*'],
allow_headers=['*'],
)


app.include_router(chat_router)