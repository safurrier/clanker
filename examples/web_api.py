"""
Web API proof-of-concept demonstrating SDK reusability.

This shows how to reuse the core AI capabilities (shitposting, chat)
in a web application without any Discord dependencies.

Run with:
    uv run uvicorn examples.web_api:app --reload
"""

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Import core SDK - no Discord dependencies!
from clanker import Context, Message, Persona, respond
from clanker.config import load_personas
from clanker.providers import ProviderFactory
from clanker.providers.base import LLM, TTS
from clanker.shitposts import (
    ShitpostRequest,
    build_request,
    load_templates,
    render_shitpost,
    sample_template,
)


# API Request/Response Models
class ChatRequest(BaseModel):
    message: str
    user_id: str
    session_id: str | None = None
    persona_name: str = "default"


class ChatResponse(BaseModel):
    reply: str
    audio_url: str | None = None


class ShitpostRequest(BaseModel):
    category: str | None = None
    template_name: str | None = None
    user_id: str
    variables: dict[str, Any] | None = None


class ShitpostResponse(BaseModel):
    shitpost: str
    template_used: str


# Global state (initialized on startup)
llm: LLM | None = None
tts: TTS | None = None
personas: dict[str, Persona] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize providers on startup."""
    global llm, tts, personas

    # Initialize the same providers used by the Discord bot
    factory = ProviderFactory()
    llm = factory.get_llm("openai")
    tts = factory.get_tts("elevenlabs") if factory.has_tts() else None
    personas = load_personas()

    print("✅ Providers initialized")
    print(f"   - LLM: {type(llm).__name__}")
    print(f"   - TTS: {type(tts).__name__ if tts else 'None'}")
    print(f"   - Personas loaded: {len(personas)}")

    yield

    print("🔌 Shutting down...")


app = FastAPI(
    title="Clanker Web API",
    description="Proof-of-concept showing SDK reusability in web applications",
    lifespan=lifespan,
)


def build_web_context(
    user_id: str,
    session_id: str | None,
    persona: Persona,
    messages: list[Message] | None = None,
) -> Context:
    """
    Build SDK Context from web request.

    This is the adapter layer - converts platform-specific data
    (HTTP request) into SDK's platform-agnostic Context.
    """
    return Context(
        request_id=str(uuid.uuid4()),
        user_id=int(hash(user_id)) % (2**31),  # Convert string to int ID
        guild_id=None,  # Not applicable for web
        channel_id=int(hash(session_id or "default")) % (2**31),
        persona=persona,
        messages=messages or [],
        metadata={"source": "web", "session": session_id},
    )


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Clanker Web API",
        "providers": {
            "llm": type(llm).__name__ if llm else None,
            "tts": type(tts).__name__ if tts else None,
        },
        "personas": list(personas.keys()),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Chat endpoint - reuses the same chat logic as the Discord bot.

    This demonstrates how the core `respond()` function works
    with any platform, not just Discord.
    """
    if not llm:
        raise HTTPException(status_code=503, detail="LLM provider not initialized")

    # Get persona (fallback to default if not found)
    persona = personas.get(request.persona_name, personas.get("default"))
    if not persona:
        raise HTTPException(status_code=400, detail=f"Persona '{request.persona_name}' not found")

    # Build user message
    user_message = Message(role="user", content=request.message)

    # Build SDK context (adapter layer)
    context = build_web_context(
        user_id=request.user_id,
        session_id=request.session_id,
        persona=persona,
        messages=[user_message],
    )

    # Use the same SDK function as the Discord bot!
    reply, audio = await respond(context, llm, tts)

    # Convert SDK response to HTTP response
    return ChatResponse(
        reply=reply.content,
        audio_url=None,  # Could upload audio and return URL
    )


@app.post("/shitpost", response_model=ShitpostResponse)
async def generate_shitpost(request: ShitpostRequest) -> ShitpostResponse:
    """
    Shitpost generation endpoint.

    This demonstrates how the shitpost pipeline is completely
    platform-agnostic and works without any Discord code.
    """
    if not llm:
        raise HTTPException(status_code=503, detail="LLM provider not initialized")

    # Load templates (same as Discord bot)
    templates = load_templates()

    # Sample a template based on request
    template = sample_template(
        templates,
        category=request.category,
        name=request.template_name,
    )

    # Build shitpost request
    shitpost_request = build_request(template, variables=request.variables or {})

    # Build SDK context
    persona = personas.get("shitposter", personas.get("default"))
    if not persona:
        raise HTTPException(status_code=500, detail="No persona available")

    context = build_web_context(
        user_id=request.user_id,
        session_id=None,
        persona=persona,
    )

    # Generate shitpost using the same SDK function!
    reply = await render_shitpost(context, llm, shitpost_request)

    return ShitpostResponse(
        shitpost=reply.content,
        template_used=template.name,
    )


@app.get("/templates")
async def list_templates():
    """List available shitpost templates."""
    templates = load_templates()
    return {
        "count": len(templates),
        "categories": list({t.category for t in templates}),
        "templates": [
            {
                "name": t.name,
                "category": t.category,
                "description": t.description,
                "variables": list(t.variables),
            }
            for t in templates
        ],
    }


@app.get("/personas")
async def list_personas():
    """List available personas."""
    return {
        "count": len(personas),
        "personas": [
            {
                "name": name,
                "personality": p.personality[:100] + "..." if len(p.personality) > 100 else p.personality,
            }
            for name, p in personas.items()
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
