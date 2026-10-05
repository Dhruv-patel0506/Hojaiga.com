import logging
import sys
from datetime import datetime

class CleanConsoleFormatter(logging.Formatter):
    """
    Formatter to output clean, structured logs without raw JSON in the terminal.
    Format: [HH:MM:SS] [Component] Message
    """
    def __init__(self):
        super().__init__()

    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        # Some organs prefix their names or use specific tags. We format it cleanly.
        component = getattr(record, 'component', record.name)
        
        # Simplify common logger names
        if component.startswith("hojaiga."):
            component = component.split(".")[-1]
            
        msg = record.getMessage()
        
        # Optional: inject visual tags based on log level
        if record.levelno >= logging.ERROR:
            msg = f"ERROR: {msg}"
        elif record.levelno >= logging.WARNING:
            msg = f"WARNING: {msg}"
            
        return f"[{timestamp}] [{component}] {msg}"

def get_clean_logger(name: str, level=logging.INFO) -> logging.Logger:
    """
    Get a logger configured with the CleanConsoleFormatter.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding multiple handlers if logger is already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(CleanConsoleFormatter())
        logger.addHandler(handler)
        
    # Ensure it doesn't propagate up to root if root is spewing JSON
    logger.propagate = False
    return logger
