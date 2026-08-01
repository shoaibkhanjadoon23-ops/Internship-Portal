from fastapi import Header, HTTPException, Depends
from jose import jwt, JWTError
from app.config import SUPABASE_JWT_SECRET
from app.db import get_db


class CurrentUser:
    def __init__(self, id: str, email: str, role: str):
        self.id = id
        self.email = email
        self.role = role


def _decode_token(token: str) -> dict:
    try:
        # Supabase issues HS256-signed JWTs using the project's JWT secret
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")


def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    """
    Reads 'Authorization: Bearer <supabase_access_token>' sent by the frontend
    (the token supabase-js gives you after login) and returns the user's id + role.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    payload = _decode_token(token)
    user_id = payload.get("sub")
    email = payload.get("email", "")

    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    # Look up role from the real profiles table (no assumptions, no dummy roles)
    db = get_db()
    result = db.table("profiles").select("role").eq("id", user_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found for this user")

    return CurrentUser(id=user_id, email=email, role=result.data["role"])


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
