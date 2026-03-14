"""Core configuration management."""
import os
from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "configs"


def _resolve_env(val: str) -> str:
    """Resolve ${ENV_VAR} patterns in config values."""
    if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
        env_key = val[2:-1]
        return os.environ.get(env_key, val)
    return val


def _deep_resolve(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deep_resolve(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_resolve(v) for v in obj]
    if isinstance(obj, str):
        return _resolve_env(obj)
    return obj


def load_settings() -> dict:
    with open(CONFIG_DIR / "settings.yaml") as f:
        raw = yaml.safe_load(f)
    return _deep_resolve(raw)


def load_thresholds() -> dict:
    with open(CONFIG_DIR / "category_thresholds.yaml") as f:
        return yaml.safe_load(f)


def load_gst_rules() -> dict:
    with open(CONFIG_DIR / "gst_rules.yaml") as f:
        return yaml.safe_load(f)


class Settings:
    """Singleton settings accessor."""
    _instance = None
    _settings = None
    _thresholds = None
    _gst = None

    @classmethod
    def get(cls) -> dict:
        if cls._settings is None:
            cls._settings = load_settings()
        return cls._settings

    @classmethod
    def thresholds(cls) -> dict:
        if cls._thresholds is None:
            cls._thresholds = load_thresholds()
        return cls._thresholds

    @classmethod
    def gst(cls) -> dict:
        if cls._gst is None:
            cls._gst = load_gst_rules()
        return cls._gst
