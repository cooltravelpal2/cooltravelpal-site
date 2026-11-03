"""Publish audit: no personal data, test data or developer text in what ships.

    python3 scripts/audit_published.py [dist] [--release-to _site]

Modeled on CollegeDream's tools/appstore/audit_shipped.py. The publish
workflow runs it on the built site before every upload, so a finding stops
the deploy. It checks every file in the publish directory for:

- fixture, demo or sample wording and stand-in names (Joe Doe, HZ-DEMO-77);
- developer paths, hosts, account names and tokens;
- email addresses other than our own (support@ and other site addresses);
- personal metadata in images and video: EXIF GPS, owner, artist and
  serial tags, XMP authors, QuickTime locations.

Text drawn inside screenshots can't be read here: look at every new app
screenshot for real names, trips and documents before adding it. Add a
reviewed exception to ALLOWED, keyed by file and matched text, with its reason.

With --release-to, a clean audit copies the files to that directory, and the
deploy uploads only that copy: skipping or removing the audit breaks the
deploy instead of letting it through. Scripts that send text elsewhere (X
posts, newsletters) call audit_text() on it before sending.
"""
import hashlib
import re
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWN_DOMAINS = {"travelpal.now", "collegedream.app", "dongdong.now"}

TEXT = {".html", ".htm", ".xml", ".xsl", ".json", ".js", ".css", ".txt", ".vtt", ".svg", ".webmanifest", ""}
VIDEO = (".mp4", ".m4a", ".mov")
MEDIA = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".heic", ".mp4", ".m4a", ".mov", ".mp3"}
# Travel news uses "pilot" and hotel reviews "fixtures" in their plain sense, so only unambiguous test wording.
TEST_WORDS = re.compile(r"(?i)\b(?:dummy|lorem ipsum|sample (?:data|card|trip|user)|test (?:data|user|account|card|trip|school|college|camp)|live test|"
                        r"working name|not cleared for release|todo|fixme|asdf|(?:john|jane|joe|jamie|alex) doe)\b|\b[A-Z]{2,4}-DEMO-\d+\b|fixture://")
DEV_TEXT = re.compile(r"(?i)/Users/\w|/home/\w+/|/private/tmp|/var/folders/|C:\\\\Users|localhost|127\.0\.0\.1|192\.168\.\d|"
                      r"example\.(?:com|org)|file:///|cooltravelpal|"
                      r"ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}")
