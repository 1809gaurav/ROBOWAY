from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Predictor(ABC):
    @abstractmethod
    def predict(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Return advisory model output for a snapshot."""


def load_predictor() -> Predictor | None:
    model_path = os.environ.get("ROBOWAY_MODEL_PATH")
    if not model_path:
        return None

    path = Path(model_path).expanduser()
    if not path.is_file():
        return None

    # No third-party model runtime is assumed. Existing adapters can be added
    # here once a concrete model format and its input/output contract are known.
    return None
