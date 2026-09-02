from dotenv import load_dotenv

load_dotenv()  # must run before any app.* import — several read env vars (e.g. DATABASE_URL) at import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chats, conversation

app = FastAPI(title="AI Customer Support Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(conversation.router)


@app.get("/health")
def health():
    return {"status": "ok"}
