#!/usr/bin/env python3
"""
Logsync – hämta branding från en webbplats: namn, logotyper, färger och typsnitt.

En webbsida får inte läsa andra webbplatser, så det här görs av den lokala tjänsten.
Bara standardbiblioteket används.

  python3 branding.py https://exempel.se            # skriver en sammanfattning

Skydd: bara http/https, bara publika adresser (inte den egna datorn eller det
lokala nätverket), storleksgränser på allt som hämtas.
"""
import base64, hashlib, html, ipaddress, json, os, re, socket, sys, urllib.error, urllib.parse, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
MAX_PAGE = 3_000_000
MAX_CSS = 2_000_000
MAX_IMG = 500_000
MAX_FONT = 700_000
ALLOW_LOCAL = os.environ.get("LOGSYNC_ALLOW_LOCAL") == "1"  # bara för tester


class BrandError(Exception):
    pass


# ---------- säker hämtning ----------
def _check(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise BrandError("Adressen måste börja med http:// eller https://")
    if ALLOW_LOCAL:
        return
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise BrandError(f"Hittar inte {u.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise BrandError("Adressen pekar på den egna datorn eller det lokala nätverket")


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check(newurl)  # varje hopp kontrolleras
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_Redirect)


def fetch(url, limit):
    """Hämtar url. Ger (bytes, content_type, slutlig_url)."""
    _check(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "sv,en;q=0.8"})
    try:
        with _opener.open(req, timeout=12) as r:
            data = r.read(limit + 1)
            if len(data) > limit:
                raise BrandError("Filen är för stor")
            return data, (r.headers.get("Content-Type") or "").split(";")[0].strip().lower(), r.geturl(), r.headers.get_content_charset()
    except urllib.error.HTTPError as e:
        raise BrandError(f"Servern svarade {e.code}")
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        raise BrandError(f"Kunde inte nå sidan ({getattr(e, 'reason', e)})")


def fetch_text(url, limit):
    data, ctype, final, charset = fetch(url, limit)
    for enc in (charset, "utf-8", "latin-1"):
        if enc:
            try:
                return data.decode(enc), final
            except (UnicodeDecodeError, LookupError):
                pass
    return data.decode("utf-8", "replace"), final


def data_url(data, ctype):
    return f"data:{ctype};base64,{base64.b64encode(data).decode()}"


# ---------- html ----------
def attrs(tag):
    """Attribut ur en starttagg som dict (namn i gemener)."""
    out = {}
    for m in re.finditer(r'([a-zA-Z_:][\w:.-]*)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', tag):
        out[m.group(1).lower()] = html.unescape(m.group(3) or m.group(4) or m.group(5) or "")
    return out


def meta(page, *names):
    for m in re.finditer(r"<meta\b[^>]*>", page, re.I):
        a = attrs(m.group(0))
        key = (a.get("property") or a.get("name") or "").lower()
        if key in names and a.get("content"):
            return a["content"].strip()
    return ""


def site_name(page, url):
    n = meta(page, "og:site_name", "application-name", "apple-mobile-web-app-title")
    if n:
        return n
    host = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.").split(".")[0]
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    if m:
        t = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
        parts = [p.strip() for p in re.split(r"\s*[|–—·]\s*|\s-\s|:\s", t) if p.strip()]
        same = [p for p in parts if host and host.lower() in p.lower().replace(" ", "")]
        best = min(same or parts or [""], key=len)  # sajtnamnet är delen som liknar adressen, annars den kortaste
        if best and len(best) <= 30:
            return best
    return host.capitalize()


LOGO_RX = re.compile(r"logo|wordmark|brand|logotype|logotyp", re.I)
ICON_RX = re.compile(r"chevron|arrow|menu|burger|search|close|caret|social|facebook|linkedin|instagram|twitter|youtube|play|cart|user|spinner|check", re.I)


