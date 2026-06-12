def get_config() -> dict:
    """Delegate to the canonical app configuration loader."""
    from app.core.config import get_config as app_get_config
    return app_get_config()
