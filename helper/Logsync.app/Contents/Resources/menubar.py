#!/usr/bin/env python3
"""Logsync – menyradsapp. Startar transkriberingstjänsten; Stäng av stänger den."""
import os, subprocess, sys, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rumps
import logsync_helper as H

DEFAULT_URL = os.environ.get("LOGSYNC_APP_URL", "https://philipatspoon.github.io/logsync/")
LOG = Path.home() / "Library/Logs/Logsync.log"
MODEL = "mlx-community/whisper-large-v3-turbo"


class App(rumps.App):
    def __init__(self):
        super().__init__("LS", quit_button=None)
        self.status = rumps.MenuItem("Startar …")
        self.menu = [self.status, None,
                     rumps.MenuItem("Öppna Logsync", callback=self.open_app),
                     rumps.MenuItem("Visa logg", callback=self.show_log), None,
                     rumps.MenuItem("Stäng av", callback=self.stop)]
        self.ready = False
        try:
            self.srv = H.serve()
        except OSError:
            rumps.alert("Logsync", "Tjänsten körs redan (port 47811 är upptagen).")
            sys.exit(0)
        H.ON_QUIT = lambda: rumps.quit_application()
        threading.Thread(target=self.prepare, daemon=True).start()
        rumps.Timer(self.tick, 1).start()

    def prepare(self):
        # Första gången: hämta ffmpeg och Whisper-modellen (~1,6 GB)
        try:
            self.status.title = "Förbereder (första gången: laddar ner modellen) …"
            H.T.ensure_ffmpeg()
            from huggingface_hub import snapshot_download
            snapshot_download(MODEL)
            self.ready = True
        except Exception as e:
            self.status.title = f"⚠ {e}"

    def tick(self, _):
        j = H.JOB
        if j.get("state") == "running":
            self.title = f"LS {round(j.get('pct') or 0)} %"
            self.status.title = j.get("msg") or "Transkriberar …"
        else:
            self.title = "LS"
            if self.ready:
                self.status.title = "Redo – styrs från Logsync i webbläsaren" if j.get("state") != "error" else f"⚠ {j.get('msg')}"

    def open_app(self, _):
        url = H.PAGE_FILE.read_text().strip() if H.PAGE_FILE.exists() else DEFAULT_URL
        if url:
            subprocess.run(["open", url])
        else:
            rumps.alert("Logsync", "Öppna Logsync i Chrome en gång medan appen körs, så kommer den ihåg adressen.")

    def show_log(self, _):
        subprocess.run(["open", "-a", "Console", str(LOG)])

    def stop(self, _):
        if H.JOB.get("state") == "running" and not rumps.alert(
                "Logsync", "En transkribering pågår. Stäng av ändå?", ok="Stäng av", cancel="Avbryt"):
            return
        rumps.quit_application()


if __name__ == "__main__":
    try:  # ingen ikon i Dock, bara i menyraden
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
    App().run()
