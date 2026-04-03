"""
chat.py  —  NthakaGuide chat blueprint
Uses HuggingFace Inference Router (HF_TOKEN).
Logs every message to ChatLog for admin analytics.
"""

import os
import time
import uuid
import logging
import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from models import db, ChatLog

chat_bp = Blueprint("chat", __name__)
logger  = logging.getLogger("soilsense.chat")

HF_API_KEY = os.environ.get("HF_TOKEN")
HF_MODEL   = "meta-llama/Llama-3.1-8B-Instruct:cerebras"
HF_URL     = "https://router.huggingface.co/v1/chat/completions"

SYSTEM_PROMPT = """You are NthakaGuide Assistant, an expert agricultural advisor
specialising exclusively in Malawian farming.

Your knowledge covers:
- Malawi's 28 districts and their climate zones (Northern Highlands, Central
  Plateau, Shire Valley, Lakeshore, etc.)
- Crops grown in Malawi: maize, tobacco, groundnuts, soya beans, cassava,
  sweet potato, sorghum, millet, rice, beans, sunflower, cotton, paprika,
  tea, coffee, macadamia
- Malawi soil types: sandy loam, clay loam, vertisols, ferralitic soils
- Fertiliser recommendations: Urea, CAN, DAP, NPK blends, Chitowe, compound D
- Malawi rainfall seasons: November-April rainy season, May-October dry season
- Pests and diseases common in Malawi: Fall Armyworm, Striga, Phytophthora,
  maize streak virus, groundnut rosette
- Irrigation schemes, conservation farming, agroforestry (Faidherbia albida)
- Malawi Agricultural Development Programme (ADMARC, FISP input subsidy scheme)
- Land use: smallholder farms, estates, customary land

STRICT RULES:
1. ONLY answer agriculture-related questions about Malawi. If asked about
   anything else, reply:
   "I can only help with Malawian agriculture topics. Please ask about crops,
   soil, fertilisers, rainfall, or farming in Malawi."
2. If greeted, respond warmly and ask how you can help with their farming.
3. Format responses clearly using markdown:
   - **bold** for key terms
   - Bullet points for lists
   - Numbered steps for processes
   - ## headings for sections
4. Keep responses concise but informative, suited to smallholder farmers.
5. Use Malawi-standard measurements (kg/ha, bags/acre, etc.).
6. Always end with a brief encouraging note for the farmer."""

GREETINGS = {
    "hi", "hello", "hey", "good morning", "good afternoon",
    "good evening", "morning", "afternoon", "evening",
    "howdy", "greetings", "hi there", "hello there",
}

OFF_TOPIC_REPLY = (
    "I can only help with Malawian agriculture topics. "
    "Please ask about crops, soil, fertilisers, rainfall, or farming in Malawi."
)


def _is_greeting(text: str) -> bool:
    return text.strip().lower() in GREETINGS


def _sanitise_messages(messages: list) -> list:
    filtered = [
        {"role": m["role"], "content": str(m["content"]).strip()}
        for m in messages
        if m.get("role") in ("user", "assistant")
        and str(m.get("content", "")).strip()
    ]
    if not filtered:
        return []
    while filtered and filtered[0]["role"] == "assistant":
        filtered.pop(0)
    if not filtered:
        return []
    alternated = [filtered[0]]
    for msg in filtered[1:]:
        if msg["role"] == alternated[-1]["role"]:
            alternated[-1]["content"] += "\n" + msg["content"]
        else:
            alternated.append(msg)
    while alternated and alternated[-1]["role"] == "assistant":
        alternated.pop()
    return alternated


def _get_current_user_id() -> str | None:
    """Silently try to read JWT user id — chat works even without auth header."""
    try:
        verify_jwt_in_request(optional=True)
        return get_jwt_identity()
    except Exception:
        return None


