from abc import ABC, abstractmethod

import numpy as np


class BaseSTTProvider(ABC):
    provider_name: str = "unknown"
    model: str = ""

    @abstractmethod
    def transcribe(self, audio_data: np.ndarray) -> str:
        ...
