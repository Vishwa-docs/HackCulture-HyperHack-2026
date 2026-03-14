"""Structured logging with loguru."""
import sys
from pathlib import Path
from loguru import logger

LOG_DIR = Path(__file__).parent.parent.parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Remove default handler
logger.remove()

# Console handler with rich formatting
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# File handler for full audit trail
logger.add(
    LOG_DIR / "pipeline_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="50 MB",
    retention="7 days",
)

def get_logger(name: str):
    return logger.bind(module=name)
