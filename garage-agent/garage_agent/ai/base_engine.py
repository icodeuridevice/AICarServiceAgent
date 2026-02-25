from abc import ABC, abstractmethod
from sqlalchemy.orm import Session


class BaseEngine(ABC):
    @abstractmethod
    def process(self, db: Session, phone: str, message: str) -> dict:
        pass
