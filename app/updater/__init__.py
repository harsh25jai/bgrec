"""Over-the-air updates (import submodules directly to avoid heavy __init__ side effects)."""

__all__ = ["UpdateCheckResult", "check_for_updates"]


def __getattr__(name: str):
    if name in __all__:
        from app.updater import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
