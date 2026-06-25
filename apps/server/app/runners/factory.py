from __future__ import annotations

from app.runners.base_runner import PreviewRunner
from app.runners.local_runner import get_local_preview_runner


def get_preview_runner() -> PreviewRunner:
    return get_local_preview_runner()
