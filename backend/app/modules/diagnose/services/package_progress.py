"""Progress reporting for long-running QField packaging."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

ProgressCallback = Callable[[int, str], None]


@dataclass
class PackageProgress:
    """Collect packaging progress events for streaming to the client."""

    on_event: ProgressCallback | None = None
    _percent: int = 0

    def emit(self, percent: int, message: str) -> None:
        self._percent = max(self._percent, min(percent, 100))
        if self.on_event:
            self.on_event(
                self._percent,
                message,
            )

    def log(self, message: str) -> None:
        if self.on_event:
            self.on_event(self._percent, message)
