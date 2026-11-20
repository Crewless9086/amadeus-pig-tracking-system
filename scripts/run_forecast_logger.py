"""Entrypoint for the existing ROOTLINE forecast cron."""
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.telemetry.forecast_logger import main

if __name__ == "__main__":
    main()
