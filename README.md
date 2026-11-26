# Auraflow

**AI-assisted IT support with a built-in ticketing workflow.**

Auraflow lets employees describe an IT problem in plain language and get an instant fix from a knowledge base. When the fix does not work, the same chat raises a ticket, detects its urgency, starts an SLA timer and routes it to the right technician automatically. Technicians work from a queue, escalate from L1 to L2, and administrators get analytics, user management and a knowledge-base editor.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![Deployed on Vercel](https://img.shields.io/badge/Deployed%20on-Vercel-000000?logo=vercel&logoColor=white)

**Live demo:** `<add your Vercel URL here>`

---

## Table of contents

1. [Features](#features)
2. [Screenshots](#screenshots)
3. [Tech stack](#tech-stack)
4. [How it works](#how-it-works)
5. [Roles and permissions](#roles-and-permissions)
6. [Project structure](#project-structure)
7. [Getting started](#getting-started)
8. [Environment variables](#environment-variables)
9. [Deploying to Vercel](#deploying-to-vercel)
10. [Security](#security)
11. [Known limitations](#known-limitations)
12. [Roadmap](#roadmap)
13. [Author](#author)

---

## Features

**For employees**
- Chat assistant that matches a problem to a knowledge-base article and shows step-by-step fixes
- Quick-reply buttons: "That fixed it", "Still not working", and related topic suggestions
- One-click ticket creation from the chat, or through a standard ticket form
- Ticket list with All / Open / Resolved tabs and search
- Live SLA status, full activity history, comments, a 1 to 5 rating, and the option to reopen a ticket

**For technicians (L1 and L2)**
- Personal work queue sorted by SLA deadline, plus a waiting list that any eligible technician can claim from
- Start, resolve (with a required note), escalate to L2 (with a required reason), and comment
- Race-safe claiming, so two people cannot take the same ticket

**For administrators**
- Analytics dashboard: tickets by urgency, status and category, the last 7 days, SLA compliance, average resolution time, ratings, and per-technician performance
- User management: change roles, activate or deactivate accounts, and set technician specialties
- Knowledge-base editor: add, edit, publish, unpublish and delete articles, with a built-in tester that shows which article a sample message would match and at what confidence
- Reassign any open ticket to any active technician (administrators manage tickets and do not work them)

**Platform**
- Four roles: Employee, L1, L2, Admin
- Automatic urgency detection with a recorded reason on every ticket
- SLA timers: Critical 1 h, High 4 h, Medium 8 h, Low 24 h
- Specialty-based auto-assignment with load balancing
- ServiceNow-inspired ticket list and ticket form (state stepper, field grid, SLA meter, activity stream)
- Light and dark themes with a manual toggle that remembers your choice
- Responsive layout

## Screenshots

> Add screenshots to a `docs/` folder and link them here.

| Login | Assistant | Ticket detail |
|---|---|---|
| `docs/login.png` | `docs/chat.png` | `docs/ticket.png` |

| Work queue | Analytics | Knowledge base |
|---|---|---|
| `docs/queue.png` | `docs/analytics.png` | `docs/kb.png` |

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, vanilla JavaScript, Jinja2 templates |
| Backend | Python, Flask, Flask-SQLAlchemy |
| Database | PostgreSQL on [Neon](https://neon.tech) |
| NLP | Lightweight pure-Python matcher (no scikit-learn, no NLTK) |
| Hosting | Vercel (serverless Python) |
| Source control | Git and GitHub |

## How it works

### 1. Knowledge-base matching

The matcher in `nlp.py` is intentionally dependency-free and deterministic.

1. The message is lowercased, common spellings are unified (for example "wi-fi" and "wifi"), and punctuation is removed.
2. Stopwords are dropped and a small suffix stemmer reduces words to a common form, so "dropping" and "drop" match.
3. Each published article is scored by word overlap, weighted by where the word appears: **keywords (3.0)**, **title (2.0)**, **category (1.0)**, **solution text (0.4)**.
4. Rare words count more than common ones through an inverse-document-frequency factor, and multi-word keyword phrases such as "blue screen" earn a bonus.
5. The score becomes a confidence value, `score / (score + 6)`. Below **30%** the bot admits it is unsure and offers topic buttons instead of guessing.

Greetings, thanks and goodbyes are detected separately so they never trigger a false match. All tuning values sit at the top of `nlp.py`.

### 2. Urgency detection

A ticket starts from the matched article's default urgency. Phrases in the user's message can raise it:

| Signal | Example phrases | Result |
|---|---|---|
| Critical | "everyone", "whole office", "ransomware", "data loss", "hacked" | Critical |
| High | "urgent", "asap", "client", "deadline", "cannot work" | At least High |
| Relaxed | "no rush", "not urgent", "low priority" | One level lower, only when no urgent words are present |

The reason is written into the ticket history, for example *Urgency set to HIGH (message mentions "client")*.

### 3. SLA

| Urgency | Target |
|---|---|
| Critical | 1 hour |
| High | 4 hours |
| Medium | 8 hours |
| Low | 24 hours |

Each ticket shows **On track**, **At risk** (last 25% of the window), **Overdue**, or **SLA met / Resolved late** once closed. Times are stored in UTC and displayed in IST.

### 4. Assignment

New tickets and L2 escalations use the same rule, with ties broken by lowest id:

1. Active **specialist** for the ticket's category, with the fewest open tickets
2. Otherwise an active **generalist** (a technician with no specialties)
3. Otherwise any active technician of that level
4. If no technician exists, the ticket waits in the unassigned queue and can be claimed

The ticket history records which rule applied.

### 5. Ticket lifecycle

```
Open  ->  In progress  ->  Resolved  ->  Rated
  |            |               |
  +-> Escalated (L2) <---------+  (reopen returns to the previous level)
```

## Roles and permissions

| Capability | Employee | L1 | L2 | Admin |
|---|:---:|:---:|:---:|:---:|
| Chat with the assistant | Yes | Yes | Yes | Yes |
| Raise tickets | Yes | Yes | Yes | Yes |
| See own tickets | Yes | Yes | Yes | Yes |
| See tickets assigned to them | - | Yes | Yes | - |
| See all tickets | - | - | Yes | Yes |
| Work queue, claim, start, resolve | - | Own tickets | Any ticket | No |
| Escalate to L2 | - | Yes | - | No |
| Reassign tickets | - | - | Yes | Yes |
| Rate and reopen own resolved tickets | Yes | - | - | - |
| Analytics, users, knowledge base | - | - | - | Yes |

Public registration always creates an **Employee**. Higher roles are assigned by an administrator or the `create_user.py` script, and role checks are enforced on the server for every route.

## Project structure

```
Auraflow/
├── app.py                  # App factory, dashboard, error pages, health routes
├── config.py               # Configuration from environment variables
├── extensions.py           # Shared SQLAlchemy instance
├── models.py               # User, Article, Ticket, TicketUpdate, ChatMessage
├── auth.py                 # Register, login, logout, role decorators
├── chat.py                 # Chat endpoints and bot replies
├── nlp.py                  # Text matching and small-talk detection
├── urgency.py              # Urgency detection
├── sla.py                  # SLA deadlines and states
├── tickets.py              # Ticket creation, assignment, list and detail pages
├── workflow.py             # Queue, claim, start, resolve, escalate, reassign, rate, reopen
├── admin.py                # Analytics and user management
├── kb.py                   # Knowledge-base editor
├── init_db.py              # Creates database tables
├── seed.py                 # Loads the 10 starter articles
├── create_user.py          # Creates accounts (password typed in the terminal)
├── reset_password.py       # Resets a password or reactivates an account
├── migrate_specialties.py  # Adds the users.specialties column to an existing database
├── requirements.txt
├── .env.example
└── templates/
    ├── base.html           # Layout, design system, theme toggle
    ├── _logo.html          # Logo and favicon
    ├── _macros.html        # Shared template macros
    ├── login.html, register.html, dashboard.html
    ├── chat.html
    ├── tickets.html, ticket_new.html, ticket_detail.html
    ├── queue.html
    ├── admin_dashboard.html, admin_users.html
    ├── kb_list.html, kb_form.html
    └── message.html
```

## Getting started

### Prerequisites

- Python 3.11 or newer
- Git
- A free [Neon](https://neon.tech) account and project

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/auraflow.git
cd auraflow

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure the environment

Copy `.env.example` to `.env` and fill in your values (see [Environment variables](#environment-variables)).

```bash
# Generate a secret key
python -c "import secrets; print(secrets.token_hex(32))"
```

> Tip: create a separate **Neon branch** for local development so test data never mixes with your live data.

### 3. Create the tables and load the knowledge base

```bash
python init_db.py
python seed.py
```

`seed.py` is safe to run more than once. It skips articles whose title already exists.

If you are upgrading a database created before technician specialties existed, also run:

```bash
python migrate_specialties.py
```

### 4. Create accounts

```bash
python create_user.py
```

The script asks for a name, email, role and (for L1 and L2) specialties. The password is typed hidden and only its hash is stored. Create an **admin** first, then technicians. Employees can register themselves at `/register`.

Example starter team:

| Role | Specialties |
|---|---|
| L1 | Network |
| L1 | Email, Collaboration |
| L1 | Hardware |
| L1 | Account Access, Software |
| L2 | Network, Hardware |
| L2 | Account Access, Email, Software, Collaboration |

Leave specialties blank to create a generalist who can take any category.

### 5. Run

```bash
python app.py
```

Open http://127.0.0.1:5000.

### Maintenance scripts

| Script | Purpose |
|---|---|
| `python create_user.py` | Create one or more accounts |
| `python reset_password.py` | Reset a password or reactivate an account |
| `python seed.py` | Add any missing starter articles |

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Neon PostgreSQL connection string (include `sslmode=require`) |
| `SECRET_KEY` | Yes on Vercel | Random string used to sign session cookies |

`.env` is listed in `.gitignore` and must never be committed. `.env.example` documents the variable names without values.

## Deploying to Vercel

1. Push the project to GitHub.
2. In Vercel, choose **Add New, Project** and import the repository.
3. Under **Settings, Environment Variables**, add `DATABASE_URL` and `SECRET_KEY` for the **Production** environment.
4. Deploy. After changing any environment variable, **redeploy**, because existing deployments do not pick up new values.
5. Run `init_db.py` (and `seed.py`, `create_user.py`) **from your own machine** against the Neon database. The web app never creates tables on startup, which suits serverless hosting.
6. Visit `/health` to confirm the app is up.

Remember to commit new files (`git add .`), or Vercel will report missing templates or modules.

## Security

- Passwords are hashed with Werkzeug (salted, one-way) and never stored or logged in plain text
- No passwords, seed accounts, `.env` or database files are committed to the repository
- Sessions use signed cookies that are `HttpOnly`, `SameSite=Lax`, and `Secure` on the live site, and expire after 12 hours
- Login shows the same message for an unknown email and a wrong password
- Public sign-up can only create Employee accounts, and the role is never read from the form
- Every protected route checks the user's role on the server, and ticket access is checked per ticket
- Database access goes through SQLAlchemy with parameterised queries, and Jinja2 escapes output by default
- Administrators cannot change their own role or deactivate themselves
- Deactivating a technician returns their open tickets to the queue and signs them out on their next request

## Known limitations

- The matcher is keyword-based. It is fast and transparent, but it does not understand meaning the way a language model does
- State-changing actions rely on `SameSite=Lax` cookies and do not use CSRF tokens yet
- There is no login rate limiting, email notification, or in-app password reset (an administrator uses `reset_password.py`)
- SLA timers run on wall-clock time, not business hours
- `/db-test` is a diagnostic route and should be removed before a production launch

## Roadmap

- CSRF protection and login rate limiting
- Email or chat notifications for assignments and SLA breaches
- Business-hours SLA calendars
- File attachments on tickets
- CSV export for analytics
- Optional LLM-backed answers on top of the knowledge base

## Author

**`<Your name>`**
GitHub: `<your-username>` &middot; LinkedIn: `<your-profile-url>`
