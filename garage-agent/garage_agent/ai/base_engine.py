from abc import ABC, abstractmethod
from sqlalchemy.orm import Session


class BaseEngine(ABC):
    @abstractmethod
    def process(self, db: Session, garage_id: int, phone: str, message: str) -> dict:
        pass