def inline_svgs(page):
    """Inbäddade SVG-logotyper, bäst först."""
    symbols = {}
    for m in re.finditer(r"<symbol\b([^>]*)>(.*?)</symbol>", page, re.I | re.S):
        a = attrs(m.group(1))
        if a.get("id"):
            symbols[a["id"]] = (a.get("viewbox"), m.group(2))
    found, seen = [], set()
    for m in re.finditer(r"<svg\b([^>]*)>(.*?)</svg>", page, re.I | re.S):
        open_tag, body = m.group(1), m.group(2)
        if "<symbol" in body.lower():
            continue  # sprite-behållare
        a = attrs(open_tag)
        own = " ".join(a.get(k, "") for k in ("class", "id", "aria-label", "title", "data-name"))
        before = page[max(0, m.start() - 300):m.start()]
        # närmaste omgivande länk/behållare: bara den sista taggen före räknas, annars smittar grannar av sig
        ctx = " ".join(re.findall(r"<(?:a|div|span|h1|header|figure)\b[^>]*>", before)[-2:])
        label_txt = " ".join(re.findall(r'visually-hidden[^>]*>([^<]{1,60})<', before)[-1:])
        score = 0
        if LOGO_RX.search(own):
            score += 4
        if LOGO_RX.search(ctx) or re.search(r"\bhome\b", label_txt, re.I):
            score += 3
        if re.search(r"(^|[\s_-])mark([\s_-]|$)", own, re.I):
            score += 2
        if ICON_RX.search(own) and not LOGO_RX.search(own):
            score -= 4
        if m.start() < len(page) * 0.25:
            score += 1
        if score <= 1:
            continue
        # <use href="#id"> → lägg in symbolens innehåll
        vb = a.get("viewbox")
        def use(mu):
            ua = attrs(mu.group(0))
            ref = (ua.get("href") or ua.get("xlink:href") or "").lstrip("#")
            if ref in symbols:
                nonlocal vb
                vb = vb or symbols[ref][0]
                return symbols[ref][1]
            return ""
        body = re.sub(r"<use\b[^>]*/?>(?:\s*</use>)?", use, body, flags=re.I)
        if not re.search(r"<(path|polygon|rect|circle|ellipse|polyline|line|g)\b", body, re.I):
            continue
        if not vb and a.get("width") and a.get("height"):
            try:
                vb = f"0 0 {float(re.sub(r'[^0-9.]', '', a['width']))} {float(re.sub(r'[^0-9.]', '', a['height']))}"
            except ValueError:
                vb = None
        if not vb:
            continue
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{html.escape(vb)}">{body.strip()}</svg>'
        if len(svg) > 80_000:
            continue
        h = hashlib.md5(re.sub(r"\s+|id=\"[^\"]*\"|data-name=\"[^\"]*\"", "", body).encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        try:
            w, hgt = [float(x) for x in vb.replace(",", " ").split()[2:4]]
            ratio = round(w / hgt, 2) if hgt else 1
        except (ValueError, IndexError):
            ratio = 1
        name = (a.get("aria-label") or a.get("title") or "").strip()
        found.append({"kind": "svg", "svg": svg, "ratio": ratio, "score": score,
                      "label": name or ("Symbol" if 0.8 <= ratio <= 1.25 else "Logotyp")})
    found.sort(key=lambda x: -x["score"])
    return found[:6]


def image_logos(page, base):
    """<img>-logotyper och ikoner, hämtade som data-URL."""
    cands = []
    for m in re.finditer(r"<img\b[^>]*>", page, re.I):
        a = attrs(m.group(0))
        hay = " ".join(a.get(k, "") for k in ("class", "id", "alt", "src", "data-src"))
        src = a.get("src") or a.get("data-src") or (a.get("srcset", "").split(",")[0].split(" ")[0])
        strict = " ".join(a.get(k, "") for k in ("class", "id", "src", "data-src"))
        alt = (a.get("alt") or "").strip()
        # "logo" i en lång bildbeskrivning är ett foto, inte en logotyp
        if src and not src.startswith("data:") and (LOGO_RX.search(strict) or (LOGO_RX.search(alt) and len(alt) <= 40)):
            cands.append((5, urllib.parse.urljoin(base, src), alt[:40] or "Logotyp"))
    for m in re.finditer(r"<link\b[^>]*>", page, re.I):
        a = attrs(m.group(0))
        rel = a.get("rel", "").lower()
        if "icon" in rel and a.get("href"):
            pri = 3 if a["href"].lower().split("?")[0].endswith(".svg") else 2 if "apple-touch" in rel else 1
            cands.append((pri, urllib.parse.urljoin(base, a["href"]), "Ikon"))
    out, seen = [], set()
    for pri, url, label in sorted(cands, key=lambda c: -c[0]):
        if url in seen or len(out) >= 4:
            continue
        seen.add(url)
        try:
            data, ctype, _, _ = fetch(url, MAX_IMG)
        except BrandError:
            continue
        path = urllib.parse.urlsplit(url).path.lower()
        if "svg" in ctype or path.endswith(".svg"):
            txt = data.decode("utf-8", "replace")
            ms = re.search(r"<svg\b.*</svg>", txt, re.I | re.S)
            if ms:
                out.append({"kind": "svg", "svg": ms.group(0), "ratio": 1, "label": label})
            continue
        if not ctype.startswith("image/"):
            ctype = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
                     "ico": "image/x-icon", "gif": "image/gif"}.get(path.rsplit(".", 1)[-1], "")
        if ctype:
            out.append({"kind": "img", "src": data_url(data, ctype), "ratio": 1, "label": label})
    return out


