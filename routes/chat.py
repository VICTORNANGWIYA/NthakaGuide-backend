"""
chat.py  —  NthakaGuide chat blueprint
Uses HuggingFace Inference Router (HF_TOKEN).
Logs every message to ChatLog for admin analytics.
"""

import os
import re
import time
import uuid
import logging
import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from models import db, ChatLog

chat_bp = Blueprint("chat", __name__)
logger  = logging.getLogger("NthakaGuide.chat")

HF_API_KEY = os.environ.get("HF_TOKEN")
HF_MODEL   = "meta-llama/Llama-3.1-8B-Instruct:cerebras"
HF_URL     = "https://router.huggingface.co/v1/chat/completions"

SYSTEM_PROMPT = """You are NthakaGuide Assistant, an expert agricultural advisor
specialising EXCLUSIVELY in Malawian farming. You ONLY answer questions about
agriculture in Malawi. You NEVER answer questions on any other topic.

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

ABSOLUTE RULES — YOU MUST FOLLOW THESE WITHOUT EXCEPTION:
1. If a question is NOT about agriculture, farming, crops, soil, fertilisers,
   pests, rainfall, or rural livelihoods in Malawi — you MUST reply with
   EXACTLY this message and NOTHING else:
   "I can only help with Malawian agriculture topics. Please ask about crops,
   soil, fertilisers, rainfall, or farming in Malawi."
2. Do NOT attempt to answer any non-agricultural question even partially.
3. Do NOT say "that's a great question but..." before refusing.
4. Do NOT offer to help with anything outside agriculture.
5. Topics you MUST REFUSE completely (not limited to):
   - General knowledge, history, geography unrelated to Malawi farming
   - Mathematics, science, coding, technology
   - Politics, religion, sports, entertainment
   - Medical, legal, financial advice
   - Weather forecasts unrelated to farming seasons
   - Recipes, cooking, food (unless directly about crop processing/storage)
   - Any creative writing, jokes, or roleplay
   - Questions about yourself or AI in general
6. If greeted, respond warmly and ask how you can help with their farming.
7. Format responses clearly using markdown:
   - **bold** for key terms
   - Bullet points for lists
   - Numbered steps for processes
   - ## headings for sections
8. Keep responses concise but informative, suited to smallholder farmers.
9. Use Malawi-standard measurements (kg/ha, bags/acre, etc.).
10. Always end with a brief encouraging note for the farmer."""

GREETINGS = {
    "hi", "hello", "hey", "good morning", "good afternoon",
    "good evening", "morning", "afternoon", "evening",
    "howdy", "greetings", "hi there", "hello there",
    "moni", "muli bwanji",  # common Chichewa greetings
}

OFF_TOPIC_REPLY = (
    "I can only help with Malawian agriculture topics. "
    "Please ask about crops, soil, fertilisers, rainfall, or farming in Malawi."
)

# ── Agricultural keyword whitelist ────────────────────────────────────────────
# If NONE of these appear in the message, it is almost certainly off-topic.
# This is a fast pre-filter BEFORE calling the expensive LLM API.
AGRI_KEYWORDS = {
    # crops
    "maize", "tobacco", "groundnut", "soybean", "soya", "cassava", "potato",
    "sweet potato", "sorghum", "millet", "rice", "bean", "sunflower", "cotton",
    "paprika", "tea", "coffee", "macadamia", "banana", "mango", "avocado",
    "tomato", "cabbage", "onion", "pigeon pea", "cowpea", "sugarcane",
    # soil & nutrients
    "soil", "nitrogen", "phosphorus", "potassium", "fertiliser", "fertilizer",
    "urea", "can", "dap", "npk", "compost", "manure", "organic matter",
    "ph", "acidity", "lime", "chitowe", "compound d",
    # farming practices
    "farm", "farming", "crop", "plant", "seed", "harvest", "planting",
    "irrigation", "water", "drought", "rain", "rainfall", "season",
    "conservation farming", "agroforestry", "intercrop", "rotation",
    "faidherbia", "mulch", "ridges", "basin",
    # pests & disease
    "pest", "disease", "weed", "striga", "armyworm", "fall armyworm",
    "aphid", "insect", "fungus", "blight", "rust", "virus", "rosette",
    "phytophthora", "streak", "spray", "pesticide", "herbicide", "fungicide",
    # malawi-specific
    "malawi", "admarc", "fisp", "subsidy", "extension", "smallholder",
    "estate", "customary land", "shire valley", "lilongwe", "blantyre",
    "mzuzu", "zomba", "district", "northern", "central", "southern",
    # general agri
    "yield", "production", "acre", "hectare", "bag", "kg", "soil test",
    "recommendation", "field", "land", "grow", "cultivat", "agricult",
    "livestock", "goat", "chicken", "cattle", "fish", "fishpond", "aquaculture",
}

