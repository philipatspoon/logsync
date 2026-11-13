#!/usr/bin/env python3
"""
Logsync – transkribera kamerafiler (MXF/MOV/MP4) med kamerans tidskod.

  python3 transkribera.py KLIPP.MXF [fler filer …] --kanaler "1=Värd,2=Gäst"

För varje fil:
  1. ffprobe läser start-tidskod, bildfrekvens och ljudkanaler.
  2. ffmpeg plockar ut varje myggkanal som 16 kHz mono-wav (bilden rörs inte).
  3. mlx-whisper transkriberar varje kanal för sig, med tid per ord.
  4. Överhörning rensas: ett ord behålls bara om dess egen kanal är högst
     just då (den andra myggan hör alltid lite av samma röst).
  5. Varje ord får kamerans tidskod = filens start-TC + ordets tid.

Ut (bredvid första filen, eller i --ut):
  <namn>_transkript.json  – för appen och Claude (ord, repliker, tidskoder)
  <namn>_transkript.md    – läsbart, en replik per rad med kamera-TC
"""
import argparse, json, os, re, subprocess, sys, tempfile, threading, time, wave
from pathlib import Path

MODEL_DEFAULT = "mlx-community/whisper-large-v3-turbo"
CANCEL = threading.Event()   # sätts av hjälptjänsten när användaren avbryter


class Cancelled(Exception):
    pass


def check_cancel():
    if CANCEL.is_set():
        raise Cancelled()


# ---------- tidskod ----------
def parse_fps(s):
    if not s or s in ("0/0",):
        return None
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b) if float(b) else None
    return float(s)


def tc_to_frames(tc, nom):
    h, m, s, f = map(int, re.split(r"[:;.]", tc))
    return ((h * 60 + m) * 60 + s) * nom + f


def frames_to_tc(fr, nom):
    fr = int(fr) % (24 * 3600 * nom)
    f = fr % nom
    s = fr // nom
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


# ---------- probe ----------
def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    streams = j.get("streams", [])
    fmt = j.get("format", {})
    # start-tidskod: format-tagg, videoström, eller separat tmcd/data-ström
    tc = (fmt.get("tags") or {}).get("timecode")
    for s in streams:
        tc = tc or (s.get("tags") or {}).get("timecode")
    vid = next((s for s in streams if s.get("codec_type") == "video"), None)
    fps = None
    if vid:
        fps = parse_fps(vid.get("r_frame_rate")) or parse_fps(vid.get("avg_frame_rate"))
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    # kanallista: (etikett 1…N, ffmpeg-map, pan-filter eller None)
    chans = []
    for ai, s in enumerate(audio):
        n = int(s.get("channels") or 1)
        for c in range(n):
            chans.append({"n": len(chans) + 1, "map": f"0:a:{ai}",
                          "pan": None if n == 1 else f"pan=mono|c0=c{c}"})
    return {
        "path": str(path),
        "start_tc": tc,
        "fps": fps,
        "duration": float(fmt.get("duration") or 0),
        "channels": chans,
        "video": f"{vid.get('codec_name')} {vid.get('width')}x{vid.get('height')}" if vid else None,
    }


def extract(path, ch, out_wav):
    extract_all(path, [(ch, out_wav)])


