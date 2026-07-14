# Carleton Central seat notifier

Polls Carleton's **public** class schedule (no login needed) and pushes a
notification to your phone the moment a course section flips from **Full → Open**
(or a waitlist opens).

It reads the same public page you can browse yourself:
<https://central.carleton.ca/prod/bwysched.p_select_term?wsea_code=EXT>

## Setup

1. **Install Python deps** (one time):
   ```
   pip install -r requirements.txt
   ```

2. **Get the phone app** (this is how you're notified):
   - Install **ntfy** from the App Store / Google Play.
   - Tap **+ Subscribe to topic** and enter your topic name **exactly** as it
     appears in `config.json` → `ntfy_topic` (currently
     `carleton-seats-833382a9`).
   - That's it — anything the script sends to that topic pops up on your phone.
   - The topic name is your only "password", so keep it private. Change it in
     `config.json` to anything hard to guess if you like.

3. **Point it at your course(s)** — edit `config.json`. It currently watches
   **all 4th-year COMP courses in Fall 2026**:
   ```json
   {
     "term_code": "202630",       // 202620=Summer26, 202630=Fall26, 202710=Winter27
     "subject": "COMP",
     "course_prefix": "4",         // "4" = every COMP 4xxx (4th year)
     "sections": [],               // [] = all sections
     "ntfy_topic": "carleton-seats-833382a9",
     "poll_seconds": 300,
     "notify_on_waitlist": true,
     "notify_current_open": false
   }
   ```
   Ways to scope it:
   - **A whole level:** `"course_prefix": "4"` → all COMP 4xxx.
   - **One exact course:** drop `course_prefix`, use `"course_number": "4102"`.
   - **Specific sections only:** `"sections": [{"crn": "31155"}, {"crn": "31158"}]`
     (5-digit CRN is the most precise) or `"sections": [{"section": "A"}]`.

   On startup it quietly learns the current state and only pings you when a
   section **changes** to open after that. Set `notify_current_open` to `true`
   if you also want to be told about seats that are already open when it starts.

## Run

Check once (good for testing):
```
python carleton_notifier.py --once
```

Run continuously (leave it running):
```
python carleton_notifier.py
```

You'll see a line per section each cycle, e.g.
`COMP 2402 A (CRN 31064): Full, No Waitlist  [full]`.
When one becomes Open, you get a phone push (and it won't nag you again for that
same section until it goes back to full and reopens).

## Notes / good manners

- The script only reads the public schedule — no credentials, no automated
  registration. You still register yourself in Carleton Central.
- Keep `poll_seconds` at 60 or higher so you're not hammering their server.
- Status values seen in the schedule: `Open`, `Full, No Waitlist`, and
  `Full, Waitlist ...`. "Open" and any waitlist-available state count as space.
- The public page doesn't expose exact seat counts, only these statuses — which
  is all that's needed to know when to jump on registration.

## Run it 24/7 in the cloud (works even when your laptop is OFF)

The script only runs while *something* is running it. Your laptop can't run it
while it's shut down or asleep. To have it watch around the clock regardless of
your laptop, run it on **GitHub Actions** (free) — it executes on GitHub's
servers every ~10 minutes. A workflow is already included at
`.github/workflows/notifier.yml`.

### One-time setup

1. **Make a GitHub account** if you don't have one: <https://github.com/signup>

2. **Create a repository** — click **New repository**, name it e.g.
   `cc-notifier`, and choose **Private** (recommended, so your ntfy topic
   stays hidden). Don't add a README (you already have one).

3. **Push this folder** to it. In a terminal here:
   ```
   cd "c:\Users\mayno\OneDrive\Documents\CC-notifier"
   git init
   git add .
   git commit -m "Carleton seat notifier"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/cc-notifier.git
   git push -u origin main
   ```

4. On GitHub, open the **Actions** tab and, if prompted, click to enable
   workflows. The schedule then starts on its own.

5. **Test it now:** Actions tab → *Carleton seat notifier* → **Run workflow**.
   Watch the run's log — it should list your sections. (It won't ping on this
   first run; it's learning the baseline. When a full section later opens,
   you'll get the push.)

That's it. It'll keep checking every ~10 minutes forever, laptop or no laptop.
It remembers state between runs (via the Actions cache), so you're only pinged
when a section *changes* to open — not every run.

### Two things to know

- **Keep the topic private:** if you ever make the repo *public*, move your
  topic out of `config.json`. Go to repo **Settings → Secrets and variables →
  Actions → New repository secret**, name it `NTFY_TOPIC`, paste your topic —
  the workflow already reads it and it overrides the file.
- **GitHub disables schedules after 60 days of no repo activity.** If you're
  watching across a long stretch, push any small commit now and then to keep it
  alive. Scheduled runs can also be delayed a few minutes when GitHub is busy.

## Or run it locally (only while the laptop is on)

Just leave a terminal open with `python carleton_notifier.py` running, or set it
up in **Windows Task Scheduler** to start at logon. This is paused whenever the
laptop sleeps or is off — that's why the cloud option above exists.