def _log_message(
    user_id: str | None,
    session_id: str,
    user_message: str,
    bot_reply: str,
    is_agricultural: bool,
    is_greeting: bool,
    had_error: bool,
    response_ms: int,
) -> None:
    """Write a ChatLog row; swallow any DB errors so chat is never blocked."""
    try:
        entry = ChatLog(
            user_id         = user_id,
            session_id      = session_id,
            user_message    = user_message[:2000],   # safety trim
            bot_reply       = bot_reply[:4000],
            is_agricultural = is_agricultural,
            is_greeting     = is_greeting,
            had_error       = had_error,
            response_ms     = response_ms,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        logger.warning("ChatLog write failed (non-fatal): %s", exc)
        db.session.rollback()


@chat_bp.route("/chat", methods=["POST"])
def chat():
    body     = request.get_json(silent=True) or {}
    messages = body.get("messages")

    if not messages or not isinstance(messages, list):
        return jsonify({"error": "Missing or invalid 'messages' array"}), 400

    if not HF_API_KEY:
        return jsonify({"error": "HF_TOKEN is not configured on the server"}), 500

    # Session id — frontend can pass one, or we generate per-request
    session_id = body.get("session_id") or str(uuid.uuid4())
    user_id    = _get_current_user_id()

    last_user = next(
        (m for m in reversed(messages) if m.get("role") == "user"), None
    )
    user_text = (last_user.get("content") or "").strip() if last_user else ""

    if not user_text:
        return jsonify({"error": "No user message found."}), 400

    # ── Fast-path: greeting ───────────────────────────────────────────────────
    if _is_greeting(user_text):
        reply = (
            "## Hello! Welcome to NthakaGuide\n\n"
            "I'm your Malawian agricultural assistant. I can help you with:\n\n"
            "- **Crop recommendations** for your district\n"
            "- **Fertiliser plans** and application rates\n"
            "- **Pest & disease** identification and control\n"
            "- **Soil management** and conservation farming\n"
            "- **Rainfall** and seasonal planting advice\n\n"
            "What would you like to know about farming in Malawi today?"
        )
        _log_message(user_id, session_id, user_text, reply,
                     is_agricultural=True, is_greeting=True,
                     had_error=False, response_ms=0)
        return jsonify({"reply": reply, "session_id": session_id})

    # ── Sanitise messages ─────────────────────────────────────────────────────
    clean_messages = _sanitise_messages(messages)
    logger.info("Sending %d messages to HuggingFace (session=%s)", len(clean_messages), session_id)

    if not clean_messages:
        return jsonify({"error": "Could not build a valid message list."}), 400

    payload = {
        "model":       HF_MODEL,
        "messages":    [{"role": "system", "content": SYSTEM_PROMPT}] + clean_messages,
        "temperature": 0.4,
        "max_tokens":  1000,
        "stream":      False,
    }
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type":  "application/json",
    }

    t0 = time.monotonic()
    had_error = False
    reply     = ""

    try:
        resp = requests.post(HF_URL, json=payload, headers=headers, timeout=45)
        resp.raise_for_status()
        data  = resp.json()
        reply = data["choices"][0]["message"]["content"].strip()

    except requests.exceptions.Timeout:
        had_error = True
        reply     = "The AI model timed out. Please try again."
        logger.error("HuggingFace timeout (session=%s)", session_id)

    except requests.exceptions.RequestException as exc:
        had_error = True
        reply     = "I'm having trouble connecting right now. Please try again in a moment."
        logger.error("HuggingFace error: %s", exc)

    except (KeyError, IndexError) as exc:
        had_error = True
        reply     = "Sorry, I could not generate a response. Please try again."
        logger.error("Unexpected HF response: %s", exc)

    response_ms = int((time.monotonic() - t0) * 1000)

    # Classify: was it agricultural? (simple heuristic — off-topic reply means no)
    is_agricultural = OFF_TOPIC_REPLY.lower() not in reply.lower()

    _log_message(user_id, session_id, user_text, reply,
                 is_agricultural=is_agricultural, is_greeting=False,
                 had_error=had_error, response_ms=response_ms)

    if had_error:
        return jsonify({"error": reply, "session_id": session_id}), 502

    return jsonify({"reply": reply, "session_id": session_id})