# ── Hard-blocked topic patterns ───────────────────────────────────────────────
# Questions matching any of these are rejected immediately without calling the LLM.
BLOCKED_PATTERNS = [
    r"\bcode\b", r"\bprogramm", r"\bpython\b", r"\bjavascript\b", r"\bhtml\b",
    r"\bmath\b", r"\bcalcul", r"\bequation\b", r"\balgebra\b",
    r"\bpolitics?\b", r"\belection\b", r"\bpresident\b", r"\bgovernment\b",
    r"\breligion\b", r"\bchurch\b", r"\bmusic\b", r"\bsong\b", r"\bmovie\b",
    r"\bsport\b", r"\bfootball\b", r"\bbasketball\b",
    r"\bmedic", r"\bdoctor\b", r"\bhospital\b", r"\btreatment\b",
    r"\blegal\b", r"\blawyer\b", r"\bcourt\b",
    r"\bfinancial\b", r"\bstock market\b", r"\binvestment\b",
    r"\bjoke\b", r"\bstory\b", r"\bpoem\b", r"\bwrite me\b",
    r"\bwho are you\b", r"\bwhat are you\b", r"\bai\b", r"\bchatgpt\b",
    r"\bhistory of\b(?!.*(?:malawi|farm|crop|agri))",
    r"\brecipe\b(?!.*(?:fertilis|spray|mix))",
]

_BLOCKED_RE = re.compile("|".join(BLOCKED_PATTERNS), re.IGNORECASE)


def _is_greeting(text: str) -> bool:
    return text.strip().lower() in GREETINGS


def _is_agricultural(text: str) -> bool:
    """
    Two-stage check:
    1. Hard-block patterns → immediately non-agricultural
    2. Keyword whitelist  → must contain at least one agricultural term
    """
    lower = text.lower()

    # Stage 1: hard block
    if _BLOCKED_RE.search(lower):
        return False

    # Stage 2: must contain at least one agri keyword
    for kw in AGRI_KEYWORDS:
        if kw in lower:
            return True

    # Short messages (greetings handled separately) that have no agri keyword
    # are treated as off-topic unless they are very short follow-ups
    if len(text.split()) <= 4:
        # Short follow-ups like "how much?", "when?" after an agri conversation
        # are allowed through — the LLM system prompt will keep it on topic
        return True

    return False


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
    try:
        entry = ChatLog(
            user_id         = user_id,
            session_id      = session_id,
            user_message    = user_message[:2000],
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

    # ── Pre-filter: block non-agricultural questions BEFORE calling LLM ───────
    if not _is_agricultural(user_text):
        logger.info("Blocked off-topic message (session=%s): %s", session_id, user_text[:80])
        _log_message(user_id, session_id, user_text, OFF_TOPIC_REPLY,
                     is_agricultural=False, is_greeting=False,
                     had_error=False, response_ms=0)
        return jsonify({"reply": OFF_TOPIC_REPLY, "session_id": session_id})

    # ── Sanitise and call HuggingFace ─────────────────────────────────────────
    clean_messages = _sanitise_messages(messages)
    if not clean_messages:
        return jsonify({"error": "Could not build a valid message list."}), 400

    logger.info("Sending %d messages to HuggingFace (session=%s)", len(clean_messages), session_id)

    payload = {
        "model":       HF_MODEL,
        "messages":    [{"role": "system", "content": SYSTEM_PROMPT}] + clean_messages,
        "temperature": 0.3,   # lower = more focused, less creative drift
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

        # ── Post-filter: if the LLM somehow answered off-topic, override it ──
        if OFF_TOPIC_REPLY.lower() in reply.lower():
            reply = OFF_TOPIC_REPLY
        elif not _is_agricultural(reply) and len(reply.split()) > 20:
            # LLM went off-topic despite system prompt — hard override
            logger.warning("LLM replied off-topic, overriding (session=%s)", session_id)
            reply = OFF_TOPIC_REPLY

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

    response_ms     = int((time.monotonic() - t0) * 1000)
    is_agri_reply   = OFF_TOPIC_REPLY.lower() not in reply.lower()

    _log_message(user_id, session_id, user_text, reply,
                 is_agricultural=is_agri_reply, is_greeting=False,
                 had_error=had_error, response_ms=response_ms)

    if had_error:
        return jsonify({"error": reply, "session_id": session_id}), 502

    return jsonify({"reply": reply, "session_id": session_id})