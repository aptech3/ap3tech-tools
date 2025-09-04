import os
import threading
import time
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk
from customtkinter import CTkImage
from PIL import Image
from tkinterdnd2 import DND_FILES, TkinterDnD

import bank_analyzer
import bsa_settings

APP_NAME = "RSG Recovery Tools"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

app = TkinterDnD.Tk()
app.title(APP_NAME)
app.geometry("1000x650")
app.resizable(False, False)

# --- Modal Popup Tracker ---
current_popup = {"window": None}


def write_env_key(name: str, value: str):
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

# --- Sidebar (Left) ---
# Widen sidebar so longer button labels fit
sidebar = ctk.CTkFrame(app, width=300, fg_color="#f2f6fa", corner_radius=0)
sidebar.pack(side="left", fill="y")

# --- Main Content Area (Right) ---
content = ctk.CTkFrame(app, fg_color="white", corner_radius=12)
content.pack(side="left", fill="both", expand=True)


def resize_keep_aspect(img, max_size):
    w, h = img.size
    if w > h:
        new_w = max_size
        new_h = int(h * max_size / w)
    else:
        new_h = max_size
        new_w = int(w * max_size / h)
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def set_sidebar(mode):
    for widget in sidebar.winfo_children():
        widget.destroy()
    if mode == "main_menu":
        return
    # --- Admin sidebar buttons ---
    main_menu_btn = ctk.CTkButton(
        sidebar,
        text="Main Menu",
        command=show_main_menu,
        fg_color="#0075c6",
        hover_color="#005a98",
        text_color="white",
        font=("Arial", 12, "bold"),
        corner_radius=20,
        height=32,
        width=120,
    )
    main_menu_btn.pack(pady=(25, 12), padx=18, anchor="nw")

    label = {"admin": "Admin", "collections": "Collections", "sales": "Sales"}.get(
        mode, ""
    )
    ctk.CTkLabel(
        sidebar,
        text=label,
        font=("Arial", 18, "bold"),
        text_color="#0075c6",
        fg_color="#f2f6fa",
        bg_color="#f2f6fa",
    ).pack(pady=(16, 4), padx=18, anchor="nw")

    if mode == "admin":
        for text, cmd in [
            ("EVG Recovery File Splitter", show_evg_splitter),
            ("Bank Statement Analyzer", show_bank_analyzer),
            ("AI Statement Analysis", show_ai_analyzer),
            ("BSA Settings", show_bsa_settings),
        ]:
            ctk.CTkButton(
                sidebar,
                text=text,
                command=cmd,
                fg_color="#0075c6",
                hover_color="#005a98",
                text_color="white",
                font=("Arial", 14, "bold"),
                corner_radius=20,
                height=38,
                width=260,
            ).pack(pady=6, padx=18, anchor="nw")


