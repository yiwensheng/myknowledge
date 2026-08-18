"""Native folder picker (local desktop only)."""

from __future__ import annotations


def pick_directory(title: str = "选择外联文档目录") -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return _pick_directory_powershell(title)
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(title=title, mustexist=True)
        return path.strip() if path else None
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def _pick_directory_powershell(title: str) -> str | None:
    import subprocess

    safe_title = title.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = '{safe_title}'
$d.ShowNewFolderButton = $true
if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{ Write-Output $d.SelectedPath }}
"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    path = (r.stdout or "").strip()
    return path or None
