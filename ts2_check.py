#!/usr/bin/env python3
"""
ts2_check.py -- Touchstone 2 (Client Website Structure Build) self-checker.

Checks two different things, which is the whole point:
  1. Is the HTML well-formed / correctly nested?  (plus optional --w3c: real
     validation against the W3C Nu validator, same engine as validator.w3.org)
  2. Does it actually contain every element the TS2 instructions demand,
     placed where the chosen client's brief asks for it?

Usage:
    python3 ts2_check.py                # check all *.html in current folder
    python3 ts2_check.py .              # check all *.html in a folder
    python3 ts2_check.py index.html about.html
    python3 ts2_check.py . --w3c        # also run the W3C validator (needs net)
    python3 ts2_check.py . --client yoga   # force client (bakery|yoga|rescue)

Exit code 0 = no errors. Read WARNs too; several of them are rubric points.
Tooling only -- it checks your code, it does not write it.
"""

import html.parser
import json
import os
import re
import subprocess
import sys
import urllib.request

# ---------------------------------------------------------------- clients ---
# Real filenames as they appear inside the provided ZIPs (note the "_c" suffix
# and that images are .png, NOT .jpg as the brief's text says).
CLIENTS = {
    "bakery": {
        "name": "North Star Bakery",
        "pages": {"products": "products.html"},
        "assets": [
            "bakery-logo_c.png", "bakery-storefront_c.png", "bakery-bread_c.png",
            "bakery-signature-loaf_c.png", "bakery-feature-small_c.png",
            "bakery-feature-large_c.png", "bakery-welcome_c.mp3",
            "bakery-welcome-mixed_c.mp3", "bakery-behind-scenes_c.mp4",
        ],
        "figure_hint": "signature loaf",
        "form_fields": ["name", "email", "date", "item", "allerg"],
    },
    "yoga": {
        "name": "Riverbend Yoga Studio",
        "pages": {"services": "services.html", "fourth": "events.html"},
        "assets": [
            "yoga-logo_c.png", "yoga-studio_c.png", "yoga-instructor_c.png",
            "yoga-workshop_c.png", "yoga-feature-small_c.png",
            "yoga-feature-large_c.png", "yoga-breathing_c.mp3",
            "yoga-intro_c.mp4",
        ],
        "figure_hint": "workshop",
        "form_fields": ["name", "email", "class", "level", "contact method", "message"],
    },
    "rescue": {
        "name": "Twin Cities Animal Rescue",
        "pages": {"services": "services.html"},
        "assets": [
            "rescue-logo_c.png", "rescue-pet_c.png", "rescue-volunteer_c.png",
            "rescue-pet-spotlight_c.png", "rescue-feature-small_c.png",
            "rescue-feature-large_c.png", "rescue-message_c.mp3",
            "rescue-message_c.mp4",
        ],
        "figure_hint": "pet spotlight",
        "form_fields": ["name", "email", "interest", "availability", "experience", "message"],
    },
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
FORM_CONTROLS = {"input", "select", "textarea"}
MEDIA_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp3",
             ".mp4", ".ogg", ".wav", ".webm", ".m4a")


