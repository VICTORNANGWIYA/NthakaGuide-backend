import uuid
import logging
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB

db     = SQLAlchemy()
logger = logging.getLogger("NthakaGuide.models")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# =========================
# USER
# =========================
class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.String(36), primary_key=True, default=_uuid)
    email      = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password   = db.Column(db.String(255), nullable=False)

    role       = db.Column(db.String(20), default="user", nullable=False)
    is_active  = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    profile          = db.relationship("Profile", backref="user", uselist=False, cascade="all, delete-orphan")
    analysis_history = db.relationship("AnalysisHistory", backref="user", cascade="all, delete-orphan")
    chat_logs        = db.relationship("ChatLog", backref="user", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


# =========================
# PROFILE
# =========================
class Profile(db.Model):
    __tablename__ = "profiles"

    id         = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id    = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    full_name  = db.Column(db.String(255))
    phone      = db.Column(db.String(30))
    district   = db.Column(db.String(100))

    avatar_url = db.Column(db.Text)  # 🔥 was 512 → TEXT safer for long URLs

    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "full_name": self.full_name,
            "phone": self.phone,
            "district": self.district,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# =========================
# ANALYSIS HISTORY
# =========================
class AnalysisHistory(db.Model):
    __tablename__ = "analysis_history"

    id      = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Context
    district     = db.Column(db.String(100), nullable=False, index=True)
    climate_zone = db.Column(db.String(100))
    input_mode   = db.Column(db.String(20), default="lab")

    # Farmer context
    land_use      = db.Column(db.String(30))
    previous_crop = db.Column(db.String(100))

    # Soil data
    nitrogen       = db.Column(db.Float)
    phosphorus     = db.Column(db.Float)
    potassium      = db.Column(db.Float)
    ph             = db.Column(db.Float)
    moisture       = db.Column(db.Float)
    temperature    = db.Column(db.Float)
    organic_matter = db.Column(db.Float)

    # Rainfall
    rainfall_mm       = db.Column(db.Float)
    rainfall_band     = db.Column(db.String(20))
    rainfall_category = db.Column(db.String(20))

    # Recommendation
    recommended_crop  = db.Column(db.String(100), nullable=False, index=True)
    crop_score        = db.Column(db.Float)
    crop_confidence   = db.Column(db.Float)
    crop_season       = db.Column(db.String(50))

    # 🔥 FIXED: was String(100) → TEXT
    fertilizer_type   = db.Column(db.Text)

    # JSON (PostgreSQL optimized)
    all_crops_json   = db.Column(JSONB)   # 🔥 faster than JSON
    soil_alerts_json = db.Column(JSONB)

    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False, index=True)

    def to_dict(self, include_full: bool = False) -> dict:
        base = {
            "id": self.id,
            "district": self.district,
            "climate_zone": self.climate_zone,
            "input_mode": self.input_mode,
            "created_at": self.created_at.isoformat(),

            "land_use": self.land_use,
            "previous_crop": self.previous_crop,

            "nitrogen": self.nitrogen,
            "phosphorus": self.phosphorus,
            "potassium": self.potassium,
            "ph": self.ph,
            "moisture": self.moisture,
            "temperature": self.temperature,
            "organic_matter": self.organic_matter,

            "rainfall_mm": self.rainfall_mm,
            "rainfall_band": self.rainfall_band,
            "rainfall_category": self.rainfall_category,

            "recommended_crop": self.recommended_crop,
            "crop_score": self.crop_score,
            "crop_confidence": self.crop_confidence,
            "crop_season": self.crop_season,
            "fertilizer_type": self.fertilizer_type,
        }

        if include_full:
            base["all_crops"] = self.all_crops_json
            base["soil_alerts"] = self.soil_alerts_json

        return base

    def __repr__(self) -> str:
        return f"<AnalysisHistory {self.id} — {self.recommended_crop} @ {self.district}>"


# =========================
# CHAT LOGS
# =========================
class ChatLog(db.Model):
    __tablename__ = "chat_logs"

    id          = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id     = db.Column(db.String(36), db.ForeignKey("users.id", ondelete="SET NULL"), index=True)

    session_id  = db.Column(db.String(64), nullable=False, index=True)

    user_message = db.Column(db.Text, nullable=False)
    bot_reply    = db.Column(db.Text)

    is_agricultural = db.Column(db.Boolean, default=True, nullable=False)
    is_greeting     = db.Column(db.Boolean, default=False, nullable=False)
    had_error       = db.Column(db.Boolean, default=False, nullable=False)

    response_ms = db.Column(db.Integer)

    created_at  = db.Column(db.DateTime(timezone=True), default=_now, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "user_message": self.user_message,
            "bot_reply": self.bot_reply,
            "is_agricultural": self.is_agricultural,
            "is_greeting": self.is_greeting,
            "had_error": self.had_error,
            "response_ms": self.response_ms,
            "created_at": self.created_at.isoformat(),
        }


class AuditLog(db.Model):
    """
    Persistent admin audit trail.
    Replaces the in-memory _AUDIT_LOG list in admin_extended.py which
    was lost on every server restart and invisible to other admins.
    """
    __tablename__ = "audit_logs"
 
    id         = db.Column(db.String(36),  primary_key=True, default=_uuid)
    admin_id   = db.Column(db.String(36),  db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action     = db.Column(db.String(100), nullable=False, index=True)
    target_id  = db.Column(db.String(100), nullable=True)   # user_id, model name, etc.
    target_label = db.Column(db.String(255), nullable=True) # email, filename, etc.
    detail     = db.Column(db.Text,        nullable=True)
    ip_address = db.Column(db.String(45),  nullable=True)   # IPv4 or IPv6
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False, index=True)
 
    # Relationship so we can show admin email without a join in Python
    admin      = db.relationship("User", foreign_keys=[admin_id], lazy="joined")
 
    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "admin_id":     self.admin_id,
            "admin_email":  self.admin.email if self.admin else "—",
            "action":       self.action,
            "target_id":    self.target_id,
            "target_label": self.target_label,
            "detail":       self.detail,
            "ip_address":   self.ip_address,
            "created_at":   self.created_at.isoformat(),
        }
 
 
class DeletionSurvey(db.Model):
    """
    Stores the reason a user gave when deleting their account.
    user_id is nullable because the account is deleted on confirmation —
    we save the survey BEFORE the account is deleted so the data is not
    lost with the user row (CASCADE would delete it otherwise).
    We store email separately for the same reason.
    """
    __tablename__ = "deletion_surveys"
 
    id           = db.Column(db.String(36),  primary_key=True, default=_uuid)
    user_id      = db.Column(db.String(36),  nullable=True)   # not a FK — user will be deleted
    user_email   = db.Column(db.String(255), nullable=False)
    reason       = db.Column(db.String(100), nullable=False)  # selected option key
    reason_label = db.Column(db.String(255), nullable=False)  # human-readable label
    details      = db.Column(db.Text,        nullable=True)   # optional free-text comment
    created_at   = db.Column(db.DateTime(timezone=True), default=_now, nullable=False, index=True)
 
    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "user_id":      self.user_id,
            "user_email":   self.user_email,
            "reason":       self.reason,
            "reason_label": self.reason_label,
            "details":      self.details,
            "created_at":   self.created_at.isoformat(),
        }