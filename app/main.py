from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

# from .ui_main_window import MainWindow
from app.ui_main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
