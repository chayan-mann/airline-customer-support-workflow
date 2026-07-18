from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from app.graph import graph

load_dotenv()

app = FastAPI(title="AI Customer Support Agent")


class ChatRequest(BaseModel):
    session_id: str # added to track separate conversations 
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    
    config = {"configurable": {"thread_id": request.session_id}}

    # LangGraph automatically pulls the past history for this thread_id and appends your new message to it!
    result = graph.invoke(
        {"messages": [{"role": "user", "content": request.message}]},
        config=config
    )
    return ChatResponse(reply=result["messages"][-1].content)
