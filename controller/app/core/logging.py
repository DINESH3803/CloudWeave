"""
Logging Configuration for Controller.

Configures standard logging output formatting and level.
"""
import logging


def setup_logging(level: str = "INFO") -> None:
    """
    Initialize root logger configuration with timestamp, level, and logger name.
    
    Accepts string level (e.g., 'INFO', 'DEBUG') and sets format across the controller.
    """
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
