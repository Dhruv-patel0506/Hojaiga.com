"""
Database Manager — SSMS Logger for UI Knowledge
Tracks layout fingerprints, popup history, and resolution pathways.

Tables:
  - ui_knowledge: Layout tree snapshots with hash fingerprints
  - ui_scanned: Individual control records with bounding boxes
  - popup_history: Cached popup resolutions for instant replay
"""

import hashlib
import json
import logging
import pyodbc
import threading

import logging.config

logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'standard': {'format': '[%(asctime)s] [%(levelname)s] %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'standard',
        },
    },
    'loggers': {
        'hojaiga': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    },
})

logger = logging.getLogger("hojaiga.database_manager")


class DatabaseManager:
    # ... (rest of the code remains the same)
