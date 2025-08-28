# main_app_pyqt.py
import os
import sys
import time
import threading
from typing import List

from PIL import Image

# Qt imports
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QStackedWidget, QFrame, QScrollArea,
    QCheckBox, QLineEdit, QTextEdit, QGridLayout, QDialog, QDialogButtonBox
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
    """Load image (logo) and keep aspect ratio similar to your Tk version."""
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
        qimg = img.toqimage() if hasattr(img, "toqimage") else None  # pillow-simd guard
        if qimg is None:
            # Fallback route
            tmp_path = os.path.join(os.path.dirname(__file__), "_logo_tmp.png")
            img.save(tmp_path)
            pm = QPixmap(tmp_path)
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return pm
        return QPixmap.fromImage(qimg)
    except Exception:
        return QPixmap()


class DropArea(QFrame):
    """Reusable drag-and-drop frame that emits a signal with file paths."""
    filesDropped = pyqtSignal(list)

    def __init__(self, label_text: str, accent: str = "#0075c6", parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(0,0,0,0);
                border: 2px dashed {accent};
                border-radius: 12px;
                min-height: 120px;
            }}
        """)
        lay = QVBoxLayout(self)
        self.lbl = QLabel(label_text)
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet(f"color:{accent}; font: 14px 'Arial'; font-style: italic;")
        lay.addWidget(self.lbl)

    def dragEnterEvent(self, e: QDragEnterEvent):
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1000, 650)

        # Root container
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
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
                        background:#e9f2fb; color:#000; font: 700 14px 'Arial';
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

        def on_files(paths: List[str]):
            self._start_bank_analysis(paths)

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
                # content widget not used in Qt; bank_analyzer should be adapted to accept callbacks if needed
                bank_analyzer.process_bank_statements_full(paths, None)
            finally:
                self._bank_spinner.stop()
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
            QMessageBox.critical(self, "Missing API Key",
                                 "OPENAI_API_KEY is not set.\n\n"
                                 "Set it in your environment (or a .env file).")
            return

        self._ai_spinner.start()
        def work():
            try:
                import ai_analysis
                # Update: ai_analysis should not manipulate Qt widgets directly unless it uses signals.
                ai_analysis.process_bank_statements_ai(paths, api_key, None)
            except Exception as e:
                QMessageBox.critical(self, "AI Analysis Error", str(e))
            finally:
                self._ai_spinner.stop()
        threading.Thread(target=work, daemon=True).start()

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
            f"color:{'white' if self._bsa_mode=='mp' else '#0075c6'}; font:700 13px 'Arial';}}"
        )
        self.btn_ex.setStyleSheet(
            "QPushButton{border-radius:13px; padding:6px 12px;"
            f"background:{'#8e7cc3' if self._bsa_mode=='excl' else '#eeeeee'};"
            f"color:{'white' if self._bsa_mode=='excl' else '#8e7cc3'}; font:700 13px 'Arial';}}"
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
            bsa_settings.edit_merchant_by_id(
                row_id,
                data.get("root", ""),
                *(edits[f].text() for f in fields[:-1]),
                notes.toPlainText()
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
                output_root = os.path.join(os.path.expanduser("~"), "Desktop", "RSG Recovery Tools data output")
                os.makedirs(output_root, exist_ok=True)
                for p in paths:
                    evg_splitter.split_recovery_pdf(p, output_dir=output_root)
            finally:
                self._evg_spinner.stop()
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