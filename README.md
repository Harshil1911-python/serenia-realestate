# LuxeRealty — Real Estate Management Platform v2.0

## 🚀 Quick Start

```bash
cd realestate
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DATABASE_URL and SECRET_KEY
python app.py           # seeds DB and starts server
```

Visit: http://localhost:5000

## 🔑 Default Login URLs & Credentials

| Role | Login URL | Username | Password |
|------|-----------|----------|----------|
| Owner | /admin/login | owner | Owner@123456 |
| Developer | /devcontrol/login | developer | Dev@123456 |

> **Change login paths in Developer → Settings → Security tab**

## 📋 What's Fixed in v2.0

- ✅ **Messages visible in admin** — full Name, Email, Phone, Subject, Message, Date
- ✅ **Settings actually save** — all fields persist to database correctly
- ✅ **Theme colors work** — primary & accent colors apply site-wide instantly
- ✅ **Backup & Restore** — full ZIP backup with DB + media, one-click restore
- ✅ **Hidden login URLs** — change /admin and /devcontrol paths in Dev Settings
- ✅ **OpenStreetMap** — replaced Google Maps with Leaflet (no API key needed)
- ✅ **Properties map view** — filter + map toggle on properties page
- ✅ **Live preview** — settings page shows color/name preview before saving
- ✅ **Contact form** — sends messages, visible in Owner → Inquiries AND Developer → Messages
- ✅ **Mobile responsive** — all pages fully responsive

## 🗂 Project Structure

```
realestate/
├── app.py              # All routes, auth, backup/restore
├── models.py           # DB models
├── requirements.txt
├── render.yaml         # Render deployment
├── Procfile
├── .env.example
├── static/
│   ├── css/style.css   # Public theme (uses CSS vars for colors)
│   ├── css/admin.css   # Admin dashboard
│   ├── js/main.js
│   └── js/admin.js
└── templates/
    ├── partials/base.html          # Public base (injects theme colors)
    ├── partials/admin_base.html    # Admin sidebar
    ├── public/                     # Public pages
    ├── owner/                      # Owner dashboard
    └── developer/                  # Developer panel
```

## 🌐 Deploy to Render

1. Push to GitHub
2. Render → New Web Service → connect repo
3. Build: `pip install -r requirements.txt`
4. Start: `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT`
5. Add PostgreSQL database → set `DATABASE_URL` env var
6. Set `SECRET_KEY` env var (random 64 chars)
7. First deploy: add `python -c "from app import init_db; init_db()"` to build command

## 🔒 Security Features

- Dynamic login URL paths (change in Dev Settings → Security)
- Account lockout after 5 failed attempts
- CSRF protection on all forms
- XSS protection via bleach
- Rate limiting on login/contact
- Role-based access control

## 🗺 Maps (OpenStreetMap)

No API key needed! Set coordinates in:
- **Owner Settings → Map** tab: set lat/lng for office location
- **Property form**: set lat/lng for each property

## 💾 Backup & Restore

Developer → DB & Backup:
- **Download Backup**: creates ZIP with all DB data (JSON) + uploaded media
- **Restore Backup**: upload backup ZIP to restore settings, testimonials, FAQs, media

## 🔗 External Links (Developer)

Developer → External Links:
- Add any website URL with type: Header Nav, Footer, Social, iFrame, Custom Page
- iFrame type embeds the external site inside your platform
