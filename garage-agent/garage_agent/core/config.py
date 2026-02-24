import os


class Settings:
    AI_ENGINE: str = os.getenv("AI_ENGINE", "rule").lower()


settings = Settings()