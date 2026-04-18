import os
from dotenv import load_dotenv

load_dotenv()


class Config:

    
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:12465387@localhost:5432/NthakaGuide",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle":  300,
        "pool_size":     10,
        "max_overflow":  20,
    }

   
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET", "change-me-in-production")
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = int(
        os.environ.get("JWT_EXPIRES_MINUTES", 60)
    )

    
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

  
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    DEBUG     = FLASK_ENV == "development"

   
    MAIL_SERVER   = os.environ.get("MAIL_SERVER",   "smtp.gmail.com")
    MAIL_PORT     = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")

    
    ZEROBOUNCE_API_KEY = os.environ.get("ZEROBOUNCE_API_KEY", "")  