import logging
from pathlib import Path


try:
    import pydantic as pydantic                
except Exception:
    pydantic = None

try:
    from platformdirs import user_data_path as _platform_user_data_path                
except Exception:
    _platform_user_data_path = None

try:
    import structlog as structlog                
except Exception:
    structlog = None

try:
    from transitions import Machine as StateMachine                
except Exception:
    StateMachine = None


def has_pydantic():
    return pydantic is not None


def has_platformdirs():
    return _platform_user_data_path is not None


def has_structlog():
    return structlog is not None


def has_transitions():
    return StateMachine is not None


def user_data_path(app_name, app_author, fallback_path):
    if _platform_user_data_path is None:
        return Path(fallback_path)
    try:
        return Path(_platform_user_data_path(appname=app_name, appauthor=app_author, ensure_exists=True))
    except Exception:
        return Path(fallback_path)


def get_logger(name):
    if structlog is not None:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
                structlog.processors.UnicodeDecoder(),
                structlog.processors.KeyValueRenderer(
                    key_order=["timestamp", "level", "logger", "event"],
                ),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        return structlog.get_logger(name)

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    class StdLoggerAdapter:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def _msg(self, event, **kwargs):
            if not kwargs:
                return str(event)
            payload = " ".join(f"{key}={value}" for key, value in kwargs.items())
            return f"{event} {payload}"

        def info(self, event, **kwargs):
            self._wrapped.info(self._msg(event, **kwargs))

        def warning(self, event, **kwargs):
            self._wrapped.warning(self._msg(event, **kwargs))

        def error(self, event, **kwargs):
            self._wrapped.error(self._msg(event, **kwargs))

    return StdLoggerAdapter(logger)
