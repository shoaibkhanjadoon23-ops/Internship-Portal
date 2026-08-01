from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.db import get_db
from app.auth import get_current_user, CurrentUser
from app.ai_providers import call_groq

router = APIRouter(prefix="/mentor", tags=["mentor"])


class ChatIn(BaseModel):
    message: str


@router.post("/chat")
def chat(payload: ChatIn, user: CurrentUser = Depends(get_current_user)):
    db = get_db()

    # Store the student's message (real history, no mock data)
    db.table("mentor_messages").insert({
        "student_id": user.id, "role": "user", "content": payload.message
    }).execute()

    # Pull recent real history for context (last 10 messages)
    history_res = (
        db.table("mentor_messages")
        .select("role, content")
        .eq("student_id", user.id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    history = list(reversed(history_res.data))

    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    prompt = (
        "You are a friendly, encouraging internship program mentor helping a student. "
        "Keep replies concise (3-6 sentences) and practical.\n\n"
        f"Conversation so far:\n{convo}\n\nassistant:"
    )

    reply = call_groq(prompt)

    db.table("mentor_messages").insert({
        "student_id": user.id, "role": "assistant", "content": reply
    }).execute()

    return {"reply": reply}


@router.get("/history")
def history(user: CurrentUser = Depends(get_current_user)):
    db = get_db()
    res = (
        db.table("mentor_messages")
        .select("*")
        .eq("student_id", user.id)
        .order("created_at")
        .execute()
    )
    return res.data
