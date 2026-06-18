from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = SERVER_ROOT / ".env"

DOTENV_VALUES = dotenv_values(ENV_FILE)

GENERATED_ROOT = PROJECT_ROOT / "generated"
DATA_ROOT = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_ROOT / "agentic_os.sqlite3"


@dataclass(frozen=True)
class LLMSettings:
    api_key: str | None
    model: str | None
    base_url: str
    timeout_seconds: float
    max_concurrency: int
    max_output_tokens: int | None

    @property
    def enabled(self) -> bool:
        return bool(self.model and self.base_url)


@dataclass(frozen=True)
class RunnerSettings:
    runner: str
    kubeconfig_path: str | None
    k8s_context: str | None
    namespace_prefix: str
    preview_exposure_mode: str
    preview_base_domain: str | None


def _read_dotenv_value(name: str) -> str | None:
    raw_value = DOTENV_VALUES.get(name)

    if not isinstance(raw_value, str):
        return None

    value = raw_value.strip()
    return value or None


def _read_first_dotenv_value(*names: str) -> str | None:
    for name in names:
        value = _read_dotenv_value(name)

        if value is not None:
            return value

    return None


def _read_dotenv_float(name: str, default: float) -> float:
    raw_value = _read_dotenv_value(name)

    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        return default


def _read_first_dotenv_float(default: float, *names: str) -> float:
    for name in names:
        raw_value = _read_dotenv_value(name)

        if raw_value is None:
            continue

        try:
            return float(raw_value)
        except ValueError:
            continue

    return default


def _read_first_dotenv_int(default: int | None, *names: str) -> int | None:
    for name in names:
        raw_value = _read_dotenv_value(name)

        if raw_value is None:
            continue

        try:
            parsed_value = int(raw_value)
        except ValueError:
            continue

        if parsed_value > 0:
            return parsed_value

    return default


def get_llm_settings() -> LLMSettings:
    return LLMSettings(
        api_key=_read_first_dotenv_value(
            "LLM_API_KEY",
            "OPENAI_API_KEY",
            "AGENTIC_OS_LLM_API_KEY",
        ),
        model=_read_first_dotenv_value(
            "LLM_MODEL",
            "OPENAI_MODEL",
            "AGENTIC_OS_LLM_MODEL",
        ),
        base_url=(
            _read_first_dotenv_value(
                "LLM_BASE_URL",
                "OPENAI_BASE_URL",
                "AGENTIC_OS_LLM_BASE_URL",
            )
            or "https://api.openai.com/v1"
        ).rstrip("/"),
        timeout_seconds=_read_first_dotenv_float(
            45.0,
            "LLM_TIMEOUT_SECONDS",
            "OPENAI_TIMEOUT_SECONDS",
            "AGENTIC_OS_LLM_TIMEOUT_SECONDS",
        ),
        max_concurrency=_read_first_dotenv_int(
            1,
            "MAX_LLM_CONCURRENCY",
        )
        or 1,
        max_output_tokens=_read_first_dotenv_int(
            None,
            "MAX_OUTPUT_TOKENS",
        ),
    )


def get_runner_settings() -> RunnerSettings:
    namespace_prefix = (
        _read_dotenv_value("AGENTIC_OS_NAMESPACE_PREFIX")
        or "agentic-os"
    ).strip().lower()
    preview_exposure_mode = (
        _read_dotenv_value("PREVIEW_EXPOSURE_MODE")
        or "port-forward"
    ).strip().lower().replace("-", "_")

    return RunnerSettings(
        runner=(_read_dotenv_value("AGENTIC_OS_RUNNER") or "local").strip().lower(),
        kubeconfig_path=_read_dotenv_value("KUBECONFIG_PATH"),
        k8s_context=_read_dotenv_value("K8S_CONTEXT"),
        namespace_prefix=namespace_prefix,
        preview_exposure_mode=preview_exposure_mode,
        preview_base_domain=_read_dotenv_value("PREVIEW_BASE_DOMAIN"),
    )
