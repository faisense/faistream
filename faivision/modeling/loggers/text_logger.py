from abc import ABC, abstractmethod
class TextLogger(ABC):
    @abstractmethod
    def log_text(self, tag: str, text: str, step: int):
        """Log text data."""