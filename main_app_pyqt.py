"""
A simple PyQt5 based front‑end for the RSG Recovery Tools project.

This module provides a graphical user interface comparable to the existing
`main_app.py` Tkinter implementation but using PyQt5 instead.  It defines
a main window with a sidebar for navigation and a content area that shows
different pages (bank statement analyser, AI statement analysis, etc.).

The drag‑and‑drop functionality is implemented using Qt's built‑in support:
the `DropArea` widget accepts files dropped onto it and emits a signal
containing the list of file paths.  When files are selected either via
drag and drop or through the browse dialog, the corresponding processing
functions from `bank_analyzer` or `ai_analysis` are run in a background
thread to avoid blocking the user interface.  A simple status message
indicates when processing is in progress.

This file is intentionally lightweight and does not attempt to port every
feature from the Tkinter version.  It should serve as a starting point
for a more complete PyQt port.  Additional functionality (such as the
administrative tools or detailed progress indicators) can be built on
top of the scaffolding provided here.

To run the application:

    python main_app_pyqt.py

Ensure that PyQt5 is installed (see `requirements.txt`).
"""

import os
import sys

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import ai_analysis  # type: ignore

# Import application logic modules.  These modules are part of the existing
# codebase and provide the core PDF processing functions.  They may rely
# on configuration values (e.g. OpenAI API keys) from a `config` module.
import bank_analyzer


def get_openai_key() -> str:
    """Helper to retrieve the OpenAI API key from the `config` module.

    The Tkinter version reads the API key in several places.  Centralising
    the lookup here makes it easier to adjust if the configuration
    mechanism changes.
    """
    try:
        import config  # type: ignore

        return getattr(config, "openai_api_key", "")
    except Exception:
        return ""


