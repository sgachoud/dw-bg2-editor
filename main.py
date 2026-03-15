"""Entry point for the BG2 Schematic Editor."""

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from ui.main_window import MainWindow
from schematic import Schematic


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BG2 Schematic Editor")
    app.setOrganizationName("dw")

    window = MainWindow()

    # If a file path is passed as CLI argument, load it immediately
    if len(sys.argv) > 1:
        try:
            window.schematic = Schematic.load(sys.argv[1])
            window._dirty = False
            window._refresh_ui()
        except Exception as exc:
            QMessageBox.critical(window, "Load Error", str(exc))

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