def extract_all(path, jobs):
    """Plockar ut flera ljudkanaler i EN genomläsning av filen.
    Ljudet ligger invävt med bilden, så varje genomläsning läser hela filen (ofta tiotals GB)."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(path)]
    for ch, out_wav in jobs:
        cmd += ["-map", ch["map"], "-vn", "-sn", "-dn"]
        if ch["pan"]:
            cmd += ["-af", ch["pan"]]
        cmd += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)]
    check_cancel()
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    while proc.poll() is None:          # vänta, men avbryt direkt om användaren ber om det
        if CANCEL.is_set():
            proc.kill(); proc.wait()
            raise Cancelled()
        time.sleep(0.3)
    if proc.returncode:
        err = proc.stderr.read().decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("ffmpeg: " + (err[-1] if err else f"fel {proc.returncode}"))


# ---------- energi (för överhörning) ----------
def load_wav(p):
    import numpy as np
    with wave.open(str(p)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return a


def db(sig, t0, t1, sr=16000):
    import numpy as np
    a, b = max(0, int(t0 * sr)), max(int(t0 * sr) + 1, int(t1 * sr))
    x = sig[a:b]
    if not len(x):
        return -120.0
    return float(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9))


# ---------- transkribering ----------
def transcribe(wav, model, lang):
    import mlx_whisper
    r = mlx_whisper.transcribe(
        str(wav), path_or_hf_repo=model, language=lang, word_timestamps=True,
        condition_on_previous_text=False,  # minskar hallucinerade upprepningar i tystnad
        no_speech_threshold=0.6, verbose=None)
    words = []
    for seg in r.get("segments", []):
        for w in seg.get("words", []):
            t = w["word"].strip()
            if t:
                words.append({"start": float(w["start"]), "end": float(w["end"]), "text": t,
                              "p": round(float(w.get("probability", 0)), 2)})
    return words


def build_turns(words, gap=1.2):
    """Slå ihop ord till repliker: samma talare och mindre än `gap` s paus."""
    turns = []
    for w in words:
        t = turns[-1] if turns else None
        if t and t["speaker"] == w["speaker"] and w["start"] - t["end"] < gap:
            t["text"] += " " + w["text"]
            t["end"] = w["end"]
            t["out_tc"] = w["out_tc"]
        else:
            turns.append({"speaker": w["speaker"], "start": w["start"], "end": w["end"],
                          "tc": w["tc"], "out_tc": w["out_tc"], "text": w["text"]})
    return turns


def process(path, names, model, lang, margin, keep_tmp, progress=None):
    say = progress or (lambda stage, msg, pct=None: None)
    info = probe(path)
    if not info["start_tc"]:
        print(f"  ⚠ Ingen tidskod i {path.name} – använder 00:00:00:00", file=sys.stderr)
    fps = info["fps"] or 25.0
    nom = round(fps)
    start = tc_to_frames(info["start_tc"] or "00:00:00:00", nom)
    chans = [c for c in info["channels"] if c["n"] in names]
    if not chans:
        sys.exit(f"Hittar inga av kanalerna {sorted(names)} i {path.name} "
                 f"(filen har {len(info['channels'])} ljudkanaler).")
    print(f"• {path.name}: start {info['start_tc']} · {fps:g} fps · {info['duration']/60:.1f} min · "
          f"{len(info['channels'])} ljudkanaler · använder " + ", ".join("K%d=%s" % (c["n"], names[c["n"]]) for c in chans))

    tmp = Path(tempfile.mkdtemp(prefix="logsync_"))
    try:
        return _process(path, names, model, lang, margin, keep_tmp, say, info, fps, nom, start, chans, tmp)
    finally:
        if not keep_tmp:   # städa även när det avbryts eller går fel
            for f in tmp.iterdir():
                f.unlink()
            tmp.rmdir()


def _process(path, names, model, lang, margin, keep_tmp, say, info, fps, nom, start, chans, tmp):
    sig, raw = {}, {}
    wavs = {c["n"]: tmp / f"ch{c['n']}.wav" for c in chans}
    size = path.stat().st_size / 1e9
    say("ljud", f"{path.name}: plockar ut ljudet ({size:.0f} GB läses en gång)".replace(".", ","))
    extract_all(path, [(c, wavs[c["n"]]) for c in chans])
    for i, c in enumerate(chans):
        wav = wavs[c["n"]]
        sig[c["n"]] = load_wav(wav)
        check_cancel()
        say("whisper", f"{path.name}: transkriberar {names[c['n']]}", (i, len(chans)))
        raw[c["n"]] = transcribe(wav, model, lang)

    words, dropped = [], 0
    for n, ws in raw.items():
        for w in ws:
            own = db(sig[n], w["start"], w["end"])
            other = max((db(sig[m], w["start"], w["end"]) for m in sig if m != n), default=-120)
            if own < other - margin:  # rösten är högre i den andra myggan = överhörning
                dropped += 1
                continue
            w = dict(w, speaker=names[n], channel=n,
                     tc=frames_to_tc(start + round(w["start"] * fps), nom),
                     out_tc=frames_to_tc(start + round(w["end"] * fps), nom),
                     file=path.name)
            words.append(w)
    words.sort(key=lambda w: w["start"])
    print(f"  {len(words)} ord · {dropped} borttagna som överhörning")
    return info, words


def run(files, names, lang="en", model=MODEL_DEFAULT, margin=3.0, out_dir=None, base=None, keep_tmp=False, progress=None):
    """Transkribera filerna och skriv .json + .md. Returnerar JSON-datat."""
    ensure_ffmpeg()
    allw, srcs = [], []
    for f in files:
        info, words = process(f, names, model, lang, margin, keep_tmp, progress)
        srcs.append({k: info[k] for k in ("path", "start_tc", "fps", "duration", "video")})
        allw += words
    nom = round(srcs[0]["fps"] or 25)
    allw.sort(key=lambda w: tc_to_frames(w["tc"], nom))
    turns = build_turns(allw)
    out_dir = Path(out_dir) if out_dir else files[0].parent
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base or files[0].stem
    j = {"format": "logsync-transkript/1", "timecode": "kamerans tidskod (filens start-TC + ordets tid)",
         "fps": srcs[0]["fps"], "language": lang, "model": model, "speakers": list(names.values()),
         "sources": srcs, "turns": turns, "words": allw}
    jp = out_dir / f"{base}_transkript.json"
    jp.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Transkript – {base}", "",
          f"- Tidskod: kamerans (från filens start-TC), {srcs[0]['fps']:g} fps",
          "- Talare per kanal: " + ", ".join("K%d = %s" % (k, v) for k, v in names.items()),
          "- Filer: " + " · ".join("%s (%s)" % (Path(s['path']).name, s['start_tc']) for s in srcs), ""]
    md += [f"`{t['tc']}` **{t['speaker']}:** {t['text']}  " for t in turns]
    mp = out_dir / f"{base}_transkript.md"
    mp.write_text("\n".join(md), encoding="utf-8")
    j["files_written"] = [str(jp), str(mp)]
    return j


def ensure_ffmpeg():
    import shutil
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    try:  # ffmpeg/ffprobe utan Homebrew – laddas ner första gången
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        sys.exit("Hittar inte ffmpeg. Starta Logsync-appen en gång så hämtas det, eller installera ffmpeg.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("filer", nargs="+", type=Path, help="MXF/MOV-filer från kameran (eller en mapp)")
    ap.add_argument("--kanaler", default="1=Värd,2=Gäst", help='T.ex. "1=Anna,2=Elin" (kamerans ljudkanal=namn)')
    ap.add_argument("--sprak", default="en", help="Språkkod, t.ex. en eller sv")
    ap.add_argument("--modell", default=MODEL_DEFAULT)
    ap.add_argument("--marginal", type=float, default=3.0,
                    help="dB: hur mycket svagare ett ords egen kanal får vara och ändå behållas (överlapp)")
    ap.add_argument("--ut", type=Path, help="Mapp för resultat (standard: bredvid första filen)")
    ap.add_argument("--namn", help="Basnamn för resultatfilerna (standard: första filens namn)")
    ap.add_argument("--behall-wav", action="store_true")
    a = ap.parse_args()

    names = {}
    for part in a.kanaler.split(","):
        k, v = part.split("=", 1)
        names[int(k.strip())] = v.strip()

    files = []
    for f in a.filer:
        files += sorted(p for p in f.iterdir() if p.suffix.lower() in (".mxf", ".mov", ".mp4")) if f.is_dir() else [f]
    if not files:
        sys.exit("Inga filer.")

    j = run(files, names, a.sprak, a.modell, a.marginal, a.ut, a.namn, a.behall_wav,
            progress=lambda stage, msg, pct=None: print("  " + msg + " …", flush=True))
    print("\n✓ Klart:\n  " + "\n  ".join(j["files_written"]))


if __name__ == "__main__":
    main()
