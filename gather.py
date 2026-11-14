#!/usr/bin/env python3
"""Prodigia gatherer.

Reads public sighting sources, files reports under events in the register,
and renders the register page. The unit of the register is the event, not
the post: reports of the same event from several sources are filed under
one entry.

Sources read by this script:
- Google News RSS queries for sighting coverage (news layer).

Other sources (NUFORC tables) are ingested from local JSON snapshots in
sources/ when present; a snapshot is produced by reading the source's
public index and saving its rows verbatim.

Standing labels are statements about the record, never about the
phenomenon:
- UNRESOLVED: the filed reports hold no established ordinary explanation.
- RESOLVED - ORDINARY: an ordinary cause is established in the record.
- INSUFFICIENT RECORD: the filed reports lack what a check requires.

Stdlib only. No accounts, no keys, no telemetry.
"""

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVENTS_PATH = ROOT / "events.json"
SOURCES_DIR = ROOT / "sources"

NEWS_QUERIES = [
    "UFO sighting",
    "UAP sighting",
    "strange lights in the sky sighting",
    "fireball in the sky witnessed",
]

SIGHTING_WORDS = (
    "sighting", "sighted", "ufo", "uap", "spotted", "seen over", "in the sky",
    "lights over", "object over", "fireball", "orb", "triangle over",
)
EXPLAINED_WORDS = (
    "starlink", "spacex", "meteor shower", "shooting star", "rocket launch",
    "identified as", "turns out", "was a plane", "were drones", "drone show",
    "satellites", "was a meteor",
)
BLOCK_WORDS = (
    "program", "unsealing", "unseals", "telescope", "documentary", "hearing",
    "congress", "podcast", "episode", "book ", "interview", "opinion",
    "what we know", "everything we know", "explained: the history",
)
STRONG = {
    "jellyfish", "tentacled", "tentacles", "fireball", "tictac", "tic",
    "boomerang", "chevron",
}
STOPWORDS = {
    "ufo", "ufos", "uap", "uaps", "sighting", "sightings", "spotted", "seen",
    "over", "near", "with", "from", "that", "this", "what", "watch", "video",
    "caught", "camera", "mysterious", "mystery", "strange", "object", "objects",
    "sky", "alien", "aliens", "expert", "offers", "theory", "really", "about",
    "after", "before", "their", "there", "could", "leaves", "mother", "like",
}
US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
]
CLASS_WORDS = [
    ("jellyfish", "Jellyfish"),
    ("triangle", "Triangle"), ("fireball", "Fireball"), ("orb", "Orb"),
    ("disc", "Disc"), ("saucer", "Disc"), ("cigar", "Cigar"),
    ("light", "Light"), ("lights", "Light"),
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "prodigia-register/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def classify(text):
    low = text.lower()
    for word, name in CLASS_WORDS:
        if word in low:
            return name
    return "Unstated"


DISTINCTIVE = (
    "jellyfish", "fireball", "orb", "triangle", "disc", "saucer", "cigar",
    "sphere", "cube", "tic tac", "tictac", "tentacle", "cylinder", "diamond",
    "boomerang", "chevron", "rectangle", "pyramid", " glowing ", "hovering",
)


def news_reports():
    out = []
    seen = set()
    for q in NEWS_QUERIES:
        url = ("https://news.google.com/rss/search?q=" +
               urllib.request.quote(q) + "&hl=en-US&gl=US&ceid=US:en")
        try:
            raw = fetch(url)
        except Exception as e:
            print(f"news query failed ({q}): {e}", file=sys.stderr)
            continue
        root = ET.fromstring(raw)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            low = title.lower()
            if not any(w in low for w in SIGHTING_WORDS):
                continue
            if any(w in low for w in BLOCK_WORDS):
                continue
            if not (re.search(r"\b(?:over|near|above) [A-Z]", title) or
                    any(st in title for st in US_STATES) or
                    any(w in low for w in DISTINCTIVE)):
                continue
            if link in seen:
                continue
            seen.add(link)
            headline, _, publisher = title.rpartition(" - ")
            if not publisher:
                headline, publisher = title, "news wire"
            try:
                dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
                date = dt.strftime("%Y-%m-%d")
                age = (datetime.now(timezone.utc).date() - dt.date()).days
                if age > 14:
                    continue
            except Exception:
                date = pub[:16]
            out.append({
                "source": publisher.strip(),
                "url": link,
                "posted": date,
                "headline": headline.strip(),
            })
    return out


def snapshot_reports():
    out = []
    if SOURCES_DIR.exists():
        for p in sorted(SOURCES_DIR.glob("*.json")):
            try:
                rows = json.loads(p.read_text())
            except Exception as e:
                print(f"snapshot unreadable ({p.name}): {e}", file=sys.stderr)
                continue
            for row in rows:
                row = dict(row)
                row.setdefault("source", p.stem.upper())
                out.append(row)
    return out


def place_of(report):
    if report.get("place"):
        return report["place"]
    head = report.get("headline", "")
    m = re.search(r"\b(?:[Oo]ver|[Nn]ear|[Aa]bove) ([A-Z]{3,5}|[A-Z][a-z]{2,}(?: [A-Z][a-z]{2,}){0,2})", head)
    if m and m.group(1) not in ("US", "U.S.", "The"):
        return m.group(1)
    for st in US_STATES:
        if st in head:
            return st
    return "Unstated in the report"


def cluster_key(report):
    place = place_of(report).split(",")[0].strip().lower()
    date = (report.get("occurred") or report.get("posted") or "")[:10]
    return (place, date)


def sig_tokens(text):
    toks = set(re.findall(r"[a-z]{4,}", text.lower()))
    return {t for t in toks if t not in STOPWORDS}


def region_of(text):
    for st in US_STATES:
        if st in text:
            return st.lower()
    return ""


def form_of(text):
    low = text.lower()
    if "jellyfish" in low or "tentacle" in low:
        return "jellyfish"
    for w in ("fireball", "triangle", "tictac", "boomerang", "chevron"):
        if w in low:
            return w
    c = classify(text)
    return c.lower() if c != "Unstated" else ""


def similar_event(report, events, rare=None):
    """File a report under an existing event when both describe the same
    form in the same region within seven days. Deliberately conservative:
    when in doubt, a new entry is opened; entries can be merged later,
    never split wrongly."""
    text = (report.get("headline") or "") + " " + (report.get("summary") or "") + " " + (report.get("place") or "")
    region = region_of(text) or place_of(report).split(",")[0].strip().lower()
    form = form_of(text)
    if not region or region == "unstated in the report" or not form:
        return None
    rdate = (report.get("occurred") or report.get("posted") or "")[:10]
    for ev in events:
        etext = ev["summary"] + " " + ev["place"]
        eregion = region_of(etext) or ev["place"].split(",")[0].strip().lower()
        if eregion != region or form_of(etext) != form:
            continue
        edate = (ev.get("occurred") or "")[:10]
        if rdate and edate:
            try:
                gap = abs((datetime.strptime(rdate, "%Y-%m-%d") -
                           datetime.strptime(edate, "%Y-%m-%d")).days)
                if gap > 7:
                    continue
            except Exception:
                pass
        return ev
    if form in ("jellyfish", "tictac", "boomerang"):
        kin = []
        for ev in events:
            etext = ev["summary"] + " " + ev["place"]
            if form_of(etext) != form:
                continue
            edate = (ev.get("occurred") or "")[:10]
            if rdate and edate:
                try:
                    gap = abs((datetime.strptime(rdate, "%Y-%m-%d") -
                               datetime.strptime(edate, "%Y-%m-%d")).days)
                    if gap > 7:
                        continue
                except Exception:
                    pass
            kin.append(ev)
        if len(kin) == 1:
            return kin[0]
    return None


def file_reports(reports, events):
    by_key = {}
    for ev in events:
        for rep in ev["reports"]:
            by_key.setdefault(cluster_key(rep), ev)
    from collections import Counter
    dfc = Counter()
    for rep in reports:
        for t in sig_tokens((rep.get("headline") or "") + " " + (rep.get("summary") or "")):
            dfc[t] += 1
    rare = {t for t, n in dfc.items() if n <= 2}
    filed = 0
    for rep in reports:
        url = rep.get("url", "")
        if any(url and url == r.get("url") for ev in events for r in ev["reports"]):
            continue
        key = cluster_key(rep)
        ev = by_key.get(key) if key[0] != "unstated in the report" else None
        if ev is None:
            ev = similar_event(rep, events, rare)
        entry = {
            "source": rep["source"], "url": url, "posted": rep.get("posted", ""),
            "headline": rep.get("headline", ""),
        }
        if ev is None:
            ev = {
                "id": None,
                "filed": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "occurred": rep.get("occurred") or rep.get("posted", ""),
                "place": place_of(rep),
                "class": rep.get("class") or classify(rep.get("headline", "") + " " + rep.get("summary", "")),
                "summary": rep.get("summary") or rep.get("headline", ""),
                "reports": [],
                "standing": "INSUFFICIENT RECORD",
                "notes": "",
            }
            events.append(ev)
            by_key[key] = ev
        ev["reports"].append(entry)
        if ev["place"] == "Unstated in the report":
            ev["place"] = place_of(rep)
        if rep.get("summary") and len(rep["summary"]) > len(ev["summary"]):
            ev["summary"] = rep["summary"]
        filed += 1
    return filed


def joinable(a, b):
    ta = a["summary"] + " " + a["place"]
    tb = b["summary"] + " " + b["place"]
    fa, fb = form_of(ta), form_of(tb)
    if not fa or fa != fb:
        return False
    try:
        gap = abs((datetime.strptime(a["occurred"][:10], "%Y-%m-%d") -
                   datetime.strptime(b["occurred"][:10], "%Y-%m-%d")).days)
        if gap > 7:
            return False
    except Exception:
        pass
    ra = region_of(ta) or a["place"].split(",")[0].strip().lower()
    rb = region_of(tb) or b["place"].split(",")[0].strip().lower()
    if ra and rb and ra == rb:
        return True
    if fa in ("jellyfish", "tictac", "boomerang"):
        others = [e for e in (a, b)]
        return True
    return False


def consolidate(events):
    """Merge events the filing rules would join, until no pair joins.
    Filing is order-sensitive; the register is not allowed to be."""
    changed = True
    while changed:
        changed = False
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                a, b = events[i], events[j]
                if joinable(a, b):
                    keep, drop = (a, b) if len(a["reports"]) >= len(b["reports"]) else (b, a)
                    urls = {r.get("url") for r in keep["reports"]}
                    for r in drop["reports"]:
                        if r.get("url") not in urls:
                            keep["reports"].append(r)
                    if keep["place"] == "Unstated in the report":
                        keep["place"] = drop["place"]
                    keep["occurred"] = min(keep["occurred"], drop["occurred"])
                    events.remove(drop)
                    changed = True
                    break
            if changed:
                break
    return events


def settle_standings(events):
    for ev in events:
        dates = [r.get("posted", "") for r in ev["reports"] if r.get("posted")]
        dates += [r.get("occurred", "") for r in ev["reports"] if r.get("occurred")]
        if dates:
            ev["occurred"] = min(ev["occurred"], min(dates)) if ev["occurred"] else min(dates)
        heads = [r.get("headline", "") for r in ev["reports"] if r.get("headline")]
        if heads:
            form = form_of(ev["summary"] + " " + ev["place"])
            def hscore(h):
                s = len(sig_tokens(h))
                if form and form in h.lower():
                    s += 3
                return s
            best = max(heads, key=hscore)
            if hscore(best) > hscore(ev["summary"]):
                ev["summary"] = best
        text = (ev["summary"] + " " + ev.get("notes", "")).lower()
        named = [w for w in EXPLAINED_WORDS if w in text]
        sources = {r["source"] for r in ev["reports"]}
        if named and ev["standing"] != "RESOLVED - ORDINARY":
            ev["standing"] = "RESOLVED - ORDINARY"
            if not ev["notes"]:
                ev["notes"] = "The record names an ordinary cause: " + named[0] + "."
        elif "NUFORC" in sources and ev["standing"] == "INSUFFICIENT RECORD":
            ev["standing"] = "UNRESOLVED"
            if not ev["notes"]:
                ev["notes"] = "No ordinary explanation is established in the filed reports."
    events.sort(key=lambda e: (e["occurred"], e["filed"]), reverse=True)
    used = set()
    for ev in events:
        if ev.get("id"):
            try:
                used.add(int(str(ev["id"]).split("-")[1]))
            except Exception:
                pass
    nxt = (max(used) + 1) if used else 1
    for ev in reversed(events):
        if not ev.get("id"):
            ev["id"] = "P-" + str(nxt).zfill(4)
            nxt += 1
    return events


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def render(events, gathered_at):
    total_reports = sum(len(e["reports"]) for e in events)
    resolved = sum(1 for e in events if e["standing"] == "RESOLVED - ORDINARY")
    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prodigia - a register of anomalous sightings</title>
<style>
body { background:#ffffff; color:#111111; font-family: Georgia, 'Times New Roman', serif;
       margin: 2.5em auto; max-width: 44em; padding: 0 1.2em; line-height: 1.5; }
h1 { font-size: 2.2em; letter-spacing: 0.12em; margin-bottom: 0.1em; }
.sub { color:#444; margin-top: 0; }
.rule { border-top: 2px solid #111; margin: 1.2em 0; }
.entry { margin: 2em 0; }
.entry h2 { font-size: 1.15em; margin-bottom: 0.2em; }
.meta { color:#444; font-size: 0.92em; margin: 0.15em 0; }
.standing { font-variant: small-caps; letter-spacing: 0.05em; }
.src { font-size: 0.92em; }
.small { color:#444; font-size: 0.9em; }
a { color:#111; }
</style>
</head>
<body>
<h1>PRODIGIA</h1>
<p class="sub">A register of anomalous sightings, kept from public reports.</p>
<div class="rule"></div>
<p>The unit of this register is the event, not the post. Reports of one event
from several sources are filed under a single entry, so an entry shows how
many independent reports the event has gathered. Each entry carries a
standing, which is a statement about the record and never about the
phenomenon: UNRESOLVED means the filed reports hold no established ordinary
explanation, RESOLVED - ORDINARY means an ordinary cause is established in
the record and is named, and INSUFFICIENT RECORD means the filed reports
lack the time, place or detail a check requires.</p>
""")
    parts.append(f'<p class="small">Last gathered {esc(gathered_at)}. '
                 f'Events in the register: {len(events)}. '
                 f'Reports filed: {total_reports}. '
                 f'Resolved to an ordinary cause: {resolved}.</p>\n<div class="rule"></div>\n')
    for ev in events:
        parts.append('<div class="entry">')
        parts.append(f'<h2>{esc(ev["id"])} - {esc(ev["occurred"])} - {esc(ev["place"])}</h2>')
        parts.append(f'<p class="meta">Class: {esc(ev["class"])}. '
                     f'Standing: <span class="standing">{esc(ev["standing"])}</span>. '
                     f'Reports filed under this event: {len(ev["reports"])}.</p>')
        parts.append(f'<p>{esc(ev["summary"])}</p>')
        if ev.get("notes"):
            parts.append(f'<p class="small">{esc(ev["notes"])}</p>')
        srcs = []
        for r in ev["reports"]:
            label = esc(r["source"]) + (f' ({esc(r["posted"])})' if r.get("posted") else "")
            if r.get("url"):
                srcs.append(f'<a href="{esc(r["url"])}">{label}</a>')
            else:
                srcs.append(label)
        parts.append(f'<p class="src">Filed from: {", ".join(srcs)}.</p>')
        parts.append('</div>')
    parts.append("""<div class="rule"></div>
<p class="small">Method: the gatherer reads public sighting sources and
files each report under the event it describes. Entries are added, merged
and re-stood as the record grows; an entry's standing can change when new
reports are filed under it. Nothing in this register is certified beyond
what its filed sources say, and uncertainty is labelled where it stands.</p>
</body>
</html>
""")
    return "".join(parts)


def main():
    events = []
    if EVENTS_PATH.exists():
        events = json.loads(EVENTS_PATH.read_text())
    reports = snapshot_reports() + news_reports()
    filed = file_reports(reports, events)
    events = consolidate(events)
    events = settle_standings(events)
    EVENTS_PATH.write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n")
    gathered_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (ROOT / "index.html").write_text(render(events, gathered_at))
    print(f"reports read: {len(reports)}; newly filed: {filed}; events in register: {len(events)}")


if __name__ == "__main__":
    main()
