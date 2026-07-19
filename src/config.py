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


def setup_openbb_credentials(config: dict | None = None) -> list[str]:
    """Configure OpenBB provider credentials from config/api_keys.toml.

    Sets credentials via direct field assignment on obb.user.credentials.
    Only configures providers whose keys are non-empty.

    Args:
        config: Optional config dict. If None, calls load_config().

    Returns:
        List of provider names that were successfully configured.
    """
    from openbb import obb

    if config is None:
        config = load_config()

    # Map config.toml sections → (OpenBB credential field name, key field in section)
    # OpenBB 4.x uses direct attribute assignment: obb.user.credentials.fmp_api_key = "xxx"
    provider_map: dict[str, tuple[str, str]] = {
        # section       → (credential_attr,    key_field)
        "fmp":          ("fmp_api_key",         "api_key"),
        "intrinio":     ("intrinio_api_key",    "api_key"),
        "tiingo":       ("tiingo_token",        "api_key"),
        "benzinga":     ("benzinga_api_key",    "api_key"),
        "fred":         ("fred_api_key",        "api_key"),
        "bls":          ("bls_api_key",         "api_key"),
        "econdb":       ("econdb_api_key",      "api_key"),
        "eia":          ("eia_api_key",         "api_key"),
        "tradingeconomics": ("tradingeconomics_api_key", "api_key"),
    }

    configured: list[str] = []

    for section, (attr_name, key_field) in provider_map.items():
        section_data = config.get(section, {})
        key_value = section_data.get(key_field, "") if isinstance(section_data, dict) else ""
        if key_value and not key_value.startswith("your-") and key_value != "":
            try:
                setattr(obb.user.credentials, attr_name, key_value)
                configured.append(section)
            except Exception as e:
                import warnings
                warnings.warn(f"Failed to set OpenBB credential '{attr_name}': {e}")

    if configured:
        print(f"[CONFIG] OpenBB credentials configured for: {', '.join(configured)}")

    return configured


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
