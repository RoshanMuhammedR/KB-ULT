import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """JSON logs, with whatever the request bound into context attached to every line.

    `merge_contextvars` is the part that matters: the tenant and trace ids are bound once
    per request and then appear on every log line that request produces, including lines
    written deep inside the pipeline that have no idea a request exists. Without it, a
    log search can find a message but not the question that caused it.

    Called by both entrypoints. The worker imports `queue.app` rather than `main`, so
    configuring in only one of them is how its logs end up in a different format.
    """
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level]
        ),
        cache_logger_on_first_use=True,
    )
