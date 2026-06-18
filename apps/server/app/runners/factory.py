from __future__ import annotations

from app.config import get_runner_settings
from app.runners.base_runner import PreviewRunner
from app.runners.local_runner import get_local_preview_runner
from app.runners.rancher_k8s_runner import (
    RancherKubernetesPreviewRunner,
    get_rancher_k8s_preview_runner,
)


_RUNNER_ALIASES = {
    "local": "local",
    "rancher_k8s": "rancher_k8s",
    "rancher-k8s": "rancher_k8s",
    "kubernetes": "rancher_k8s",
    "k8s": "rancher_k8s",
}

def _normalize_runner_name(runner_name: str) -> str:
    normalized = _RUNNER_ALIASES.get(runner_name.strip().lower())

    if normalized is None:
        raise ValueError(
            "Unsupported AGENTIC_OS_RUNNER value. Use 'local' or 'rancher_k8s'."
        )

    return normalized


def get_preview_runner() -> PreviewRunner:
    runner_settings = get_runner_settings()
    runner_name = _normalize_runner_name(runner_settings.runner)

    if runner_name == "local":
        return get_local_preview_runner()

    return get_rancher_k8s_runner()


def get_rancher_k8s_runner() -> RancherKubernetesPreviewRunner:
    runner_settings = get_runner_settings()
    return get_rancher_k8s_preview_runner(runner_settings)
