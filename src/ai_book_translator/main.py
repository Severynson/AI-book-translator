from __future__ import annotations

import sys
from dotenv import load_dotenv
from PyQt5.QtWidgets import QApplication

from ai_book_translator.config.settings import Settings
from ai_book_translator.ui.app_window import AppWindow


def main() -> int:
    load_dotenv()  # load .env into environment if present

    app = QApplication(sys.argv)
    settings = Settings()

    w = AppWindow(settings=settings)
    w.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
