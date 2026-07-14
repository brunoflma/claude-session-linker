# -*- coding: utf-8 -*-
# ============================================================================
# setup_gui.py - Instalador visual do Claude Session Linker
# ============================================================================
# Usa somente a stdlib, pois roda antes das dependencias da GUI principal
# existirem. Executa .app\setup.ps1 e mostra o progresso em uma janela com a
# identidade visual do Claude Session Linker.
# ============================================================================
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import font as tkfont

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent


def _load_app_version() -> str:
    # Single source of truth shared with session_linker.py and setup.ps1.
    try:
        return (APP_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


APP_VERSION = _load_app_version()
SETUP_PS1 = APP_DIR / "setup.ps1"
RESULT_FILE = APP_DIR / "logs" / "setup-result.txt"
ICON_PATH = APP_DIR / "icon.ico"
LAUNCHER = ROOT_DIR / "Claude Session Linker.vbs"
PY_DOWNLOAD = "https://www.python.org/downloads/"
NO_WIN = 0x08000000

BG = "#0B0D10"
SURF = "#15181D"
SURF2 = "#1B2027"
SURF3 = "#242A33"
TXT = "#F4EFE3"
TXT2 = "#C8BDAE"
TXT3 = "#8F9BA8"
BRD = "#343A42"
BLUE = "#4FB7C5"
BLUE_H = "#3B9CAA"
GREEN = "#78B87A"
GREEN_H = "#5F9F64"
RED = "#E26D5A"
RED_H = "#BF5747"
YELLOW = "#E2B457"
PAPER = "#F4EFE7"
PAPER2 = "#FCF9F3"
PAPER3 = "#EFE6D8"
INK = "#202226"
INK2 = "#5F5C55"
INK3 = "#8B8174"
LINE = "#DED4C5"


def _rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = min(radius, max(0, (x2 - x1) // 2), max(0, (y2 - y1) // 2))
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=16, **kwargs)


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, bg, hover, fg="#FFFFFF", command=None, width=160, height=36):
        super().__init__(
            parent, width=width, height=height, bg=parent.cget("bg"),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self._bg = bg
        self._hover = hover
        self._command = command
        self._shape = _rounded_rect(self, 1, 1, width - 1, height - 1, 8, fill=bg, outline="")
        self._label = self.create_text(
            width // 2, height // 2, text=text, fill=fg, font=("Segoe UI", 10, "bold"),
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.tag_bind(self._shape, "<Button-1>", self._on_click)
        self.tag_bind(self._label, "<Button-1>", self._on_click)

    def _on_enter(self, _event=None):
        self.itemconfigure(self._shape, fill=self._hover)

    def _on_leave(self, _event=None):
        self.itemconfigure(self._shape, fill=self._bg)

    def _on_click(self, _event=None):
        if self._command:
            self._command()


if sys.platform.startswith("win"):
    try:
        import ctypes
        # Per-monitor V2 keeps Tk usable when the window is moved between
        # displays with different scaling. Older Windows versions fall back.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Claude.SessionLinker.Setup")
    except Exception:
        pass


class SetupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Claude Session Linker - Setup")
        self.configure(bg=PAPER)
        self.resizable(True, True)
        if ICON_PATH.exists():
            try:
                self.iconbitmap(default=str(ICON_PATH))
            except Exception:
                pass

        self._bar_run = False
        self._bar_pos = 0
        self._status_code = None
        self._result_msg = ""

        self.f_title = tkfont.Font(family="Segoe UI", size=17, weight="bold")
        self.f_hero = tkfont.Font(family="Segoe UI", size=19, weight="bold")
        self.f_sub = tkfont.Font(family="Segoe UI", size=10)
        self.f_status = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.f_btn = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_log = tkfont.Font(family="Consolas", size=9)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self._compact = screen_w < 900 or screen_h < 680
        self._build()
        target_w = min(860, max(520, screen_w - 48))
        target_h = min(540, max(440, screen_h - 72))
        self.minsize(min(520, target_w), min(440, target_h))
        self._center(target_w, target_h)
        self.after(80, self._lift_once)
        if "--self-test-finish" not in sys.argv:
            self.after(350, self._start)

    def _build(self):
        shell = tk.Frame(self, bg=PAPER)
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(shell, bg=BG, width=286)
        sidebar.pack(side="top" if self._compact else "left", fill="x" if self._compact else "y")
        if not self._compact:
            sidebar.pack_propagate(False)
        side = tk.Frame(sidebar, bg=BG)
        side.pack(fill="both", expand=True, padx=18 if self._compact else 22, pady=12 if self._compact else 22)

        tk.Label(
            side,
            text="Claude Session Linker",
            bg=BG,
            fg=TXT,
            font=self.f_title,
            anchor="w",
            justify="left",
            wraplength=238,
        ).pack(fill="x")
        tk.Label(
            side,
            text="Prepara o ambiente local para vincular sessões do Code e do Cowork entre contas Claude.",
            bg=BG,
            fg=TXT2,
            font=self.f_sub,
            anchor="w",
            justify="left",
            wraplength=238,
        ).pack(fill="x", pady=(4, 0))

        status_canvas = tk.Canvas(side, height=86, bg=BG, highlightthickness=0, bd=0)
        status_canvas.pack(fill="x", pady=(10 if self._compact else 26, 0))
        _rounded_rect(status_canvas, 1, 1, 241, 85, 10, fill=SURF, outline=BRD)
        status_inner = tk.Frame(status_canvas, bg=SURF)
        status_canvas.create_window(13, 12, window=status_inner, anchor="nw", width=216, height=62)
        self._dot = tk.Canvas(status_inner, width=12, height=12, bg=SURF, highlightthickness=0)
        self._dot.pack(anchor="w")
        self._dot_id = self._dot.create_oval(2, 2, 11, 11, fill=YELLOW, outline="")
        self._status = tk.Label(
            status_inner,
            text="Aguardando setup...",
            bg=SURF,
            fg=TXT,
            font=self.f_status,
            anchor="w",
            justify="left",
            wraplength=206,
        )
        self._status.pack(fill="x", pady=(8, 0))

        self._version_label = tk.Label(
            side,
            text=f"v{APP_VERSION}",
            bg=BG,
            fg=TXT3,
            font=self.f_sub,
            anchor="w",
        )
        self._version_label.pack(side="bottom", fill="x")

        main = tk.Frame(shell, bg=PAPER)
        main.pack(side="top" if self._compact else "left", fill="both", expand=True)

        header = tk.Frame(main, bg=PAPER)
        header.pack(fill="x", padx=22, pady=(22, 14))
        tk.Label(
            header,
            text="Configuração do ambiente",
            bg=PAPER,
            fg=INK,
            font=self.f_hero,
            anchor="w",
            justify="left",
            wraplength=510,
        ).pack(fill="x")
        tk.Label(
            header,
            text="Instala dependências em um venv isolado e verifica a interface.",
            bg=PAPER,
            fg=INK2,
            font=self.f_sub,
            anchor="w",
            justify="left",
            wraplength=510,
        ).pack(fill="x", pady=(2, 0))

        self._bar = tk.Canvas(main, height=4, bg=PAPER3, highlightthickness=0)
        self._bar.pack(fill="x", padx=22, pady=(0, 14))
        self._bar_id = self._bar.create_rectangle(0, 0, 0, 4, fill=BLUE, outline="")

        body = tk.Frame(main, bg=PAPER)
        body.pack(fill="x", padx=22, pady=(0, 10))
        text = (
            "O setup cria um ambiente Python isolado em .app\\venv e instala "
            "as dependências necessárias para abrir a interface."
        )
        tk.Label(
            body,
            text=text,
            bg=PAPER,
            fg=INK2,
            font=self.f_sub,
            anchor="w",
            justify="left",
            wraplength=510,
        ).pack(fill="x")

        logwrap = tk.Frame(main, bg=PAPER)
        logwrap.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        self._log = tk.Text(
            logwrap,
            bg=PAPER2,
            fg=INK2,
            insertbackground=INK,
            font=self.f_log,
            relief="flat",
            borderwidth=0,
            height=10,
            wrap="word",
            padx=10,
            pady=8,
            state="disabled",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=LINE,
        )
        self._log.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(logwrap, command=self._log.yview)
        sb.pack(side="right", fill="y")
        self._log.configure(yscrollcommand=sb.set)

        self._actions = tk.Frame(main, bg=PAPER)
        self._actions.pack(fill="x", padx=22, pady=(0, 18))

    def _flat_button(self, parent, text, bg, hover, fg="#FFFFFF", cmd=None, side="right", width=None):
        if width is None:
            width = max(112, min(230, 24 + len(text) * 8))
        button = RoundedButton(parent, text, bg, hover, fg=fg, command=cmd, width=width, height=36)
        if self._compact:
            button.pack(side="top", anchor="e", pady=(6, 0))
        else:
            button.pack(side=side, padx=(8 if side == "right" else 0, 0))
        return button

    def _center(self, width, height):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        width = min(width, max(320, sw - 32))
        height = min(height, max(320, sh - 48))
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _lift_once(self):
        self.lift()
        self.attributes("-topmost", True)
        self.after(500, lambda: self.attributes("-topmost", False))

    def _append(self, text):
        self._log.configure(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _replace_log(self, text):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_status(self, text, color):
        self._status.configure(text=text)
        self._dot.itemconfigure(self._dot_id, fill=color)

    def _animate_bar(self):
        if not self._bar_run:
            return
        width = self._bar.winfo_width() or 560
        segment = width * 0.28
        self._bar_pos = (self._bar_pos + 8) % (width + segment)
        x0 = self._bar_pos - segment
        self._bar.coords(self._bar_id, x0, 0, self._bar_pos, 4)
        self.after(16, self._animate_bar)

    def _start_bar(self):
        self._bar_run = True
        self._animate_bar()

    def _stop_bar(self, color):
        self._bar_run = False
        width = self._bar.winfo_width() or 560
        self._bar.coords(self._bar_id, 0, 0, width, 4)
        self._bar.itemconfigure(self._bar_id, fill=color)

    def _start(self):
        if not SETUP_PS1.exists():
            self._finish(1, f"setup.ps1 não encontrado em:\n{SETUP_PS1}")
            return
        self._set_status("Configurando ambiente...", BLUE)
        self._append("Iniciando setup do Claude Session Linker...\n")
        self._start_bar()
        threading.Thread(target=self._run_setup, daemon=True).start()

    def _get_system_executable(self, subpath: str) -> str:
        """Securely resolves the path to a system executable without relying on
        PATH or SystemRoot environment variables, preventing binary planting."""
        if sys.platform.startswith("win"):
            try:
                import ctypes
                buf = ctypes.create_unicode_buffer(260)
                length = ctypes.windll.kernel32.GetSystemDirectoryW(buf, 260)
                if length > 0:
                    return os.path.join(buf[:length], subpath)
            except Exception:
                pass
        return os.path.join(r"C:\Windows\System32", subpath)

    def _run_setup(self):
        try:
            powershell_cmd = self._get_system_executable(os.path.join("WindowsPowerShell", "v1.0", "powershell.exe"))
            proc = subprocess.Popen(
                [
                    powershell_cmd,
                    "-NoLogo",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SETUP_PS1),
                ],
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=NO_WIN,
            )
            if proc.stdout is not None:
                for line in proc.stdout:
                    self.after(0, self._append, line)
            proc.wait()
            code = proc.returncode
        except Exception as exc:
            self.after(0, self._finish, 1, f"Falha ao executar o setup:\n{exc}")
            return

        msg = ""
        try:
            raw = RESULT_FILE.read_text(encoding="utf-8-sig").lstrip("\ufeff")
            if raw.startswith("STATUS="):
                first, _, rest = raw.partition("\n")
                try:
                    code = int(first.split("=", 1)[1].strip())
                except Exception:
                    pass
                msg = rest.strip()
            else:
                msg = raw.strip()
        except Exception:
            pass
        self.after(0, self._finish, code, msg)

    def _finish(self, code, msg):
        self._status_code = code
        self._result_msg = msg
        for widget in self._actions.winfo_children():
            widget.destroy()

        low = (msg or "").lower()
        if code == 0:
            self._set_status("Ambiente pronto", GREEN)
            self._stop_bar(GREEN)
            if msg:
                self._replace_log(msg.strip() + "\n")
            self._flat_button(self._actions, "Abrir Claude Session Linker", GREEN, GREEN_H, cmd=self._open_app, width=230)
            self._flat_button(self._actions, "Fechar", SURF3, BRD, fg=TXT, cmd=self.destroy, width=104)
        else:
            self._set_status("Configuração incompleta", RED)
            self._stop_bar(RED)
            if msg:
                self._append("\n" + msg.strip() + "\n")
            if "python.org" in low or "python" in low:
                self._flat_button(self._actions, "Baixar Python", YELLOW, "#C99735", fg=BG, cmd=lambda: self._open(PY_DOWNLOAD), width=136)
            self._flat_button(self._actions, "Tentar novamente", BLUE, BLUE_H, cmd=self._retry, width=160)
            self._flat_button(self._actions, "Fechar", SURF3, BRD, fg=TXT, cmd=self.destroy, side="left", width=104)

    def _retry(self):
        self._replace_log("")
        for widget in self._actions.winfo_children():
            widget.destroy()
        self._start()

    def _open(self, url):
        try:
            os.startfile(url)
        except Exception:
            import webbrowser
            webbrowser.open(url)

    def _open_app(self):
        try:
            if LAUNCHER.exists():
                os.startfile(str(LAUNCHER))
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = SetupApp()
    if "--self-test-finish" in sys.argv:
        try:
            code = int(sys.argv[sys.argv.index("--self-test-finish") + 1])
        except Exception:
            code = 0
        samples = {
            0: "Ambiente pronto. Use o atalho 'Claude Session Linker.vbs' para abrir.",
            2: "Python 3.10+ não encontrado. Instale em https://python.org e tente de novo.",
            4: "Falha ao instalar dependências. Verifique sua conexão e tente novamente.",
        }
        def finish_self_test():
            app._finish(code, samples.get(code, ""))
            if "--self-test-exit" in sys.argv:
                app.after(350, app.destroy)

        app.after(300, finish_self_test)
    app.mainloop()
