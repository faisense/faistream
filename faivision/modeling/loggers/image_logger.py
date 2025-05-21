from abc import ABC, abstractmethod

class ImageLogger(ABC):
    @abstractmethod
    def log_image(self, tag: str, image, step: int):
        """
        Log an image.
        `image` could be a PIL Image, numpy array, or tensor depending on implementation.
        """