# ------------------------------------------------------------------ parser --
class Page(html.parser.HTMLParser):
    def __init__(self, src, name):
        super().__init__(convert_charrefs=True)
        self.src, self.name = src, name
        self.stack, self.elems, self.problems = [], [], []
        self.text_in = {}          # tag -> accumulated text (audio/video fallback)
        self.doctype = False
        self.feed(src)
        self.feed("\n" * 4)        # flush any dangling end tag handling
        self.close()

    def handle_decl(self, decl):
        if decl.strip().lower().startswith("doctype"):
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        a = {}
        for k, v in attrs:
            a[k.lower()] = v if v is not None else ""
        line = self.getpos()[0]
        path = [t for t, _ in self.stack]
        self.elems.append(El(tag, a, line, path))
        if tag not in VOID:
            self.stack.append((tag, line))

    def handle_startendtag(self, tag, attrs):          # <img />
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        line = self.getpos()[0]
        open_tags = [t for t, _ in self.stack]
        if tag in open_tags:
            while self.stack:
                t, ln = self.stack.pop()
                if t == tag:
                    break
                if t not in ("p", "li", "dt", "dd", "option", "thead", "tbody",
                             "tfoot", "tr", "td", "th"):
                    self.problems.append(
                        f"line {ln}: <{t}> is never closed -- <{tag}> on line {line} "
                        f"was found first. Fix the nesting.")
            return
        self.problems.append(f"line {line}: stray closing </{tag}> with no matching opening tag.")

    def handle_data(self, data):
        if data.strip():
            for t, _ in self.stack:
                if t in ("audio", "video"):
                    self.text_in[t] = self.text_in.get(t, "") + data.strip() + " "

    def finish(self):
        for t, ln in self.stack:
            if t not in ("html", "body", "p", "li", "tbody", "tr", "td",
                         "thead", "tfoot", "option", "dt", "dd", "th"):
                self.problems.append(f"line {ln}: <{t}> is left unclosed at end of file.")
        self.stack = []


class El:
    __slots__ = ("tag", "a", "line", "path")

    def __init__(self, tag, a, line, path):
        self.tag, self.a, self.line, self.path = tag, a, line, path

    def in_(self, *anc):
        return any(p in anc for p in self.path)


