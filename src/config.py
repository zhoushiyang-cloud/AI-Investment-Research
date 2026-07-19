"""
config.py — Unified configuration and OpenBB credential management.

Reads config/api_keys.toml and sets up OpenBB provider credentials.
All scripts should import `load_config()` from here, NOT duplicate their own.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Load and return the full configuration from config/api_keys.toml.

    Returns:
        dict with sections: fmp, intrinio, tiingo, benzinga, openai, anthropic, etc.

    Raises:
        SystemExit: if config/api_keys.toml is not found.
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    config_path = PROJECT_ROOT / "config" / "api_keys.toml"
    if not config_path.exists():
        print("ERROR: config/api_keys.toml not found.")
        print("Run: cp config/api_keys.toml.example config/api_keys.toml")
        sys.exit(1)

    with open(config_path, "rb") as f:
        return tomllib.load(f)


def setup_openbb_credentials(config: dict | None = None) -> None:
    """Configure OpenBB provider credentials from api_keys.toml.

    Reads credentials and sets them via obb.user.credentials.
    Only sets keys that are non-empty in the config.

    Args:
        config: Optional config dict. If None, calls load_config().
    """
    from openbb import obb

    if config is None:
        config = load_config()

    creds: dict[str, str] = {}

    # Map config sections to OpenBB credential field names
    provider_keys = {
        "fmp": "fmp_api_key",
        "intrinio": "intrinio_api_key",
        "tiingo": "tiingo_token",
        "benzinga": "benzinga_api_key",
    }

    for section, cred_field in provider_keys.items():
        if section in config and config[section].get("api_key"):
            creds[cred_field] = config[section]["api_key"]

    if creds:
        try:
            obb.user.credentials.patch(**creds)
        except AttributeError:
            # Older OpenBB versions use a different credential API
            for key, value in creds.items():
                obb.user.credentials.patch({key: value})


def get_available_providers(command_result: list) -> list[str]:
    """Extract available provider names from OpenBB command metadata.

    Args:
        command_result: Result from calling obb.equity.*.method with __doc__ inspection.

    Returns:
        List of provider short names.
    """
    # This is a heuristic — OpenBB returns available providers in warnings/extra
    return []


def pick_provider(*preferences: str) -> str:
    """Pick the first provider from the preference chain that is configured.

    Always falls back to yfinance (free, no key) or sec (free, no key).

    Args:
        preferences: Provider short names in order of preference.

    Returns:
        The best available provider name.
    """
    config = load_config()

    provider_to_key = {
        "fmp": ("fmp", "api_key"),
        "intrinio": ("intrinio", "api_key"),
        "tiingo": ("tiingo", "api_key"),
        "benzinga": ("benzinga", "api_key"),
    }

    for provider in preferences:
        if provider in ("yfinance", "sec"):
            return provider  # Free, always available
        key_info = provider_to_key.get(provider)
        if key_info:
            section, field = key_info
            if config.get(section, {}).get(field, ""):
                return provider

    return "yfinance"  # Ultimate fallback