class DropArea(QFrame):
    """A frame that accepts drag‑and‑drop file paths.

    When one or more files are dropped onto this widget, the
    `files_dropped` signal is emitted with a list of file paths.
    """

    files_dropped = pyqtSignal(list)

    def __init__(self, prompt: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setStyleSheet(
            """
            DropArea {
                border: 2px dashed #0075c6;
                border-radius: 8px;
                background-color: #f2f6fa;
            }
            """
        )
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(prompt)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setLayout(layout)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if files:
            self.files_dropped.emit(files)
        event.acceptProposedAction()


class AnalyzerThread(QThread):
    """Worker thread to process PDF files without blocking the UI."""

    finished = pyqtSignal()

    def __init__(self, files: list[str], mode: str) -> None:
        super().__init__()
        self.files = files
        self.mode = mode

    def run(self) -> None:
        # Choose the appropriate processing function based on mode
        try:
            if self.mode == "bank":
                # Use bank analyzer processing (no API key needed)
                bank_analyzer.process_bank_statements_full(self.files, get_openai_key())
            elif self.mode == "ai":
                # AI analysis requires an OpenAI API key
                key = get_openai_key()
                ai_analysis.process_bank_statements_ai(self.files, key, None)  # type: ignore
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    """Main application window replicating the Tkinter structure using PyQt.

    The window is divided into a left sidebar and a right content area.  The
    sidebar updates dynamically based on the current section (main menu,
    admin, collections, sales).  The content area displays pages which are
    created via helper methods.  Navigation methods (`show_*`) update both
    the sidebar and the content accordingly.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RSG Recovery Tools (PyQt Edition)")
        self.resize(1000, 650)

        # Root widget and layout
        central = QWidget()
        root_layout = QHBoxLayout()
        central.setLayout(root_layout)
        self.setCentralWidget(central)

        # Sidebar: a widget containing a vertical layout.  We'll keep a
        # reference to the layout so we can clear and rebuild it when the
        # user navigates to different sections.
        self.sidebar_widget = QWidget()
        self.sidebar_layout = QVBoxLayout()
        self.sidebar_widget.setLayout(self.sidebar_layout)
        # Match the width of the Tkinter version's sidebar (approx 220 px)
        self.sidebar_widget.setFixedWidth(220)
        root_layout.addWidget(self.sidebar_widget)

        # Content area: a stacked widget holding all pages.  We'll map
        # descriptive string keys to page indices via self.page_indices.
        self.pages = QStackedWidget()
        root_layout.addWidget(self.pages, 1)
        self.page_indices: dict[str, int] = {}

        # Create pages and store their indices
        self.page_indices["main_menu"] = self.pages.addWidget(self._create_main_menu_page())
        self.page_indices["admin"] = self.pages.addWidget(self._create_admin_page())
        self.page_indices["bank_analyzer"] = self.pages.addWidget(self._create_bank_page())
        self.page_indices["ai_analyzer"] = self.pages.addWidget(self._create_ai_page())
        self.page_indices["bsa_settings"] = self.pages.addWidget(self._create_bsa_settings_page())
        self.page_indices["evg_splitter"] = self.pages.addWidget(self._create_evg_splitter_page())
        self.page_indices["collections"] = self.pages.addWidget(self._create_collections_page())
        self.page_indices["sales"] = self.pages.addWidget(self._create_sales_page())

        # Create an additional status bar to show processing messages
        self.status_label = QLabel("")
        self.statusBar().addPermanentWidget(self.status_label)

        # Start at the main menu
        self.show_main_menu()

    # ---------------------------------------------------------------------
    # Sidebar helpers
    # ---------------------------------------------------------------------
    def clear_sidebar(self) -> None:
        """Remove all widgets from the sidebar layout."""
        while self.sidebar_layout.count():
            item = self.sidebar_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_sidebar(self, mode: str) -> None:
        """Populate the sidebar based on the current navigation mode.

        When `mode` is 'main_menu', the sidebar is blank.  Otherwise a
        'Main Menu' button is added along with a heading and context-
        specific menu items.
        """
        self.clear_sidebar()
        if mode == "main_menu":
            return

        # Main menu button
        main_btn = QPushButton("Main Menu")
        main_btn.setFixedHeight(32)
        main_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #0075c6;
                color: white;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005a98;
            }
            """
        )
        main_btn.clicked.connect(self.show_main_menu)
        self.sidebar_layout.addWidget(main_btn)
        self.sidebar_layout.addSpacing(12)

        # Section heading
        section_label_text = {"admin": "Admin", "collections": "Collections", "sales": "Sales"}.get(
            mode, ""
        )
        if section_label_text:
            header = QLabel(section_label_text)
            header.setStyleSheet("font-size: 18px; font-weight: bold; color: #0075c6;")
            self.sidebar_layout.addWidget(header)
            self.sidebar_layout.addSpacing(6)

        # Add section-specific navigation buttons
        if mode == "admin":
            items = [
                ("EVG Recovery File Splitter", self.show_evg_splitter),
                ("Bank Statement Analyzer", self.show_bank_analyzer),
                ("AI Statement Analysis", self.show_ai_analysis),
                ("BSA Settings", self.show_bsa_settings),
            ]
            for text, handler in items:
                btn = QPushButton(text)
                btn.setFixedHeight(38)
                btn.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #0075c6;
                        color: white;
                        border-radius: 20px;
                        font-size: 14px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #005a98;
                    }
                    """
                )
                btn.clicked.connect(handler)
                self.sidebar_layout.addWidget(btn)
                self.sidebar_layout.addSpacing(6)
        elif mode in ("collections", "sales"):
            # Collections and Sales currently have no sub-menu functionality.
            placeholder = QLabel("No tools available.")
            placeholder.setStyleSheet("font-size: 14px; color: #666;")
            self.sidebar_layout.addWidget(placeholder)
            self.sidebar_layout.addSpacing(6)

        self.sidebar_layout.addStretch(1)

    # ---------------------------------------------------------------------
    # Content helpers
    # ---------------------------------------------------------------------
    def set_content(self, mode: str) -> None:
        """Switch the stacked widget to the page corresponding to `mode`."""
        index = self.page_indices.get(mode)
        if index is not None:
            self.pages.setCurrentIndex(index)

    # ---------------------------------------------------------------------
    # Navigation methods (call these to change pages)
    # ---------------------------------------------------------------------
    def show_main_menu(self) -> None:
        self.set_sidebar("main_menu")
        self.set_content("main_menu")

    def show_admin(self) -> None:
        self.set_sidebar("admin")
        self.set_content("admin")

    def show_collections(self) -> None:
        self.set_sidebar("collections")
        self.set_content("collections")

    def show_sales(self) -> None:
        self.set_sidebar("sales")
        self.set_content("sales")

    def show_bank_analyzer(self) -> None:
        # When selecting a sub‑tool under admin, keep the admin sidebar visible.
        self.set_sidebar("admin")
        self.set_content("bank_analyzer")

    def show_ai_analysis(self) -> None:
        self.set_sidebar("admin")
        self.set_content("ai_analyzer")

    def show_bsa_settings(self) -> None:
        self.set_sidebar("admin")
        self.set_content("bsa_settings")

    def show_evg_splitter(self) -> None:
        self.set_sidebar("admin")
        self.set_content("evg_splitter")

    def _create_bank_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        # Page title
        title = QLabel("Bank Statement Analyzer")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #0075c6;")
        layout.addWidget(title)
        layout.addSpacing(12)
        # Subtitle
        subtitle = QLabel("Drag and drop PDF bank statements here, or click Browse.")
        subtitle.setStyleSheet("font-size: 16px; color: #333;")
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        # Drop area
        drop = DropArea("Drop files here")
        layout.addWidget(drop, 1)
        drop.files_dropped.connect(lambda files: self._process_files(files, "bank"))
        # Browse button
        browse_btn = QPushButton("Browse Files")
        browse_btn.setFixedWidth(180)
        browse_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #0075c6;
                color: white;
                border-radius: 22px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005a98;
            }
            """
        )
        browse_btn.clicked.connect(lambda: self._browse_files("bank"))
        layout.addSpacing(18)
        layout.addWidget(browse_btn, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        return widget

    def _create_ai_page(self) -> QWidget:
        """Create the AI Statement Analysis page."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        title = QLabel("AI Statement Analysis")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #ba0075;")
        layout.addWidget(title)
        layout.addSpacing(12)
        subtitle = QLabel("Analyze bank statements using AI (OpenAI charges apply).")
        subtitle.setStyleSheet("font-size: 16px; color: #ba0075;")
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        drop = DropArea("Drop files here")
        layout.addWidget(drop, 1)
        drop.files_dropped.connect(lambda files: self._process_files(files, "ai"))
        browse_btn = QPushButton("Browse Files")
        browse_btn.setFixedWidth(180)
        browse_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #ba0075;
                color: white;
                border-radius: 22px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7e0059;
            }
            """
        )
        browse_btn.clicked.connect(lambda: self._browse_files("ai"))
        layout.addSpacing(18)
        layout.addWidget(browse_btn, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        return widget

    def _create_bsa_settings_page(self) -> QWidget:
        """Create a stub for the BSA Settings page."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        title = QLabel("Bank Statement Analyzer Settings")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #0075c6;")
        layout.addWidget(title)
        layout.addSpacing(20)
        message = QLabel("Settings UI not implemented yet.")
        message.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(message, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        return widget

    def _create_evg_splitter_page(self) -> QWidget:
        """Create a stub for the EVG Recovery File Splitter page."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        title = QLabel("EVG Recovery File Splitter")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #0075c6;")
        layout.addWidget(title)
        layout.addSpacing(20)
        message = QLabel("EVG splitter UI not implemented yet.")
        message.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(message, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        return widget

    def _create_collections_page(self) -> QWidget:
        """Create a stub for the Collections page."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        title = QLabel("Collections")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #0075c6;")
        layout.addWidget(title)
        layout.addSpacing(20)
        message = QLabel("Collections functionality is not implemented yet.")
        message.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(message, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        return widget

    def _create_sales_page(self) -> QWidget:
        """Create a stub for the Sales page."""
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        title = QLabel("Sales")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #0075c6;")
        layout.addWidget(title)
        layout.addSpacing(20)
        message = QLabel("Sales functionality is not implemented yet.")
        message.setStyleSheet("font-size: 16px; color: #666;")
        layout.addWidget(message, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        return widget

    def _create_main_menu_page(self) -> QWidget:
        """Create the main menu page with logo, title and navigation buttons.

        This replicates the layout of the Tkinter version: a centred logo and
        title with buttons for Collections, Sales and Admin.  An Exit button
        is placed in the bottom right corner of the page.
        """
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        layout.setAlignment(Qt.AlignCenter)
        # Logo
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        # Try to load a logo image from the project directory.  If the file
        # is missing, fall back to a text placeholder.
        logo_path = os.path.join(os.getcwd(), "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Scale the pixmap to a reasonable size while keeping aspect ratio
            pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("RSG")
            logo_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #0075c6;")
        layout.addWidget(logo_label)
        layout.addSpacing(12)
        # Title
        title = QLabel("RSG Recovery Tools")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #0075c6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(24)
        # Buttons for Collections, Sales, Admin
        buttons = [
            ("Collections", self.show_collections),
            ("Sales", self.show_sales),
            ("Admin", self.show_admin),
        ]
        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setFixedSize(240, 50)
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #0075c6;
                    color: white;
                    border-radius: 25px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #005a98;
                }
                """
            )
            btn.clicked.connect(handler)
            layout.addWidget(btn, alignment=Qt.AlignCenter)
            layout.addSpacing(12)
        layout.addSpacing(12)
        # Exit button at bottom right: create a horizontal layout to push it to the right
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        exit_btn = QPushButton("Exit")
        exit_btn.setFixedSize(80, 32)
        exit_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #0075c6;
                color: white;
                border-radius: 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005a98;
            }
            """
        )
        exit_btn.clicked.connect(self.close)
        bottom_layout.addWidget(exit_btn)
        # Insert the bottom layout at the end of the page layout
        layout.addLayout(bottom_layout)
        return widget

    def _create_admin_page(self) -> QWidget:
        """Create the admin landing page with a welcome message.

        When the user selects 'Admin' from the main menu, this page is shown
        and instructs them to choose a tool from the sidebar.
        """
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        title = QLabel("Administrator Tools")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #0075c6;")
        layout.addWidget(title)
        layout.addSpacing(20)
        message = QLabel("Select a tool from the left-hand sidebar to get started.")
        message.setStyleSheet("font-size: 16px; color: #333;")
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch(1)
        return widget

    def _browse_files(self, mode: str) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Bank Statement PDFs", os.getcwd(), "PDF Files (*.pdf)"
        )
        if files:
            self._process_files(files, mode)

    def _process_files(self, files: list[str], mode: str) -> None:
        # Update status bar
        action = "Analyzing" if mode == "ai" else "Processing"
        self.status_label.setText(f"{action} {len(files)} file(s)…")
        # Start worker thread
        worker = AnalyzerThread(files, mode)
        worker.finished.connect(lambda: self.status_label.setText("Done."))
        worker.start()


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
