# main_app_pyqt.py
import os
import sys
import time
import threading
from typing import List
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt

# Qt imports
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QFont, QDesktopServices, QImage
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QStackedWidget, QFrame, QScrollArea,
    QCheckBox, QLineEdit, QTextEdit, QGridLayout, QDialog, QDialogButtonBox, QComboBox, QSpinBox
)

# --- Your domain modules (unchanged) ---
import bank_analyzer
import bsa_settings
# ai_analysis and evg_splitter are imported on-demand in handlers


APP_NAME = "RSG Recovery Tools"


# -----------------------------
# Helpers / Shared Components
# -----------------------------
def pil_to_qpixmap(path: str, max_size: int = 260) -> QPixmap:
    """Load image (logo) and keep aspect ratio. Uses in-memory Pillow->QImage conversion."""
    try:
        img = Image.open(path)
        w, h = img.size
        if w > h:
            new_w = max_size
            new_h = int(h * max_size / w)
        else:
            new_h = max_size
            new_w = int(w * max_size / h)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        qimg = ImageQt(img)  # Pillow -> QImage adapter
        return QPixmap.fromImage(qimg)
    except Exception:
        return QPixmap()


class DropArea(QFrame):
    """Reusable drag-and-drop frame that emits a signal with file paths."""
    filesDropped = pyqtSignal(list)

    def __init__(self, label_text: str, accent: str = "#0075c6", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._accent = accent
        self._base_style = f"""
            QFrame {{
                background: rgba(0,0,0,0);
                border: 2px dashed {accent};
                border-radius: 12px;
                min-height: 120px;
            }}
        """
        self._hover_style = f"""
            QFrame {{
                background: rgba(0,0,0,0.02);
                border: 2px solid {accent};
                border-radius: 12px;
                min-height: 120px;
            }}
        """
        self.setStyleSheet(self._base_style)
        lay = QVBoxLayout(self)
        self.lbl = QLabel(label_text)
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet(f"color:{accent}; font: 14px 'Arial'; font-style: italic;")
        lay.addWidget(self.lbl)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setStyleSheet(self._hover_style)

    def dragMoveEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        paths = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p:
                paths.append(p)
        if paths:
            self.filesDropped.emit(paths)
        self.setStyleSheet(self._base_style)

    def dragLeaveEvent(self, e):
        self.setStyleSheet(self._base_style)


class ElipsisSpinner(QObject):
    """Tiny text spinner 'Thinking', 'Analyzing', 'Splitting' with dots."""
    tick = pyqtSignal(str)

    def __init__(self, base_text: str, interval_ms: int = 130, parent=None):
        super().__init__(parent)
        self.base = base_text
        self._dots = 0
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._advance)

    def start(self):
        self._dots = 0
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.tick.emit("")  # clear

    def _advance(self):
        self._dots = (self._dots + 1) % 4
        self.tick.emit(self.base + ("." * self._dots))


