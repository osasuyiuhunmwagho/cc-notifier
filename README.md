# cc-notifier

Get a phone alert the moment a full Carleton course opens up. It watches the public class schedule and pushes a notification when a section flips from **Full → Open** (or a waitlist opens), so I don't have to keep refreshing Carleton Central during registration.

<img width="1151" height="409" alt="image" src="https://github.com/user-attachments/assets/1f6aaa18-0a39-42b5-af1d-94865312574c" />

## How it works

- Scrapes Carleton's public schedule (no login, read-only): reads the Status column (Open / Full / Waitlist) for the courses I care about.
- When one opens, it pushes to my phone through [ntfy](https://ntfy.sh).
- Runs itself every ~10 min on **GitHub Actions**, so it works even when my laptop is off.

Currently watching all 4th-year COMP courses plus PHIL 2003 and HIST 1301.

## Setup

**1. Install deps**
```
pip install -r requirements.txt
```

**2. Get notifications on your phone**
Install the **ntfy** app, tap *Subscribe to topic*, and pick a hard-to-guess topic name (e.g. `carleton-seats-xxxxx`).

**3. Pick your courses** — edit `config.json`:
```json
"watch": [
  { "subject": "COMP", "course_number": "4102" },
  { "subject": "COMP", "course_prefix": "4" },
  { "subject": "PHIL", "course_number": "2003", "sections": [{ "crn": "33777" }] }
]
```
- `course_number` = one exact course. `course_prefix: "4"` = the whole 4000 level.
- `sections` narrows to specific ones (by CRN or section letter). Leave it out to watch all.
- Terms: `202620` Summer 26, `202630` Fall 26, `202710` Winter 27.

## Run it

Test once:
```
python carleton_notifier.py --once
```
Run forever (locally):
```
python carleton_notifier.py
```
Or just let the GitHub Action run it 24/7 — it's in `.github/workflows/notifier.yml`. On the first run it quietly notes what's already full, then only pings you when something changes to open.

## Notes

- The topic name is basically the password for your alerts, so it's kept out of this repo and stored in a GitHub secret called `NTFY_TOPIC` (Settings → Secrets and variables → Actions). To run locally, set an `NTFY_TOPIC` env var.
- Read-only and polite (checks every ~10 min). You still register yourself — this just tells you when to.
