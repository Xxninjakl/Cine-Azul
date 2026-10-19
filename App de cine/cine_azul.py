from __future__ import annotations

import csv
import ctypes
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

try:
    from PIL import Image, ImageOps, ImageTk

    PIL_AVAILABLE = True
except ImportError:
    Image = ImageOps = ImageTk = None  # type: ignore[assignment]
    PIL_AVAILABLE = False


APP_NAME = "CineAzul"
CARD_WIDTH = 212
POSTER_WIDTH = 176
POSTER_HEIGHT = 250
DRAWER_WIDTH = 282
DRAWER_STEPS = 14

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT '',
    director TEXT NOT NULL DEFAULT '',
    rating TEXT NOT NULL DEFAULT '',
    synopsis TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    cover_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

FIELDS = [
    "title",
    "year",
    "genre",
    "director",
    "rating",
    "synopsis",
    "file_path",
    "cover_path",
]


def default_database_path() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "peliculas.db"


class MovieDatabase:
    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connect_and_prepare()

    def _connect_and_prepare(self) -> None:
        connection = sqlite3.connect(self.path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if "movies" not in tables and tables:
                raise ValueError("La base de datos elegida no tiene el formato de CineAzul.")
            connection.execute(SCHEMA)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(movies)").fetchall()
            }
            required = {"id", *FIELDS}
            if not required.issubset(columns):
                raise ValueError("La tabla 'movies' no contiene las columnas que necesita CineAzul.")
            connection.commit()
        finally:
            connection.close()

    def list_movies(self, query: str = "") -> list[dict[str, Any]]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            if query.strip():
                needle = f"%{query.strip()}%"
                rows = connection.execute(
                    """SELECT * FROM movies
                       WHERE title LIKE ? OR year LIKE ? OR genre LIKE ? OR director LIKE ?
                       ORDER BY title COLLATE NOCASE""",
                    (needle, needle, needle, needle),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM movies ORDER BY title COLLATE NOCASE"
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def save_movie(self, values: dict[str, str], movie_id: int | None = None) -> None:
        connection = sqlite3.connect(self.path)
        try:
            if movie_id is None:
                connection.execute(
                    """INSERT INTO movies
                       (title, year, genre, director, rating, synopsis, file_path, cover_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    tuple(values[field] for field in FIELDS),
                )
            else:
                connection.execute(
                    """UPDATE movies SET title=?, year=?, genre=?, director=?, rating=?,
                       synopsis=?, file_path=?, cover_path=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (*[values[field] for field in FIELDS], movie_id),
                )
            connection.commit()
        finally:
            connection.close()

    def delete_movie(self, movie_id: int) -> None:
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("DELETE FROM movies WHERE id=?", (movie_id,))
            connection.commit()
        finally:
            connection.close()

    def import_csv(self, source: Path) -> int:
        aliases = {
            "titulo": "title",
            "título": "title",
            "title": "title",
            "año": "year",
            "anio": "year",
            "year": "year",
            "genero": "genre",
            "género": "genre",
            "genre": "genre",
            "director": "director",
            "calificacion": "rating",
            "calificación": "rating",
            "rating": "rating",
            "sinopsis": "synopsis",
            "descripcion": "synopsis",
            "descripción": "synopsis",
            "synopsis": "synopsis",
            "archivo": "file_path",
            "ruta": "file_path",
            "file_path": "file_path",
            "portada": "cover_path",
            "imagen": "cover_path",
            "cover_path": "cover_path",
        }
        connection = sqlite3.connect(self.path)
        inserted = 0
        try:
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if not reader.fieldnames:
                    raise ValueError("El CSV no tiene encabezados.")
                mapped = {name: aliases.get(name.strip().lower()) for name in reader.fieldnames}
                if "title" not in mapped.values():
                    raise ValueError("El CSV debe tener una columna 'titulo' o 'title'.")
                for row in reader:
                    values = {field: "" for field in FIELDS}
                    for original, value in row.items():
                        target = mapped.get(original)
                        if target and value is not None:
                            values[target] = value.strip()
                    if values["title"]:
                        connection.execute(
                            """INSERT INTO movies
                               (title, year, genre, director, rating, synopsis, file_path, cover_path)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            tuple(values[field] for field in FIELDS),
                        )
                        inserted += 1
            connection.commit()
            return inserted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def export_csv(self, destination: Path) -> int:
        movies = self.list_movies()
        with destination.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows({field: movie.get(field, "") for field in FIELDS} for movie in movies)
        return len(movies)


def detect_vlc() -> str | None:
    executable = shutil.which("vlc") or shutil.which("vlc.exe")
    if executable:
        return executable
    if platform.system() == "Windows":
        roots = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
        local = os.environ.get("LOCALAPPDATA")
        candidates = [Path(root) / "VideoLAN" / "VLC" / "vlc.exe" for root in roots if root]
        if local:
            candidates.append(Path(local) / "Programs" / "VideoLAN" / "VLC" / "vlc.exe")
        return next((str(path) for path in candidates if path.is_file()), None)
    if platform.system() == "Darwin":
        return "/Applications/VLC.app"
    return None


def open_movie_file(path: Path) -> None:
    system = platform.system()
    vlc = detect_vlc()
    if vlc and system != "Darwin":
        subprocess.Popen([vlc, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif system == "Darwin":
        if vlc:
            subprocess.Popen(["open", "-a", "VLC", str(path)])
        else:
            subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class MovieDialog(tk.Toplevel):
    def __init__(
        self,
        parent: "CineAzulApp",
        movie: dict[str, Any] | None = None,
    ):
        super().__init__(parent)
        self.parent_app = parent
        self.palette = parent.palette
        self.movie = movie or {}
        self.result: dict[str, str] | None = None
        self.poster_preview: tk.PhotoImage | Any | None = None
        self.title("Editar película" if movie else "Añadir película")
        self.geometry("660x720")
        self.minsize(600, 660)
        self.configure(bg=self.palette["bg"])
        self.transient(parent)
        self.grab_set()
        self._build()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        x = self.parent_app.winfo_rootx() + (self.parent_app.winfo_width() - self.winfo_width()) // 2
        y = self.parent_app.winfo_rooty() + (self.parent_app.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build(self) -> None:
        c = self.palette
        outer = tk.Frame(self, bg=c["bg"], padx=26, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(
            outer,
            text="DETALLES DE LA PELÍCULA",
            bg=c["bg"],
            fg=c["accent"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            outer,
            text="Tu próxima noche de cine empieza aquí",
            bg=c["bg"],
            fg=c["text"],
            font=("Segoe UI Semibold", 18),
        ).pack(anchor="w", pady=(3, 18))

        content = tk.Frame(outer, bg=c["bg"])
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)

        self.entries: dict[str, tk.Entry] = {}
        self._field(content, "Título *", "title", 0, 0, "Ej. Interstellar")
        self._field(content, "Año", "year", 0, 1, "2024")
        self._field(content, "Género", "genre", 1, 0, "Ciencia ficción, drama")
        self._field(content, "Director", "director", 1, 1, "Nombre del director")
        self._field(content, "Calificación (0–10)", "rating", 2, 0, "8.5")

        tk.Label(
            content,
            text="SINOPSIS",
            bg=c["bg"],
            fg=c["muted"],
            font=("Segoe UI", 9, "bold"),
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 5))
        self.synopsis = tk.Text(
            content,
            height=5,
            wrap="word",
            bg=c["input"],
            fg=c["text"],
            insertbackground=c["text"],
            relief="flat",
            padx=10,
            pady=9,
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground=c["border"],
            highlightcolor=c["accent"],
        )
        self.synopsis.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.synopsis.insert("1.0", self.movie.get("synopsis", ""))

        self._path_row(content, "ARCHIVO DE VIDEO", "file_path", 5, "Seleccionar video…", [
            ("Videos", "*.mkv *.mp4 *.avi *.mov *.wmv *.m4v *.webm"), ("Todos los archivos", "*.*")
        ])
        self._path_row(content, "IMAGEN DE PORTADA", "cover_path", 7, "Seleccionar imagen…", [
            ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("Todos los archivos", "*.*")
        ])

        self.path_vars: dict[str, tk.StringVar] = {}
        for key in ("file_path", "cover_path"):
            value = self.movie.get(key, "")
            self.path_vars[key] = tk.StringVar(value=str(value or ""))
            entry = getattr(self, f"_{key}_entry")
            entry.configure(textvariable=self.path_vars[key])
        self._update_poster_preview()

        buttons = tk.Frame(outer, bg=c["bg"])
        buttons.pack(fill="x", pady=(20, 0))
        self.parent_app.make_button(buttons, "Cancelar", self.destroy, secondary=True).pack(side="right")
        self.parent_app.make_button(buttons, "Guardar película", self._save).pack(side="right", padx=(0, 9))

    def _field(self, parent: tk.Widget, label: str, key: str, row: int, column: int, hint: str) -> None:
        c = self.palette
        holder = tk.Frame(parent, bg=c["bg"])
        holder.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 10, 10 if column == 0 else 0), pady=(0, 4))
        tk.Label(holder, text=label.upper(), bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 5))
        entry = tk.Entry(
            holder,
            bg=c["input"],
            fg=c["text"],
            insertbackground=c["text"],
            relief="flat",
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground=c["border"],
            highlightcolor=c["accent"],
        )
        entry.pack(fill="x", ipady=8, padx=1)
        value = self.movie.get(key, "")
        entry.insert(0, str(value or ""))
        if not value:
            entry.insert(0, "")
        self.entries[key] = entry

    def _path_row(self, parent: tk.Widget, label: str, key: str, row: int, button_text: str, filetypes: list[tuple[str, str]]) -> None:
        c = self.palette
        tk.Label(parent, text=label, bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(13, 5)
        )
        holder = tk.Frame(parent, bg=c["bg"])
        holder.grid(row=row + 1, column=0, columnspan=2, sticky="ew")
        holder.columnconfigure(0, weight=1)
        entry = tk.Entry(
            holder,
            bg=c["input"],
            fg=c["text"],
            insertbackground=c["text"],
            relief="flat",
            font=("Segoe UI", 9),
            highlightthickness=1,
            highlightbackground=c["border"],
        )
        entry.grid(row=0, column=0, sticky="ew", ipady=8, padx=(0, 8))
        setattr(self, f"_{key}_entry", entry)
        self.parent_app.make_button(
            holder,
            button_text,
            lambda: self._browse_path(key, filetypes),
            secondary=True,
            small=True,
        ).grid(row=0, column=1)
        if key == "cover_path":
            self.cover_preview_label = tk.Label(
                holder,
                text="▧",
                bg=c["placeholder"],
                fg=c["muted"],
                font=("Segoe UI", 18),
                width=5,
                height=4,
            )
            self.cover_preview_label.grid(row=0, column=2, padx=(10, 0))

    def _browse_path(self, key: str, filetypes: list[tuple[str, str]]) -> None:
        if key == "file_path":
            path = filedialog.askopenfilename(parent=self, title="Elige el archivo de la película", filetypes=filetypes)
        else:
            path = filedialog.askopenfilename(parent=self, title="Elige la imagen de portada", filetypes=filetypes)
        if path:
            self.path_vars[key].set(path)
            if key == "file_path" and not self.entries["title"].get().strip():
                self.entries["title"].insert(0, Path(path).stem)
            if key == "cover_path":
                self._update_poster_preview()

    def _update_poster_preview(self) -> None:
        path = self.path_vars.get("cover_path", tk.StringVar(value="")).get().strip()
        if not path or not Path(path).is_file():
            if hasattr(self, "cover_preview_label"):
                self.cover_preview_label.configure(image="", text="▧")
            return
        try:
            image = load_cover(Path(path), 112, 158)
            if image is not None:
                self.poster_preview = image
                self.cover_preview_label.configure(image=image, text="")
                self.cover_preview_label.image = image
            else:
                self.cover_preview_label.configure(image="", text="Vista previa\nno disponible")
        except Exception:
            self.cover_preview_label.configure(image="", text="Vista previa\nno disponible")

    def _save(self) -> None:
        values = {key: entry.get().strip() for key, entry in self.entries.items()}
        values["synopsis"] = self.synopsis.get("1.0", "end-1c").strip()
        values["file_path"] = self.path_vars["file_path"].get().strip()
        values["cover_path"] = self.path_vars["cover_path"].get().strip()
        if not values["title"]:
            messagebox.showwarning("Falta el título", "Escribe el título de la película para guardarla.", parent=self)
            self.entries["title"].focus_set()
            return
        if values["year"] and not values["year"].isdigit():
            messagebox.showwarning("Año no válido", "El año debe contener solo números.", parent=self)
            self.entries["year"].focus_set()
            return
        if values["rating"]:
            try:
                rating = float(values["rating"].replace(",", "."))
                if not 0 <= rating <= 10:
                    raise ValueError
                values["rating"] = f"{rating:g}"
            except ValueError:
                messagebox.showwarning("Calificación no válida", "Usa un número entre 0 y 10.", parent=self)
                self.entries["rating"].focus_set()
                return
        self.result = values
        self.destroy()


def load_cover(path: Path, width: int, height: int) -> Any | None:
    if PIL_AVAILABLE:
        with Image.open(path) as source:
            image = ImageOps.fit(source.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
    try:
        image = tk.PhotoImage(file=str(path))
        ratio = max(1, (image.width() + width - 1) // width, (image.height() + height - 1) // height)
        return image.subsample(ratio, ratio)
    except tk.TclError:
        return None


class CineAzulApp(tk.Tk):
    THEMES = {
        "dark": {
            "bg": "#08111f",
            "panel": "#101c2e",
            "panel_alt": "#14233a",
            "input": "#0c1728",
            "text": "#f0f5ff",
            "muted": "#91a3be",
            "accent": "#55a2ff",
            "accent_hover": "#77b5ff",
            "accent_text": "#071321",
            "border": "#20334e",
            "placeholder": "#1a2b43",
            "success": "#56d6c2",
            "shadow": "#050b14",
        },
        "light": {
            "bg": "#eef3fa",
            "panel": "#ffffff",
            "panel_alt": "#f6f9fd",
            "input": "#f8fafd",
            "text": "#13243b",
            "muted": "#61748e",
            "accent": "#236ed1",
            "accent_hover": "#155ab4",
            "accent_text": "#ffffff",
            "border": "#d8e2ef",
            "placeholder": "#e4ebf4",
            "success": "#0c8d7d",
            "shadow": "#dce5f0",
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self.title("CineAzul")
        self.geometry("1180x820")
        self.minsize(800, 620)
        database_path = default_database_path()
        self.settings_path = database_path.with_name("settings.json")
        settings = self._read_settings()
        stored_theme = settings.get("theme", "dark")
        self.theme_name = stored_theme if isinstance(stored_theme, str) else "dark"
        if self.theme_name not in self.THEMES:
            self.theme_name = "dark"
        stored_wallpaper = settings.get("wallpaper", "")
        self.wallpaper_path = stored_wallpaper if isinstance(stored_wallpaper, str) else ""
        if self.wallpaper_path and not Path(self.wallpaper_path).is_file():
            self.wallpaper_path = ""
        self.palette = self.THEMES[self.theme_name]
        self.database = MovieDatabase(database_path)
        self.movies: list[dict[str, Any]] = []
        self.poster_refs: list[Any] = []
        self._render_job: str | None = None
        self._drawer_job: str | None = None
        self._wallpaper_job: str | None = None
        self.menu_open = False
        self._window_chrome_applied = False
        self._drag_origin: tuple[int, int, int, int] | None = None
        self.wallpaper_photo: Any | None = None
        self.gallery_wallpaper_photo: Any | None = None
        self.gallery_wallpaper_labels: list[tk.Label] = []
        self.configure(bg=self.palette["bg"])
        self._build_shell()
        self.bind("<Control-f>", lambda _event: self.search_entry.focus_set())
        self.bind("<Control-n>", lambda _event: self.add_movie())
        self.bind("<Escape>", lambda _event: self.set_menu_open(False))
        self.bind("<Configure>", self._on_root_configure, add="+")
        self.refresh_movies()
        self.after_idle(self._apply_wallpaper)
        self.after(120, self._apply_window_chrome)

    def _read_settings(self) -> dict[str, str]:
        try:
            loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self) -> None:
        settings = {"theme": self.theme_name, "wallpaper": self.wallpaper_path}
        try:
            self.settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            messagebox.showwarning("No se guardaron las preferencias", str(error), parent=self)

    def _apply_window_chrome(self) -> None:
        if platform.system() != "Windows":
            self.overrideredirect(True)
            self._window_chrome_applied = True
            return
        try:
            hwnd = ctypes.c_void_p(self.winfo_id())
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_style.restype = ctypes.c_ssize_t

            # Keep the normal Windows frame behavior (taskbar, resize, minimize)
            # while removing only the native caption area.
            style = get_style(hwnd, -16)  # GWL_STYLE
            style &= ~0x00C00000  # WS_CAPTION
            style |= 0x00040000 | 0x00020000 | 0x00010000 | 0x00080000
            set_style(hwnd, -16, style)

            set_window_pos = user32.SetWindowPos
            set_window_pos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            set_window_pos.restype = ctypes.c_int
            set_window_pos(hwnd, None, 0, 0, 0, 0, 0x0027)  # FRAMECHANGED | NOZORDER | NOMOVE | NOSIZE

            try:
                dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
                dwm.DwmSetWindowAttribute.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_uint,
                    ctypes.c_void_p,
                    ctypes.c_uint,
                ]
                dwm.DwmSetWindowAttribute.restype = ctypes.c_long
                color = self.palette["bg"]
                red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
                colorref = ctypes.c_uint(red | (green << 8) | (blue << 16))
                dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(colorref), ctypes.sizeof(colorref))
            except (AttributeError, OSError):
                pass

            self._window_chrome_applied = True
            self.update_idletasks()
            self._sync_window_controls()
        except (AttributeError, OSError, tk.TclError, ctypes.ArgumentError):
            pass

    def _begin_window_drag(self, event: tk.Event) -> None:
        if platform.system() == "Windows":
            try:
                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                user32.ReleaseCapture()
                send_message = user32.SendMessageW
                send_message.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
                send_message.restype = ctypes.c_ssize_t
                send_message(ctypes.c_void_p(self.winfo_id()), 0x00A1, 2, 0)  # WM_NCLBUTTONDOWN / HTCAPTION
            except (AttributeError, OSError):
                pass
        else:
            self._drag_origin = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())

    def _drag_window(self, event: tk.Event) -> None:
        if self._drag_origin is None:
            return
        start_x, start_y, window_x, window_y = self._drag_origin
        self.geometry(f"+{window_x + event.x_root - start_x}+{window_y + event.y_root - start_y}")

    def _minimize_window(self) -> None:
        self.iconify()

    def _toggle_maximize(self) -> None:
        try:
            if self.state() == "zoomed":
                self.state("normal")
            else:
                self.state("zoomed")
            self.after_idle(self._sync_window_controls)
        except tk.TclError:
            pass

    def _sync_window_controls(self) -> None:
        if not hasattr(self, "maximize_button"):
            return
        try:
            self.maximize_button.configure(text="❐" if self.state() == "zoomed" else "□")
        except tk.TclError:
            pass

    def make_button(
        self,
        parent: tk.Widget,
        text: str,
        command: Any,
        *,
        secondary: bool = False,
        small: bool = False,
    ) -> tk.Button:
        c = self.palette
        bg = c["panel_alt"] if secondary else c["accent"]
        fg = c["text"] if secondary else c["accent_text"]
        hover = c["border"] if secondary else c["accent_hover"]
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI Semibold", 9 if small else 10),
            padx=12 if small else 15,
            pady=7 if small else 10,
            highlightthickness=0,
        )
        button.bind("<Enter>", lambda _e: self._animate_button_color(button, hover))
        button.bind("<Leave>", lambda _e: self._animate_button_color(button, bg))
        return button

    @staticmethod
    def _mix_color(start: str, end: str, amount: float) -> str:
        start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
        end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
        mixed = tuple(round(a + (b - a) * amount) for a, b in zip(start_rgb, end_rgb))
        return "#" + "".join(f"{channel:02x}" for channel in mixed)

    def _animate_button_color(self, button: tk.Button, target: str) -> None:
        old_job = getattr(button, "_color_job", None)
        if old_job:
            try:
                self.after_cancel(old_job)
            except tk.TclError:
                pass
        try:
            start = str(button.cget("bg"))
        except tk.TclError:
            return
        if start == target:
            return

        def step(index: int = 1) -> None:
            try:
                if not button.winfo_exists():
                    return
                button.configure(bg=self._mix_color(start, target, min(index / 6, 1)))
                if index < 6:
                    button._color_job = self.after(16, lambda: step(index + 1))  # type: ignore[attr-defined]
            except tk.TclError:
                return

        step()

    def _build_shell(self) -> None:
        c = self.palette
        self.shell = tk.Frame(self, bg=c["bg"])
        self.shell.pack(fill="both", expand=True)
        self.shell_wallpaper = tk.Label(self.shell, bg=c["bg"], bd=0, highlightthickness=0)
        self.shell_wallpaper.place(x=0, y=0, relwidth=1, relheight=1)
        self.shell_wallpaper.lower()

        self.window_bar = tk.Frame(self.shell, bg=c["bg"], height=34)
        self.window_bar.pack(fill="x")
        self.window_bar.pack_propagate(False)
        self.window_title = tk.Label(
            self.window_bar,
            text="CineAzul",
            bg=c["bg"],
            fg=c["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.window_title.pack(side="left", padx=(14, 0), fill="y")
        controls = tk.Frame(self.window_bar, bg=c["bg"])
        controls.pack(side="right", fill="y")
        self.minimize_button = self._window_control(controls, "—", self._minimize_window)
        self.minimize_button.pack(side="left", fill="y")
        self.maximize_button = self._window_control(controls, "□", self._toggle_maximize)
        self.maximize_button.pack(side="left", fill="y")
        self.close_button = self._window_control(controls, "×", self.destroy, close=True)
        self.close_button.pack(side="left", fill="y")
        for widget in (self.window_bar, self.window_title):
            widget.bind("<ButtonPress-1>", self._begin_window_drag)
            if platform.system() != "Windows":
                widget.bind("<B1-Motion>", self._drag_window)
                widget.bind("<Double-Button-1>", lambda _event: self._toggle_maximize())

        top = tk.Frame(self.shell, bg=c["bg"], padx=32, pady=20)
        top.pack(fill="x")
        self.menu_button = self.make_button(top, "☰", self.toggle_menu, secondary=True, small=True)
        self.menu_button.configure(font=("Segoe UI", 15, "bold"), width=2, padx=7, pady=6)
        self.menu_button.pack(side="left", padx=(0, 14))
        brand = tk.Frame(top, bg=c["bg"])
        brand.pack(side="left")
        mark = tk.Label(
            brand,
            text="▶",
            bg=c["accent"],
            fg=c["accent_text"],
            font=("Segoe UI", 14, "bold"),
            width=3,
            height=1,
            pady=5,
        )
        mark.pack(side="left", padx=(0, 12))
        names = tk.Frame(brand, bg=c["bg"])
        names.pack(side="left")
        tk.Label(names, text="CINEAZUL", bg=c["bg"], fg=c["text"], font=("Segoe UI", 16, "bold")).pack(anchor="w")

        divider = tk.Frame(self.shell, bg=c["border"], height=1)
        divider.pack(fill="x", padx=32)

        content_head = tk.Frame(self.shell, bg=c["bg"])
        content_head.pack(fill="x", padx=32, pady=(24, 16))
        heading = tk.Frame(content_head, bg=c["bg"])
        heading.pack(side="left", fill="x", expand=True)
        tk.Label(heading, text="MI BIBLIOTECA", bg=c["bg"], fg=c["accent"], font=("Segoe UI", 9, "bold")).pack(anchor="w")
        title_row = tk.Frame(heading, bg=c["bg"])
        title_row.pack(anchor="w", pady=(3, 0))
        tk.Label(title_row, text="Películas", bg=c["bg"], fg=c["text"], font=("Segoe UI Semibold", 25)).pack(side="left")
        self.count_label = tk.Label(title_row, text="0 títulos", bg=c["bg"], fg=c["muted"], font=("Segoe UI", 10))
        self.count_label.pack(side="left", padx=(12, 0), pady=(8, 0))

        self.search_var = tk.StringVar()
        search = tk.Frame(content_head, bg=c["panel"], highlightthickness=1, highlightbackground=c["border"])
        search.pack(side="right", pady=(15, 0))
        tk.Label(search, text="⌕", bg=c["panel"], fg=c["muted"], font=("Segoe UI", 18)).pack(side="left", padx=(11, 1))
        self.search_entry = tk.Entry(
            search,
            textvariable=self.search_var,
            width=28,
            bg=c["panel"],
            fg=c["text"],
            insertbackground=c["text"],
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.search_entry.pack(side="left", ipady=10, padx=(2, 12))
        self.search_entry.insert(0, "Buscar título, género, director…")
        self.search_entry.configure(fg=c["muted"])
        self.search_entry.bind("<FocusIn>", self._search_focus_in)
        self.search_entry.bind("<FocusOut>", self._search_focus_out)
        self.search_var.trace_add("write", lambda *_: self._schedule_refresh())

        self.gallery_holder = tk.Frame(self.shell, bg=c["bg"])
        self.gallery_holder.pack(fill="both", expand=True, padx=32, pady=(0, 18))
        self.canvas = tk.Canvas(self.gallery_holder, bg=c["bg"], highlightthickness=0)
        self.cards_frame = tk.Frame(self.canvas, bg=c["bg"])
        self.cards_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.unbind_all("<MouseWheel>")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.search_var.set("")
        self._build_menu_drawer()

    def _window_control(self, parent: tk.Widget, symbol: str, command: Any, *, close: bool = False) -> tk.Button:
        c = self.palette
        hover = "#c42b1c" if close else c["panel_alt"]
        button = tk.Button(
            parent,
            text=symbol,
            command=command,
            bg=c["bg"],
            fg=c["text"] if close else c["muted"],
            activebackground=hover,
            activeforeground="#ffffff" if close else c["text"],
            relief="flat",
            bd=0,
            width=5,
            cursor="hand2",
            font=("Segoe UI", 11 if close else 10),
            highlightthickness=0,
        )
        button.bind("<Enter>", lambda _event: self._animate_button_color(button, hover))
        button.bind("<Leave>", lambda _event: self._animate_button_color(button, c["bg"]))
        return button

    def _build_menu_drawer(self) -> None:
        c = self.palette
        self.menu_open = False
        self.menu_panel = tk.Frame(
            self.shell,
            bg=c["panel"],
            width=DRAWER_WIDTH,
            highlightthickness=1,
            highlightbackground=c["border"],
        )
        self.menu_panel.pack_propagate(False)

        header = tk.Frame(self.menu_panel, bg=c["panel"], padx=20, pady=22)
        header.pack(fill="x")
        tk.Label(header, text="CINEAZUL", bg=c["panel"], fg=c["accent"], font=("Segoe UI", 10, "bold")).pack(side="left")
        self.make_button(header, "×", lambda: self.set_menu_open(False), secondary=True, small=True).pack(side="right")
        tk.Label(
            self.menu_panel,
            text="Tu espacio de cine",
            bg=c["panel"],
            fg=c["text"],
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w", padx=20, pady=(3, 20))

        self._menu_section("BIBLIOTECA")
        self._menu_option("＋   Añadir película", self.add_movie)
        self._menu_option("⇧   Importar CSV", self.import_csv)
        self._menu_option("⇩   Exportar CSV", self.export_csv)
        self._menu_option("▤   Abrir base de datos", self.open_database)
        self._menu_section("PERSONALIZACIÓN", top_pad=22)
        self._menu_option("▧   Cambiar fondo", self.choose_wallpaper)
        self._menu_option("×   Quitar fondo", self.remove_wallpaper)
        theme_text = "☼   Usar tema claro" if self.theme_name == "dark" else "☾   Usar tema oscuro"
        self._menu_option(theme_text, self.toggle_theme)

        footer = tk.Frame(self.menu_panel, bg=c["panel"], padx=20, pady=18)
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg=c["border"], height=1).pack(fill="x", pady=(0, 12))
        tk.Label(footer, text="Las preferencias se guardan automáticamente.", bg=c["panel"], fg=c["muted"], font=("Segoe UI", 8), wraplength=230, justify="left").pack(anchor="w")
        self.menu_panel.place_forget()

    def _menu_section(self, title: str, top_pad: int = 0) -> None:
        c = self.palette
        tk.Label(
            self.menu_panel,
            text=title,
            bg=c["panel"],
            fg=c["muted"],
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", padx=20, pady=(top_pad, 7))

    def _menu_option(self, title: str, command: Any) -> None:
        button = self.make_button(
            self.menu_panel,
            title,
            lambda action=command: self._run_menu_action(action),
            secondary=True,
            small=False,
        )
        button.configure(anchor="w", padx=16)
        button.pack(fill="x", padx=12, pady=3)

    def _run_menu_action(self, command: Any) -> None:
        self.set_menu_open(False)
        self.after(250, command)

    def toggle_menu(self) -> None:
        self.set_menu_open(not self.menu_open)

    def set_menu_open(self, opened: bool) -> None:
        if not hasattr(self, "menu_panel") or self.menu_open == opened:
            return
        if self._drawer_job:
            try:
                self.after_cancel(self._drawer_job)
            except tk.TclError:
                pass
            self._drawer_job = None
        self.menu_open = opened
        start_x = self.menu_panel.winfo_x() if self.menu_panel.winfo_manager() else -DRAWER_WIDTH
        if opened:
            self.menu_panel.place(x=start_x, y=0, width=DRAWER_WIDTH, relheight=1)
            self.menu_panel.lift()
        end_x = 0 if opened else -DRAWER_WIDTH
        start_x = min(0, max(-DRAWER_WIDTH, start_x))

        def animate(frame: int = 0) -> None:
            progress = min(1.0, frame / DRAWER_STEPS)
            eased = progress * progress * (3 - 2 * progress)
            x = round(start_x + (end_x - start_x) * eased)
            self.menu_panel.place(x=x, y=0, width=DRAWER_WIDTH, relheight=1)
            if frame < DRAWER_STEPS:
                self._drawer_job = self.after(14, lambda: animate(frame + 1))
            else:
                self._drawer_job = None
                if not opened:
                    self.menu_panel.place_forget()

        animate()

    def _on_root_configure(self, event: tk.Event) -> None:
        if event.widget is self:
            self._sync_window_controls()
            if self.wallpaper_path:
                self._schedule_wallpaper_refresh()

    def _schedule_wallpaper_refresh(self) -> None:
        if self._wallpaper_job:
            try:
                self.after_cancel(self._wallpaper_job)
            except tk.TclError:
                pass
        self._wallpaper_job = self.after(150, self._apply_wallpaper)

    def _make_wallpaper_photo(self, path: Path, width: int, height: int) -> Any:
        if not PIL_AVAILABLE:
            raise RuntimeError("Para usar fondos personalizados necesitas Pillow. Instálalo con: py -m pip install Pillow")
        width, height = max(2, width), max(2, height)
        with Image.open(path) as source:
            image = ImageOps.fit(source.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
        tint = (8, 17, 31) if self.theme_name == "dark" else (255, 255, 255)
        strength = 0.35 if self.theme_name == "dark" else 0.16
        image = Image.blend(image, Image.new("RGB", (width, height), tint), strength)
        return ImageTk.PhotoImage(image)

    def _clear_gallery_wallpaper(self) -> None:
        for label in self.gallery_wallpaper_labels:
            try:
                label.destroy()
            except tk.TclError:
                pass
        self.gallery_wallpaper_labels.clear()
        self.gallery_wallpaper_photo = None

    def _apply_wallpaper(self, refresh_shell: bool = True) -> None:
        self._wallpaper_job = None
        self._clear_gallery_wallpaper()
        path = Path(self.wallpaper_path) if self.wallpaper_path else None
        if path is None or not path.is_file() or not PIL_AVAILABLE:
            if refresh_shell and hasattr(self, "shell_wallpaper"):
                self.shell_wallpaper.configure(image="", bg=self.palette["bg"])
                self.wallpaper_photo = None
            return
        try:
            self.update_idletasks()
            if refresh_shell:
                root_photo = self._make_wallpaper_photo(
                    path,
                    max(2, self.shell.winfo_width()),
                    max(2, self.shell.winfo_height()),
                )
                self.wallpaper_photo = root_photo
                self.shell_wallpaper.configure(image=root_photo)

            tile_width = max(2, self.canvas.winfo_width())
            tile_height = max(2, self.canvas.winfo_height())
            self.gallery_wallpaper_photo = self._make_wallpaper_photo(path, tile_width, tile_height)
            content_height = max(
                tile_height,
                self.cards_frame.winfo_reqheight(),
                self.cards_frame.winfo_height(),
            )
            tile_count = (content_height + tile_height - 1) // tile_height
            for index in range(tile_count):
                label = tk.Label(
                    self.cards_frame,
                    image=self.gallery_wallpaper_photo,
                    bg=self.palette["bg"],
                    bd=0,
                    highlightthickness=0,
                )
                label.place(x=0, y=index * tile_height, width=tile_width, height=tile_height)
                label.lower()
                self.gallery_wallpaper_labels.append(label)
        except (OSError, ValueError, tk.TclError):
            self.wallpaper_photo = None
            self.gallery_wallpaper_photo = None
            if refresh_shell:
                self.shell_wallpaper.configure(image="", bg=self.palette["bg"])

    def choose_wallpaper(self) -> None:
        if not PIL_AVAILABLE:
            messagebox.showinfo(
                "Instala Pillow para usar fondos",
                "Abre una terminal y ejecuta:\n\npy -m pip install Pillow",
                parent=self,
            )
            return
        selected = filedialog.askopenfilename(
            parent=self,
            title="Elige el fondo de CineAzul",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("Todos los archivos", "*.*")],
        )
        if not selected:
            return
        candidate = Path(selected).resolve()
        try:
            self._make_wallpaper_photo(candidate, max(2, self.winfo_width()), max(2, self.winfo_height()))
        except (OSError, ValueError, tk.TclError) as error:
            messagebox.showerror("No se pudo cargar la imagen", str(error), parent=self)
            return
        self.wallpaper_path = str(candidate)
        self._save_settings()
        self._apply_wallpaper()

    def remove_wallpaper(self) -> None:
        self.wallpaper_path = ""
        self._save_settings()
        self._apply_wallpaper()

    def _search_focus_in(self, _event: tk.Event) -> None:
        if self.search_entry.get() == "Buscar título, género, director…":
            self.search_entry.delete(0, "end")
            self.search_entry.configure(fg=self.palette["text"])

    def _search_focus_out(self, _event: tk.Event) -> None:
        if not self.search_entry.get().strip():
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, "Buscar título, género, director…")
            self.search_entry.configure(fg=self.palette["muted"])

    def _search_text(self) -> str:
        value = self.search_entry.get().strip()
        return "" if value == "Buscar título, género, director…" else value

    def _schedule_refresh(self) -> None:
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after(120, self.refresh_movies)

    def _on_frame_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.cards_window, width=event.width)
        self._schedule_refresh()

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh_movies(self) -> None:
        self._render_job = None
        query = self._search_text()
        self.movies = self.database.list_movies(query)
        all_count = len(self.database.list_movies())
        shown = len(self.movies)
        self.count_label.configure(text=f"{shown} {'título' if shown == 1 else 'títulos'}" if not query else f"{shown} de {all_count} títulos")
        self._clear_gallery_wallpaper()
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        self.poster_refs = []
        if not self.movies:
            self._empty_state(bool(query))
            if self.wallpaper_path:
                self.after_idle(lambda: self._apply_wallpaper(refresh_shell=False))
            return
        width = max(1, self.canvas.winfo_width())
        columns = max(1, width // (CARD_WIDTH + 20))
        for index, movie in enumerate(self.movies):
            card = self._movie_card(self.cards_frame, movie)
            card.grid(row=index // columns, column=index % columns, padx=(0, 16), pady=(0, 20), sticky="n")
        if self.wallpaper_path:
            self.after_idle(lambda: self._apply_wallpaper(refresh_shell=False))

    def _empty_state(self, searching: bool) -> None:
        c = self.palette
        empty = tk.Frame(self.cards_frame, bg=c["bg"])
        empty.pack(expand=True, pady=70)
        icon = tk.Label(empty, text="▧", bg=c["panel"], fg=c["accent"], font=("Segoe UI", 34), width=3, height=1, pady=10)
        icon.pack(pady=(0, 18))
        if searching:
            title = "No encontramos esa película"
            hint = "Prueba con otro título, género o director."
        else:
            title = "Tu colección comienza aquí"
            hint = "Añade una película y crea tu propia biblioteca de cine."
        tk.Label(empty, text=title, bg=c["bg"], fg=c["text"], font=("Segoe UI Semibold", 17)).pack()
        tk.Label(empty, text=hint, bg=c["bg"], fg=c["muted"], font=("Segoe UI", 10)).pack(pady=(7, 16))
        if not searching:
            self.make_button(empty, "＋  Añadir primera película", self.add_movie).pack()
        else:
            self.make_button(empty, "Limpiar búsqueda", lambda: self.search_var.set(""), secondary=True, small=True).pack()

    def _movie_card(self, parent: tk.Widget, movie: dict[str, Any]) -> tk.Frame:
        c = self.palette
        outer = tk.Frame(parent, bg=c["bg"], width=CARD_WIDTH, height=370)
        outer.pack_propagate(False)
        surface = tk.Frame(outer, bg=c["panel"], highlightthickness=1, highlightbackground=c["border"], cursor="hand2")
        surface.pack(fill="both", expand=True)
        poster = tk.Frame(surface, bg=c["placeholder"], width=POSTER_WIDTH, height=POSTER_HEIGHT)
        poster.pack(padx=17, pady=(16, 12))
        poster.pack_propagate(False)
        cover_path = Path(str(movie.get("cover_path", ""))) if movie.get("cover_path") else None
        photo = None
        if cover_path and cover_path.is_file():
            try:
                photo = load_cover(cover_path, POSTER_WIDTH, POSTER_HEIGHT)
            except Exception:
                photo = None
        if photo is not None:
            image_label = tk.Label(poster, image=photo, bg=c["placeholder"], cursor="hand2")
            image_label.place(relwidth=1, relheight=1)
            self.poster_refs.append(photo)
            poster_children: list[tk.Widget] = [image_label]
        else:
            poster_title = tk.Label(
                poster,
                text="CINE\nAZUL",
                bg=c["placeholder"],
                fg=c["muted"],
                font=("Segoe UI", 17, "bold"),
                justify="center",
                cursor="hand2",
            )
            poster_title.place(relx=0.5, rely=0.48, anchor="center")
            tk.Label(poster, text="▶", bg=c["placeholder"], fg=c["accent"], font=("Segoe UI", 16), cursor="hand2").place(relx=0.5, rely=0.78, anchor="center")
            poster_children = list(poster.winfo_children())

        title = str(movie.get("title") or "Sin título")
        year = str(movie.get("year") or "")
        genre = str(movie.get("genre") or "")
        title_label = tk.Label(surface, text=title, bg=c["panel"], fg=c["text"], font=("Segoe UI Semibold", 11), anchor="w", cursor="hand2", wraplength=176, justify="left")
        title_label.pack(fill="x", padx=17)
        details = "  ·  ".join(part for part in [year, genre] if part) or "Sin detalles"
        detail_label = tk.Label(surface, text=details, bg=c["panel"], fg=c["muted"], font=("Segoe UI", 8), anchor="w", cursor="hand2", wraplength=176, justify="left")
        detail_label.pack(fill="x", padx=17, pady=(4, 9))
        footer = tk.Frame(surface, bg=c["panel"])
        footer.pack(fill="x", padx=17, pady=(0, 13))
        rating = str(movie.get("rating") or "")
        if rating:
            tk.Label(footer, text=f"★  {rating}/10", bg=c["panel"], fg=c["success"], font=("Segoe UI Semibold", 9)).pack(side="left")
        else:
            tk.Label(footer, text="", bg=c["panel"], fg=c["muted"], font=("Segoe UI", 9)).pack(side="left")
        edit = tk.Label(footer, text="Editar", bg=c["panel"], fg=c["accent"], font=("Segoe UI Semibold", 9), cursor="hand2")
        edit.pack(side="right")
        edit.bind("<Button-1>", lambda _e, item=movie: self.edit_movie(item))
        delete = tk.Label(footer, text="Borrar", bg=c["panel"], fg=c["muted"], font=("Segoe UI", 9), cursor="hand2")
        delete.pack(side="right", padx=(0, 10))
        delete.bind("<Button-1>", lambda _e, item=movie: self.delete_movie(item))

        def play(_event: tk.Event | None = None, item: dict[str, Any] = movie) -> None:
            self.play_movie(item)

        for widget in [surface, poster, *poster_children, title_label, detail_label]:
            widget.bind("<Button-1>", play)
        return outer

    def add_movie(self) -> None:
        dialog = MovieDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            try:
                self.database.save_movie(dialog.result)
                self.refresh_movies()
            except sqlite3.Error as error:
                messagebox.showerror("No se pudo guardar", str(error), parent=self)

    def edit_movie(self, movie: dict[str, Any]) -> None:
        dialog = MovieDialog(self, movie)
        self.wait_window(dialog)
        if dialog.result:
            try:
                self.database.save_movie(dialog.result, int(movie["id"]))
                self.refresh_movies()
            except sqlite3.Error as error:
                messagebox.showerror("No se pudo guardar", str(error), parent=self)

    def play_movie(self, movie: dict[str, Any]) -> None:
        raw_path = str(movie.get("file_path") or "").strip()
        if not raw_path:
            if messagebox.askyesno(
                "Falta el archivo de video",
                f"Todavía no has vinculado el archivo de «{movie['title']}». ¿Quieres añadirlo ahora?",
                parent=self,
            ):
                self.edit_movie(movie)
            return
        path = Path(raw_path).expanduser()
        if not path.is_file():
            messagebox.showerror(
                "No se encuentra el video",
                f"No encontramos este archivo:\n{path}\n\nEdita la película para elegir su ubicación actual.",
                parent=self,
            )
            return
        try:
            open_movie_file(path)
        except (OSError, subprocess.SubprocessError) as error:
            messagebox.showerror(
                "No se pudo abrir el video",
                f"CineAzul intentó usar VLC o el reproductor asociado al archivo.\n\n{error}",
                parent=self,
            )

    def delete_movie(self, movie: dict[str, Any]) -> None:
        if messagebox.askyesno("Eliminar película", f"¿Eliminar «{movie['title']}» de tu biblioteca?", parent=self):
            self.database.delete_movie(int(movie["id"]))
            self.refresh_movies()

    def open_database(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Abrir base de datos de CineAzul",
            filetypes=[("Bases SQLite", "*.db *.sqlite *.sqlite3"), ("Todos los archivos", "*.*")],
        )
        if not selected:
            return
        try:
            candidate = MovieDatabase(Path(selected))
        except (sqlite3.Error, OSError, ValueError) as error:
            messagebox.showerror("No se pudo abrir la base de datos", str(error), parent=self)
            return
        self.database = candidate
        self.refresh_movies()

    def import_csv(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Importar películas desde CSV",
            filetypes=[("Archivo CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if not selected:
            return
        try:
            inserted = self.database.import_csv(Path(selected))
            self.refresh_movies()
            messagebox.showinfo("Importación lista", f"Se añadieron {inserted} películas a tu biblioteca.", parent=self)
        except (OSError, csv.Error, ValueError, sqlite3.Error) as error:
            messagebox.showerror("No se pudo importar el CSV", str(error), parent=self)

    def export_csv(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar biblioteca a CSV",
            defaultextension=".csv",
            initialfile="mi_biblioteca_cineazul.csv",
            filetypes=[("Archivo CSV", "*.csv")],
        )
        if not selected:
            return
        try:
            total = self.database.export_csv(Path(selected))
            messagebox.showinfo("Exportación lista", f"Se exportaron {total} películas.", parent=self)
        except (OSError, csv.Error) as error:
            messagebox.showerror("No se pudo exportar", str(error), parent=self)

    def toggle_theme(self) -> None:
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.palette = self.THEMES[self.theme_name]
        self._save_settings()
        if self._render_job:
            self.after_cancel(self._render_job)
            self._render_job = None
        if self._drawer_job:
            try:
                self.after_cancel(self._drawer_job)
            except tk.TclError:
                pass
            self._drawer_job = None
        if self._wallpaper_job:
            try:
                self.after_cancel(self._wallpaper_job)
            except tk.TclError:
                pass
            self._wallpaper_job = None
        for child in self.winfo_children():
            child.destroy()
        self.configure(bg=self.palette["bg"])
        self._build_shell()
        self.refresh_movies()
        self.after_idle(self._apply_wallpaper)
        self.after(120, self._apply_window_chrome)


if __name__ == "__main__":
    try:
        app = CineAzulApp()
        app.mainloop()
    except (OSError, sqlite3.Error, ValueError) as error:
        messagebox.showerror("CineAzul no pudo iniciar", str(error))
        sys.exit(1)
