from dataclasses import dataclass
from typing import Dict


@dataclass
class ModelConfig:
    provider: str       # "anthropic" or "groq"
    model_id: str       # actual model string passed to the API
    display_name: str   # shown in Telegram buttons


AVAILABLE_MODELS = {
    "sonnet": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4 (Anthropic)",
    ),
    "haiku": ModelConfig(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        display_name="Claude Haiku 4.5 (Anthropic) — faster, cheaper",
    ),
    "groq": ModelConfig(
        provider="groq",
        model_id="llama-3.3-70b-versatile",
        display_name="Llama 3.3 70B (Groq) — free, fast",
    ),
}

DEFAULT_MODEL_KEY = "sonnet"

# Per-chat active model — key is Telegram chat_id (int)
_active_models: Dict[int, str] = {}


def get_model(chat_id: int = 0) -> ModelConfig:
    key = _active_models.get(chat_id, DEFAULT_MODEL_KEY)
    return AVAILABLE_MODELS[key]


def get_model_key(chat_id: int = 0) -> str:
    return _active_models.get(chat_id, DEFAULT_MODEL_KEY)


def set_model(chat_id: int, key: str) -> ModelConfig:
    if key not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown model key: {key}")
    _active_models[chat_id] = key
    return AVAILABLE_MODELS[key]
