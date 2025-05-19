import customtkinter as ctk
from PIL import Image
from customtkinter import CTkImage
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import bank_analyzer
import bsa_settings
import threading
import time

APP_NAME = "RSG Recovery Tools"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

app = TkinterDnD.Tk()
app.title(APP_NAME)
app.geometry("1000x650")
app.resizable(False, False)

# --- Modal Popup Tracker ---
current_popup = {"window": None}

# --- Sidebar (Left) ---
sidebar = ctk.CTkFrame(app, width=220, fg_color="#f2f6fa", corner_radius=0)
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
        sidebar, text="Main Menu", command=show_main_menu,
        fg_color="#0075c6", hover_color="#005a98",
        text_color="white", font=("Arial", 12, "bold"),
        corner_radius=20, height=32, width=120
    )
    main_menu_btn.pack(pady=(25, 12), padx=18, anchor="nw")

    label = {"admin":"Admin", "collections":"Collections", "sales":"Sales"}.get(mode, "")
    ctk.CTkLabel(
        sidebar, text=label, font=("Arial", 18, "bold"),
        text_color="#0075c6", fg_color="#f2f6fa", bg_color="#f2f6fa"
    ).pack(pady=(16, 4), padx=18, anchor="nw")

    if mode == "admin":
        for text, cmd in [
            ("Bank Statement Analyzer", show_bank_analyzer),
            ("BSA Settings", show_bsa_settings)
        ]:
            ctk.CTkButton(
                sidebar, text=text, command=cmd,
                fg_color="#0075c6", hover_color="#005a98",
                text_color="white", font=("Arial", 14, "bold"),
                corner_radius=20, height=38, width=170
            ).pack(pady=6, padx=18, anchor="nw")

def set_content(mode):
    for widget in content.winfo_children():
        widget.destroy()

    if mode == "main_menu":
        try:
            logo_image = Image.open("logo.png")
            logo_image = resize_keep_aspect(logo_image, 260)
            logo = CTkImage(light_image=logo_image, size=logo_image.size)
            ctk.CTkLabel(content, image=logo, text="", fg_color="white", bg_color="white").pack(pady=(50, 30))
        except Exception:
            ctk.CTkLabel(content, text="LOGO", font=("Arial", 36),
                         text_color="#0075c6", fg_color="white", bg_color="white").pack(pady=(50, 30))

        ctk.CTkLabel(content, text=APP_NAME,
                     font=("Arial", 28, "bold"), text_color="#0075c6",
                     fg_color="white", bg_color="white").pack(pady=(0, 40))

        for text, cmd in [("Collections", show_collections),
                          ("Sales", show_sales),
                          ("Admin", show_admin)]:
            ctk.CTkButton(content, text=text, command=cmd,
                          fg_color="#0075c6", hover_color="#005a98",
                          text_color="white", font=("Arial", 16, "bold"),
                          corner_radius=30, height=44, width=320).pack(pady=15)

    elif mode == "admin":
        ctk.CTkLabel(content, text="Please select an admin tool from the menu on the left.",
                     font=("Arial", 20, "italic"), text_color="#0075c6",
                     fg_color="white", bg_color="white").place(relx=0.5, rely=0.2, anchor="center")

    elif mode == "bank_analyzer":
        ctk.CTkLabel(content, text="Bank Statement Analyzer",
                    font=("Arial", 24, "bold"), text_color="#0075c6").pack(pady=(35, 12))
        ctk.CTkLabel(content, text="Drag and drop PDF bank statements here, or click to browse.",
                    font=("Arial", 16), text_color="#333").pack(pady=(0, 25))

        drop_frame = ctk.CTkFrame(content, width=400, height=120, fg_color="#e8f0fa", corner_radius=16)
        drop_frame.pack(pady=12)
        drop_frame.pack_propagate(False)
        ctk.CTkLabel(drop_frame, text="Drop files here", font=("Arial", 14, "italic"), text_color="#0075c6")\
            .place(relx=0.5, rely=0.5, anchor="center")

        # --- Browse Button ---
        ctk.CTkButton(content, text="Browse Files", command=lambda: browse_files(),
                    fg_color="#0075c6", hover_color="#005a98",
                    text_color="white", font=("Arial", 14, "bold"),
                    corner_radius=22, width=180).pack(pady=18)

        # --- Animated Thinking Label (NOW just below Browse Button!) ---
        thinking_label = ctk.CTkLabel(content, text="", font=("Arial", 15, "italic"), text_color="#0075c6")
        thinking_label.pack(pady=(0, 8))

        thinking_event = threading.Event()

        def animate_thinking():
            text = "Thinking"
            i = 0
            while not thinking_event.is_set():
                # Loop a space through the word for animation
                display = text[:i+1] + " " + text[i+1:] if i < len(text) else text
                def update_label(t=display):
                    if thinking_label.winfo_exists():
                        thinking_label.configure(text=t)
                thinking_label.after(0, update_label)
                time.sleep(0.15)
                i = (i + 1) % len(text)
            # Clear label at end
            def clear_label():
                if thinking_label.winfo_exists():
                    thinking_label.configure(text="")
            thinking_label.after(0, clear_label)

        def run_bank_analyzer(filepaths):
            import config
            openai_api_key = config.openai_api_key
            try:
                bank_analyzer.process_bank_statements_full(filepaths, openai_api_key, content)
            finally:
                thinking_event.set()  # Stop animation

        def on_drop(event):
            filepaths = app.tk.splitlist(event.data)
            thinking_label.configure(text="")  # clear label (in case)
            thinking_event.clear()
            threading.Thread(target=animate_thinking, daemon=True).start()
            threading.Thread(target=run_bank_analyzer, args=(filepaths,), daemon=True).start()

        drop_frame.drop_target_register(DND_FILES)
        drop_frame.dnd_bind('<<Drop>>', on_drop)

        def browse_files():
            filepaths = filedialog.askopenfilenames(
                title="Select Bank Statement PDFs",
                filetypes=[("PDF files", "*.pdf")])
            if filepaths:
                thinking_label.configure(text="")  # clear label (in case)
                thinking_event.clear()
                threading.Thread(target=animate_thinking, daemon=True).start()
                threading.Thread(target=run_bank_analyzer, args=(filepaths,), daemon=True).start()

    elif mode == "bsa_settings":
        ctk.CTkLabel(content, text="Bank Statement Analyzer Settings",
                     font=("Arial", 24, "bold"), text_color="#0075c6").pack(pady=(35, 12))

        # ... [NO CHANGES MADE TO THE SETTINGS SECTION] ...
        # Rest of your bsa_settings code goes here (unchanged)
        # [Keep all your table, import/export, edit, and delete code here]

# --- Navigation helper functions ---
def show_main_menu():    set_sidebar("main_menu");    set_content("main_menu")
def show_admin():        set_sidebar("admin");        set_content("admin")
def show_collections():  set_sidebar("collections");  set_content("collections")
def show_sales():        set_sidebar("sales");        set_content("sales")
def show_bank_analyzer():set_sidebar("admin");        set_content("bank_analyzer")
def show_bsa_settings(): set_sidebar("admin");        set_content("bsa_settings")

show_main_menu()

# --- Exit Button ---
exit_btn = ctk.CTkButton(
    app, text="Exit", command=app.destroy,
    fg_color="#0075c6", hover_color="#005a98",
    text_color="white", font=("Arial",10,"bold"),
    corner_radius=20, height=28, width=90
)
exit_btn.place(relx=0.98, rely=0.98, anchor="se")

app.mainloop()
