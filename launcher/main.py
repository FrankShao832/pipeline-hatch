# ！/usr/bin/env python3


import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    """_summary_
    """

    app = QApplication(sys.argv)
    app.setApplicationName("Y Pipeline")

    # Create the main window.
    window = MainWindow()
    window.show()

    #
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
