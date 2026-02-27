# CLAUDE.md — Phoenix Solutions Repository

## Repository Overview

This repository contains two distinct projects:

1. **Phoenix Consulting Website** — Static HTML/CSS/JS marketing site (root directory)
2. **Phoenix Warm-Up Engine** — Python desktop email warm-up application (`phoenix_warmup/`)

---

## Phoenix Consulting Website

**Technology:** Static HTML5 (Hyperspace by HTML5 UP template)
**Files:** `index.html`, `Learn More.html`, `What we do.html`, `elements.html`
**Assets:** `assets/` (CSS, JS, SCSS, Font Awesome icons), `images/`

### Notes
- No build step required — pure static files
- Links between pages are case-sensitive: use exact filenames (`What we do.html`)
- Contact form at `index.html` uses `action="#"` — backend integration not yet implemented

---

## Phoenix Warm-Up Engine (`phoenix_warmup/`)

### Purpose
A local Python desktop application for automated email warm-up of Zoho inboxes. Simulates human-like sending behavior to improve email deliverability.

### Technology Stack
- **Python 3.11+**
- **CustomTkinter** — UI (dark mode, branded colors)
- **APScheduler** — Background scheduling (BackgroundScheduler with ThreadPoolExecutor)
- **smtplib** (stdlib) — SMTP email sending
- **imapclient** — IMAP inbox scanning
- **Faker** — Content variation
- **python-dotenv** — Environment configuration
- **Pillow** — Logo image handling
- **CSV** — All data storage (no SQL, no external DB)

### Project Structure
```
phoenix_warmup/
├── main.py              # Entry point (PyInstaller-safe)
├── app.py               # Application assembler
├── scheduler.py         # APScheduler wrapper (WarmupScheduler)
├── core/                # Business logic (no UI dependencies)
│   ├── smtp_engine.py
│   ├── imap_engine.py
│   ├── warmup_engine.py
│   ├── reply_engine.py
│   ├── ramp_logic.py
│   ├── logger.py
│   └── content_generator.py
├── storage/             # Thread-safe CSV CRUD
│   ├── inbox_store.py
│   ├── log_store.py
│   └── recipient_store.py
├── data/                # CSV data files (user data, not committed with credentials)
├── ui/                  # CustomTkinter dashboard
│   └── dashboard.py
├── assets/              # Static assets (logo)
├── .env                 # Configuration (not committed to production)
└── requirements.txt
```

### Development Conventions

#### Threading Model (CRITICAL)
- **All UI operations MUST happen on the main thread only**
- Background jobs (APScheduler) communicate with the UI via `queue.Queue`
- The dashboard polls the queue every 500ms using `tkinter.after()`
- Never call tkinter widget methods from background threads

```python
# CORRECT: Post to queue from background thread
self.ui_queue.put_nowait({"type": "send", "inbox": email, "message": msg})

# WRONG: Calling tkinter from background thread (will crash)
self.some_label.configure(text="new text")  # DON'T do this in a thread
```

#### CSV Storage Pattern
- Each store module (`inbox_store.py`, etc.) has a module-level `threading.Lock()`
- All reads AND writes must be wrapped with `with _lock:`
- Never call private `_read_raw()` or `_write_raw()` without holding the lock
- LogStore uses append-only mode for performance; never rewrites the whole file

#### Core Engine Contracts
- `WarmupEngine.run_cycle()` — Called every 60s by scheduler; must be safe to call concurrently (APScheduler `max_instances=1` prevents this but the code should be re-entrant)
- `ReplyEngine.run_reply_cycle()` — Called every 5min; connects fresh IMAP per inbox
- All engines `return` silently on errors; they never `raise` to the scheduler

#### Content Rules (Do Not Violate)
- Plain text email bodies ONLY — no HTML tags
- No links/URLs in email bodies
- No fixed subject/body patterns — always use random templates from `content_generator.py`
- Send intervals: 30min–3hrs (Stage 1), 15min–90min (Stage 2), 10min–1hr (Stage 3), 5min–40min (Stage 4)

#### Safety Rules
- Never send emails immediately on startup
- Check `within_working_hours()` before every send
- Auto-pause inbox on: bounce rate > 5%, auth failure, or SMTP errors (configurable)
- Never log passwords — `logger.py` has `_redact_passwords()` for sanitizing error messages

### Brand Colors
```python
PRIMARY     = "#FF6A00"   # Deep orange (Phoenix brand)
SECONDARY   = "#1E1E1E"   # Dark charcoal
BG          = "#2B2B2B"   # Dark background
ACCENT      = "#FFFFFF"   # White text
```

### Running the Application
```bash
cd phoenix_warmup
pip install -r requirements.txt
python main.py
```

### Building Executable (PyInstaller)
```bash
# Windows
pyinstaller --onefile --windowed --add-data "assets;assets" --add-data "data;data" --name "PhoenixWarmUpEngine" main.py

# macOS/Linux
pyinstaller --onefile --windowed --add-data "assets:assets" --add-data "data:data" --name "PhoenixWarmUpEngine" main.py
```

### Key Data Schemas

**inboxes.csv:**
```
email,smtp_host,smtp_port,imap_host,imap_port,password,stage,daily_sent,
daily_limit,status,last_sent_at,paused_reason,working_hours_start,working_hours_end
```

**recipients.csv:**
```
email,name,domain,active,count_used,last_used
```

**logs.csv:**
```
timestamp,inbox_email,event_type,recipient,subject,details
```
Event types: `SEND`, `REPLY`, `BOUNCE`, `ERROR`, `PAUSE`, `RESUME`, `STAGE`, `RESET`, `INFO`

### Adding New Features
1. New storage fields → Update the `HEADERS` list and `InboxRecord` dataclass in the relevant store
2. New UI events → Add to `EVENT_ICONS` dict in `dashboard.py` and handle in `_dispatch_event()`
3. New scheduler jobs → Add to `WarmupScheduler.start()` in `scheduler.py`
4. New content templates → Add to lists in `content_generator.py`

### Common Pitfalls
- **Don't update CSV headers without migrating existing data** — The stores use `csv.DictReader` which maps by header name; adding columns without defaults will break loading old files
- **Don't add `time.sleep()` in warmup/reply engines** — Sleeping in APScheduler jobs blocks the thread pool. Use interval triggers instead
- **Don't store objects across scheduler ticks** — The engine may hold stale inbox records; always re-fetch from store before writing
- **PyInstaller data paths** — Use `get_assets_dir()` / `get_data_dir()` from `main.py`, never hardcode relative paths

---

## Git Branch
- Development branch: `claude/claude-md-mm4sflow7n0zw5xr-xxFye`
- Upstream: `smitchandarana/demo2` → `main`