# ----------------------------------------------------------------- helpers --
def strip_comments(text):
    """Comments are not content: <figure> inside a TODO must not count as done."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def local(path):
    return path.split("?")[0].split("#")[0]


def is_remote(path):
    return bool(re.match(r"^(https?:)?//|^data:|^mailto:|^tel:|^#", path or ""))


def label_for(el, labels_for, labels_wrapping):
    return el.a.get("id", "") in labels_for or (el.a.get("id", "") in labels_wrapping
                                                or el.a.get("name", "") in labels_wrapping)


def check_page(p, page_files, client):
    """Return list of (level, message). level: ERR / WARN / OK / INFO"""
    out = []
    E = p.elems
    has = lambda t: [e for e in E if e.tag == t]
    one = lambda t: has(t)

    # ---- boilerplate -------------------------------------------------------
    if not p.doctype:
        out.append(("ERR", "missing <!DOCTYPE html> as the very first line."))
    html_el = has("html")
    if not html_el:
        out.append(("ERR", "no <html> element."))
    elif not html_el[0].a.get("lang"):
        out.append(("ERR", "<html> has no lang=\"en\" -- a real accessibility failure."))
    if not any(e.a.get("charset", "").lower().replace('"', "") == "utf-8" for e in has("meta")):
        out.append(("ERR", 'missing <meta charset="utf-8">.'))
    if not has("title"):
        out.append(("ERR", "missing <title>."))
    elif re.search(r"<title>\s*</title>", p.src, re.I):
        out.append(("WARN", "<title> is empty -- name the page and the client, "
                            "e.g. \"Services | Riverbend Yoga Studio\"."))
    if not any(e.a.get("name") == "viewport" for e in has("meta")):
        out.append(("WARN", 'no <meta name="viewport" ...>; standard boilerplate, include it.'))

    # ---- structure ---------------------------------------------------------
    for tag, why in (("header", "page header"), ("nav", "navigation"),
                     ("main", "unique main landmark"), ("footer", "page footer")):
        n = len(one(tag))
        if n == 0:
            out.append(("ERR", f"no <{tag}> ({why})."))
        elif tag == "main" and n > 1:
            out.append(("ERR", f"{n} <main> elements -- exactly one per page."))
    for tag in ("header", "nav", "footer"):
        for e in one(tag):
            if e.in_("main"):
                out.append(("WARN", f"line {e.line}: <{tag}> is inside <main>; "
                                    f"it belongs outside it."))

    h1 = one("h1")
    if len(h1) == 0:
        out.append(("ERR", "no <h1> on this page."))
    elif len(h1) > 1:
        out.append(("ERR", f"{len(h1)} <h1> elements -- TS2 requires exactly one per page."))

    # heading order, no skipped levels
    prev = 0
    for e in E:
        if re.fullmatch(r"h[1-6]", e.tag):
            lvl = int(e.tag[1])
            if prev and lvl > prev + 1:
                out.append(("WARN", f"line {e.line}: <{e.tag}> jumps from h{prev} "
                                    f"-- go one level at a time."))
            prev = lvl

    # ---- navigation --------------------------------------------------------
    navs = one("nav")
    if navs:
        n = navs[0]
        if not any(e.tag == "ul" and e.in_("nav") for e in E):
            out.append(("ERR", "nav has no <ul> list; instructions require an unordered list."))
        links = [e for e in E if e.tag == "a" and e.in_("nav")]
        if not links:
            out.append(("ERR", "nav contains no links."))
        hrefs = {local(e.a.get("href", "")) for e in links}
        for e in links:
            href = e.a.get("href", "")
            f = local(href)
            if not href:
                out.append(("ERR", f"line {e.line}: nav link with an empty href."))
            elif href.startswith("#"):
                out.append(("WARN", f"line {e.line}: nav link \"{href}\" is an in-page jump, "
                                    f"not one of the four pages."))
            elif is_remote(href) or href.startswith("/") or re.match(r"^[A-Za-z]:", href):
                out.append(("ERR", f"line {e.line}: \"{href}\" is not a relative path "
                                   f"(no http…, no leading /, no drive letter)."))
            elif f not in page_files and os.sep + f not in page_files:
                out.append(("ERR", f"line {e.line}: nav links to \"{f}\" which is not one "
                                   f"of your html files (typo or wrong name)."))
        missing = [f for f in page_files if f != p.name and f not in hrefs]
        if missing:
            out.append(("ERR", "nav does not link to: " + ", ".join(sorted(missing))
                        + " -- every page must reach every other page."))

    # ---- images ------------------------------------------------------------
    imgs = [e for e in E if e.tag == "img"]
    for e in imgs:
        alt = (e.a.get("alt") or "").strip()
        if "alt" not in e.a:
            out.append(("ERR", f"line {e.line}: <img> has no alt attribute at all."))
        elif not alt and e.in_("picture") is False:
            out.append(("WARN", f"line {e.line}: <img alt=\"\"> -- empty alt is only right "
                                f"for a purely decorative image; TS2 wants meaningful text."))
        elif re.fullmatch(r"(image|photo|pic|picture|img)?\s*(of|of a|of an)?\s*[\w.-]*"
                          r"(\.png|\.jpg|\.jpeg)?", alt, re.I) or alt.lower().endswith(
                          (".png", ".jpg", ".jpeg")):
            out.append(("WARN", f"line {e.line}: alt=\"{alt}\" is the filename or a "
                                f"placeholder, not a description of this client's content."))
        elif len(alt) < 15:
            out.append(("WARN", f"line {e.line}: alt=\"{alt}\" is thin -- say what it shows "
                                f"and why it matters to the client."))
        src = e.a.get("src", "")
        if not src:
            out.append(("ERR", f"line {e.line}: <img> with no src."))
        elif not is_remote(src):
            out.append(check_asset(p, src, e.line, client, "img src"))
    if len([e for e in imgs]) < 1:
        out.append(("WARN", "no <img> on this page."))

    # ---- figure / figcaption ----------------------------------------------
    for e in one("figure"):
        if not any(c.tag == "figcaption" and c.in_("figure") for c in E):
            out.append(("ERR", f"line {e.line}: <figure> with no <figcaption> inside it."))
        elif client and not any(k in strip_comments(p.src).lower()
                                for k in client["figure_hint"].split()):
            out.append(("INFO", f"line {e.line}: figure found; brief wants it to feature the "
                                f"\"{client['figure_hint']}\" -- make the caption say that."))
    for e in one("figcaption"):
        if not e.in_("figure"):
            out.append(("ERR", f"line {e.line}: <figcaption> outside a <figure>."))

    # ---- picture / responsive image ---------------------------------------
    for e in one("picture"):
        sources = [s for s in E if s.tag == "source" and s.in_("picture")]
        if not sources:
            out.append(("ERR", f"line {e.line}: <picture> with no <source>; that is not a "
                               f"responsive image, that is just an image."))
        for s in sources:
            if not (s.a.get("srcset") or s.a.get("media") or s.a.get("type")):
                out.append(("ERR", f"line {s.line}: <source> inside <picture> has no "
                                   f"srcset/media attribute."))
            srcset = s.a.get("srcset", "")
            for cand in srcset.split(","):
                cand = local(cand.strip().split()[0]) if cand.strip() else ""
                if cand and not is_remote(cand):
                    out.append(check_asset(p, cand, s.line, client, "source srcset"))
        if not any(i.tag == "img" and i.in_("picture") for i in E):
            out.append(("ERR", f"line {e.line}: <picture> is missing the fallback <img>."))
        has_rule = any(s.a.get("media") for s in sources) or \
            any(re.search(r"\d+w", s.a.get("srcset", "")) for s in sources)
        if not has_rule:
            out.append(("WARN", "no <source> in this <picture> has a media=\"(max-width: 600px)\" "
                                "rule or a w-descriptor srcset, so the browser has no reason "
                                "to pick the small file. This is the check that proves the "
                                "image is actually responsive."))

    # ---- audio / video -----------------------------------------------------
    for e in one("audio") + one("video"):
        if not (e.a.get("src") or any(c.tag == "source" and c.in_(e.tag) for c in E)):
            out.append(("ERR", f"line {e.line}: <{e.tag}> has no src and no <source> child."))
        if e.a.get("src") and not is_remote(e.a["src"]):
            out.append(check_asset(p, e.a["src"], e.line, client, e.tag + " src"))
        if "controls" not in e.a:
            out.append(("WARN", f"line {e.line}: <{e.tag}> has no controls attribute -- "
                                f"visitors cannot play it."))
        if not (p.text_in.get(e.tag) or "").strip():
            out.append(("ERR", f"line {e.line}: <{e.tag}> has no fallback text between the "
                               f"tags -- an explicit TS2 'common mistake'."))
        elif "your browser" not in p.text_in[e.tag].lower() and "not support" not in p.text_in[e.tag].lower():
            out.append(("WARN", f"line {e.line}: fallback text reads "
                                f"\"{p.text_in[e.tag].strip()[:60]}\" -- the usual shape is "
                                f"\"Your browser doesn't support video. Here is a transcript: …\""))
    # <source> children of audio/video need type/src too
    for s in one("source"):
        if s.in_("picture"):
            continue
        if not s.a.get("src"):
            out.append(("ERR", f"line {s.line}: <source> with no src."))
        if not s.a.get("type"):
            out.append(("WARN", f"line {s.line}: <source> without type=\"video/mp4\" etc."))
    if has("video") and "poster" in has("video")[0].a:
        out.append(("INFO", "video has a poster image -- nice touch."))

    # ---- forms -------------------------------------------------------------
    for f in one("form"):
        fs = [e for e in E if e.tag == "fieldset" and e.in_("form")]
        if not fs:
            out.append(("ERR", f"line {f.line}: <form> has no <fieldset>."))
        for g in fs:
            if not any(c.tag == "legend" and c.in_("fieldset") for c in E):
                out.append(("ERR", f"line {g.line}: <fieldset> with no <legend>."))
        if fs and not one("legend"):
            out.append(("ERR", "no <legend> anywhere in this form."))
        labels_for = {e.a.get("for", "") for e in one("label")} - {""}
        controls = [e for e in E if e.tag in FORM_CONTROLS and e.in_("form")
                    and e.a.get("type") not in ("hidden", "submit", "reset", "button")]
        # implicit labels: control nested inside a <label>
        for e in controls:
            if "label" in e.path:
                continue
            if not (e.a.get("id", "") in labels_for):
                nm = e.a.get("name") or e.a.get("type") or e.tag
                out.append(("ERR", f"line {e.line}: <{e.tag} name=\"{nm}\"> has no matching "
                                   f"label (needs id=... plus label for=... , or wrap the "
                                   f"field in the label) -- an unlabeled field costs both "
                                   f"accessibility and TS2 credit."))
        if not controls:
            out.append(("ERR", f"line {f.line}: form has no real fields (only buttons?)."))
        validators = [e for e in E if e.in_("form") and (
            "required" in e.a or e.a.get("type") in ("email", "tel", "url", "date", "number")
            or "pattern" in e.a or "minlength" in e.a or "maxlength" in e.a
            or e.tag == "select" or e.tag == "textarea")]
        if not validators:
            out.append(("ERR", "form has no built-in validation (use required, type=\"email\", "
                               "pattern=…, min/max on at least one field)."))
        if not any(e.tag == "input" and e.a.get("type") == "email" for e in controls):
            out.append(("WARN", "form has no input type=\"email\"; the brief asks for an email."))
        if not any((e.tag == "input" and e.a.get("type") in ("submit", "image")) or
                   (e.tag == "button" and e.a.get("type", "submit") == "submit")
                   for e in E if e.in_("form")):
            out.append(("ERR", f"line {f.line}: form has no submit button."))
        for e in one("select"):
            if not any(o.tag == "option" and o.in_("select") for o in E):
                out.append(("WARN", f"line {e.line}: <select> with no <option> items."))
        if client:
            blob = p.src.lower()
            miss = [k for k in client["form_fields"] if k.split()[0] not in blob]
            if miss:
                out.append(("INFO", "form may be missing a field the brief asks for: "
                                    + ", ".join(miss)))

    # ---- no CSS / no JS ----------------------------------------------------
    if one("style"):
        out.append(("ERR", "<style> element present -- TS2 forbids CSS at this stage."))
    for e in one("link"):
        if "stylesheet" in e.a.get("rel", ""):
            out.append(("ERR", "linked stylesheet present -- TS2 forbids CSS at this stage."))
    if one("script"):
        out.append(("ERR", "<script> present -- TS2 forbids JavaScript at this stage."))
    js_attrs = [(e.tag, e.line) for e in E if any(k.startswith("on") for k in e.a)]
    for t, ln in js_attrs:
        out.append(("ERR", f"line {ln}: <{t}> has an inline event handler (onclick etc.) "
                           f"-- that is JavaScript; remove it."))
    style_attrs = [(e.tag, e.line) for e in E if "style" in e.a]
    for t, ln in style_attrs:
        out.append(("ERR", f"line {ln}: <{t}> has a style=\"\" attribute -- that is CSS."))

    # ---- misc hygiene ------------------------------------------------------
    ids = [e.a["id"] for e in E if e.a.get("id")]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        out.append(("WARN", "duplicate id(s): " + ", ".join(sorted(dupes))
                    + " -- ids must be unique (label for= points at the first one)."))
    for e in one("a"):
        if not (e.a.get("href") or "").strip():
            out.append(("WARN", f"line {e.line}: <a> with no href -- that is a placeholder, "
                                f"not a link."))
    if "TODO" in p.src or "FIXME" in p.src:
        out.append(("WARN", "TODO/FIXME comment still in the file."))
    if re.search(r"<p>\s*</p>|<div>\s*</div>", p.src):
        out.append(("INFO", "empty <p>/<div> left behind."))
    if not p.problems:
        out.append(("OK", "tags nest cleanly; nothing left unclosed."))
    for pr in p.problems:
        out.append(("ERR", pr))
    return [o for o in out if o]


def check_asset(p, src, line, client, what):
    """Verify a referenced media file actually exists and belongs to the client ZIP."""
    target = os.path.normpath(os.path.join(os.path.dirname(p.abspath), local(src)))
    if os.path.isfile(target):
        base = os.path.basename(target).lower()
        if client and base not in [a.lower() for a in client["assets"]]:
            return ("WARN", f"line {line}: {what}=\"{src}\" is not a file from the "
                            f"{client['name']} ZIP. Use only the chosen client's assets.")
        if " " in src:
            return ("WARN", f"line {line}: {what}=\"{src}\" contains a space; rename the file "
                            f"(spaces become %20 and break).")
        return ("OK", f"{what} resolves to a real file.")
    return ("ERR", f"line {line}: {what}=\"{src}\" does not exist (expected {target}). "
                   f"Broken media path -- check the exact filename, it ends in _c and is .png.")


def client_for(files, forced):
    if forced:
        return CLIENTS[forced]
    blob = " ".join(strip_comments(open(f, encoding="utf-8", errors="ignore").read())
                     for f in files).lower()
    scores = {k: sum(blob.count(a) for a in v["assets"]) for k, v in CLIENTS.items()}
    best = max(scores, key=lambda k: scores[k])
    return CLIENTS[best] if scores[best] else None


def w3c(files):
    """Send each file to the W3C Nu validator and print what it says."""
    bad_total = 0
    for f in files:
        data = open(f, "rb").read()
        req = urllib.request.Request(
            "https://validator.w3.org/nu/?out=json", data=data,
            headers={"Content-Type": "text/html; charset=utf-8",
                     "User-Agent": "ts2-check/1.0"})
        body, exc = None, None
        for attempt in (60, 90):                       # one retry; the service is chatty
            try:
                body = json.loads(urllib.request.urlopen(req, timeout=attempt).read())
                break
            except Exception as e:                     # noqa: BLE001
                exc = e
        if body is None:
            print(f"    {os.path.basename(f)}: W3C request failed ({exc}) -- paste the code "
                  f"into https://validator.w3.org/nu/ manually instead.")
            continue
        msgs = [m for m in body.get("messages", []) if m.get("type") != "info"]
        if not msgs:
            print(f"    {os.path.basename(f)}: W3C says Document is valid.")
        for m in msgs:
            bad_total += 1
            ln = m.get("lastLine", "?")
            print(f"    {os.path.basename(f)}:{ln}: {m['message']}")
    return bad_total


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_w3c = "--w3c" in sys.argv
    forced = None
    for a in sys.argv[1:]:
        if a.startswith("--client"):
            forced = a.split("=", 1)[1] if "=" in a else None
    if "--client" in sys.argv:
        i = sys.argv.index("--client")
        if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("--"):
            forced = sys.argv[i + 1]
            args = [a for a in args if a != forced]
    args = [a for a in args if a not in ("--w3c",)]

    # The site is the folder; you may check one page at a time and the nav /
    # required-element checks still see the whole four-page site.
    folders = [a for a in args if os.path.isdir(a)]
    explicit = [a for a in args if a.endswith(".html") and os.path.isfile(a)]
    if folders:
        path = folders[0]
    elif explicit:
        path = os.path.dirname(os.path.abspath(explicit[0]))
    else:
        path = "."
    all_files = sorted(os.path.abspath(os.path.join(path, f)) for f in os.listdir(path)
                       if f.endswith(".html"))
    all_files = [f for f in all_files if "Sophia Learning" not in f and "_files" not in f]
    files = [os.path.abspath(a) for a in explicit] if explicit else all_files
    if not all_files:
        print("No .html files found here. cd into the folder holding index.html.")
        return 2

    client = client_for(all_files, forced)
    page_files = sorted(os.path.basename(f) for f in all_files)
    print(f"\nTouchstone 2 self-check -- site of {len(all_files)} page(s): "
          f"{', '.join(page_files)}")
    print(f"Client detected: {client['name'] if client else 'none of the three ZIPs'}"
          f"\n{'=' * 74}")

    errs = warns = 0
    site = {"figure": [], "picture": [], "media": [], "form": [], "img": 0}
    parsed = {}
    for f in files:
        p = Page(open(f, encoding="utf-8", errors="ignore").read(), os.path.basename(f))
        p.abspath = os.path.abspath(f)
        parsed[f] = p
        results = check_page(p, page_files, client)
        print(f"\n{os.path.basename(f)}")
        for lvl, msg in results:
            if lvl == "ERR":
                errs += 1
            elif lvl == "WARN":
                warns += 1
            if lvl != "OK":
                icon = {"ERR": "x  ", "WARN": "!  ", "INFO": "i  "}[lvl]
                print(f"  {icon}{msg}")
        src = strip_comments(open(f, encoding="utf-8", errors="ignore").read()).lower()
        if f not in all_files:
            continue
        site["img"] += len(re.findall(r"<img\b", src))
        for k, tok in (("figure", "<figure"), ("picture", "<picture"),
                       ("media", ("<audio", "<video")), ("form", "<form")):
            toks = tok if isinstance(tok, tuple) else (tok,)
            if any(t in src for t in toks):
                site[k].append(os.path.basename(f))
    for f in all_files:
        if f in files:
            continue
        src = strip_comments(open(f, encoding="utf-8", errors="ignore").read()).lower()
        site["img"] += len(re.findall(r"<img\b", src))
        for k, tok in (("figure", "<figure"), ("picture", "<picture"),
                       ("media", ("<audio", "<video")), ("form", "<form")):
            toks = tok if isinstance(tok, tuple) else (tok,)
            if any(t in src for t in toks):
                site[k].append(os.path.basename(f))

    print(f"\n{'=' * 74}\nSITE-WIDE REQUIRED ELEMENTS")
    rows = [("figure", "one <figure> + <figcaption>"),
            ("picture", "one responsive image via <picture>"),
            ("media", "one audio/video element WITH fallback text"),
            ("form", "one complete form (label + fieldset + legend + validation)")]
    n_img = site["img"]
    where = f"{n_img} image(s)"
    flag = "OK  " if n_img >= 2 else "x   "
    errs += 0 if n_img >= 2 else 1
    print(f"  {flag}{'at least two relevant images, meaningful alt text':<62} -> {where}")
    for k, label in rows:
        where = ", ".join(site[k]) or "NOWHERE"
        errs += 0 if site[k] else 1
        print(f"  {'OK  ' if site[k] else 'x   '}{label:<62} -> {where}")

    expected = {"index.html", "about.html"}
    third = {"products.html", "services.html"}
    fourth = {"contact.html", "events.html"}
    pf = set(page_files)
    if not expected <= pf:
        print(f"  x   page set must include index.html + about.html   -> got {', '.join(page_files)}")
        errs += 1
    if not (pf & third):
        print("  x   need products.html or services.html")
        errs += 1
    if not (pf & fourth):
        print("  x   need contact.html or events.html")
        errs += 1
    if len(pf) != 4:
        print(f"  !   TS2 wants exactly four pages; you have {len(pf)}")
        warns += 1

    if do_w3c:
        print(f"\n{'=' * 74}\nW3C MARKUP VALIDATOR (validator.w3.org/nu)")
        errs += w3c(files)

    print(f"\n{'=' * 74}")
    print(f"{errs} error(s), {warns} warning(s).")
    print("Errors = the assignment's own checklist says this is missing/broken.")
    print("Warnings = legal HTML but usually costs you a rubric point.\n")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