# The developer's own account and name words, as sha256 prefixes so this public file doesn't spell them out.
PRIVATE_WORDS = {'2ba89aa561f58111', '965a5816266d2301', 'd6328cdcf9a8aba7'}
# Values a broken template or script leaves on a page. Checked outside <script> and <style>, and not in .js or .css.
DEBUG = re.compile(r"\bundefined\b|\[object Object\]|\bNaN\b|\{\{[^}]*\}\}|\$\{[^}]*\}")
PHONE = re.compile(r"(?<![\w.])(?:\+?1[ .-])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\w|\.\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# Reviewed matches that are fine to ship.
ALLOWED = {
    ("blog/california-highway-1-big-sur-road-trip/index.html", "1-800-427-7623"): "Caltrans' public road-information line",
}
# EXIF tags that identify a person, device or place.
PERSONAL_TAGS = {0x013B: "Artist", 0x8298: "Copyright", 0xA430: "CameraOwnerName", 0xA431: "BodySerialNumber",
                 0xA435: "LensSerialNumber", 0x9C9D: "XPAuthor", 0x9286: "UserComment", 0x8825: "GPSInfo"}
XMP_PERSONAL = re.compile(r"<(?:dc:creator|photoshop:(?:City|Country|State|AuthorsPosition)|Iptc4xmpCore:Location|exif:GPS\w+|xmpRights:Owner|aux:SerialNumber|tiff:Artist)\b")
QUICKTIME_PERSONAL = re.compile(rb"\xa9xyz|com\.apple\.quicktime\.(?:location|author|artist|displayname)|\xa9aut|\xa9ART")

problems = []


def report(label, kind, found, text="", at=None):
    if (label, found) in ALLOWED or found in ALLOWED:
        return
    where = f" in …{text[max(0, at.start() - 50):at.end() + 30]}…" if at else ""
    problems.append(f"{label}: {kind} {found!r}{where}")


def scan_text(label, text):
    shown = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", text)
    checks = [(TEST_WORDS, "test data", text), (DEV_TEXT, "developer text", text), (PHONE, "phone number", shown)]
    if not label.lower().endswith((".js", ".css")):
        checks.append((DEBUG, "debug value", shown))
    for pattern, kind, body in checks:
        for m in pattern.finditer(body):
            report(label, kind, m.group(0), body, m)
    for m in re.finditer(r"[A-Za-z0-9]+", text):
        if hashlib.sha256(m.group(0).lower().encode()).hexdigest()[:16] in PRIVATE_WORDS:
            report(label, "developer's private name", m.group(0), text, m)
    for m in EMAIL.finditer(text):
        address = m.group(0)
        if re.search(r"@\d+x\.\w+$", address):
            continue  # image@2x.png
        if address.split("@", 1)[1].lower() not in OWN_DOMAINS:
            report(label, "email address", address, text, m)


def exif_tags(tiff):
    """Tag ids in IFD0 and the Exif IFD of a TIFF/EXIF block."""
    if tiff[:2] not in (b"II", b"MM"):
        return set()
    order = "<" if tiff[:2] == b"II" else ">"
    tags, todo, seen = set(), [struct.unpack(order + "I", tiff[4:8])[0]], set()
    while todo:
        offset = todo.pop()
        if offset in seen or offset + 2 > len(tiff):
            continue
        seen.add(offset)
        count = struct.unpack(order + "H", tiff[offset:offset + 2])[0]
        for i in range(count):
            entry = tiff[offset + 2 + 12 * i: offset + 14 + 12 * i]
            if len(entry) < 12:
                break
            tag = struct.unpack(order + "H", entry[:2])[0]
            tags.add(tag)
            if tag == 0x8769:  # Exif sub-IFD
                todo.append(struct.unpack(order + "I", entry[8:12])[0])
    return tags


def scan_media(label, data):
    # JPEG APP1, PNG eXIf and WebP EXIF blocks all hold a TIFF header a few bytes after the marker.
    for marker in (b"Exif\x00\x00", b"eXIf", b"EXIF"):
        start = data.find(marker)
        if start == -1:
            continue
        head = data[start:start + 32]
        header = min((i for i in (head.find(b"II*\x00"), head.find(b"MM\x00*")) if i != -1), default=-1)
        if header != -1:
            for tag in exif_tags(data[start + header:]):
                if tag in PERSONAL_TAGS:
                    report(label, "personal metadata", PERSONAL_TAGS[tag])
    raw = data.decode("latin-1")
    xmp = re.search(r"<x:xmpmeta.*?</x:xmpmeta>", raw, re.S)
    if xmp:
        for m in XMP_PERSONAL.finditer(xmp.group(0)):
            report(label, "personal XMP", m.group(0))
    # Only movie containers have QuickTime atoms; in an image these bytes can turn up by chance.
    if label.lower().endswith(VIDEO) and QUICKTIME_PERSONAL.search(data):
        report(label, "personal metadata", QUICKTIME_PERSONAL.search(data).group(0).decode("latin-1"))
    for m in DEV_TEXT.finditer(raw):
        report(label, "developer text in media metadata", m.group(0))
    for m in re.finditer(r"[A-Za-z0-9]{5,}", raw):
        if hashlib.sha256(m.group(0).lower().encode()).hexdigest()[:16] in PRIVATE_WORDS:
            report(label, "developer's private name in media metadata", m.group(0))


def audit_text(label, text):
    """Problems in text that is about to be posted or sent; empty when it is clean."""
    del problems[:]
    scan_text(label, text)
    return list(problems)


def main():
    args = sys.argv[1:]
    release_to = None
    if "--release-to" in args:
        i = args.index("--release-to")
        release_to = Path(args[i + 1])
        del args[i:i + 2]
    published = Path(args[0]) if args else ROOT / "dist"
    if not published.is_dir():
        sys.exit(f"{published} not found; build the site first")
    files = sorted(p for p in published.rglob("*") if p.is_file())
    for path in files:
        label = str(path.relative_to(published))
        data = path.read_bytes()
        if path.suffix.lower() in MEDIA:
            scan_media(label, data)
        elif path.suffix.lower() in TEXT:
            scan_text(label, data.decode("utf-8", "replace"))

    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} to check in {published}. Fix them, or add a reviewed exception with its reason.")
        sys.exit(1)
    print(f"{len(files)} published files: no test data, personal data or developer text found.")
    if release_to:
        if release_to.exists():
            shutil.rmtree(release_to)
        shutil.copytree(published, release_to)
        print(f"Released the audited files to {release_to}.")


if __name__ == "__main__":
    main()
