import logging
import sys
from logging.handlers import RotatingFileHandler

from config.settings import (
    LOG_BACKUP_COUNT,
    LOG_DIR,
    LOG_LEVEL,
    LOG_MAX_BYTES,
    create_project_directories,
)


LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)s | "
    "%(name)s | "
    "%(message)s"
)

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(
    name: str = "pipeline_ptax",
) -> logging.Logger:
    """
    Cria um logger que escreve simultaneamente no terminal
    e em um arquivo com rotação automática.

    Args:
        name:
            Nome utilizado para identificar o logger.

    Returns:
        Logger configurado.
    """

    create_project_directories()

    logger = logging.getLogger(name)

    log_level = getattr(
        logging,
        LOG_LEVEL,
        logging.INFO,
    )

    logger.setLevel(log_level)
    logger.propagate = False

    # Evita handlers duplicados quando o módulo é importado
    # mais de uma vez.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt=LOG_FORMAT,
        datefmt=DATE_FORMAT,
    )

    console_handler = logging.StreamHandler(
        sys.stdout
    )

    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    log_file = LOG_DIR / "pipeline_ptax.log"

    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )

    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger