from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from app.graph import graph

load_dotenv()

app = FastAPI(title="AI Customer Support Agent")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    result = graph.invoke({"messages": [{"role": "user", "content": request.message}]})
    return ChatResponse(reply=result["messages"][-1].content)