# -----------------------------
# Main Window
# -----------------------------
class MainWindow(QMainWindow):
    # Cross-thread worker signals (ensure UI updates happen on the main thread)
    bank_done = pyqtSignal()
    bank_error = pyqtSignal(str)
    bank_progress = pyqtSignal(str)
    ai_done = pyqtSignal()
    ai_error = pyqtSignal(str)
    evg_done = pyqtSignal()
    evg_error = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1000, 650)
        self._ai_expected_outputs: List[str] = []
        self._ai_expected_summaries: List[str] = []
        self._ai_dir_to_summary = {}
        # In-app PDF preview state
        self.ai_preview_images: List[QImage] = []
        self.ai_preview_page_labels: List[QLabel] = []
        self.ai_preview_page_count: int = 0
        self.ai_preview_current_page: int = 0
        self.ai_zoom: float = 1.0

        # Root container
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)

        # Sidebar
        self.sidebar = QFrame()
        # Widen sidebar so long labels fit nicely
        self.sidebar.setFixedWidth(320)
        self.sidebar.setStyleSheet("QFrame{background:#f2f6fa;}")

        self.sidebarLayout = QVBoxLayout(self.sidebar)
        self.sidebarLayout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(self.sidebar)

        # Content stack
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Build pages
        self.page_main = self._build_main_menu()
        self.page_admin = self._build_admin()
        self.page_bank = self._build_bank_analyzer()
        self.page_ai = self._build_ai_analyzer()
        self.page_bsa = self._build_bsa_settings()
        self.page_evg = self._build_evg_splitter()

        # Add to stack
        for page in [self.page_main, self.page_admin, self.page_bank, self.page_ai, self.page_bsa, self.page_evg]:
            self.stack.addWidget(page)

        # Top-level nav
        self._set_sidebar("main_menu")
        self.stack.setCurrentWidget(self.page_main)

        # Exit button (bottom-right like your Tk `place`)
        exit_btn = QPushButton("Exit", self)
        exit_btn.setStyleSheet("""
            QPushButton{
                background:#0075c6; color:white; padding:6px 14px; border-radius:14px; font: 700 11px 'Arial';
            }
            QPushButton:hover{ background:#005a98; }
        """)
        exit_btn.clicked.connect(self.close)
        # Position using a floating layout trick
        self.statusBar().addPermanentWidget(exit_btn)

        # Connect worker signals
        self.bank_done.connect(self._on_bank_done)
        self.bank_error.connect(self._on_bank_error)
        self.ai_done.connect(self._on_ai_done)
        self.ai_error.connect(self._on_ai_error)
        self.evg_done.connect(self._on_evg_done)
        self.evg_error.connect(self._on_evg_error)
        self.bank_progress.connect(self._on_bank_progress)

        # Brief status timer to clear completion text on the bank analyzer page
        self._bank_status_timer = QTimer(self)
        self._bank_status_timer.setSingleShot(True)
        # Clear the spinner label text after a short delay when showing 'Complete!'
        self._bank_status_timer.timeout.connect(lambda: self.bank_spinner_label.setText(""))

    # ---------------- Sidebar ----------------
    def _clear_sidebar(self):
        while self.sidebarLayout.count():
            item = self.sidebarLayout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _set_sidebar(self, mode: str):
        self._clear_sidebar()
        if mode == "main_menu":
            return

        def add_label(text, color):
            lab = QLabel(text)
            lab.setStyleSheet(f"color:{color}; font: 700 18px 'Arial';")
            self.sidebarLayout.addWidget(lab)

        btn = QPushButton("Main Menu")
        btn.setStyleSheet("""
            QPushButton{
                background:#0075c6; color:white; font: 700 12px 'Arial';
                border-radius: 20px; padding:6px 14px;
            }
            QPushButton:hover{ background:#005a98; }
        """)
        btn.clicked.connect(lambda: self.show_page("main_menu"))
        self.sidebarLayout.addWidget(btn)
        self.sidebarLayout.addSpacing(10)

        label_map = {"admin": ("Admin", "#0075c6"),
                     "collections": ("Collections", "#0075c6"),
                     "sales": ("Sales", "#0075c6")}
        if mode in label_map:
            add_label(*label_map[mode])

        if mode == "admin":
            for text, handler in [
                ("EVG Recovery File Splitter", lambda: self.show_page("evg_splitter")),
                ("Bank Statement Analyzer", lambda: self.show_page("bank_analyzer")),
                ("AI Statement Analysis", lambda: self.show_page("ai_analyzer")),
                ("BSA Settings", lambda: self.show_page("bsa_settings")),
            ]:
                b = QPushButton(text)
                b.setStyleSheet("""
                    QPushButton{
                        background:#e9f2fb; color:#000; font: 700 13px 'Arial';
                        border-radius: 20px; padding:8px 14px;
                    }
                    QPushButton:hover{ background:#d4e8fb; }
                """)
                b.clicked.connect(handler)
                self.sidebarLayout.addWidget(b)
        self.sidebarLayout.addStretch(1)

    # ---------------- Pages ----------------
    def _build_main_menu(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        v.setContentsMargins(20, 20, 20, 20)

        # Logo
        pm = pil_to_qpixmap("logo.png", max_size=260)
        if not pm.isNull():
            img = QLabel()
            img.setPixmap(pm)
            v.addSpacing(30)
            v.addWidget(img, alignment=Qt.AlignmentFlag.AlignHCenter)
        else:
            lbl = QLabel("LOGO")
            lbl.setStyleSheet("color:#0075c6; font: 36px 'Arial';")
            v.addSpacing(30)
            v.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(APP_NAME)
        title.setStyleSheet("color:#0075c6; font: 700 28px 'Arial';")
        v.addSpacing(10)
        v.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        v.addSpacing(20)

        def big_btn(text, cb):
            b = QPushButton(text)
            b.setFixedWidth(320)
            b.setFixedHeight(44)
            b.setStyleSheet("""
                QPushButton{
                    background:#0075c6; color:white; font: 700 16px 'Arial';
                    border-radius: 30px;
                }
                QPushButton:hover{ background:#005a98; }
            """)
            b.clicked.connect(cb)
            v.addWidget(b, alignment=Qt.AlignmentFlag.AlignHCenter)
            v.addSpacing(12)

        big_btn("Collections", lambda: self.show_page("collections"))
        big_btn("Sales", lambda: self.show_page("sales"))
        big_btn("Admin", lambda: self.show_page("admin"))
        return page

    def _build_admin(self) -> QWidget:
        page = QWidget()
        lab = QLabel("Please select an admin tool from the menu on the left.")
        lab.setStyleSheet("color:#0075c6; font: italic 20px 'Arial';")
        lay = QVBoxLayout(page)
        lay.addSpacing(80)
        lay.addWidget(lab, alignment=Qt.AlignmentFlag.AlignHCenter)
        return page

    # ---- Bank Analyzer ----
    def _build_bank_analyzer(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)
        v.setContentsMargins(20, 20, 20, 20)

        t = QLabel("Bank Statement Analyzer")
        t.setStyleSheet("color:#0075c6; font: 700 24px 'Arial';")
        v.addWidget(t)
        v.addWidget(self._subtitle("Drag and drop PDF bank statements here, or click to browse."))
        v.addSpacing(6)

        drop = DropArea("Drop files here", accent="#0075c6")
        v.addWidget(drop)

        self.bank_spinner_label = QLabel("")
        self.bank_spinner_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.bank_spinner_label.setStyleSheet("color:#0075c6; font: 700 20px 'Arial';")
        v.addWidget(self.bank_spinner_label)

        # Progress line (shows current file and step)
        self.bank_progress_label = QLabel("")
        self.bank_progress_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.bank_progress_label.setStyleSheet("color:#333; font: 12px 'Arial';")
        v.addWidget(self.bank_progress_label)

        spinner = ElipsisSpinner("Thinking")
        spinner.tick.connect(self.bank_spinner_label.setText)
        self._bank_spinner = spinner

        browse = QPushButton("Browse Files")
        browse.setStyleSheet("""
            QPushButton{ background:#0075c6; color:white; font: 700 14px 'Arial';
                         border-radius: 22px; padding:8px 18px; }
            QPushButton:hover{ background:#005a98; }
        """)
        v.addSpacing(6)
        v.addWidget(browse, alignment=Qt.AlignmentFlag.AlignHCenter)

        # OCR-first toggle for more accurate parsing
        self.chk_ocr_first = QCheckBox("Use OCR-first (slower, more accurate)")
        self.chk_ocr_first.setChecked(False)
        self.chk_ocr_first.setToolTip("Runs OCR for all pages before parsing; improves headers/columns detection.")
        v.addWidget(self.chk_ocr_first, alignment=Qt.AlignmentFlag.AlignHCenter)

        def on_files(paths: List[str]):
            pdfs = [p for p in paths if os.path.isfile(p) and p.lower().endswith('.pdf')]
            if not pdfs:
                QMessageBox.warning(self, "No PDFs", "Please drop one or more PDF files.")
                return
            self._start_bank_analysis(pdfs)

        def on_browse():
            paths, _ = QFileDialog.getOpenFileNames(self, "Select Bank Statement PDFs",
                                                    filter="PDF files (*.pdf)")
            if paths:
                self._start_bank_analysis(paths)

        drop.filesDropped.connect(on_files)
        browse.clicked.connect(on_browse)
        return page

    def _start_bank_analysis(self, paths: List[str]):
        # spinner
        self._bank_spinner.start()
        def work():
            try:
                # Respect OCR-first toggle via environment variable for current process
                prev = os.getenv("BANK_OCR_FIRST")
                if self.chk_ocr_first.isChecked():
                    os.environ["BANK_OCR_FIRST"] = "1"
                else:
                    if "BANK_OCR_FIRST" in os.environ:
                        del os.environ["BANK_OCR_FIRST"]
                # Emit progress safely from worker via signal
                def _progress(msg: str):
                    try:
                        self.bank_progress.emit(msg)
                    except Exception:
                        pass
                bank_analyzer.process_bank_statements_full(paths, None, progress_cb=_progress)
                # restore
                if prev is not None:
                    os.environ["BANK_OCR_FIRST"] = prev
                else:
                    if "BANK_OCR_FIRST" in os.environ:
                        del os.environ["BANK_OCR_FIRST"]
            except Exception as e:
                self.bank_error.emit(str(e))
            else:
                self.bank_done.emit()
        threading.Thread(target=work, daemon=True).start()

    # ---- AI Analyzer ----
    def _build_ai_analyzer(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)
        v.setContentsMargins(20, 20, 20, 20)

        t = QLabel("AI Statement Analysis")
        t.setStyleSheet("color:#ba0075; font: 700 24px 'Arial';")
        v.addWidget(t)
        v.addWidget(self._subtitle("Analyze bank statements using AI (OpenAI charges apply).", color="#ba0075"))
        v.addSpacing(6)

        drop = DropArea("Drop files here", accent="#ba0075")
        v.addWidget(drop)

        self.ai_spinner_label = QLabel("")
        self.ai_spinner_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.ai_spinner_label.setStyleSheet("color:#ba0075; font: 700 20px 'Arial';")
        v.addWidget(self.ai_spinner_label)

        spinner = ElipsisSpinner("Analyzing")
        spinner.tick.connect(self.ai_spinner_label.setText)
        self._ai_spinner = spinner

        browse = QPushButton("Browse Files")
        browse.setStyleSheet("""
            QPushButton{ background:#ba0075; color:white; font: 700 14px 'Arial';
                         border-radius: 22px; padding:8px 18px; }
            QPushButton:hover{ background:#7e0059; }
        """)
        v.addSpacing(6)
        v.addWidget(browse, alignment=Qt.AlignmentFlag.AlignHCenter)

        def on_files(paths: List[str]):
            self._start_ai_analysis(paths)

        def on_browse():
            paths, _ = QFileDialog.getOpenFileNames(self, "Select Bank Statement PDFs",
                                                    filter="PDF files (*.pdf)")
            if paths:
                self._start_ai_analysis(paths)

        drop.filesDropped.connect(on_files)
        browse.clicked.connect(on_browse)

        # Dedicated button to set/save OpenAI API key (belongs to AI page)
        set_key = QPushButton("Set/OpenAI Key")
        set_key.setStyleSheet("""
            QPushButton{ background:#ba0075; color:white; font: 700 12px 'Arial';
                         border-radius: 18px; padding:6px 14px; }
            QPushButton:hover{ background:#7e0059; }
        """)
        v.addWidget(set_key, alignment=Qt.AlignmentFlag.AlignHCenter)

        def on_set_key():
            self._prompt_openai_key_and_save()
        set_key.clicked.connect(on_set_key)

        # Option: auto-open first output folder on completion
        self.ai_auto_open_checkbox = QCheckBox("Auto-open first output folder when done")
        self.ai_auto_open_checkbox.setChecked(True)
        v.addWidget(self.ai_auto_open_checkbox, alignment=Qt.AlignmentFlag.AlignHCenter)

        # In-app PDF preview controls + area
        v.addSpacing(10)
        prev_label = QLabel("Preview")
        prev_label.setStyleSheet("color:#555; font: 700 13px 'Arial';")
        v.addWidget(prev_label)

        # Controls row: Prev/Next, Page spin, Zoom - / Reset / +
        ctrl = QHBoxLayout()
        self.btn_ai_prev = QPushButton("Prev")
        self.btn_ai_next = QPushButton("Next")
        self.ai_page_spin = QSpinBox()
        self.ai_page_spin.setRange(1, 1)
        self.ai_page_spin.setValue(1)
        self.ai_page_of_label = QLabel("of 0")
        self.ai_page_of_label.setStyleSheet("color:#666; font: 12px 'Arial';")
        ctrl.addWidget(self.btn_ai_prev)
        ctrl.addWidget(self.btn_ai_next)
        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("Page:"))
        ctrl.addWidget(self.ai_page_spin)
        ctrl.addWidget(self.ai_page_of_label)
        ctrl.addStretch(1)
        self.btn_ai_zoom_out = QPushButton("Zoom -")
        self.btn_ai_zoom_reset = QPushButton("Reset")
        self.btn_ai_zoom_in = QPushButton("Zoom +")
        self.ai_zoom_label = QLabel("100%")
        self.ai_zoom_label.setStyleSheet("color:#666; font: 12px 'Arial';")
        ctrl.addWidget(self.btn_ai_zoom_out)
        ctrl.addWidget(self.btn_ai_zoom_reset)
        ctrl.addWidget(self.btn_ai_zoom_in)
        ctrl.addSpacing(8)
        ctrl.addWidget(self.ai_zoom_label)
        v.addLayout(ctrl)

        self.ai_preview_scroll = QScrollArea()
        self.ai_preview_scroll.setWidgetResizable(True)
        v.addWidget(self.ai_preview_scroll, 1)
        self.ai_preview_container = QWidget()
        self.ai_preview_scroll.setWidget(self.ai_preview_container)
        from PyQt6.QtWidgets import QVBoxLayout as _QVBox
        self.ai_preview_layout = _QVBox(self.ai_preview_container)
        self.ai_preview_layout.setContentsMargins(10, 10, 10, 10)
        self.ai_preview_layout.setSpacing(8)

        # Initial placeholder
        ph = QLabel("Run AI Statement Analysis to see the summary preview here.")
        ph.setStyleSheet("color:#888; font: italic 12px 'Arial';")
        ph.setWordWrap(True)
        self.ai_preview_layout.addWidget(ph)

        # Wire controls
        self.btn_ai_prev.clicked.connect(lambda: self._goto_ai_page(self.ai_preview_current_page))
        self.btn_ai_next.clicked.connect(lambda: self._goto_ai_page(self.ai_preview_current_page + 2))
        self.ai_page_spin.valueChanged.connect(lambda v: self._goto_ai_page(v))
        self.btn_ai_zoom_in.clicked.connect(lambda: self._ai_set_zoom(self.ai_zoom * 1.2))
        self.btn_ai_zoom_out.clicked.connect(lambda: self._ai_set_zoom(self.ai_zoom / 1.2))
        self.btn_ai_zoom_reset.clicked.connect(lambda: self._ai_set_zoom(1.0))
        return page

    def _start_ai_analysis(self, paths: List[str]):
        # optional dotenv for local dev
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            try:
                import config  # optional local file, ignored by git
                api_key = getattr(config, "openai_api_key", "")
            except Exception:
                api_key = ""
        if not api_key:
            # Prompt user to paste key and save to .env
            api_key = self._prompt_openai_key_and_save()
            if not api_key:
                QMessageBox.critical(self, "Missing API Key",
                                     "OPENAI_API_KEY is not set.\n\n"
                                     "Set it in your environment (or a .env file),\n"
                                     "or add config.py with openai_api_key='...'")
                return

        # Pre-compute where outputs will be written so we can inform the user on completion
        try:
            import ai_analysis as _ai_for_paths
            out_dirs = [str(_ai_for_paths.get_statement_subfolder(p)) for p in paths]
            summaries = []
            dir_to_summary = {}
            for p in paths:
                sub = _ai_for_paths.get_statement_subfolder(p)
                name = _ai_for_paths.extract_company_name(p)
                s = str(sub / f"{name} Summary.pdf")
                summaries.append(s)
                dir_to_summary[str(sub)] = s
        except Exception:
            out_dirs = []
            summaries = []
            dir_to_summary = {}
            for p in paths:
                try:
                    rp = Path(p).resolve()
                    no_ext = rp.with_suffix("")
                    sub = no_ext.parent / f"{no_ext.name}_analysis"
                    out_dirs.append(str(sub))
                    s = str(sub / f"{no_ext.name} Summary.pdf")
                    summaries.append(s)
                    dir_to_summary[str(sub)] = s
                except Exception:
                    pass
        self._ai_expected_outputs = sorted({d for d in out_dirs})
        self._ai_expected_summaries = summaries
        self._ai_dir_to_summary = dir_to_summary

        self._ai_spinner.start()
        def work():
            try:
                import ai_analysis
                ai_analysis.process_bank_statements_ai(paths, api_key, None)
            except Exception as e:
                self.ai_error.emit(str(e))
            else:
                self.ai_done.emit()
        threading.Thread(target=work, daemon=True).start()

    def _prompt_openai_key_and_save(self) -> str:
        """Prompt for API key, save to .env next to this file, set env var, and return the key (or empty)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Set OpenAI API Key")
        dlg.resize(460, 180)
        v = QVBoxLayout(dlg)

        lab = QLabel("Paste your OpenAI API key. It will be saved to a local .env file (not committed).")
        lab.setWordWrap(True)
        lab.setStyleSheet("font: 13px 'Arial';")
        v.addWidget(lab)

        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText("sk-... or sk-svcacct-...")
        v.addWidget(edit)

        show = QCheckBox("Show key")
        def toggle_show(checked: bool):
            edit.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        show.toggled.connect(toggle_show)
        v.addWidget(show)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(buttons)

        result_key = ""
        def save():
            nonlocal result_key
            k = edit.text().strip()
            if not k:
                QMessageBox.warning(dlg, "Missing Key", "Please paste your API key.")
                return
            try:
                self._write_env_key("OPENAI_API_KEY", k)
                os.environ["OPENAI_API_KEY"] = k
                result_key = k
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "Save Error", str(e))
        buttons.accepted.connect(save)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            return result_key
        return ""

    def _write_env_key(self, name: str, value: str):
        """Upsert NAME=value into a .env file in the project directory (same dir as this script)."""
        root_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(root_dir, ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        written = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{name}="):
                new_lines.append(f'{name}="{value}"')
                written = True
            else:
                new_lines.append(line)
        if not written:
            new_lines.append(f'{name}="{value}"')
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

    # ---- BSA Settings ----
    def _build_bsa_settings(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)
        v.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Bank Statement Analyzer Settings")
        title.setStyleSheet("color:#0075c6; font: 700 24px 'Arial';")
        v.addWidget(title)

        # Tabs (two buttons)
        tabBar = QHBoxLayout()
        self._bsa_mode = "mp"  # "mp" or "excl"

        self.btn_mp = QPushButton("Merchant Processor List")
        self.btn_ex = QPushButton("Exclusion List")
        self._style_tab_buttons()
        self.btn_mp.clicked.connect(lambda: self._switch_bsa_mode("mp"))
        self.btn_ex.clicked.connect(lambda: self._switch_bsa_mode("excl"))

        tabBar.addWidget(self.btn_mp)
        tabBar.addWidget(self.btn_ex)
        v.addLayout(tabBar)

        # Import/Export row
        tools = QHBoxLayout()
        self.btn_import = QPushButton("Import")
        self.btn_export = QPushButton("Export")
        tools.addWidget(self.btn_import)
        tools.addWidget(self.btn_export)
        v.addLayout(tools)

        self.btn_import.clicked.connect(self._bsa_import)
        self.btn_export.clicked.connect(self._bsa_export)

        # Scrollable table area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        v.addWidget(self.scroll, 1)

        self.table_container = QWidget()
        self.scroll.setWidget(self.table_container)
        self.table_grid = QGridLayout(self.table_container)
        self.table_grid.setContentsMargins(6, 6, 6, 6)
        self.table_grid.setHorizontalSpacing(8)
        self.table_grid.setVerticalSpacing(4)

        # Controls bottom row
        ctrl = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_del = QPushButton("Delete")
        ctrl.addWidget(self.btn_add)
        ctrl.addStretch(1)
        ctrl.addWidget(self.btn_del)
        v.addLayout(ctrl)

        self.btn_add.clicked.connect(self._bsa_add_item)
        self.btn_del.clicked.connect(self._bsa_delete_selected)

        self._checkbox_by_id = {}

        self._render_bsa_table()
        return page

    def _style_tab_buttons(self):
        self.btn_mp.setStyleSheet(
            "QPushButton{border-radius:13px; padding:6px 12px;"
            f"background:{'#0075c6' if self._bsa_mode=='mp' else '#eeeeee'};"
            f"color:{'white' if self._bsa_mode=='mp' else '#0075c6'}; font:700 13px 'Arial';"
            "}"
        )
        self.btn_ex.setStyleSheet(
            "QPushButton{border-radius:13px; padding:6px 12px;"
            f"background:{'#8e7cc3' if self._bsa_mode=='excl' else '#eeeeee'};"
            f"color:{'white' if self._bsa_mode=='excl' else '#8e7cc3'}; font:700 13px 'Arial';"
            "}"
        )

    def _switch_bsa_mode(self, mode: str):
        self._bsa_mode = mode
        self._style_tab_buttons()
        self._render_bsa_table()

    def _render_bsa_table(self):
        # clear grid
        while self.table_grid.count():
            item = self.table_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._checkbox_by_id.clear()

        if self._bsa_mode == "mp":
            items = bsa_settings.get_all_merchants_with_ids()
            headers = ["", "Root", "Merchant Processor", "C/O", "Address", "City", "State", "ZIP", "Notes"]
            accent = "#0075c6"
        else:
            items = bsa_settings.get_all_exclusions_with_ids()
            headers = ["", "Excluded Entity", "Reason", "Notes"]
            accent = "#8e7cc3"

        # headers
        for c, h in enumerate(headers):
            lab = QLabel(h)
            lab.setStyleSheet(f"color:{accent}; font:700 13px 'Arial';")
            self.table_grid.addWidget(lab, 0, c, alignment=Qt.AlignmentFlag.AlignLeft)

        # rows
        for r, row in enumerate(items, start=1):
            row_id = row[0]
            chk = QCheckBox()
            self._checkbox_by_id[row_id] = chk
            self.table_grid.addWidget(chk, r, 0)

            for ci, value in enumerate(row[1:], start=1):
                lab = QLabel(value or "")
                lab.setStyleSheet("font: 12px 'Arial';")
                lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.table_grid.addWidget(lab, r, ci, alignment=Qt.AlignmentFlag.AlignLeft)

                # make merchant name clickable to edit (2nd column for mp mode)
                if self._bsa_mode == "mp" and ci == 1:
                    lab.setStyleSheet("font: 12px 'Arial'; text-decoration: underline; color:#0075c6;")
                    lab.mousePressEvent = (lambda _e, rid=row_id: self._open_edit_popup(rid))  # noqa

    def _bsa_import(self):
        if self._bsa_mode == "mp":
            path, _ = QFileDialog.getOpenFileName(self, "Import Merchant List", filter="Text Files (*.txt)")
            if path:
                bsa_settings.import_merchants_txt(path)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Import Exclusion List", filter="Text Files (*.txt)")
            if path:
                bsa_settings.import_exclusions_txt(path)
        self._render_bsa_table()

    def _bsa_export(self):
        if self._bsa_mode == "mp":
            path, _ = QFileDialog.getSaveFileName(self, "Export Merchant List", filter="Text Files (*.txt)")
            if path:
                bsa_settings.export_merchants_txt(path)
                QMessageBox.information(self, "Exported", f"Merchant list exported to:\n{path}")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Export Exclusion List", filter="Text Files (*.txt)")
            if path:
                bsa_settings.export_exclusions_txt(path)
                QMessageBox.information(self, "Exported", f"Exclusion list exported to:\n{path}")

    def _open_edit_popup(self, row_id: int):
        data = bsa_settings.get_merchant_by_id(row_id)
        if not data:
            QMessageBox.critical(self, "Error", "Merchant not found!")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit Merchant: {data['name']}")
        dlg.resize(420, 545)
        grid = QGridLayout(dlg)

        fields = ["root", "name", "co", "address", "city", "state", "zip", "notes"]
        edits = {}

        r = 0
        for f in fields[:-1]:
            lab = QLabel(("C/O" if f == "co" else f.capitalize()) + ":")
            grid.addWidget(lab, r, 0)
            e = QLineEdit(data.get(f, "") or "")
            grid.addWidget(e, r, 1)
            edits[f] = e
            r += 1

        grid.addWidget(QLabel("Notes:"), r, 0)
        notes = QTextEdit(data.get("notes") or "")
        grid.addWidget(notes, r, 1)
        r += 1

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        grid.addWidget(buttons, r, 0, 1, 2)

        def save():
            # Ensure correct parameter order for edit_merchant_by_id
            bsa_settings.edit_merchant_by_id(
                row_id,
                edits["root"].text(),
                edits["name"].text(),
                edits["co"].text(),
                edits["address"].text(),
                edits["city"].text(),
                edits["state"].text(),
                edits["zip"].text(),
                notes.toPlainText(),
            )
            dlg.accept()
            self._render_bsa_table()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()

    def _bsa_add_item(self):
        if self._bsa_mode == "mp":
            dlg = QDialog(self)
            dlg.setWindowTitle("Add Merchant Processor")
            dlg.resize(420, 545)
            grid = QGridLayout(dlg)

            labels = ["Root", "MP Name", "C/O", "Address", "City", "State", "ZIP"]
            edits = [QLineEdit() for _ in labels]

            for i, lbl in enumerate(labels):
                edit = edits[i] if i < len(edits) else None
                # do your layout with lbl + edit
                grid.addWidget(QLabel(lbl + ":"), i, 0)
                grid.addWidget(edit, i, 1)

            grid.addWidget(QLabel("Notes:"), len(labels), 0)
            notes = QTextEdit()
            grid.addWidget(notes, len(labels), 1)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            grid.addWidget(buttons, len(labels)+1, 0, 1, 2)

            def save():
                data = [e.text().strip() for e in edits]
                if not data[1]:  # MP Name
                    QMessageBox.warning(self, "Missing Name", "Merchant name is required.")
                    return
                bsa_settings.add_merchant_full(*data, notes.toPlainText().strip())
                dlg.accept()
                self._render_bsa_table()

            buttons.accepted.connect(save)
            buttons.rejected.connect(dlg.reject)
            dlg.exec()
        else:
            dlg = QDialog(self)
            dlg.setWindowTitle("Add Exclusion")
            dlg.resize(400, 310)
            v = QVBoxLayout(dlg)

            ent = QLineEdit()
            rea = QLineEdit()
            nts = QTextEdit()

            def row(lbl, w):
                lab = QLabel(lbl)
                lab.setStyleSheet("font: 13px 'Arial';")
                v.addWidget(lab)
                v.addWidget(w)

            row("Excluded Entity:", ent)
            row("Reason:", rea)
            row("Notes:", nts)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            v.addWidget(buttons)

            def save():
                entity = ent.text().strip()
                if not entity:
                    QMessageBox.warning(self, "Missing Entity", "Excluded entity is required.")
                    return
                bsa_settings.add_exclusion(entity, rea.text().strip(), nts.toPlainText().strip())
                dlg.accept()
                self._render_bsa_table()

            buttons.accepted.connect(save)
            buttons.rejected.connect(dlg.reject)
            dlg.exec()

    def _bsa_delete_selected(self):
        selected = [mid for mid, chk in self._checkbox_by_id.items() if chk.isChecked()]
        if not selected:
            QMessageBox.warning(self, "Delete", "No items selected.")
            return
        if QMessageBox.question(self, "Confirm Delete", f"Delete {len(selected)} selected?") == QMessageBox.StandardButton.Yes:
            if self._bsa_mode == "mp":
                bsa_settings.delete_merchants_by_ids(selected)
            else:
                bsa_settings.delete_exclusions_by_ids(selected)
            self._render_bsa_table()

    # ---- EVG Splitter ----
    def _build_evg_splitter(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignTop)
        v.setContentsMargins(20, 20, 20, 20)

        t = QLabel("EVG Recovery File Splitter")
        t.setStyleSheet("color:#1e9148; font: 700 24px 'Arial';")
        v.addWidget(t)
        v.addWidget(self._subtitle("Drag and drop the EVG Recovery PDF here, or click to browse.", color="#255532"))
        v.addSpacing(6)

        drop = DropArea("Drop files here", accent="#1e9148")
        v.addWidget(drop)

        self.evg_spinner_label = QLabel("")
        self.evg_spinner_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.evg_spinner_label.setStyleSheet("color:#1e9148; font: 700 20px 'Arial';")
        v.addWidget(self.evg_spinner_label)

        spinner = ElipsisSpinner("Splitting")
        spinner.tick.connect(self.evg_spinner_label.setText)
        self._evg_spinner = spinner

        browse = QPushButton("Browse Files")
        browse.setStyleSheet("""
            QPushButton{ background:#1e9148; color:white; font: 700 14px 'Arial';
                         border-radius: 22px; padding:8px 18px; }
            QPushButton:hover{ background:#18843d; }
        """)
        v.addSpacing(6)
        v.addWidget(browse, alignment=Qt.AlignmentFlag.AlignHCenter)

        def on_files(paths: List[str]):
            self._start_evg_split(paths)

        def on_browse():
            paths, _ = QFileDialog.getOpenFileNames(self, "Select EVG Recovery PDF(s)",
                                                    filter="PDF files (*.pdf)")
            if paths:
                self._start_evg_split(paths)

        drop.filesDropped.connect(on_files)
        browse.clicked.connect(on_browse)
        return page

    def _start_evg_split(self, paths: List[str]):
        self._evg_spinner.start()
        def work():
            try:
                import evg_splitter
                # Optional redaction helper
                try:
                    import contract_redactor
                except Exception:
                    contract_redactor = None
                output_root = os.path.join(os.path.expanduser("~"), "Desktop", "RSG Recovery Tools data output")
                os.makedirs(output_root, exist_ok=True)
                for p in paths:
                    save_dir = evg_splitter.split_recovery_pdf(p, output_dir=output_root)
                    # If Mulligan Funding contract detected, auto-redact page 5 sensitive fields
                    if contract_redactor and isinstance(save_dir, str) and os.path.isdir(save_dir):
                        try:
                            for fname in os.listdir(save_dir):
                                if fname.lower().endswith(" contract.pdf"):
                                    cpath = os.path.join(save_dir, fname)
                                    try:
                                        contract_redactor.redact_if_mulligan(cpath, page_number=5)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
            except Exception as e:
                self.evg_error.emit(str(e))
            else:
                self.evg_done.emit()
        threading.Thread(target=work, daemon=True).start()

    # ---------------- Misc ----------------
    def _subtitle(self, text: str, color: str = "#333") -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{color}; font: 16px 'Arial';")
        return lab

    # ---- Public navigation (mirrors your Tk helpers) ----
    def show_page(self, key: str):
        if key == "main_menu":
            self._set_sidebar("main_menu")
            self.stack.setCurrentWidget(self.page_main)
        elif key == "admin":
            self._set_sidebar("admin")
            self.stack.setCurrentWidget(self.page_admin)
        elif key == "collections":
            self._set_sidebar("collections")
            self.stack.setCurrentWidget(self.page_admin)
        elif key == "sales":
            self._set_sidebar("sales")
            self.stack.setCurrentWidget(self.page_admin)
        elif key == "bank_analyzer":
            self._set_sidebar("admin")
            self.stack.setCurrentWidget(self.page_bank)
        elif key == "ai_analyzer":
            self._set_sidebar("admin")
            self.stack.setCurrentWidget(self.page_ai)
        elif key == "bsa_settings":
            self._set_sidebar("admin")
            self.stack.setCurrentWidget(self.page_bsa)
        elif key == "evg_splitter":
            self._set_sidebar("admin")
            self.stack.setCurrentWidget(self.page_evg)

    # ---------------- Worker signal handlers (main thread) ----------------
    def _on_bank_done(self):
        self._bank_spinner.stop()
        try:
            # Show a friendly completion message and where to find results
            try:
                output_path = bank_analyzer.get_desktop_output_folder()
            except Exception:
                output_path = os.path.join(os.path.expanduser('~'), 'Desktop', 'RSG Recovery Tools data output')
            self.bank_spinner_label.setText("Complete!")
            self.bank_progress_label.setText("")
            self._bank_status_timer.start(2200)
            QMessageBox.information(self, "Bank Analysis Complete",
                                    f"Redacted pages and summary saved under:\n{output_path}")
        except Exception:
            pass

    def _on_bank_error(self, msg: str):
        self._bank_spinner.stop()
        QMessageBox.critical(self, "Bank Analyzer Error", msg)

    def _on_ai_done(self):
        self._ai_spinner.stop()
        # Auto-open first result folder if enabled
        try:
            if getattr(self, 'ai_auto_open_checkbox', None) and self.ai_auto_open_checkbox.isChecked():
                if self._ai_expected_outputs:
                    first = self._ai_expected_outputs[0]
                    if first:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(first))
        except Exception:
            pass

        # Also preview the first summary in-app if available
        try:
            if self._ai_expected_summaries:
                first_pdf = self._ai_expected_summaries[0]
                if first_pdf and os.path.exists(first_pdf):
                    self._display_pdf_in_ai_viewer(first_pdf)
        except Exception:
            pass

        # Inform where results were saved and provide Open Folder button
        try:
            if self._ai_expected_outputs:
                self._show_ai_result_dialog(self._ai_expected_outputs)
        except Exception:
            pass

    def _on_ai_error(self, msg: str):
        self._ai_spinner.stop()
        QMessageBox.critical(self, "AI Analysis Error", msg)

    def _on_evg_done(self):
        self._evg_spinner.stop()
        try:
            output_path = os.path.join(os.path.expanduser("~"), "Desktop", "RSG Recovery Tools data output")
            QMessageBox.information(self, "EVG Split Complete",
                                    f"Split files saved under:\n{output_path}")
        except Exception:
            pass

    def _on_evg_error(self, msg: str):
        self._evg_spinner.stop()
        QMessageBox.critical(self, "EVG Splitter Error", msg)

    def _on_bank_progress(self, msg: str):
        self.bank_progress_label.setText(msg)

    def _show_ai_result_dialog(self, paths: List[str]):
        dlg = QDialog(self)
        dlg.setWindowTitle("AI Analysis Complete")
        dlg.resize(520, 180)
        v = QVBoxLayout(dlg)
        lab = QLabel("Summaries saved under:")
        v.addWidget(lab)
        combo = QComboBox()
        for p in paths:
            combo.addItem(p)
        v.addWidget(combo)

        buttons = QDialogButtonBox()
        btn_open = QPushButton("Open Folder")
        btn_preview = QPushButton("Preview Here")
        btn_close = QPushButton("Close")
        buttons.addButton(btn_open, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(btn_preview, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(btn_close, QDialogButtonBox.ButtonRole.RejectRole)
        v.addWidget(buttons)

        def do_open():
            try:
                p = combo.currentText().strip()
                if p:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(p))
            except Exception:
                pass
            # keep dialog open

        def do_preview():
            try:
                p = combo.currentText().strip()
                target = None
                if p in getattr(self, '_ai_dir_to_summary', {}):
                    target = self._ai_dir_to_summary[p]
                if not target:
                    # fallback: find a file ending with ' Summary.pdf'
                    for fname in os.listdir(p):
                        if fname.endswith(' Summary.pdf'):
                            target = os.path.join(p, fname)
                            break
                if target and os.path.exists(target):
                    self._display_pdf_in_ai_viewer(target)
            except Exception:
                pass
            dlg.accept()

        btn_open.clicked.connect(do_open)
        btn_preview.clicked.connect(do_preview)
        btn_close.clicked.connect(dlg.reject)

        dlg.exec()

    def _display_pdf_in_ai_viewer(self, pdf_path: str):
        # Clear current preview
        try:
            while self.ai_preview_layout.count():
                item = self.ai_preview_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        except Exception:
            pass

        info = QLabel(f"Previewing: {pdf_path}")
        info.setStyleSheet("color:#555; font: 12px 'Arial';")
        info.setWordWrap(True)
        self.ai_preview_layout.addWidget(info)

        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            # Reset preview state
            self.ai_preview_images = []
            self.ai_preview_page_labels = []
            self.ai_preview_page_count = len(doc)
            self.ai_preview_current_page = 0
            # Update page controls
            self.ai_page_spin.blockSignals(True)
            self.ai_page_spin.setRange(1, max(1, self.ai_preview_page_count))
            self.ai_page_spin.setValue(1 if self.ai_preview_page_count else 0)
            self.ai_page_spin.blockSignals(False)
            self.ai_page_of_label.setText(f"of {self.ai_preview_page_count}")

            max_pages = 24  # safeguard
            for i, page in enumerate(doc):
                if i >= max_pages:
                    more = QLabel("(Preview truncated)")
                    more.setStyleSheet("color:#888; font: italic 12px 'Arial';")
                    self.ai_preview_layout.addWidget(more)
                    break
                # Render at base DPI; zoom is applied later by scaling
                pix = page.get_pixmap(dpi=144)
                # Create QImage from pixmap bytes
                fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                qimg = img.copy()  # detach from underlying buffer
                self.ai_preview_images.append(qimg)
                lbl = QLabel()
                lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                self.ai_preview_page_labels.append(lbl)
                self.ai_preview_layout.addWidget(lbl)
            doc.close()
            # Apply initial zoom to populate pixmaps
            self._ai_set_zoom(1.0)
            # Scroll to the top (first page)
            if self.ai_preview_page_labels:
                try:
                    self.ai_preview_scroll.ensureWidgetVisible(self.ai_preview_page_labels[0])
                except Exception:
                    pass
        except Exception as e_fitz:
            # Fallback to pdf2image if PyMuPDF isn't available or fails
            try:
                from pdf2image import convert_from_path
                # Reuse poppler path helper from bank_analyzer if available
                try:
                    import bank_analyzer as _ba
                    poppler_path = _ba.get_poppler_path()
                except Exception:
                    poppler_path = None

                images = convert_from_path(pdf_path, dpi=144, poppler_path=poppler_path)
                # Reset preview state
                self.ai_preview_images = []
                self.ai_preview_page_labels = []
                self.ai_preview_page_count = len(images)
                self.ai_preview_current_page = 0
                self.ai_page_spin.blockSignals(True)
                self.ai_page_spin.setRange(1, max(1, self.ai_preview_page_count))
                self.ai_page_spin.setValue(1 if self.ai_preview_page_count else 0)
                self.ai_page_spin.blockSignals(False)
                self.ai_page_of_label.setText(f"of {self.ai_preview_page_count}")

                max_pages = 24
                for i, img in enumerate(images):
                    if i >= max_pages:
                        more = QLabel("(Preview truncated)")
                        more.setStyleSheet("color:#888; font: italic 12px 'Arial';")
                        self.ai_preview_layout.addWidget(more)
                        break
                    # Convert PIL image to QImage via ImageQt
                    from PIL.ImageQt import ImageQt as _ImageQt
                    qimg = _ImageQt(img).copy()  # ensure it detaches
                    self.ai_preview_images.append(qimg)
                    lbl = QLabel()
                    lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                    self.ai_preview_page_labels.append(lbl)
                    self.ai_preview_layout.addWidget(lbl)
                # Apply initial zoom
                self._ai_set_zoom(1.0)
                if self.ai_preview_page_labels:
                    try:
                        self.ai_preview_scroll.ensureWidgetVisible(self.ai_preview_page_labels[0])
                    except Exception:
                        pass
            except Exception as e_p2i:
                # Show detailed error to help diagnose
                err = QLabel("Unable to render PDF preview.\n" + str(e_fitz) + "\n" + str(e_p2i))
                err.setStyleSheet("color:#c00; font: 12px 'Arial';")
                err.setWordWrap(True)
                self.ai_preview_layout.addWidget(err)

    def _ai_set_zoom(self, zoom: float):
        # Clamp zoom between 50% and 300%
        try:
            z = max(0.5, min(3.0, zoom))
            self.ai_zoom = z
            self.ai_zoom_label.setText(f"{int(round(self.ai_zoom*100))}%")
            if not self.ai_preview_images or not self.ai_preview_page_labels:
                return
            for img, lbl in zip(self.ai_preview_images, self.ai_preview_page_labels):
                w = int(img.width() * self.ai_zoom)
                h = int(img.height() * self.ai_zoom)
                if w <= 0 or h <= 0:
                    w, h = 1, 1
                pm = QPixmap.fromImage(img).scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                lbl.setPixmap(pm)
        except Exception:
            pass

    def _goto_ai_page(self, one_based_index: int):
        try:
            if self.ai_preview_page_count <= 0:
                return
            idx = one_based_index - 1
            idx = max(0, min(self.ai_preview_page_count - 1, idx))
            self.ai_preview_current_page = idx
            # sync spin without recursion if needed
            if self.ai_page_spin.value() != idx + 1:
                self.ai_page_spin.blockSignals(True)
                self.ai_page_spin.setValue(idx + 1)
                self.ai_page_spin.blockSignals(False)
            # scroll to label
            lbl = self.ai_preview_page_labels[idx]
            self.ai_preview_scroll.ensureWidgetVisible(lbl, 0, 0)
        except Exception:
            pass


def main():
    # Headless guard similar to your Tk code
    HEADLESS = os.getenv("HEADLESS_TEST") == "1" or (os.getenv("CI") and not os.getenv("DISPLAY"))
    if HEADLESS:
        # no-op mode to let tests import the module
        return

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
