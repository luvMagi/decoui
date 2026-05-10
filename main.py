"""Demo entry point."""
import logging
from decoui import gui_main
from decoui.example import *  # noqa: F401, F403

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gui_main(title="decoui Examples", db_path="history.db")
