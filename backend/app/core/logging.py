import logging
import sys


def setup_logging():
    """Configure structured logging for backend microservices."""
    logging_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=logging_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("perplexity_core")
    return logger


logger = setup_logging()
