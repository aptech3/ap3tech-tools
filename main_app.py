import customtkinter as ctk
from PIL import Image
from customtkinter import CTkImage
from tkinter import filedialog, messagebox
import bank_analyzer
import bsa_settings

APP_NAME = "RSG Recovery Tools"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title(APP_NAME)
app.geometry("1000x650")
app.resizable(False, False)
app.configure(fg_color="white")

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

        def browse_files():
            filepaths = filedialog.askopenfilenames(
                title="Select Bank Statement PDFs",
                filetypes=[("PDF files", "*.pdf")])
            if filepaths:
                selected_label.configure(text="\n".join(filepaths))
                bank_analyzer.process_bank_statements(filepaths, content)

        ctk.CTkButton(content, text="Browse Files", command=browse_files,
                      fg_color="#0075c6", hover_color="#005a98",
                      text_color="white", font=("Arial", 14, "bold"),
                      corner_radius=22, width=180).pack(pady=18)

        selected_label = ctk.CTkLabel(content, text="", font=("Arial", 12),
                                      text_color="#444", fg_color="white")
        selected_label.pack(pady=5)

    elif mode == "bsa_settings":
        ctk.CTkLabel(content, text="Bank Statement Analyzer Settings",
                     font=("Arial", 24, "bold"), text_color="#0075c6").pack(pady=(35, 12))

        # Import / Export
        btn_frame = ctk.CTkFrame(content, fg_color="white", corner_radius=0)
        btn_frame.pack(pady=4)
        def do_export(): 
            path = filedialog.asksaveasfilename(title="Export Merchant List",
                                                defaultextension=".txt",
                                                filetypes=[("Text Files", "*.txt")])
            if path:
                bsa_settings.export_merchants_txt(path)
                messagebox.showinfo("Exported!", f"Merchant list exported to:\n{path}")
        def do_import():
            path = filedialog.askopenfilename(title="Import Merchant List",
                                              filetypes=[("Text Files", "*.txt")])
            if path:
                bsa_settings.import_merchants_txt(path)
                messagebox.showinfo("Imported!", f"Merchant list imported from:\n{path}")
                refresh_table()

        ctk.CTkButton(btn_frame, text="Import", command=do_import,
                      fg_color="#0075c6", hover_color="#005a98",
                      text_color="white", font=("Arial", 12, "bold"),
                      corner_radius=14, height=30, width=110).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="Export", command=do_export,
                      fg_color="#0075c6", hover_color="#005a98",
                      text_color="white", font=("Arial", 12, "bold"),
                      corner_radius=14, height=30, width=110).pack(side="left", padx=4)

        # Scrollable table setup
        table_frame = ctk.CTkFrame(content, fg_color="white", corner_radius=12)
        table_frame.pack(fill="both", expand=True, pady=(10,0), padx=16)
        canvas = ctk.CTkCanvas(table_frame, bg="white", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        vsb = ctk.CTkScrollbar(table_frame, orientation="vertical", command=canvas.yview)
        vsb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=vsb.set)
        table_inner = ctk.CTkFrame(canvas, fg_color="white")
        canvas.create_window((0,0), window=table_inner, anchor="nw")

        set_content.checkbox_vars = {}

        def on_frame_configure(evt):
            canvas.configure(scrollregion=canvas.bbox("all"))
        table_inner.bind("<Configure>", on_frame_configure)

        # Full-field table
        def refresh_table():
            for w in table_inner.winfo_children():
                w.destroy()
            set_content.checkbox_vars.clear()
            merchants = bsa_settings.get_all_merchants_with_ids()

            headers = ["", "Merchant Processor", "C/O", "Address", "City", "State", "ZIP", "Notes"]
            widths  = [  3,               200,     80,      170,     90,     50,    60,    180 ]
            for col, (h, w) in enumerate(zip(headers, widths)):
                ctk.CTkLabel(table_inner, text=h, font=("Arial", 13, "bold"),
                             text_color="#0075c6", anchor="w", width=w)\
                    .grid(row=0, column=col, sticky="w", padx=(4 if col==0 else 2,2))

            for r, (mid, name, co, addr, city, st, zipc, notes) in enumerate(merchants, start=1):
                var = ctk.BooleanVar()
                set_content.checkbox_vars[mid] = var
                ctk.CTkCheckBox(table_inner, variable=var, text="", width=18, fg_color="#0075c6")\
                    .grid(row=r, column=0, padx=(4,2), pady=2, sticky="w")

                # Name as edit button
                ctk.CTkButton(
                    table_inner, text=name, fg_color="white", text_color="#222",
                    width=widths[1], anchor="w", hover_color="#f0f8ff",
                    command=make_edit(mid, name, co, addr, city, st, zipc, notes)
                ).grid(row=r, column=1, sticky="w", padx=2, pady=2)

                # Other fields
                for ci, val in enumerate([co, addr, city, st, zipc, notes], start=2):
                    ctk.CTkLabel(table_inner, text=val or "", anchor="w",
                                 width=widths[ci], font=("Arial", 12))\
                        .grid(row=r, column=ci, sticky="w", padx=2, pady=2)
                    
        
        def make_edit(mid, name, co, addr, city, st, zipc, notes):
            def edit_popup():
                if current_popup["window"] and current_popup["window"].winfo_exists():
                    current_popup["window"].lift(); current_popup["window"].focus_force(); return
                popup = ctk.CTkToplevel(app)
                current_popup["window"] = popup
                popup.title("Edit Merchant Processor")
                popup.geometry("440x654"); popup.resizable(False,False)
                popup.transient(app); popup.grab_set()
                x = app.winfo_x() + (app.winfo_width()//2) - 220
                y = app.winfo_y() + (app.winfo_height()//2) - 260
                popup.geometry(f"+{x}+{y}")

                field_w = 350
                for lbl, val in [
                    ("Merchant Processor Name:", name),
                    ("C/O:", co),
                    ("Address:", addr),
                    ("City:", city),
                    ("State:", st),
                    ("ZIP:", zipc)
                ]:
                    ctk.CTkLabel(popup, text=lbl).pack(anchor="w", padx=18, pady=(14 if lbl.endswith("Name:") else 8,0))
                    var = ctk.StringVar(value=val)
                    ctk.CTkEntry(popup, textvariable=var, width=field_w).pack(padx=18,pady=3)
                    locals()[lbl.split()[0].lower()+"_var"] = var

                ctk.CTkLabel(popup, text="Notes:").pack(anchor="w", padx=18, pady=(8,0))
                notes_box = ctk.CTkTextbox(popup, width=field_w, height=90)
                notes_box.pack(padx=18,pady=3); notes_box.insert("1.0", notes or "")

                bf = ctk.CTkFrame(popup, fg_color="white")
                bf.pack(pady=16)
                def save_and_close():
                    bsa_settings.edit_merchant_by_id(
                        mid,
                        name_var.get(), co_var.get(), address_var.get(),
                        city_var.get(), state_var.get(), zip_var.get(),
                        notes_box.get("1.0","end-1c")
                    )
                    popup.grab_release(); current_popup["window"]=None; popup.destroy(); refresh_table()
                ctk.CTkButton(bf, text="Save", command=save_and_close,
                              fg_color="#0075c6", hover_color="#005a98", width=80).pack(side="left",padx=10)
                ctk.CTkButton(bf, text="Cancel", command=popup.destroy,
                              fg_color="#bbb", width=80).pack(side="left",padx=10)
                popup.protocol("WM_DELETE_WINDOW", lambda: (popup.grab_release(), current_popup.__setitem__("window",None), popup.destroy()))
            return edit_popup

        # <<== CRITICAL: Populate on first show!
        refresh_table()

        # Add / Delete controls
        ctrl = ctk.CTkFrame(content, fg_color="white", corner_radius=0)
        ctrl.pack(fill="x", pady=(8,16))

        def add_merchant_popup():
            if current_popup["window"] and current_popup["window"].winfo_exists():
                current_popup["window"].lift(); current_popup["window"].focus_force()
                return
            popup = ctk.CTkToplevel(app)
            current_popup["window"] = popup
            popup.title("Add Merchant Processor")
            popup.geometry("420x545"); popup.resizable(False, False)
            popup.transient(app); popup.grab_set()
            x = app.winfo_x() + (app.winfo_width()//2) - 210
            y = app.winfo_y() + (app.winfo_height()//2) - 225
            popup.geometry(f"+{x}+{y}")

            labels = ["Merchant Processor Name", "C/O", "Address", "City", "State", "ZIP"]
            vars   = [ctk.StringVar() for _ in labels]
            for i, (lbl, var) in enumerate(zip(labels, vars)):
                ctk.CTkLabel(popup, text=lbl+":", font=("Arial",13))\
                   .pack(pady=(8 if i==0 else 2,0), anchor="w", padx=18)
                ctk.CTkEntry(popup, textvariable=var, width=340).pack(pady=1, padx=18)

            ctk.CTkLabel(popup, text="Notes:", font=("Arial",13)).pack(pady=2, anchor="w", padx=18)
            notes_box = ctk.CTkTextbox(popup, width=340, height=64)
            notes_box.pack(pady=1, padx=18)

            def add_and_close():
                data = [v.get().strip() for v in vars]
                if not data[0]:
                    messagebox.showwarning("Missing Name","Merchant name is required."); return
                notes = notes_box.get("1.0","end-1c").strip()
                bsa_settings.add_merchant_full(*data, notes)
                popup.destroy(); current_popup["window"]=None
                refresh_table()

            btnf = ctk.CTkFrame(popup, fg_color="white", corner_radius=0)
            btnf.pack(pady=14)
            ctk.CTkButton(btnf, text="Save", command=add_and_close,
                          fg_color="#0075c6", hover_color="#005a98", width=80).pack(side="left", padx=8)
            ctk.CTkButton(btnf, text="Cancel", command=popup.destroy,
                          fg_color="#bbb", width=80).pack(side="left", padx=8)

            popup.protocol("WM_DELETE_WINDOW", lambda: (popup.grab_release(), current_popup.__setitem__("window",None), popup.destroy()))



        # Delete button
        def delete_merchants_selected():
            to_delete = [mid for mid,var in set_content.checkbox_vars.items() if var.get()]
            if not to_delete:
                messagebox.showwarning("Delete","No merchants selected."); return
            if messagebox.askyesno("Confirm Delete", f"Delete {len(to_delete)}?"):
                bsa_settings.delete_merchants_by_ids(to_delete)
                refresh_table()

        ctk.CTkButton(ctrl, text="Add", command=add_merchant_popup,
                      fg_color="#0075c6", hover_color="#005a98", width=90).pack(side="left", padx=6)
        ctk.CTkButton(ctrl, text="Delete", command=delete_merchants_selected,
                      fg_color="#e74c3c", hover_color="#c0392b", width=90).pack(side="right", padx=6)

        ctk.CTkLabel(content, text="• Click a merchant name to edit all fields. Use checkboxes and Delete to remove. Add to create new.",
                     font=("Arial",12), text_color="#666").pack(pady=(8,10))

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
