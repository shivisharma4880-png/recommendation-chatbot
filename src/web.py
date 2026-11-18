from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

from src.catalogue import storefront_groups
from src.engine import RecommendationEngine
from src.filters import ShopperSlots
from src.session import SessionStore
from src.visuals import visual_for

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

engine = RecommendationEngine()
sessions = SessionStore()
BOT_USER_NAME = os.getenv("BOT_USER_NAME", "Shivi")

NO_STORE = "no-store, no-cache, must-revalidate, max-age=0"


class NoStoreWebAssets(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/static/"):
            response.headers["Cache-Control"] = NO_STORE
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app = FastAPI(title="Fashion recommendation chatbot")
app.add_middleware(NoStoreWebAssets)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


SESSION_ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,128}$"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str = Field(..., pattern=SESSION_ID_PATTERN)


class ResetRequest(BaseModel):
    session_id: str = Field(..., pattern=SESSION_ID_PATTERN)


def _public_context(slots: ShopperSlots) -> dict:
    ctx = slots.to_context_dict()
    return {
        "occasion": ctx.get("occasion"),
        "activity": ctx.get("activity"),
        "budget_max": ctx.get("budget_max"),
        "size": ctx.get("size"),
        "colour": ctx.get("colour"),
        "category": ctx.get("category"),
        "product_type": ctx.get("product_type"),
        "style": ctx.get("style"),
        "intent": ctx.get("intent"),
        "sentiment": ctx.get("sentiment"),
        "handoff": ctx.get("handoff_requested"),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/product-image/{product_id}")
def product_image(product_id: str) -> FileResponse:
    safe_id = "".join(ch for ch in product_id if ch.isalnum())
    path = WEB_DIR / "product-images" / f"{safe_id}.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Unknown product")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": NO_STORE})


def catalogue_payload() -> dict:
    groups = []
    for group in storefront_groups(engine.products):
        types = []
        for block in group["types"]:
            types.append(
                {
                    "product_type": block["product_type"],
                    "count": len(block["products"]),
                    "products": [{**product.to_dict(), **visual_for(product)} for product in block["products"]],
                }
            )
        sample = group["types"][0]["products"][0] if group["types"] else None
        groups.append(
            {
                "category": group["category"],
                "emoji": visual_for(sample)["emoji"] if sample else "🛍️",
                "count": group["count"],
                "types": types,
            }
        )
    return {"count": len(engine.products), "categories": groups}


@app.get("/api/catalogue")
def catalogue() -> dict:
    return catalogue_payload()


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "grok": engine.grok.available,
        "llm_provider": engine.grok.provider if engine.grok.available else None,
        "llm_model": engine.grok.model if engine.grok.available else None,
        "products": len(engine.products),
        "user_name": BOT_USER_NAME,
        "heading": f"{BOT_USER_NAME}'s Product Assistant Bot",
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    # one turn at a time per chat; different chats run in parallel
    with sessions.chat_lock(req.session_id):
        slots = sessions.get(req.session_id)
        try:
            result = engine.handle_turn(req.session_id, req.message, slots)
        except Exception:
            logger.exception("Engine error for session %s", req.session_id)
            raise HTTPException(status_code=500, detail="The assistant hit an error. Please try again.")
        sessions.update(req.session_id, slots)
    return {
        "reply": result.reply,
        "products": result.products,
        "context": _public_context(slots),
        "follow_ups": result.follow_ups,
        "intent": result.intent,
        "sentiment": result.sentiment,
        "handoff": result.handoff,
        "comparison": result.comparison,
    }


@app.post("/api/reset")
def reset(req: ResetRequest) -> dict:
    with sessions.chat_lock(req.session_id):
        sessions.reset(req.session_id)
    return {"ok": True, "context": {}}


def main() -> None:
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
