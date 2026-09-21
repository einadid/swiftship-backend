# SwiftShip Backend - Courier & Logistics API

SwiftShip holo ekta Courier Management Platform. User parcel book korte pare, track korte pare, admin sob parcel manage kore.

### Tech Stack
- FastAPI + Uvicorn
- SQLite + SQLAlchemy
- JWT Auth + bcrypt
- Pydantic validation

### Main Features
- JWT Login/Signup, Refresh Token, Forgot/Reset Password
- Parcel CRUD - price auto calculate (base + per kg)
- Search by tracking/name/phone, Filter by status/service/date, Sorting, Pagination
- Public Tracking by tracking number
- Admin Analytics - revenue, by_status, recent parcels
- Service CRUD & User Management (block/unblock)

### Run Locally
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000