"""Interfaccia comune dei display."""
from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image


class Display(ABC):
    """Destinazione dei fotogrammi (immagini RGB)."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    @abstractmethod
    def show(self, img: Image.Image) -> None:
        """Mostra il fotogramma."""

    def close(self) -> None:
        """Rilascia il pannello."""
