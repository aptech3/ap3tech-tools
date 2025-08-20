import csv
import os
import sqlite3
from datetime import datetime

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "merchant_db.sqlite")


def connect_db():
    """Create/connect to the SQLite database and ensure tables exist."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS MerchantProcessors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        root TEXT,            -- <<<<< THIS LINE IS NEW!
        name TEXT UNIQUE NOT NULL,
        co TEXT,
        address TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        notes TEXT,
        date_added TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS Suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        date_found TEXT NOT NULL,
        found_in_file TEXT
    )""")
    # --- Exclusion List Table ---
    c.execute("""CREATE TABLE IF NOT EXISTS Exclusions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity TEXT UNIQUE NOT NULL,
        reason TEXT,
        notes TEXT,
        date_added TEXT NOT NULL
    )""")
    conn.commit()
    return conn


# ---- Merchant CRUD by Name (legacy for search/import/export) ----


def get_all_merchants():
    """Return a list of all merchant names, sorted alphabetically (for matching)."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT name FROM MerchantProcessors ORDER BY name COLLATE NOCASE")
    result = [row[0] for row in c.fetchall()]
    conn.close()
    return result


# ---- Merchant CRUD by ID (for GUI/table) ----


def get_all_merchants_with_ids():
    """Return list of (id, root, name, co, address, city, state, zip, notes) for all merchants."""
    conn = connect_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, root, name, co, address, city, state, zip, notes FROM MerchantProcessors ORDER BY name COLLATE NOCASE"
    )
    result = c.fetchall()
    conn.close()
    return result


def get_merchant_by_id(row_id):
    """Get a merchant's full data by its row ID."""
    conn = connect_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, root, name, co, address, city, state, zip, notes FROM MerchantProcessors WHERE id = ?",
        (row_id,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        keys = ["id", "root", "name", "co", "address", "city", "state", "zip", "notes"]
        return dict(zip(keys, row, strict=False))
    else:
        return None


def add_merchant_full(root, name, co="", address="", city="", state="", zip_code="", notes=""):
    """Add a merchant processor with all fields (no duplicates on name)."""
    conn = connect_db()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO MerchantProcessors
                (root, name, co, address, city, state, zip, notes, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                root.strip(),
                name.strip(),
                co.strip(),
                address.strip(),
                city.strip(),
                state.strip(),
                zip_code.strip(),
                notes.strip(),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        print("[DEBUG] IntegrityError on add:", e)
    conn.close()


def edit_merchant_by_id(row_id, root, name, co, address, city, state, zip_code, notes):
    """Edit a merchant by row ID, updating all fields including root."""
    conn = connect_db()
    c = conn.cursor()
    c.execute(
        """
        UPDATE MerchantProcessors
        SET root = ?, name = ?, co = ?, address = ?, city = ?, state = ?, zip = ?, notes = ?
        WHERE id = ?""",
        (
            root.strip(),
            name.strip(),
            co.strip(),
            address.strip(),
            city.strip(),
            state.strip(),
            zip_code.strip(),
            notes.strip(),
            row_id,
        ),
    )
    conn.commit()
    conn.close()


# For compatibility with main_app.py calling edit_merchant_full_by_id:
edit_merchant_full_by_id = edit_merchant_by_id


def delete_merchants_by_ids(list_of_ids):
    """Delete merchants by list of row IDs (for GUI)."""
    conn = connect_db()
    c = conn.cursor()
    for row_id in list_of_ids:
        c.execute("DELETE FROM MerchantProcessors WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


# ---- Exclusion List CRUD ----


def get_all_exclusions_with_ids():
    """Return list of (id, entity, reason, notes) for all exclusions."""
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, entity, reason, notes FROM Exclusions ORDER BY entity COLLATE NOCASE")
    result = c.fetchall()
    conn.close()
    return result


def add_exclusion(entity, reason="", notes=""):
    """Add an exclusion with all fields (no duplicates on entity)."""
    conn = connect_db()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO Exclusions
                (entity, reason, notes, date_added)
            VALUES (?, ?, ?, ?)""",
            (entity.strip(), reason.strip(), notes.strip(), datetime.now().isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def edit_exclusion_by_id(row_id, entity, reason, notes):
    """Edit an exclusion by row ID, updating all fields."""
    conn = connect_db()
    c = conn.cursor()
    c.execute(
        """
        UPDATE Exclusions
        SET entity = ?, reason = ?, notes = ?
        WHERE id = ?""",
        (entity.strip(), reason.strip(), notes.strip(), row_id),
    )
    conn.commit()
    conn.close()


def delete_exclusions_by_ids(list_of_ids):
    """Delete exclusions by list of row IDs (for GUI)."""
    conn = connect_db()
    c = conn.cursor()
    for row_id in list_of_ids:
        c.execute("DELETE FROM Exclusions WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


# --- Export/Import for .txt files (all fields, CSV format recommended) ---


def export_merchants_txt(filepath):
    """Export all merchants to a .txt (CSV) file."""
    merchants = get_all_merchants_with_ids()
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Write header
        writer.writerow(["root", "name", "co", "address", "city", "state", "zip", "notes"])
        for _, root, name, co, address, city, state, zip_code, notes in merchants:
            writer.writerow([root, name, co, address, city, state, zip_code, notes])


def import_merchants_txt(filepath):
    """Import merchant list from a .txt (CSV) file."""
    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        first = True
        for row in reader:
            print("[DEBUG] import row:", row)  # keep this for now!
            if (
                first and row and (row[0].lower() in ["root", "name"])
            ):  # supports files with/without root
                first = False  # Skip header
                continue
            if len(row) < 2:
                continue
            fields = (row + [""] * 8)[
                :8
            ]  # 8 fields: root, name, co, address, city, state, zip, notes
            add_merchant_full(*fields)


def export_exclusions_txt(filepath):
    """Export all exclusions to a .txt (CSV) file."""
    exclusions = get_all_exclusions_with_ids()
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["entity", "reason", "notes"])
        for _, entity, reason, notes in exclusions:
            writer.writerow([entity, reason, notes])


def import_exclusions_txt(filepath):
    """Import exclusions from a .txt (CSV) file."""
    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        first = True
        for row in reader:
            if first and row and row[0].lower() == "entity":
                first = False  # Skip header
                continue
            if len(row) < 1:
                continue
            fields = (row + [""] * 3)[:3]
            add_exclusion(*fields)


# ---- Suggestions CRUD ----


def get_suggestions():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT name, date_found, found_in_file FROM Suggestions ORDER BY date_found DESC")
    result = c.fetchall()
    conn.close()
    return result


def add_suggestion(name, found_in_file=""):
    name = name.strip()
    if not name:
        return
    merchants = get_all_merchants()
    suggestions = [s[0] for s in get_suggestions()]
    if name in merchants or name in suggestions:
        return
    conn = connect_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO Suggestions (name, date_found, found_in_file) VALUES (?, ?, ?)",
        (name, datetime.now().isoformat(), found_in_file),
    )
    conn.commit()
    conn.close()


def approve_suggestions(list_of_names):
    for name in list_of_names:
        add_merchant_full(name)
        delete_suggestions([name])


def delete_suggestions(list_of_names):
    conn = connect_db()
    c = conn.cursor()
    for name in list_of_names:
        c.execute("DELETE FROM Suggestions WHERE name = ?", (name.strip(),))
    conn.commit()
    conn.close()
