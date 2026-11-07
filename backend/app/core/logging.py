import logging
import re
import sys

# Parametri di query che non devono finire nei log: `code`/`state` del callback
# Open Banking (e OAuth Google) sono credenziali a breve vita.
_SENSITIVE_QUERY_PARAM = re.compile(r"([?&](?:code|state|session_state|access_token|id_token)=)[^&\s\"]+", re.IGNORECASE)


def redact_query_secrets(text: str) -> str:
    return _SENSITIVE_QUERY_PARAM.sub(r"\1***", text)


class RedactAccessLogFilter(logging.Filter):
    """Maschera i parametri sensibili nell'access log di uvicorn
    (`args = (client, method, full_path, http_version, status)`)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(redact_query_secrets(a) if isinstance(a, str) else a for a in record.args)
        return True


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactAccessLogFilter) for f in access_logger.filters):
        access_logger.addFilter(RedactAccessLogFilter())
