#!/usr/bin/env python3
"""Logsync – menyradsapp. Startar transkriberingstjänsten; Stäng av stänger den."""
import os, shutil, subprocess, sys, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rumps
import logsync_helper as H

DEFAULT_URL = os.environ.get("LOGSYNC_APP_URL", "https://philipatspoon.github.io/logsync/")
LOG = Path.home() / "Library/Logs/Logsync.log"
MODEL = "mlx-community/whisper-large-v3-turbo"
SUPPORT = Path.home() / "Library/Application Support/Logsync"   # allt appen laddar ner ligger här
APPS = [Path.home() / "Applications/Logsync.app", Path("/Applications/Logsync.app")]


def folder_size(p):
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            fp = os.path.join(root, f)
            if not os.path.islink(fp):
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    return total


def gb(n):
    return f"{n / 1e9:.1f} GB".replace(".", ",")


class App(rumps.App):
    def __init__(self):
        super().__init__("LS", quit_button=None)
        self.status = rumps.MenuItem("Startar …")
        self.storage = rumps.MenuItem("Lagring: räknar …")
        self.menu = [self.status, None,
                     rumps.MenuItem("Öppna Logsync", callback=self.open_app),
                     rumps.MenuItem("Visa logg", callback=self.show_log), None,
                     self.storage, rumps.MenuItem("Visa i Finder", callback=self.show_folder),
                     rumps.MenuItem("Avinstallera Logsync …", callback=self.uninstall), None,
                     rumps.MenuItem("Stäng av", callback=self.stop)]
        self.ready = False
        try:
            self.srv = H.serve()
        except OSError:
            rumps.alert("Logsync", "Tjänsten körs redan (port 47811 är upptagen).")
            sys.exit(0)
        H.ON_QUIT = lambda: rumps.quit_application()
        threading.Thread(target=self.prepare, daemon=True).start()
        threading.Thread(target=self.measure, daemon=True).start()
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

    def measure(self):
        self.storage.title = f"Lagring: {gb(folder_size(SUPPORT))} (modell, Python och paket)"

    def show_folder(self, _):
        subprocess.run(["open", str(SUPPORT)])

    def uninstall(self, _):
        if H.JOB.get("state") == "running":
            rumps.alert("Logsync", "En transkribering pågår. Vänta tills den är klar.")
            return
        size = gb(folder_size(SUPPORT))
        if not rumps.alert("Avinstallera Logsync",
                           f"Tar bort Logsync-appen, Whisper-modellen och allt den har laddat ner ({size}).\n\n"
                           "Manus, loggar och transkript i webbläsaren påverkas inte, och inte heller "
                           "transkriptfilerna bredvid dina kamerafiler.",
                           ok="Avinstallera", cancel="Avbryt"):
            return
        shutil.rmtree(SUPPORT, ignore_errors=True)
        for app in APPS:
            shutil.rmtree(app, ignore_errors=True)
        LOG.unlink(missing_ok=True)
        left = [str(a) for a in APPS if a.exists()]
        rumps.alert("Logsync är avinstallerat",
                    "Allt är borttaget." if not left else
                    "Allt är borttaget utom " + ", ".join(left) + ". Dra den till papperskorgen i Finder.")
        rumps.quit_application()

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
