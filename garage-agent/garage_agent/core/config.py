import os

STAFF_ALERT_PHONE = os.getenv("STAFF_ALERT_PHONE", None)

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")


class Settings:
    AI_ENGINE: str = os.getenv("AI_ENGINE", "rule").lower()


settings = Settings()

