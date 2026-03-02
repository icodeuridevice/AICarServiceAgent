import os

STAFF_ALERT_PHONE = os.getenv("STAFF_ALERT_PHONE", None)


class Settings:
    AI_ENGINE: str = os.getenv("AI_ENGINE", "rule").lower()


settings = Settings()
