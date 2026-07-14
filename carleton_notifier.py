#!/usr/bin/env python3
"""
Carleton Central seat-availability notifier.

Polls the PUBLIC Carleton class schedule (no login required) for one or more
course sections and pushes a phone notification (via ntfy.sh) the moment a
section flips from Full -> Open (or a waitlist opens up).

Public schedule: https://central.carleton.ca/prod/bwysched.p_select_term?wsea_code=EXT

Usage:
    python carleton_notifier.py            # uses config.json in this folder
    python carleton_notifier.py --once     # check a single time and exit
    python carleton_notifier.py --config other.json
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://central.carleton.ca/prod/"
SELECT_TERM = BASE + "bwysched.p_select_term?wsea_code=EXT"
SEARCH_FIELDS = BASE + "bwysched.p_search_fields"
COURSE_SEARCH = BASE + "bwysched.p_course_search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
#  Scraping
# --------------------------------------------------------------------------- #
def search_sections(term_code, subject, number="", crn=""):
    """Return a list of section dicts for the given search.

    Each dict: {status, crn, course, section, title}
    Raises requests.RequestException on network trouble.
    """
    s = requests.Session()
    s.headers.update(HEADERS)

    # 1) fresh session id
    r = s.get(SELECT_TERM, timeout=30)
    r.raise_for_status()
    m = re.search(r'name="session_id" value="(\d+)"', r.text)
    if not m:
        raise RuntimeError("Could not obtain a session id from Carleton Central.")
    session_id = m.group(1)

    # 2) register the term, get the search form
    r = s.post(
        SEARCH_FIELDS,
        data={"wsea_code": "EXT", "session_id": session_id, "term_code": term_code},
        timeout=30,
    )
    r.raise_for_status()
    form = BeautifulSoup(r.text, "html.parser").find(
        "form", action="bwysched.p_course_search"
    )
    if form is None:
        raise RuntimeError(
            f"No search form for term {term_code}. Is the term code correct/open?"
        )

    # 3) build the POST body exactly like a browser does.
    #    KEY quirks discovered by reverse-engineering the form:
    #      * every sel_* field carries a hidden 'dummy' sentinel that MUST stay
    #      * the 7 day checkboxes (m,t,w,r,f,s,u) are all submitted by default;
    #        omit them and the search silently returns "No courses"
    #      * sel_number / sel_crn are scalar text inputs -> REPLACE, don't append
    data = []
    for inp in form.find_all("input"):
        name = inp.get("name")
        itype = (inp.get("type") or "text").lower()
        if not name or itype in ("submit", "button", "image", "reset"):
            continue
        value = inp.get("value", "")
        if name == "sel_number":
            value = number
        elif name == "sel_crn":
            value = crn
        data.append((name, value))
    for sel in form.find_all("select"):
        name = sel.get("name")
        for opt in sel.find_all("option"):
            if opt.has_attr("selected"):
                data.append((name, opt.get("value", "")))
    data.append(("sel_subj", subject))

    r = s.post(COURSE_SEARCH, data=data, timeout=30)
    r.raise_for_status()
    return parse_results(r.text)


def parse_results(html):
    soup = BeautifulSoup(html, "html.parser")
    sections = []
    for row in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        # A data row looks like: [Select, Status, CRN(5 digits), Course, Section, Title, ...]
        if len(cells) >= 6 and re.fullmatch(r"\d{5}", cells[2]):
            sections.append(
                {
                    "status": cells[1],
                    "crn": cells[2],
                    "course": cells[3],
                    "section": cells[4],
                    "title": cells[5],
                }
            )
    return sections


def has_space(status, include_waitlist=True):
    """True when the status indicates a seat (or an open waitlist) is available.

    Observed statuses:
      "Open"                -> a real seat is free            (space)
      "Full, No Waitlist"   -> full, no waitlist              (no space)
      "Waitlist Full"       -> full AND waitlist full         (no space)
      "Full, Waitlist ..."  -> full but waitlist has room     (waitlist space)
    """
    s = status.lower()
    if "open" in s:
        return True
    if include_waitlist and "waitlist" in s:
        # exclude the two "no room" waitlist phrasings
        if "no waitlist" not in s and "waitlist full" not in s:
            return True
    return False


# --------------------------------------------------------------------------- #
#  Notification
# --------------------------------------------------------------------------- #
def notify_ntfy(topic, title, message, click_url=None, priority="urgent"):
    url = f"https://ntfy.sh/{topic}"
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": priority,
        "Tags": "tada,books",
    }
    if click_url:
        headers["Click"] = click_url
    r = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=30)
    r.raise_for_status()


# --------------------------------------------------------------------------- #
#  Main loop
# --------------------------------------------------------------------------- #
def matches_target(section, targets):
    """targets: list of {crn} or {section} filters. Empty -> match all."""
    if not targets:
        return True
    for t in targets:
        if "crn" in t and section["crn"] == str(t["crn"]):
            return True
        if "section" in t and section["section"].upper() == str(t["section"]).upper():
            return True
    return False


def gather_sections(term, subject, number="", prefix=""):
    """Collect sections for a subject, filtered to an exact number or a number
    prefix (e.g. prefix='4' -> all 4000-level). Deduped by CRN."""
    subject = subject.upper()
    if prefix:
        # a 1-char prefix matches too many across all subjects and gets capped
        # at 300, so sweep prefix+0..9 (e.g. '4' -> '40'..'49').
        queries = [prefix + str(d) for d in range(10)] if len(prefix) == 1 else [prefix]
        found = {}
        for q in queries:
            for s in search_sections(term, subject, q):
                if s["course"].upper().startswith(f"{subject} {prefix}"):
                    found[s["crn"]] = s
        return list(found.values())
    # exact number (or subject-only)
    want = (subject + number).replace(" ", "")
    return [
        s
        for s in search_sections(term, subject, number)
        if not number or s["course"].replace(" ", "").upper() == want
    ]


def check_once(cfg, state, notify=True):
    term = cfg["term_code"]
    subject = cfg["subject"].upper()
    number = str(cfg.get("course_number", ""))
    prefix = str(cfg.get("course_prefix", ""))
    targets = cfg.get("sections", [])  # list of {"crn": ...} or {"section": ...}
    include_waitlist = cfg.get("notify_on_waitlist", True)
    # On the very first check we record the current state silently, so you only
    # get pinged when a section *changes* to open from now on. Set
    # notify_current_open=true to also be told about seats already open at start.
    notify_current = cfg.get("notify_current_open", False)

    sections = gather_sections(term, subject, number, prefix)
    watched = [s for s in sections if matches_target(s, targets)]

    if not watched:
        log(
            f"WARNING: no sections matched {subject} {number} "
            f"(targets={targets}). Found {len(sections)} rows total. "
            "Check subject/number/CRN/term in config.json."
        )
        return

    for s in sorted(watched, key=lambda x: (x["course"], x["section"])):
        key = s["crn"]
        open_now = has_space(s["status"], include_waitlist)
        first_seen = key not in state
        was_open = state.get(key, False)
        flag = "OPEN" if open_now else "full"
        log(f"  {s['course']} {s['section']} (CRN {s['crn']}): {s['status']}  [{flag}]")

        # Notify on a full->open transition. On first sighting, only notify if
        # the user opted in to hearing about currently-open sections.
        should_notify = notify and open_now and (
            (not was_open) if not first_seen else notify_current
        )
        if should_notify:
            title = f"Seat open: {s['course']} {s['section']}"
            msg = (
                f"{s['course']} {s['section']} - {s['title']}\n"
                f"CRN {s['crn']} is now {s['status']}.\n"
                f"Register in Carleton Central now!"
            )
            try:
                notify_ntfy(cfg["ntfy_topic"], title, msg, click_url=SELECT_TERM)
                log(f"  >>> NOTIFIED via ntfy topic '{cfg['ntfy_topic']}'")
            except Exception as e:  # noqa: BLE001
                log(f"  !!! ntfy notification failed: {e}")
        state[key] = open_now


def load_config(path):
    import os

    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    # Allow the ntfy topic to come from an env var (e.g. a GitHub Actions secret)
    # so it doesn't have to be committed to a public repo.
    if os.environ.get("NTFY_TOPIC"):
        cfg["ntfy_topic"] = os.environ["NTFY_TOPIC"]
    for req in ("term_code", "subject", "ntfy_topic"):
        if not cfg.get(req):
            sys.exit(f"config.json is missing required field: {req}")
    return cfg


def load_state(path):
    if path and Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(path, state):
    if path:
        Path(path).write_text(json.dumps(state), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Carleton Central seat notifier")
    ap.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    ap.add_argument("--once", action="store_true", help="check a single time and exit")
    ap.add_argument(
        "--state-file",
        default=None,
        help="Persist open/full state here so runs remember each other "
        "(needed for stateless schedulers like GitHub Actions).",
    )
    args = ap.parse_args()

    cfg = load_config(args.config)
    interval = int(cfg.get("poll_seconds", 180))
    state = load_state(args.state_file)

    label = f"{cfg['subject'].upper()} {cfg.get('course_number','')}".strip()
    log(f"Watching {label} (term {cfg['term_code']}) every {interval}s.")
    log(f"Notifications -> ntfy.sh topic '{cfg['ntfy_topic']}'")
    if cfg.get("sections"):
        log(f"Target sections: {cfg['sections']}")

    if args.once:
        check_once(cfg, state)
        save_state(args.state_file, state)
        return

    while True:
        try:
            check_once(cfg, state)
            save_state(args.state_file, state)
        except KeyboardInterrupt:
            log("Stopped.")
            break
        except Exception as e:  # noqa: BLE001
            log(f"Check failed (will retry): {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