def set_content(mode):
    for widget in content.winfo_children():
        widget.destroy()

    # Track which BSA Settings tab is selected ("mp" or "excl")
    if not hasattr(set_content, "bsa_settings_list_mode"):
        set_content.bsa_settings_list_mode = "mp"
    list_mode = set_content.bsa_settings_list_mode

    if mode == "main_menu":
        try:
            logo_image = Image.open("logo.png")
            logo_image = resize_keep_aspect(logo_image, 260)
            logo = CTkImage(light_image=logo_image, size=logo_image.size)
            ctk.CTkLabel(
                content, image=logo, text="", fg_color="white", bg_color="white"
            ).pack(pady=(50, 30))
        except Exception:
            ctk.CTkLabel(
                content,
                text="LOGO",
                font=("Arial", 36),
                text_color="#0075c6",
                fg_color="white",
                bg_color="white",
            ).pack(pady=(50, 30))

        ctk.CTkLabel(
            content,
            text=APP_NAME,
            font=("Arial", 28, "bold"),
            text_color="#0075c6",
            fg_color="white",
            bg_color="white",
        ).pack(pady=(0, 40))

        for text, cmd in [
            ("Collections", show_collections),
            ("Sales", show_sales),
            ("Admin", show_admin),
        ]:
            ctk.CTkButton(
                content,
                text=text,
                command=cmd,
                fg_color="#0075c6",
                hover_color="#005a98",
                text_color="white",
                font=("Arial", 16, "bold"),
                corner_radius=30,
                height=44,
                width=320,
            ).pack(pady=15)

    elif mode == "admin":
        ctk.CTkLabel(
            content,
            text="Please select an admin tool from the menu on the left.",
            font=("Arial", 20, "italic"),
            text_color="#0075c6",
            fg_color="white",
            bg_color="white",
        ).place(relx=0.5, rely=0.2, anchor="center")

    elif mode == "bank_analyzer":
        ctk.CTkLabel(
            content,
            text="Bank Statement Analyzer",
            font=("Arial", 24, "bold"),
            text_color="#0075c6",
        ).pack(pady=(35, 12))
        ctk.CTkLabel(
            content,
            text="Drag and drop PDF bank statements here, or click to browse.",
            font=("Arial", 16),
            text_color="#333",
        ).pack(pady=(0, 25))

        drop_frame = ctk.CTkFrame(
            content, width=400, height=120, fg_color="#e8f0fa", corner_radius=16
        )
        drop_frame.pack(pady=12)
        drop_frame.pack_propagate(False)
        ctk.CTkLabel(
            drop_frame,
            text="Drop files here",
            font=("Arial", 14, "italic"),
            text_color="#0075c6",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # --- JUMPING LETTERS ANIMATION ---
        canvas_height = 42
        canvas_width = 250
        jumping_canvas = ctk.CTkCanvas(
            content,
            width=canvas_width,
            height=canvas_height,
            bg="white",
            highlightthickness=0,
        )
        jumping_text = "Thinking"
        jumping_canvas.pack_forget()

        selected_label = ctk.CTkLabel(
            content, text="", font=("Arial", 12), text_color="#444", fg_color="white"
        )
        selected_label.pack(pady=5)

        thinking_event = threading.Event()

        def draw_jumping_letters(idx=0):
            if not jumping_canvas.winfo_exists():
                return
            jumping_canvas.delete("all")
            base_y = 25
            jump_height = 12
            font_size = 26
            font = ("Arial", font_size, "bold")
            spacing = 0
            char_widths = []
            for char in jumping_text:
                char_widths.append(15 if char != " " else 12)
            total_width = sum(char_widths) + spacing * (len(jumping_text) - 1)
            start_x = (canvas_width - total_width) // 2 + 5
            x = start_x
            for i, char in enumerate(jumping_text):
                y = base_y - jump_height if i == idx else base_y
                jumping_canvas.create_text(x, y, text=char, fill="#0075c6", font=font)
                x += char_widths[i] + spacing

        def animate_jumping_letters():
            idx = 0
            if not jumping_canvas.winfo_exists():
                return
            jumping_canvas.pack(pady=(8, 12))
            try:
                while not thinking_event.is_set():
                    if not jumping_canvas.winfo_exists():
                        return
                    draw_jumping_letters(idx)
                    idx = (idx + 1) % len(jumping_text)
                    time.sleep(0.13)
            finally:
                if jumping_canvas.winfo_exists():
                    jumping_canvas.delete("all")
                    jumping_canvas.pack_forget()

        # --- END JUMPING LETTERS ANIMATION ---

        def run_bank_analyzer(filepaths):
            try:
                bank_analyzer.process_bank_statements_full(filepaths, content)
            finally:
                thinking_event.set()

        def on_drop(event):
            filepaths = app.tk.splitlist(event.data)
            selected_label.configure(text="")
            thinking_event.clear()
            threading.Thread(target=animate_jumping_letters, daemon=True).start()
            threading.Thread(
                target=run_bank_analyzer, args=(filepaths,), daemon=True
            ).start()

        drop_frame.drop_target_register(DND_FILES)
        drop_frame.dnd_bind("<<Drop>>", on_drop)

        def browse_files():
            filepaths = filedialog.askopenfilenames(
                title="Select Bank Statement PDFs", filetypes=[("PDF files", "*.pdf")]
            )
            if filepaths:
                selected_label.configure(text="")
                thinking_event.clear()
                threading.Thread(target=animate_jumping_letters, daemon=True).start()
                threading.Thread(
                    target=run_bank_analyzer, args=(filepaths,), daemon=True
                ).start()

        ctk.CTkButton(
            content,
            text="Browse Files",
            command=browse_files,
            fg_color="#0075c6",
            hover_color="#005a98",
            text_color="white",
            font=("Arial", 14, "bold"),
            corner_radius=22,
            width=180,
        ).pack(pady=18)

    elif mode == "ai_analyzer":
        ctk.CTkLabel(
            content,
            text="AI Statement Analysis",
            font=("Arial", 24, "bold"),
            text_color="#ba0075",
        ).pack(pady=(35, 12))
        ctk.CTkLabel(
            content,
            text="Analyze bank statements using AI (OpenAI charges apply).",
            font=("Arial", 16),
            text_color="#ba0075",
        ).pack(pady=(0, 25))

        drop_frame = ctk.CTkFrame(
            content, width=400, height=120, fg_color="#ffe8fa", corner_radius=16
        )
        drop_frame.pack(pady=12)
        drop_frame.pack_propagate(False)
        ctk.CTkLabel(
            drop_frame,
            text="Drop files here",
            font=("Arial", 14, "italic"),
            text_color="#ba0075",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # --- JUMPING LETTERS ANIMATION ---
        canvas_height = 42
        canvas_width = 250
        jumping_canvas = ctk.CTkCanvas(
            content,
            width=canvas_width,
            height=canvas_height,
            bg="white",
            highlightthickness=0,
        )
        jumping_text = "Analyzing"
        jumping_canvas.pack_forget()

        selected_label = ctk.CTkLabel(
            content, text="", font=("Arial", 12), text_color="#444", fg_color="white"
        )
        selected_label.pack(pady=5)

        thinking_event = threading.Event()

        def draw_jumping_letters(idx=0):
            if not jumping_canvas.winfo_exists():
                return
            jumping_canvas.delete("all")
            base_y = 25
            jump_height = 12
            font_size = 26
            font = ("Arial", font_size, "bold")
            spacing = 0
            char_widths = []
            for char in jumping_text:
                char_widths.append(15 if char != " " else 12)
            total_width = sum(char_widths) + spacing * (len(jumping_text) - 1)
            start_x = (canvas_width - total_width) // 2 + 5
            x = start_x
            for i, char in enumerate(jumping_text):
                y = base_y - jump_height if i == idx else base_y
                jumping_canvas.create_text(x, y, text=char, fill="#ba0075", font=font)
                x += char_widths[i] + spacing

        def animate_jumping_letters():
            idx = 0
            if not jumping_canvas.winfo_exists():
                return
            jumping_canvas.pack(pady=(8, 12))
            try:
                while not thinking_event.is_set():
                    if not jumping_canvas.winfo_exists():
                        return
                    draw_jumping_letters(idx)
                    idx = (idx + 1) % len(jumping_text)
                    time.sleep(0.13)
            finally:
                if jumping_canvas.winfo_exists():
                    jumping_canvas.delete("all")
                    jumping_canvas.pack_forget()

        # --- END JUMPING LETTERS ANIMATION ---

        def run_ai_analyzer(filepaths):
            import os
            from tkinter import messagebox

            # Optional: allow local .env files in dev without changing CI
            try:
                from dotenv import load_dotenv  # safe even if not installed in prod/CI

                load_dotenv()
            except Exception:
                pass

            openai_api_key = os.getenv("OPENAI_API_KEY", "")
            if not openai_api_key:
                try:
                    import config  # optional, ignored by git
                    openai_api_key = getattr(config, "openai_api_key", "")
                except Exception:
                    openai_api_key = ""

            if not openai_api_key:
                # Prompt for key and save to .env
                key = simpledialog.askstring(
                    "OpenAI API Key",
                    "Paste your OpenAI API key:\n(It will be saved to a local .env file)",
                    parent=app,
                    show='*'
                )
                if key:
                    try:
                        write_env_key("OPENAI_API_KEY", key)
                        os.environ["OPENAI_API_KEY"] = key
                        openai_api_key = key
                    except Exception as e:
                        thinking_event.set()
                        messagebox.showerror("Save Error", str(e))
                        return
                else:
                    # Stop the animation and inform the user clearly
                    thinking_event.set()
                    messagebox.showerror(
                        "Missing API Key",
                        "OPENAI_API_KEY is not set.\n\n"
                        "Set it in your environment (or .env for local dev),\n"
                        "or create config.py with openai_api_key='...'.",
                    )
                    return

            try:
                import ai_analysis

                # Process & update the right-hand content panel as it already does
                ai_analysis.process_bank_statements_ai(
                    filepaths, openai_api_key, content
                )
            except Exception as e:
                messagebox.showerror("AI Analysis Error", f"{e}")
            finally:
                thinking_event.set()

        def on_drop(event):
            filepaths = app.tk.splitlist(event.data)
            selected_label.configure(text="")
            thinking_event.clear()
            threading.Thread(target=animate_jumping_letters, daemon=True).start()
            threading.Thread(
                target=run_ai_analyzer, args=(filepaths,), daemon=True
            ).start()

        drop_frame.drop_target_register(DND_FILES)
        drop_frame.dnd_bind("<<Drop>>", on_drop)

        def browse_files():
            filepaths = filedialog.askopenfilenames(
                title="Select Bank Statement PDFs", filetypes=[("PDF files", "*.pdf")]
            )
            if filepaths:
                selected_label.configure(text="")
                thinking_event.clear()
                threading.Thread(target=animate_jumping_letters, daemon=True).start()
                threading.Thread(
                    target=run_ai_analyzer, args=(filepaths,), daemon=True
                ).start()

        ctk.CTkButton(
            content,
            text="Browse Files",
            command=browse_files,
            fg_color="#ba0075",
            hover_color="#7e0059",
            text_color="white",
            font=("Arial", 14, "bold"),
            corner_radius=22,
            width=180,
        ).pack(pady=18)

        # Dedicated button to set/save OpenAI API key
        def set_openai_key():
            key = simpledialog.askstring(
                "OpenAI API Key",
                "Paste your OpenAI API key:\n(It will be saved to a local .env file)",
                parent=app,
                show='*'
            )
            if key:
                try:
                    write_env_key("OPENAI_API_KEY", key)
                    os.environ["OPENAI_API_KEY"] = key
                    messagebox.showinfo("Saved", ".env updated with OPENAI_API_KEY")
                except Exception as e:
                    messagebox.showerror("Save Error", str(e))

        ctk.CTkButton(
            content,
            text="Set/OpenAI Key",
            command=set_openai_key,
            fg_color="#ba0075",
            hover_color="#7e0059",
            text_color="white",
            font=("Arial", 13, "bold"),
            corner_radius=22,
            width=180,
        ).pack(pady=(0, 18))

    elif mode == "bsa_settings":
        ctk.CTkLabel(
            content,
            text="Bank Statement Analyzer Settings",
            font=("Arial", 24, "bold"),
            text_color="#0075c6",
        ).pack(pady=(35, 12))

        # --- Tab Buttons ---
        tab_frame = ctk.CTkFrame(content, fg_color="white", corner_radius=0)
        tab_frame.pack(pady=(8, 2))
        mp_btn = ctk.CTkButton(
            tab_frame,
            text="Merchant Processor List",
            command=lambda: (
                setattr(set_content, "bsa_settings_list_mode", "mp"),
                set_content("bsa_settings"),
            ),
            fg_color="#0075c6" if list_mode == "mp" else "#eee",
            text_color="white" if list_mode == "mp" else "#0075c6",
            font=("Arial", 13, "bold"),
            corner_radius=13,
            width=200,
        )
        excl_btn = ctk.CTkButton(
            tab_frame,
            text="Exclusion List",
            command=lambda: (
                setattr(set_content, "bsa_settings_list_mode", "excl"),
                set_content("bsa_settings"),
            ),
            fg_color="#8e7cc3" if list_mode == "excl" else "#eee",
            text_color="white" if list_mode == "excl" else "#8e7cc3",
            font=("Arial", 13, "bold"),
            corner_radius=13,
            width=200,
        )
        mp_btn.pack(side="left", padx=5)
        excl_btn.pack(side="left", padx=5)

        # --- Import/Export Buttons ---
        btn_frame = ctk.CTkFrame(content, fg_color="white", corner_radius=0)
        btn_frame.pack(pady=4)
        if list_mode == "mp":

            def do_export():
                path = filedialog.asksaveasfilename(
                    title="Export Merchant List",
                    defaultextension=".txt",
                    filetypes=[("Text Files", "*.txt")],
                )
                if path:
                    bsa_settings.export_merchants_txt(path)
                    messagebox.showinfo(
                        "Exported!", f"Merchant list exported to:\n{path}"
                    )

            # --- inside set_content() where list_mode == "mp" ---
            def do_import():
                path = filedialog.askopenfilename(
                    title="Import Merchant List", filetypes=[("Text Files", "*.txt")]
                )
                if path:
                    bsa_settings.import_merchants_txt(path)
                    messagebox.showinfo(
                        "Imported!", f"Merchant list imported from:\n{path}"
                    )
                    merchants_now = bsa_settings.get_all_merchants_with_ids()
                    print(
                        f"[DEBUG] After import: {len(merchants_now)} merchant(s) in DB: {merchants_now}"
                    )
                    refresh_table()

            ctk.CTkButton(
                btn_frame,
                text="Import",
                command=do_import,
                fg_color="#0075c6",
                hover_color="#005a98",
                text_color="white",
                font=("Arial", 12, "bold"),
                corner_radius=14,
                height=30,
                width=110,
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                btn_frame,
                text="Export",
                command=do_export,
                fg_color="#0075c6",
                hover_color="#005a98",
                text_color="white",
                font=("Arial", 12, "bold"),
                corner_radius=14,
                height=30,
                width=110,
            ).pack(side="left", padx=4)
        else:

            def do_export():
                path = filedialog.asksaveasfilename(
                    title="Export Exclusion List",
                    defaultextension=".txt",
                    filetypes=[("Text Files", "*.txt")],
                )
                if path:
                    bsa_settings.export_exclusions_txt(path)
                    messagebox.showinfo(
                        "Exported!", f"Exclusion list exported to:\n{path}"
                    )

            def do_import():
                path = filedialog.askopenfilename(
                    title="Import Exclusion List", filetypes=[("Text Files", "*.txt")]
                )
                if path:
                    bsa_settings.import_exclusions_txt(path)
                    messagebox.showinfo(
                        "Imported!", f"Exclusion list imported from:\n{path}"
                    )
                    exclusions_now = bsa_settings.get_all_exclusions_with_ids()
                    print(
                        f"[DEBUG] After import: {len(exclusions_now)} exclusions in DB: {exclusions_now}"
                    )
                    refresh_table()

            ctk.CTkButton(
                btn_frame,
                text="Import",
                command=do_import,
                fg_color="#8e7cc3",
                hover_color="#0f6c2d",
                text_color="white",
                font=("Arial", 12, "bold"),
                corner_radius=14,
                height=30,
                width=110,
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                btn_frame,
                text="Export",
                command=do_export,
                fg_color="#8e7cc3",
                hover_color="#0f6c2d",
                text_color="white",
                font=("Arial", 12, "bold"),
                corner_radius=14,
                height=30,
                width=110,
            ).pack(side="left", padx=4)

        # --- Scrollable Table ---
        table_frame = ctk.CTkFrame(content, fg_color="white", corner_radius=12)
        table_frame.pack(fill="both", expand=True, pady=(10, 0), padx=16)
        canvas = ctk.CTkCanvas(table_frame, bg="white", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        vsb = ctk.CTkScrollbar(
            table_frame, orientation="vertical", command=canvas.yview
        )
        vsb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=vsb.set)
        table_inner = ctk.CTkFrame(canvas, fg_color="white")
        canvas.create_window((0, 0), window=table_inner, anchor="nw")

        set_content.checkbox_vars = {}

        def on_frame_configure(evt):
            canvas.configure(scrollregion=canvas.bbox("all"))

        table_inner.bind("<Configure>", on_frame_configure)

        # --- Table/CRUD context setup ---
        def refresh_table():
            for w in table_inner.winfo_children():
                w.destroy()
            set_content.checkbox_vars.clear()
            if list_mode == "mp":
                items = bsa_settings.get_all_merchants_with_ids()
                headers = [
                    "",
                    "Root",
                    "Merchant Processor",
                    "C/O",
                    "Address",
                    "City",
                    "State",
                    "ZIP",
                    "Notes",
                ]
                widths = [3, 80, 200, 80, 170, 90, 50, 60, 180]
            else:
                items = bsa_settings.get_all_exclusions_with_ids()
                headers = ["", "Excluded Entity", "Reason", "Notes"]
                widths = [3, 220, 180, 210]

            for col, (h, w) in enumerate(zip(headers, widths, strict=False)):
                ctk.CTkLabel(
                    table_inner,
                    text=h,
                    font=("Arial", 13, "bold"),
                    text_color="#0075c6" if list_mode == "mp" else "#8e7cc3",
                    anchor="w",
                    width=w,
                ).grid(row=0, column=col, sticky="w", padx=(4 if col == 0 else 2, 2))

            for r, row in enumerate(items, start=1):
                var = ctk.BooleanVar()
                set_content.checkbox_vars[row[0]] = var
                ctk.CTkCheckBox(
                    table_inner,
                    variable=var,
                    text="",
                    width=18,
                    fg_color="#0075c6" if list_mode == "mp" else "#8e7cc3",
                ).grid(row=r, column=0, padx=(4, 2), pady=2, sticky="w")
                for ci, val in enumerate(row[1:], start=1):
                    lbl = ctk.CTkLabel(
                        table_inner,
                        text=val or "",
                        anchor="w",
                        width=widths[ci],
                        font=("Arial", 12),
                    )

                    # If this is the Merchant Name column, make it clickable and highlight on hover
                    if list_mode == "mp" and ci == 1:  # Only for Merchant Name

                        def make_edit_handler(
                            row_id=row[0],
                        ):  # Need default arg to avoid late binding
                            def handler(event=None):
                                open_edit_popup(row_id)

                            return handler

                        def on_enter(e, label=lbl):
                            label.configure(bg_color="#e5f2ff")

                        def on_leave(e, label=lbl):
                            label.configure(bg_color="white")

                        lbl.bind("<Button-1>", make_edit_handler())
                        lbl.bind("<Enter>", on_enter)
                        lbl.bind("<Leave>", on_leave)
                        lbl.configure(cursor="hand2")
                    lbl.grid(row=r, column=ci, sticky="w", padx=2, pady=2)

        refresh_table()

        def open_edit_popup(row_id):
            data = bsa_settings.get_merchant_by_id(row_id)
            if not data:
                messagebox.showerror("Error", "Merchant not found!")
                return
            popup = ctk.CTkToplevel(app)
            popup.transient(app)
            popup.grab_set()
            popup.lift()
            popup.focus_force()

            popup_w, popup_h = 420, 545

            app.update_idletasks()
            parent_x = app.winfo_x()
            parent_y = app.winfo_y()
            parent_w = app.winfo_width()
            parent_h = app.winfo_height()

            center_x = parent_x + (parent_w // 2) - (popup_w // 2)
            center_y = parent_y + (parent_h // 2) - (popup_h // 2)
            popup.geometry(f"{popup_w}x{popup_h}+{center_x}+{center_y}")
            popup.title(f"Edit Merchant: {data['name']}")

            fields = ["root", "name", "co", "address", "city", "state", "zip", "notes"]
            vars = {f: ctk.StringVar(value=data.get(f, "")) for f in fields}
            row = 0

            popup.grid_columnconfigure(1, weight=1)

            for f in fields[:-1]:
                display_name = f.capitalize() if f != "co" else "C/O"
                ctk.CTkLabel(popup, text=display_name + ":", font=("Arial", 13)).grid(
                    row=row, column=0, sticky="e", padx=14, pady=6
                )
                ctk.CTkEntry(popup, textvariable=vars[f], width=280).grid(
                    row=row, column=1, padx=8, pady=6, sticky="ew"
                )
                row += 1

            ctk.CTkLabel(popup, text="Notes:", font=("Arial", 13)).grid(
                row=row, column=0, sticky="ne", padx=14, pady=6
            )
            notes_box = ctk.CTkTextbox(popup, width=280, height=64)
            notes_box.insert("1.0", data["notes"] or "")
            notes_box.grid(row=row, column=1, padx=8, pady=6, sticky="nsew")

            # Let notes box expand if window resizes
            popup.grid_rowconfigure(row, weight=1)
            row += 1

            def save_changes():
                bsa_settings.edit_merchant_by_id(
                    row_id, data.get("root", ""), *[vars[f].get() for f in fields]
                )
                popup.destroy()
                refresh_table()

            btnf = ctk.CTkFrame(popup, fg_color="white", corner_radius=0)
            btnf.grid(row=row, column=0, columnspan=2, pady=(0, 20))
            ctk.CTkButton(
                btnf, text="Save", command=save_changes, fg_color="#0075c6", width=90
            ).pack(side="left", padx=8)
            ctk.CTkButton(
                btnf, text="Cancel", command=popup.destroy, fg_color="#bbb", width=90
            ).pack(side="left", padx=8)

        # --- Add/Edit Popups (unchanged, but call correct CRUD for each tab) ---
        def add_item_popup():
            if current_popup["window"] and current_popup["window"].winfo_exists():
                current_popup["window"].lift()
                current_popup["window"].focus_force()
                return
            popup = ctk.CTkToplevel(app)
            popup.transient(app)
            popup.grab_set()
            popup.lift()
            popup.focus_force()

            popup_w, popup_h = 420, 545

            app.update_idletasks()
            parent_x = app.winfo_x()
            parent_y = app.winfo_y()
            parent_w = app.winfo_width()
            parent_h = app.winfo_height()

            center_x = parent_x + (parent_w // 2) - (popup_w // 2)
            center_y = parent_y + (parent_h // 2) - (popup_h // 2)
            popup.geometry(f"{popup_w}x{popup_h}+{center_x}+{center_y}")
            current_popup["window"] = popup

            popup.grid_columnconfigure(1, weight=1)

            if set_content.bsa_settings_list_mode == "mp":
                popup.title("Add Merchant Processor")
                labels = ["Root", "MP Name", "C/O", "Address", "City", "State", "ZIP"]
                vars = [ctk.StringVar() for _ in labels]

                # --- Layout fields ---
                for i, (lbl, var) in enumerate(zip(labels, vars, strict=False)):
                    pretty_lbl = lbl if lbl != "C/O" else "C/O"
                    ctk.CTkLabel(popup, text=pretty_lbl + ":", font=("Arial", 13)).grid(
                        row=i, column=0, sticky="e", padx=14, pady=6
                    )
                    ctk.CTkEntry(popup, textvariable=var, width=280).grid(
                        row=i, column=1, padx=8, pady=6, sticky="ew"
                    )

                # Notes (multiline) field
                notes_row = len(labels)
                ctk.CTkLabel(popup, text="Notes:", font=("Arial", 13)).grid(
                    row=notes_row, column=0, sticky="ne", padx=14, pady=6
                )
                notes_box = ctk.CTkTextbox(popup, width=280, height=64)
                notes_box.grid(row=notes_row, column=1, padx=8, pady=6, sticky="nsew")

                # Let notes box expand
                popup.grid_rowconfigure(notes_row, weight=1)

                # Save/Cancel buttons
                btn_row = notes_row + 1
                btnf = ctk.CTkFrame(popup, fg_color="white", corner_radius=0)
                btnf.grid(row=btn_row, column=0, columnspan=2, pady=(0, 20))
                ctk.CTkButton(
                    btnf,
                    text="Save",
                    command=lambda: add_and_close(),
                    fg_color="#0075c6",
                    width=90,
                ).pack(side="left", padx=8)
                ctk.CTkButton(
                    btnf,
                    text="Cancel",
                    command=popup.destroy,
                    fg_color="#bbb",
                    width=90,
                ).pack(side="left", padx=8)

                def add_and_close():
                    data = [v.get().strip() for v in vars]
                    if not data[0]:
                        messagebox.showwarning(
                            "Missing Name", "Merchant name is required."
                        )
                        return
                    notes = notes_box.get("1.0", "end-1c").strip()
                    bsa_settings.add_merchant_full(*data, notes)
                    popup.destroy()
                    current_popup["window"] = None
                    refresh_table()

            else:
                # (Keep your exclusion popup code the same as before)
                popup.title("Add Exclusion")
                popup.geometry("400x310")
                entity_var = ctk.StringVar()
                reason_var = ctk.StringVar()
                ctk.CTkLabel(popup, text="Excluded Entity:", font=("Arial", 13)).pack(
                    pady=(10, 2), anchor="w", padx=18
                )
                ctk.CTkEntry(popup, textvariable=entity_var, width=320).pack(
                    pady=2, padx=18
                )
                ctk.CTkLabel(popup, text="Reason:", font=("Arial", 13)).pack(
                    pady=(6, 2), anchor="w", padx=18
                )
                ctk.CTkEntry(popup, textvariable=reason_var, width=320).pack(
                    pady=2, padx=18
                )
                ctk.CTkLabel(popup, text="Notes:", font=("Arial", 13)).pack(
                    pady=2, anchor="w", padx=18
                )
                notes_box = ctk.CTkTextbox(popup, width=320, height=48)
                notes_box.pack(pady=2, padx=18)

                def add_and_close():
                    entity = entity_var.get().strip()
                    reason = reason_var.get().strip()
                    notes = notes_box.get("1.0", "end-1c").strip()
                    if not entity:
                        messagebox.showwarning(
                            "Missing Entity", "Excluded entity is required."
                        )
                        return
                    bsa_settings.add_exclusion(entity, reason, notes)
                    popup.destroy()
                    current_popup["window"] = None
                    refresh_table()

                btnf = ctk.CTkFrame(popup, fg_color="white", corner_radius=0)
                btnf.pack(pady=14)
                ctk.CTkButton(
                    btnf,
                    text="Save",
                    command=add_and_close,
                    fg_color="#8e7cc3",
                    hover_color="#0f6c2d",
                    width=80,
                ).pack(side="left", padx=8)
                ctk.CTkButton(
                    btnf,
                    text="Cancel",
                    command=popup.destroy,
                    fg_color="#bbb",
                    width=80,
                ).pack(side="left", padx=8)

            popup.protocol(
                "WM_DELETE_WINDOW",
                lambda: (
                    popup.grab_release(),
                    current_popup.__setitem__("window", None),
                    popup.destroy(),
                ),
            )

        def delete_items_selected():
            to_delete = [
                mid for mid, var in set_content.checkbox_vars.items() if var.get()
            ]
            if not to_delete:
                messagebox.showwarning("Delete", "No items selected.")
                return
            msg = f"Delete {len(to_delete)} selected?"
            if messagebox.askyesno("Confirm Delete", msg):
                if list_mode == "mp":
                    bsa_settings.delete_merchants_by_ids(to_delete)
                else:
                    bsa_settings.delete_exclusions_by_ids(to_delete)
                refresh_table()

        # --- Add/Delete buttons ---
        ctrl = ctk.CTkFrame(content, fg_color="white", corner_radius=0)
        ctrl.pack(fill="x", pady=(8, 16))
        ctk.CTkButton(
            ctrl,
            text="Add",
            command=add_item_popup,
            fg_color="#0075c6" if list_mode == "mp" else "#8e7cc3",
            hover_color="#005a98" if list_mode == "mp" else "#0f6c2d",
            width=90,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            ctrl,
            text="Delete",
            command=delete_items_selected,
            fg_color="#e74c3c",
            hover_color="#c0392b",
            width=90,
        ).pack(side="right", padx=6)

        ctk.CTkLabel(
            content,
            text="• Click a merchant name to edit all fields. Use checkboxes and Delete to remove. Add to create new.",
            font=("Arial", 12),
            text_color="#666",
        ).pack(pady=(8, 10))

    elif mode == "evg_splitter":
        ctk.CTkLabel(
            content,
            text="EVG Recovery File Splitter",
            font=("Arial", 24, "bold"),
            text_color="#1e9148",
        ).pack(pady=(35, 12))
        ctk.CTkLabel(
            content,
            text="Drag and drop the EVG Recovery PDF here, or click to browse.",
            font=("Arial", 16),
            text_color="#255532",
        ).pack(pady=(0, 25))

        drop_frame = ctk.CTkFrame(
            content, width=400, height=120, fg_color="#e8faec", corner_radius=16
        )
        drop_frame.pack(pady=12)
        drop_frame.pack_propagate(False)
        ctk.CTkLabel(
            drop_frame,
            text="Drop files here",
            font=("Arial", 14, "italic"),
            text_color="#1e9148",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # --- JUMPING LETTERS ANIMATION (green) ---
        canvas_height = 42
        canvas_width = 250
        jumping_canvas = ctk.CTkCanvas(
            content,
            width=canvas_width,
            height=canvas_height,
            bg="white",
            highlightthickness=0,
        )
        jumping_text = "Splitting"
        jumping_canvas.pack_forget()

        selected_label = ctk.CTkLabel(
            content, text="", font=("Arial", 12), text_color="#444", fg_color="white"
        )
        selected_label.pack(pady=5)

        thinking_event = threading.Event()

        def draw_jumping_letters(idx=0):
            if not jumping_canvas.winfo_exists():
                return
            jumping_canvas.delete("all")
            base_y = 25
            jump_height = 12
            font_size = 26
            font = ("Arial", font_size, "bold")
            spacing = 0
            char_widths = []
            for char in jumping_text:
                char_widths.append(15 if char != " " else 12)
            total_width = sum(char_widths) + spacing * (len(jumping_text) - 1)
            start_x = (canvas_width - total_width) // 2 + 5
            x = start_x
            for i, char in enumerate(jumping_text):
                y = base_y - jump_height if i == idx else base_y
                jumping_canvas.create_text(x, y, text=char, fill="#1e9148", font=font)
                x += char_widths[i] + spacing

        def animate_jumping_letters():
            idx = 0
            if not jumping_canvas.winfo_exists():
                return
            jumping_canvas.pack(pady=(8, 12))
            try:
                while not thinking_event.is_set():
                    if not jumping_canvas.winfo_exists():
                        return
                    draw_jumping_letters(idx)
                    idx = (idx + 1) % len(jumping_text)
                    time.sleep(0.13)
            finally:
                if jumping_canvas.winfo_exists():
                    jumping_canvas.delete("all")
                    jumping_canvas.pack_forget()

        # --- END JUMPING LETTERS ANIMATION ---

        def run_evg_splitter(filepaths):
            try:
                import evg_splitter
                # Redaction helper (optional)
                try:
                    import contract_redactor
                except Exception:
                    contract_redactor = None

                output_root = os.path.join(
                    os.path.expanduser("~"), "Desktop", "RSG Recovery Tools data output"
                )
                os.makedirs(output_root, exist_ok=True)
                for file in filepaths:
                    save_dir = evg_splitter.split_recovery_pdf(file, output_dir=output_root)
                    # If Mulligan Funding contract detected, auto-redact page 5 sensitive fields
                    if contract_redactor and isinstance(save_dir, str) and os.path.isdir(save_dir):
                        try:
                            for fname in os.listdir(save_dir):
                                if fname.lower().endswith(" contract.pdf"):
                                    cpath = os.path.join(save_dir, fname)
                                    # Redact only if it's a Mulligan Funding contract
                                    try:
                                        contract_redactor.redact_if_mulligan(cpath, page_number=5)
                                    except Exception:
                                        # continue processing others; errors surface via general flow
                                        pass
                        except Exception:
                            pass
            finally:
                thinking_event.set()

        def on_drop(event):
            filepaths = app.tk.splitlist(event.data)
            filepaths = [p for p in filepaths if str(p).lower().endswith('.pdf')]
            if not filepaths:
                messagebox.showwarning("Invalid Drop", "Please drop one or more PDF files.")
                return
            selected_label.configure(text=f"{len(filepaths)} file(s) queued…")
            thinking_event.clear()
            threading.Thread(target=animate_jumping_letters, daemon=True).start()
            threading.Thread(
                target=run_evg_splitter, args=(filepaths,), daemon=True
            ).start()
            def notify_when_done():
                if thinking_event.is_set():
                    try:
                        output_root = os.path.join(os.path.expanduser("~"), "Desktop", "RSG Recovery Tools data output")
                        messagebox.showinfo("EVG Split Complete", f"Split files saved under:\n{output_root}")
                    except Exception:
                        pass
                else:
                    content.after(250, notify_when_done)
            content.after(250, notify_when_done)

        drop_frame.drop_target_register(DND_FILES)
        drop_frame.dnd_bind("<<Drop>>", on_drop)

        def browse_files():
            filepaths = filedialog.askopenfilenames(
                title="Select EVG Recovery PDF(s)", filetypes=[("PDF files", "*.pdf")]
            )
            if filepaths:
                filepaths = [p for p in filepaths if str(p).lower().endswith('.pdf')]
                if not filepaths:
                    messagebox.showwarning("Browse Files", "No PDF files selected.")
                    return
                selected_label.configure(text=f"{len(filepaths)} file(s) queued…")
                thinking_event.clear()
                threading.Thread(target=animate_jumping_letters, daemon=True).start()
                threading.Thread(
                    target=run_evg_splitter, args=(filepaths,), daemon=True
                ).start()
                def notify_when_done():
                    if thinking_event.is_set():
                        try:
                            output_root = os.path.join(os.path.expanduser("~"), "Desktop", "RSG Recovery Tools data output")
                            messagebox.showinfo("EVG Split Complete", f"Split files saved under:\n{output_root}")
                        except Exception:
                            pass
                    else:
                        content.after(250, notify_when_done)
                content.after(250, notify_when_done)

        ctk.CTkButton(
            content,
            text="Browse Files",
            command=browse_files,
            fg_color="#1e9148",
            hover_color="#18843d",
            text_color="white",
            font=("Arial", 14, "bold"),
            corner_radius=22,
            width=180,
        ).pack(pady=18)


# --- Navigation helper functions ---
def show_main_menu():
    set_sidebar("main_menu")
    set_content("main_menu")


def show_admin():
    set_sidebar("admin")
    set_content("admin")


def show_collections():
    set_sidebar("collections")
    set_content("collections")


def show_sales():
    set_sidebar("sales")
    set_content("sales")


def show_bank_analyzer():
    set_sidebar("admin")
    set_content("bank_analyzer")


def show_ai_analyzer():
    set_sidebar("admin")
    set_content("ai_analyzer")


def show_bsa_settings():
    set_sidebar("admin")
    set_content("bsa_settings")


def show_evg_splitter():
    set_sidebar("admin")
    set_content("evg_splitter")


show_main_menu()

# --- Exit Button ---
exit_btn = ctk.CTkButton(
    app,
    text="Exit",
    command=app.destroy,
    fg_color="#0075c6",
    hover_color="#005a98",
    text_color="white",
    font=("Arial", 10, "bold"),
    corner_radius=20,
    height=28,
    width=90,
)
exit_btn.place(relx=0.98, rely=0.98, anchor="se")

HEADLESS = os.getenv("HEADLESS_TEST") == "1" or (
    os.getenv("CI") and not os.getenv("DISPLAY")
)
if not HEADLESS:
    # create Tk and run your GUI
    ...
    app.mainloop()
else:
    # optionally expose no-op functions for tests
    def show_ai_analyzer():
        return None
