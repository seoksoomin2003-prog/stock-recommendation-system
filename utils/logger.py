import logging
import os
import sys


def setup_logger(name: str):
    """Return a named logger with exactly one console handler.

    P6-18: the previous implementation appended a new handler on every call,
    so modules that called ``setup_logger`` with the same name duplicated every
    log line.  The handler is now attached once per logger name.
    ``QPP_LOG_LEVEL`` (default INFO) controls verbosity.
    """
    logger = logging.getLogger(name)
    logger.setLevel(os.getenv("QPP_LOG_LEVEL", "INFO").upper())
    if not any(getattr(h, "_qpp_console", False) for h in logger.handlers):
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        ch._qpp_console = True
        logger.addHandler(ch)
    logger.propagate = False
    return logger
