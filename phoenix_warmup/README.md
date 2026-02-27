# Phoenix Warm-Up Engine
**by Phoenix Solutions**

A production-ready local Email Warm-Up Desktop Application for managing and automating Zoho inbox warm-up. Simulates human-like sending behavior to improve email deliverability.

---

## Features

- **Multi-inbox management** — Add, pause, resume, and delete Zoho inboxes
- **Automatic warm-up** — Stage-based sending with human-like randomized intervals
- **Auto-reply simulation** — IMAP scanning + probabilistic replies
- **Live activity feed** — Real-time dashboard showing all sends/replies/errors
- **Safety controls** — Auto-pause on bounce rate > 5%, auth failures, or consecutive errors
- **CSV-based storage** — All data stored locally in plain CSV files (no database required)
- **Non-blocking UI** — Background scheduling never freezes the interface
- **PyInstaller-ready** — Export to a standalone `.exe` with one command

---

## Warm-Up Stages

| Stage | Emails/Day | Notes |
|-------|-----------|-------|
| 1     | 5         | Initial ramp-up |
| 2     | 15        | Building reputation |
| 3     | 25        | Establishing volume |
| 4     | 40        | Full warm-up rate |

Stage automatically advances when daily quota is met consistently.

---

## Quick Setup

### 1. Prerequisites
- Python 3.11 or newer
- A Zoho email account with an **App Password** (not your regular password)

### 2. Install dependencies
```bash
cd phoenix_warmup
pip install -r requirements.txt
```

### 3. Configure (optional)
Edit `.env` to adjust working hours, bounce threshold, and reply rate:
```
WORK_START=08:00
WORK_END=20:00
BOUNCE_THRESHOLD=0.05
REPLY_RATE=0.40
```

### 4. Run the application
```bash
python main.py
```

---

## How to Use

1. **Launch** the app — double-click `main.py` or run `python main.py`
2. **Add Recipients** — Click "Add Recipients" to generate a pool of test addresses with Faker, or add real addresses manually
3. **Add an Inbox** — Click "+ Add Inbox", enter your Zoho email and app password, select a stage
4. **Test Connection** — Use the "Test Connection" button in the Add Inbox dialog to verify credentials
5. **Start Warm-Up** — Click the green "▶ Start" button in the header
6. **Monitor** — Watch the Live Activity Feed on the right for real-time status

---

## Zoho App Password Setup

1. Log in to your Zoho account at `accounts.zoho.com`
2. Go to **Security** → **App Passwords**
3. Generate a new app password for "Mail"
4. Use this password (not your login password) in the Phoenix Warm-Up Engine

**Zoho SMTP/IMAP settings (pre-filled by default):**
- SMTP: `smtp.zoho.in` port `587` (STARTTLS)
- IMAP: `imap.zoho.in` port `993` (SSL)

---

## Project Structure

```
phoenix_warmup/
├── main.py              # Entry point
├── app.py               # Application assembler
├── scheduler.py         # APScheduler background jobs
├── core/
│   ├── smtp_engine.py   # SMTP send logic
│   ├── imap_engine.py   # IMAP inbox scanning
│   ├── warmup_engine.py # Warm-up orchestration
│   ├── reply_engine.py  # Auto-reply logic
│   ├── ramp_logic.py    # Stage/limit calculations
│   ├── logger.py        # Structured event logging
│   └── content_generator.py  # Faker-based content
├── storage/
│   ├── inbox_store.py   # CSV CRUD for inboxes
│   ├── log_store.py     # CSV append-only log
│   └── recipient_store.py    # CSV CRUD for recipients
├── data/
│   ├── inboxes.csv      # Managed inboxes
│   ├── recipients.csv   # Recipient pool
│   └── logs.csv         # Activity log
├── ui/
│   └── dashboard.py     # CustomTkinter UI
├── assets/
│   └── phoenix_logo.png # App logo (auto-generated if missing)
├── .env                 # Configuration
└── requirements.txt     # Python dependencies
```

---

## Export to Standalone Executable (PyInstaller)

### Install PyInstaller
```bash
pip install pyinstaller
```

### Build (Windows)
```bash
cd phoenix_warmup
pyinstaller --onefile --windowed ^
  --add-data "assets;assets" ^
  --add-data "data;data" ^
  --name "PhoenixWarmUpEngine" ^
  main.py
```

### Build (macOS / Linux)
```bash
cd phoenix_warmup
pyinstaller --onefile --windowed \
  --add-data "assets:assets" \
  --add-data "data:data" \
  --name "PhoenixWarmUpEngine" \
  main.py
```

The compiled executable will be in the `dist/` directory.

**Important:** Place the `.env` file and `data/` folder alongside the executable before running.

---

## Safety & Compliance

- Emails are only sent during configured working hours
- Plain text only — no HTML, no links, no images
- Random send intervals (30 min – 3 hours depending on stage)
- Random reply delays (5 – 45 minutes)
- Auto-pause triggers:
  - Bounce rate > 5% in last 24 hours
  - SMTP authentication failure
  - 3+ consecutive SMTP errors
- All events logged to `data/logs.csv` (no passwords stored)

---

## Data Files

All data is stored in the `data/` directory as CSV files:

- `inboxes.csv` — Your configured Zoho inboxes (includes encrypted passwords)
- `recipients.csv` — Pool of recipient addresses for warm-up
- `logs.csv` — Full activity log (sends, replies, errors, stage changes)

These files can be backed up, inspected in Excel, or edited manually.

---

## Troubleshooting

**App won't start:**
- Ensure Python 3.11+ is installed: `python --version`
- Run `pip install -r requirements.txt`

**SMTP authentication failed:**
- Verify you're using an **App Password** (not your regular Zoho password)
- Ensure SMTP access is enabled in Zoho settings

**No emails being sent:**
- Check that the scheduler is running (green "● Running" badge in header)
- Verify working hours in `.env` match your local time
- Check that recipients have been added (click "Add Recipients")
- Check `data/logs.csv` for error messages

**UI appears frozen:**
- The UI should never freeze — if it does, restart the application
- Check the activity feed for any error messages

---

## License

Phoenix Solutions © 2024. All rights reserved.
