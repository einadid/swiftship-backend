# SwiftShip — Backend (FastAPI)

Courier & Logistics Management Platform — API backend for the Phitron Final Exam SDP project.

## Stack

- **FastAPI** + Uvicorn
- **SQLite** via SQLAlchemy (zero-config; switch `DATABASE_URL` env to Postgres for production)
- **JWT** (PyJWT) — 30-min access tokens + 7-day refresh tokens (rotation on refresh)
- **bcrypt** password hashing
- **Pydantic v2** request/response validation (BD phone format, password strength, weights, prices)
- Auto-seeded demo data on first run (`app/seed.py`) — see demo accounts below

## Run

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- API base: `http://localhost:8000/api`
- Interactive docs (Swagger): `http://localhost:8000/docs`
- Health check: `GET /api/health`

The SQLite file is created at `backend/data/app.db` and auto-seeded with
3 users, 4 services and 18 parcels the first time the server starts.

## Environment variables (all optional in dev)

| Variable | Default | Purpose |
|---|---|---|
| `JWT_SECRET` | dev secret | Sign key for JWTs — **change in production** |
| `ACCESS_TOKEN_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | `7` | Refresh token lifetime |
| `CORS_ORIGINS` | `*` | Comma-separated allowed frontend origins |
| `DATABASE_URL` | `sqlite:///.../data/app.db` | Any SQLAlchemy URL (Postgres etc.) |

## API overview

### Authentication — `/api/auth`
| Method | Path | Access | Description |
|---|---|---|---|
| POST | `/signup` | public | Create account → JWT pair |
| POST | `/login` | public | Login → JWT pair + user |
| POST | `/refresh` | public (valid refresh token) | Rotate to a new token pair |
| GET | `/me` | user | Current user profile |
| POST | `/forgot-password` | public | Create 1h reset token (returns demo reset URL) |
| POST | `/reset-password` | public (valid token) | Set new password |
| POST | `/change-password` | user | Change own password |

### Parcels — `/api/parcels`
| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/` | user (own) / admin (all) | **Search, filter, sort, paginate** — params: `search, status, service_id, date_from, date_to, sort_by, sort_order, page, page_size` |
| GET | `/summary` | user | Own-parcel counts, spent, active |
| GET | `/track/{tracking_number}` | **public** | Track a parcel (status + history) |
| GET | `/stats` | admin | Dashboard analytics (revenue, by-status, recent) |
| GET | `/{id}` | owner / admin | Parcel detail |
| POST | `/` | user | Book a parcel (auto tracking no. + price) |
| PUT | `/{id}` | owner (while pending) / admin | Update parcel |
| PATCH | `/{id}/status` | admin | Move through delivery status pipeline |
| DELETE | `/{id}` | owner (while pending) / admin | Delete parcel |

### Services — `/api/services`
| Method | Path | Access | Description |
|---|---|---|---|
| GET | `/` | public | Active services (`?all=true` for admin) |
| POST / PUT / DELETE | `/`, `/{id}` | admin | CRUD (deletion blocked when in use) |

### Users — `/api/users` (admin only)
| Method | Path | Description |
|---|---|---|
| GET `/` | List/search/sort/paginate users |
| GET `/{id}` | User detail |
| PATCH `/{id}/active` | Block / unblock |
| POST `/{id}/reset-password` | Force password reset |

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Admin | `admin@swiftship.com` | `Admin@123` |
| User | `user@swiftship.com` | `User@123` |
| User | `karim@swiftship.com` | `Karim@123` |

## Project structure

```
backend/
├── requirements.txt
└── app/
    ├── main.py          # app factory, CORS, routers, health
    ├── database.py      # SQLAlchemy engine/session (SQLite default)
    ├── models.py        # User, Service, Parcel, PasswordResetToken
    ├── schemas.py       # Pydantic request/response models + validators
    ├── security.py      # bcrypt + JWT helpers
    ├── deps.py          # get_current_user / get_current_admin
    ├── seed.py          # demo data (runs on first startup)
    └── routers/
        ├── auth.py      # signup/login/refresh/forgot/reset/change password
        ├── parcels.py   # listing (search/filter/sort/paginate) + CRUD + tracking + stats
        ├── services.py  # delivery service catalog (admin CRUD)
        └── users.py     # user management (admin)
```
# swiftship-backend