# ---------- css ----------
def stylesheets(page, base):
    """All CSS: inbäddad och upp till fyra länkade stilmallar. Ger [(css, bas-url)]."""
    out = [(m.group(1), base) for m in re.finditer(r"<style\b[^>]*>(.*?)</style>", page, re.I | re.S)]
    n = 0
    for m in re.finditer(r"<link\b[^>]*>", page, re.I):
        a = attrs(m.group(0))
        if "stylesheet" in a.get("rel", "").lower() and a.get("href") and n < 4:
            url = urllib.parse.urljoin(base, a["href"])
            try:
                css, final = fetch_text(url, MAX_CSS)
                out.append((css, final))
                n += 1
            except BrandError:
                pass
    return out


def _hex(c):
    c = c.lower()
    if len(c) == 4:
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c[:7]


def _hsl(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    s = 0 if mx == mn else (mx - mn) / (1 - abs(2 * l - 1) + 1e-9)
    return s, l


def colors(sheets, page):
    """Sidans färger: namngivna (brand/primary/accent) först, sedan de vanligaste mättade."""
    count, named = {}, {}
    for css, _ in sheets:
        for m in re.finditer(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3}\b|#[0-9a-fA-F]{6}\b)", css):
            named.setdefault(_hex(m.group(2)), m.group(1))
        for m in re.finditer(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", css):
            h = _hex(m.group(0))
            count[h] = count.get(h, 0) + 1
        for m in re.finditer(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})", css):
            h = "#%02x%02x%02x" % tuple(min(255, int(x)) for x in m.groups())
            count[h] = count.get(h, 0) + 1
    theme = meta(page, "theme-color")
    if re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", theme or ""):
        count[_hex(theme)] = count.get(_hex(theme), 0) + 50
        named.setdefault(_hex(theme), "theme-color")
    scored = []
    for h, n in count.items():
        s, l = _hsl(h)
        var = named.get(h, "")
        boost = 40 if re.search(r"brand|primary|accent|theme|main", var, re.I) else 6 if var else 0
        if s < 0.25 or l < 0.12 or l > 0.93:
            continue  # grått, svart och vitt är inte en accentfärg
        scored.append((n + boost + s * 4, h, var))
    scored.sort(reverse=True)
    out, picked = [], []
    for _, h, var in scored:
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        if any(abs(r - pr) + abs(g - pg) + abs(b - pb) < 40 for pr, pg, pb in picked):
            continue  # nästan samma som en redan vald
        picked.append((r, g, b))
        out.append({"hex": h, "name": var.lstrip("-")})
        if len(out) >= 10:
            break
    return out


GENERIC = {"serif", "sans-serif", "monospace", "system-ui", "cursive", "fantasy", "inherit", "initial", "ui-sans-serif",
           "ui-serif", "ui-monospace", "-apple-system", "blinkmacsystemfont", "arial", "helvetica", "helvetica neue",
           "times", "times new roman", "georgia", "verdana", "tahoma", "segoe ui", "roboto", "courier", "courier new"}
ICONFONT = re.compile(r"icon|awesome|material|glyph|swiper|slick|symbol|emoji|fa-", re.I)


def fonts(sheets, want_data):
    """Sidans huvudtypsnitt: familj och dess @font-face-filer."""
    faces = {}
    for css, base in sheets:
        for m in re.finditer(r"@font-face\s*\{([^}]*)\}", css, re.I | re.S):
            body = m.group(1)
            fam = re.search(r"font-family\s*:\s*([^;]+)", body, re.I)
            src = re.search(r"src\s*:\s*([^;]+(?:;\s*src\s*:[^;]+)?)", body, re.I)
            if not fam or not src:
                continue
            family = fam.group(1).strip().strip("\"'")
            if ICONFONT.search(family):
                continue
            style = (re.search(r"font-style\s*:\s*([\w-]+)", body, re.I) or [None, "normal"])[1].lower()
            wm = re.search(r"font-weight\s*:\s*([^;]+)", body, re.I)
            wtxt = (wm.group(1).strip().lower() if wm else "400").replace("normal", "400").replace("bold", "700")
            nums = [int(x) for x in re.findall(r"\d{3}", wtxt)] or [400]
            weight = f"{nums[0]} {nums[-1]}" if len(nums) > 1 else str(nums[0])  # intervall = variabelt typsnitt
            urls = re.findall(r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)(?:\s*format\(\s*[\"']?([\w-]+)[\"']?\s*\))?", body, re.I)
            best = None
            for u, fmt in urls:
                if u.startswith("data:"):
                    continue
                ext = (fmt or urllib.parse.urlsplit(u).path.rsplit(".", 1)[-1]).lower()
                rank = {"woff2": 0, "woff": 1, "truetype": 2, "ttf": 2, "opentype": 3, "otf": 3}.get(ext)
                if rank is not None and (best is None or rank < best[0]):
                    best = (rank, urllib.parse.urljoin(base, u), {"truetype": "ttf", "opentype": "otf"}.get(ext, ext))
            if best and style == "normal":
                faces.setdefault(family, {})[weight] = {"weight": weight, "url": best[1], "format": best[2]}
    if not faces:
        return None
    # Huvudtypsnitt: det som body/html/:root pekar på, annars familjen med flest vikter
    use = {}
    for css, _ in sheets:
        for m in re.finditer(r"(?:^|[},\s])(body|html|:root|h1|h2)\b[^{}]*\{([^}]*)\}", css, re.I):
            for fm in re.finditer(r"(?:font-family|--[\w-]*font[\w-]*)\s*:\s*([^;}]+)", m.group(2), re.I):
                for i, name in enumerate(n.strip().strip("\"'") for n in fm.group(1).split(",")):
                    if name in faces:
                        use[name] = use.get(name, 0) + (3 if i == 0 else 1)
    family = max(use, key=use.get) if use else max(faces, key=lambda f: len(faces[f]))
    out = {"family": family, "faces": []}
    order = sorted(faces[family].values(), key=lambda f: abs(int(f["weight"].split()[0]) - 450))  # närmast normal/medium först
    for f in sorted(order[:6], key=lambda f: int(f["weight"].split()[0])):
        face = {"weight": f["weight"], "format": f["format"], "name": urllib.parse.unquote(urllib.parse.urlsplit(f["url"]).path.rsplit("/", 1)[-1])}
        if want_data:
            try:
                data, _, _, _ = fetch(f["url"], MAX_FONT)
                face["data"] = data_url(data, "font/" + f["format"])
            except BrandError:
                continue
        out["faces"].append(face)
    return out if out["faces"] else None


# ---------- huvudfunktion ----------
def fetch_brand(url, want_fonts=True):
    url = (url or "").strip()
    if not url:
        raise BrandError("Ange en webbadress")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    page, final = fetch_text(url, MAX_PAGE)
    sheets = stylesheets(page, final)
    logos = inline_svgs(page) + image_logos(page, final)
    for l in logos:
        l.pop("score", None)
    return {"url": final, "name": site_name(page, final), "logos": logos[:8],
            "colors": colors(sheets, page), "font": fonts(sheets, want_fonts)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        b = fetch_brand(sys.argv[1], want_fonts=False)
    except BrandError as e:
        sys.exit(f"Fel: {e}")
    print("Namn:     ", b["name"])
    print("Logotyper:", ", ".join(f"{l['label']} ({l['kind']}, {l['ratio']})" for l in b["logos"]) or "–")
    print("Färger:   ", ", ".join(c["hex"] + (f" ({c['name']})" if c["name"] else "") for c in b["colors"]) or "–")
    print("Typsnitt: ", f"{b['font']['family']} – vikter {', '.join(f['weight'] for f in b['font']['faces'])}" if b["font"] else "–")
