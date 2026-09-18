# 🛠️ Backend Instruction — SwiftShip Frontend-টা কাজ করতে Backend-এ কী কী লাগবে

এই ডকুমেন্টটা হলো **contract**: ফ্রন্টএন্ড (এই repo) যে API গুলো কল করে, backend ঠিক সেই
path + field name + response shape ফেরত দিলেই পুরো ওয়েবসাইট কোনো পরিবর্তন কাজ করবে।

> সংক্ষেপে: **৬টা জিনিস** ঠিক করলেই সব চলবে —
> 1. সব route `/api` prefix-এর নিচে mount করা (`app.include_router(..., prefix="/api")`)
> 2. CORS allow করা + `localhost:5173`/Netlify domain যোগ করা
> 3. JWT response-এ `{ user, tokens: { access_token, refresh_token } }` shape
> 4. List API-গুলোতে pagination envelope `{ items, total, page, page_size, total_pages }`
> 5. Parcel object-এ nested `service` + `owner`, আর status enum হুবহু frontend-এর নামে
> 6. `/parcels/summary`, `/parcels/stats`, `/parcels/track/{n}` route গুলো `/parcels/{id}` এর **আগে** declare করা

---

## 0. Frontend কীভাবে API কল করে

- Dev-এ ফ্রন্টএন্ড relative URL ব্যবহার করে: `fetch('/api/parcels/')`
  → `vite.config.js` proxy এটাকে `http://127.0.0.1:8000/api/parcels/` এ পাঠায়।
- Production-এ `VITE_API_URL` env দিয়ে দেওয়া হয়: `VITE_API_URL=https://your-backend.onrender.com/api`
- তাই backend-এর প্রতিটা route **`/api` দিয়ে শুরু হতে হবে**। (prefix ছাড়া backend থাকলে
  `vite.config.js`-এ `rewrite` লাইনটা uncomment করো, কিন্তু exam-এ `/api` prefix রাখাই ভালো।)

### CORS (এটা না করলে সব request browser-এ আটকে যাবে)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "https://your-frontend.netlify.app",
        "https://your-frontend.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# টিপস: exam/demo-র জন্য allow_origins=["*"] এবং allow_credentials=False ও চলবে,
# কারণ ফ্রন্টএন্ড token পাঠায় Authorization header-এ (cookie নয়)।
```

---

## 1. Authentication & Authorization (20 marks)

### Endpoints

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/auth/signup` | public | `{full_name, email, phone, password}` | `201 {user, tokens}` |
| POST | `/api/auth/login` | public | `{email, password}` | `200 {user, tokens}` |
| POST | `/api/auth/refresh` | public | `{refresh_token}` | `200 {access_token, refresh_token}` |
| GET | `/api/auth/me` | **Bearer** | — | `200 user` |
| POST | `/api/auth/forgot-password` | public | `{email}` | `200 {message, reset_url?}` |
| POST | `/api/auth/reset-password` | public | `{token, new_password}` | `200 {message}` |

### `user` object (এই field নামগুলোই frontend পড়ে)

```json
{ "id": 2, "full_name": "Rahim Uddin", "email": "user@swiftship.com",
  "phone": "01700000002", "role": "user", "is_active": true,
  "created_at": "2026-09-10T10:00:00Z" }
```

`role` অবশ্যই `"admin"` অথবা `"user"` — frontend `user.role === 'admin'` দিয়ে
sidebar, protected route আর admin-only button দেখায়।

### `tokens` object (⚠️ সবচেয়ে বেশি ভুল এখানেই হয়)

```json
{ "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer", "expires_in": 1800 }
```

Frontend `data.tokens.access_token` পড়ে (নেস্টেড `tokens` key বাধ্যতামূলক)।
Login response-এ `user` + `tokens` দুটোই একসাথে দাও:

```json
{
  "user": { "...": "..." },
  "tokens": { "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer", "expires_in": 1800 }
}
```

- Access token expiry: **30 মিনিট**, refresh: **7 দিন** (`exp` claim দিতে হবে)।
- ৪০১ হলে frontend নিজে `/auth/refresh` কল করে আবার চেষ্টা করে, তারপর fail করলে
  token মুছে `/login?reason=...` এ পাঠায়। তাই refresh endpoint অবশ্যই `200` দিতে হবে
  এবং নতুন `access_token` (এবং চাইলে নতুন `refresh_token`) ফেরত দেবে।
- Block করা user-এর login-এ **403** দাও, message: `Account is blocked. Contact support.`

### Password hashing (bcrypt)

```python
import bcrypt  # requirements: bcrypt

def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()

def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        return False
# passlib ব্যবহার করতে চাইলে: CryptContext(schemes=["bcrypt"]) + bcrypt==4.0.1 pin করো
```

### JWT + role guard

```python
import jwt, os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-env")
ALGORITHM = "HS256"
ACCESS_MINUTES, REFRESH_DAYS = 30, 7

def create_token(user, kind="access"):
    delta = timedelta(minutes=ACCESS_MINUTES) if kind == "access" else timedelta(days=REFRESH_DAYS)
    payload = {"sub": str(user.id), "role": user.role, "type": kind,
               "exp": datetime.now(timezone.utc) + delta}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

bearer = HTTPBearer(auto_error=False)

def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(get_db)):
    if cred is None:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(cred.credentials)
    if payload.get("type") != "access":
        raise HTTPException(401, "Wrong token type")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "User no longer exists")
    if not user.is_active:
        raise HTTPException(403, "Account is blocked")
    return user

def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin privileges required")
    return user
```

> ⚠️ Admin-only endpoint গুলো (`/parcels/stats`, `/users/*`, service POST/PUT/DELETE,
> `/parcels/{id}/status`, `/services/?all=true`) অবশ্যই `require_admin` দিয়ে protect করো —
> নাহলে "route protection" মার্ক কাটবে। Frontend-এ UI লুকানো আছে, কিন্তু backend-ও protect করা লাগবে।

### Forgot / Reset password

```python
@router.post("/forgot-password")
def forgot_password(payload: ForgotIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    reset_url = None
    if user:
        token = secrets.token_urlsafe(32)            # DB-তে store: reset_token + reset_token_expiry(UTC now + 1h)
        user.reset_token, user.reset_token_expiry = token, datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        # আসল ইমেইল পাঠানো optional (exam-এ SMTP নাই, তাই reset_url response-এ দিয়ে দাও)
        reset_url = f"{FRONTEND_URL}/reset-password?token={token}"
    # enumeration ঠেকাতে সবসময় একই message
    return {"message": "If an account exists for that email, a reset link has been sent.",
            "reset_url": reset_url}   # reset_url null হলে frontend কোনো link দেখাবে না
```

`FRONTEND_URL` env দাও: dev-এ `http://localhost:5173`, production-এ Netlify/Vercel link।
ফ্রন্টএন্ড এই URL থেকে path কেটে `/reset-password?token=...` রুটে নিয়ে যায় — তাই
**token অবশ্যই query param `token` নামে** থাকবে (frontend `?token=` পড়ে)।

---

## 2. Data model — field নাম হুবহু এইগুলো হতে হবে

```python
class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    full_name     = Column(String(120), nullable=False)
    email         = Column(String(160), unique=True, index=True, nullable=False)  # lowercase করে store করো
    phone         = Column(String(20))
    password_hash = Column(String(255), nullable=False)
    role          = Column(String(10), default="user")        # "user" | "admin"
    is_active     = Column(Boolean, default=True)
    reset_token  = Column(String(120))
    reset_token_expiry = Column(DateTime(timezone=True))
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Service(Base):
    __tablename__ = "services"
    id, name, description
    base_price   = Column(Float, default=0)
    price_per_kg = Column(Float, default=0)
    eta_days     = Column(Integer, default=3)
    is_active    = Column(Boolean, default=True)

class Parcel(Base):
    __tablename__ = "parcels"
    id, tracking_number (unique), owner_id (FK users.id), service_id (FK services.id)
    sender_name, sender_phone, recipient_name, recipient_phone
    pickup_address, delivery_address
    weight_kg = Column(Float, nullable=False)
    notes     = Column(Text, nullable=True)
    price     = Column(Float, default=0)                  # server-এ হিসাব করবে
    status    = Column(String(20), default="pending")
    created_at, updated_at
```

### Parcel response (nested service + owner বাধ্যতামূলক)

```json
{
  "id": 3, "tracking_number": "SS20260003", "status": "pending",
  "sender_name": "Rahim Uddin", "sender_phone": "01700000002",
  "recipient_name": "Sabbir Rahman", "recipient_phone": "01933333333",
  "pickup_address": "House 12, Road 5, Dhanmondi, Dhaka",
  "delivery_address": "Banani, Dhaka", "weight_kg": 0.8, "notes": "Call before delivery",
  "price": 260.0, "service_id": 3, "owner_id": 2,
  "service": { "id": 3, "name": "Same-Day Delivery", "base_price": 200, "price_per_kg": 50, "eta_days": 0, "is_active": true },
  "owner":   { "id": 2, "full_name": "Rahim Uddin", "email": "user@swiftship.com", "role": "user" },
  "created_at": "2026-09-18T06:20:00Z", "updated_at": "2026-09-18T06:20:00Z"
}
```

Frontend এই nested key গুলো পড়ে: `p.service.name` (table-এ service column),
`p.owner.full_name` (admin table-এ owner column), `p.tracking_number`, `p.status`, `p.price`, `p.weight_kg`, `p.created_at`।

Price সবসময় server-এ হিসাব করবে:
`price = service.base_price + service.price_per_kg * parcel.weight_kg` (round 2 decimal)।
Edit-এ `weight_kg` বদলালে আবার হিসাব করো; কখনো client-এর পাঠানো `price` বিশ্বাস করো না।

### Status enum (frontend-এর badge/রঙ এর সাথে বাঁধা)

`pending` → `picked_up` → `in_transit` → `out_for_delivery` → `delivered`, অথবা `cancelled`

- **status label/color frontend-এই আছে** (`src/components/Badge.jsx`)। Backend শুধু এই ৬টা
  exact string দেবে — `"In Transit"`, `"in-transit"`, `"PICKED_UP"` ইত্যাদি দিলে badge-এ raw text দেখাবে।
- Status পরিবর্তনের অনুমতি: `pending` → যে কোনো next; `delivered`/`cancelled` থেকে ফেরা যাবে না
  (অথবা admin-কে allow করো, কিন্তু invalid হলে **422** দাও)।

### Tracking number

`SS` + `year` + ৪-ডিজিট id, যেমন `SS20260001`. সবসময় unique ও uppercase।

---

## 3. Listing API — pagination / search / filter / sort (20 marks)

প্রতিটা list endpoint **একই envelope** ফেরত দেবে:

```json
{ "items": [ ... ], "total": 42, "page": 1, "page_size": 10, "total_pages": 5 }
```

Frontend `data.items`, `data.total`, `data.page`, `data.total_pages` পড়ে — তাই key নাম বদলাবে না।

### Query params (frontend এগুলো পাঠায়)

| Param | Type | কোথায় | মানে |
|---|---|---|---|
| `search` | string | parcels, users | tracking no / sender / recipient / phone / address / name / email — case-insensitive `ilike %search%` |
| `status` | string | parcels | exact status match |
| `service_id` | int | parcels | service filter |
| `date_from`, `date_to` | `YYYY-MM-DD` | parcels | `created_at` এর date range (inclusive) |
| `sort_by` | string | parcels, users | `created_at`, `tracking_number`, `sender_name`, `recipient_name`, `price`, `status` |
| `sort_order` | `asc` \| `desc` | parcels, users | direction (default `desc`) |
| `page` | int ≥1 | all | default 1 |
| `page_size` | int | all | frontend 5/10/20/50 পাঠায় (default 10, max 100 clamp) |

অবশ্যই **whitelist** করো, unrestricted `sort_by` সরাসরি SQL-এ দিও না:

```python
SORTABLE = {"created_at", "tracking_number", "sender_name", "recipient_name", "price", "status"}

def paginate(query, page: int, page_size: int, sort_by: str, sort_order: str, model, default_sort="created_at"):
    sort_by = sort_by if sort_by in SORTABLE else default_sort
    col = getattr(model, sort_by)
    query = query.order_by(col.asc() if sort_order == "asc" else col.desc())
    total = query.count()
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": max(1, math.ceil(total / page_size))}
```

`sort_by=price` এর জন্য numeric ordering দিতে হবে (string comparison নয়)।

---

## 4. Parcels endpoints

| Method | Path | Auth | কে | Response |
|---|---|---|---|---|
| GET | `/api/parcels/` | Bearer | user = নিজের, admin = সব | pagination envelope |
| POST | `/api/parcels/` | Bearer | সব | `201` parcel |
| GET | `/api/parcels/{id}` | Bearer | owner বা admin | parcel |
| PUT | `/api/parcels/{id}` | Bearer | owner (pending হলে) বা admin | parcel |
| DELETE | `/api/parcels/{id}` | Bearer | owner (pending হলে) বা admin | `204` |
| PATCH | `/api/parcels/{id}/status` | **admin** | admin | parcel |
| GET | `/api/parcels/summary` | Bearer | user | summary |
| GET | `/api/parcels/stats` | **admin** | admin | stats |
| GET | `/api/parcels/track/{tracking_number}` | **public** | যে কেউ | tracker object |

### 🚨 Route order trap (অনেকেই এখানে আটকে যায়)

FastAPI উপরে-থেকে-নিচে match করে। তাই `/parcels/{parcel_id}` যদি `/parcels/summary` এর
**আগে** থাকে, তাহলে `summary` কে `parcel_id` ভাববে → `422 int_parsing` error।
ক্রম ঠিক এইভাবে রাখো:

```python
@router.get("/parcels/summary")          # 1. static route আগে
@router.get("/parcels/stats")
@router.get("/parcels/track/{tracking_number}")
@router.get("/parcels/")                 # 2. list
@router.post("/parcels/")
@router.get("/parcels/{parcel_id}")      # 3. dynamic route সবার শেষে
@router.put("/parcels/{parcel_id}")
@router.patch("/parcels/{parcel_id}/status")
@router.delete("/parcels/{parcel_id}")
```

### `GET /parcels/` (owner filter ভুল করা যাবে না)

```python
@router.get("/parcels/")
def list_parcels(search: str | None = None, status: str | None = None, service_id: int | None = None,
                 date_from: date | None = None, date_to: date | None = None,
                 sort_by: str = "created_at", sort_order: str = "desc",
                 page: int = 1, page_size: int = 10,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Parcel).options(joinedload(Parcel.service), joinedload(Parcel.owner))
    if user.role != "admin":                      # admin সব দেখে, user শুধু নিজের
        q = q.filter(Parcel.owner_id == user.id)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(Parcel.tracking_number.ilike(like), Parcel.sender_name.ilike(like),
                         Parcel.recipient_name.ilike(like), Parcel.sender_phone.ilike(like),
                         Parcel.recipient_phone.ilike(like), Parcel.delivery_address.ilike(like)))
    if status:      q = q.filter(Parcel.status == status)
    if service_id:  q = q.filter(Parcel.service_id == service_id)
    if date_from:   q = q.filter(func.date(Parcel.created_at) >= date_from)
    if date_to:     q = q.filter(func.date(Parcel.created_at) <= date_to)
    return paginate(q, page, page_size, sort_by, sort_order, Parcel)
```

### Create / Update

```python
class ParcelCreate(BaseModel):
    service_id: int
    sender_name: str = Field(min_length=2)
    sender_phone: str = Field(pattern=r"^(\+?88)?01[3-9]\d{8}$")
    recipient_name: str = Field(min_length=2)
    recipient_phone: str = Field(pattern=r"^(\+?88)?01[3-9]\d{8}$")
    pickup_address: str = Field(min_length=5)
    delivery_address: str = Field(min_length=5)
    weight_kg: float = Field(gt=0, le=500)
    notes: str | None = None

@router.post("/parcels/", status_code=201)
def create_parcel(payload: ParcelCreate, db=Depends(get_db), user=Depends(get_current_user)):
    service = db.get(Service, payload.service_id)
    if not service or not service.is_active:
        raise HTTPException(422, "Selected delivery service is not available")
    parcel = Parcel(owner_id=user.id, service_id=service.id, status="pending",
                    price=round(service.base_price + service.price_per_kg * payload.weight_kg, 2),
                    tracking_number=next_tracking_number(db), **payload.model_dump(exclude={"service_id"}))
    db.add(parcel); db.commit(); db.refresh(parcel)
    return parcel
```

Edit rules (frontend exactly এটাই ধরে নিয়ে UI দেখায়):

- user শুধু **`pending`** parcel edit/delete করতে পারে → নাহলে **400** `"Only pending parcels can be edited"`.
- admin যেকোনো status-এর parcel edit/delete করতে পারে (delete করলে parcel + তার history মুছে যাবে)।
- `PUT` বডিতে `service_id` না থাকলেও চলবে (frontend edit-এ service পাঠায় না), কিন্তু
  `weight_kg` বদলালে price আবার হিসাব করতে হবে।
- অন্য কারো parcel-এ access দিলে **403**।

### Status update (admin panel-এর dropdown এটা কল করে)

```python
class StatusIn(BaseModel):
    status: Literal["pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "cancelled"]

@router.patch("/parcels/{parcel_id}/status")
def change_status(parcel_id: int, payload: StatusIn, db=Depends(get_db), admin=Depends(require_admin)):
    parcel = db.get(Parcel, parcel_id) or raise_(HTTPException(404, "Parcel not found"))
    parcel.status = payload.status
    parcel.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(parcel)
    return parcel          # frontend updated.tracking_number পড়ে toast দেখায়
```

### Public tracking — `GET /parcels/track/{tracking_number}` (login লাগবে না)

```python
@router.get("/parcels/track/{tracking_number}")
def track(tracking_number: str, db=Depends(get_db)):
    parcel = db.query(Parcel).options(joinedload(Parcel.service)).filter(
        func.upper(Parcel.tracking_number) == tracking_number.upper()).first()
    if not parcel:
        raise HTTPException(404, "No parcel found with that tracking number")
    index = ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered"].index(parcel.status) \
            if parcel.status != "cancelled" else -1
    steps = ["Booked", "Picked up", "In transit", "Out for delivery", "Delivered"]
    return {
        "tracking_number": parcel.tracking_number,
        "status": parcel.status,
        "sender_name": parcel.sender_name,
        "recipient_name": parcel.recipient_name,
        "pickup_address": parcel.pickup_address,
        "delivery_address": parcel.delivery_address,
        "weight_kg": parcel.weight_kg,
        "price": parcel.price,
        "service_name": parcel.service.name if parcel.service else "",
        "booked_at": parcel.created_at,
        "last_updated": parcel.updated_at,
        "history": [{"label": s, "done": index >= i} for i, s in enumerate(steps)],
    }
```

> `history` না দিলেও frontend নিজেই status থেকে timeline আঁকতে পারে (fallback আছে),
> কিন্তু দিলে প্যানেলের timeline-এ tick mark গুলো backend-এর সত্যি data থেকে আসবে — বেশি মার্ক।

### Summary (user dashboard) ও Stats (admin dashboard)

```json
// GET /api/parcels/summary   → নিজের parcel-এর হিসাব
{ "total": 3, "active": 2, "delivered": 1, "cancelled": 0, "total_spent": 475.0 }
// active  = status not in ("delivered", "cancelled")
// total_spent = delivered parcel গুলোর price যোগফল

// GET /api/parcels/stats     → admin only
{ "total_parcels": 12, "active_parcels": 7, "total_revenue": 5430.0,
  "total_users": 8, "total_services": 4,
  "by_status": { "pending": 3, "picked_up": 1, "in_transit": 2,
                 "out_for_delivery": 1, "delivered": 5, "cancelled": 0 },
  "recent_parcels": [ /* সর্বশেষ ৫টা parcel object */ ] }
```

`by_status`-এ **সবগুলো status key থাকতে হবে** (০ হলেও) — নাহলে admin chart-এ bar গুলো অসম্পূর্ণ দেখাবে।
`recent_parcels`-এ nested `service`/`owner` লাগবে না, কিন্তু `tracking_number`, `sender_name`, `price`, `status` লাগবে।

---

## 5. Services endpoints

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/services/` | public | `[service, ...]` — শুধু `is_active = true` |
| GET | `/api/services/?all=true` | **admin** | সব (active + inactive) |
| POST | `/api/services/` | **admin** | `201` service |
| PUT | `/api/services/{id}` | **admin** | service |
| DELETE | `/api/services/{id}` | **admin** | `204` |

- ⚠️ এখানে **plain array** ফেরত দিতে হবে (pagination envelope **নয়**) — frontend `services.map(...)`
  করে, তাই `{items: [...]}` দিলে booking form ফাঁকা দেখাবে।
- `is_active = false` করা service user-এর booking dropdown-এ আসবে না।
- কোনো parcel যে service ব্যবহার করছে সেটা delete করতে দিলে **409** দাও
  (`"Service is used by existing parcels — deactivate it instead"`); অথবা parcel-এর FK `ondelete="SET NULL"`
  রাখো। Frontend 409 message-টাই toast-এ দেখাবে।
- `base_price`, `price_per_kg`, `eta_days`, `is_active` — এই নামগুলোই frontend পড়ে
  (`eta_days === 0` হলে "Same day" দেখায়)।

---

## 6. Users endpoints (admin panel)

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/users/` | **admin** | pagination envelope (`search`, `sort_order`, `page`, `page_size`) |
| PATCH | `/api/users/{id}/active` | **admin** | user (`{"is_active": false}` block, `true` unblock) |
| POST | `/api/users/{id}/reset-password` | **admin** | `{message}` (`{"new_password": "..."}`) |

- `/users/` এ কখনো `password_hash`/`reset_token` পাঠাবে না — শুধু public field (id, full_name,
  email, phone, role, is_active, created_at)।
- Admin নিজের account block করতে পারবে না → **400** দাও (frontend সেই button লুকিয়ে রাখে, তবু backend check দরকার)।
- Bulk delete user/parcel দরকার নেই — frontend single delete ব্যবহার করে।

---

## 7. Error format (frontend toast-এ এটাই দেখায়)

সব error `{"detail": "মানুষের পড়ার মতো message"}` আকারে দাও:

| Code | কখন | উদাহরণ `detail` |
|---|---|---|
| 400 | business rule ভাঙা | `Only pending parcels can be edited` |
| 401 | token নাই/expired/wrong password | `Invalid email or password` |
| 403 | role/permission বা block | `Account is blocked. Contact support.` |
| 404 | entity নাই | `Parcel not found` |
| 409 | duplicate/conflict | `Email already registered` |
| 422 | validation (Pydantic) | `Input should be a valid number` |

Pydantic-এর 422 দিলে detail list আকারে আসে — frontend সেটাও handle করে
(`detail[].msg` join করে toast দেখায়), কিন্তু custom message দিলে আরও ভালো দেখায়।

---

## 8. Seed data (এটা must match, নাহলে landing page/login hint মিলবে না)

Startup-এ (বা আলাদা `seed.py`) idempotent ভাবে এই data দাও:

```python
def seed(db):
    if db.query(User).count() == 0:
        db.add_all([
            User(full_name="Admin User", email="admin@swiftship.com", phone="01700000001",
                 password_hash=hash_password("Admin@123"), role="admin"),
            User(full_name="Rahim Uddin", email="user@swiftship.com", phone="01700000002",
                 password_hash=hash_password("User@123"), role="user"),
        ])
    if db.query(Service).count() == 0:
        db.add_all([
            Service(name="Standard Delivery",     description="Regular nationwide delivery",   base_price=60,   price_per_kg=20,  eta_days=5),
            Service(name="Express Delivery",      description="Faster delivery within 48 hours", base_price=120, price_per_kg=35, eta_days=2),
            Service(name="Same-Day Delivery",     description="Within Dhaka city, same day",    base_price=200,  price_per_kg=50,  eta_days=0),
            Service(name="International Courier", description="Air freight to 40+ countries",   base_price=1500, price_per_kg=850, eta_days=12),
        ])
    if db.query(Parcel).count() == 0:
        # demo parcel: tracking_number "SS20260001DEMO", status "delivered"
        # → landing page ও /track page দুটোতেই এটা দেখানো আছে
        ...
    db.commit()
```

- **Admin:** `admin@swiftship.com` / `Admin@123` • **User:** `user@swiftship.com` / `User@123`
  (Login page-এ quick-fill button এই দুটো দিয়েই set করা আছে; submission-এ এই credential-ই দিতে হবে)
- Demo tracking number: **`SS20260001DEMO`** (delivered অবস্থায় seed করলে timeline-টা সুন্দর দেখাবে)
- Services: ঠিক **৪টা** seed করো (landing page-এ "4 delivery services" লেখা আছে)।

---

## 9. `main.py` — সব একসাথে

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine, SessionLocal
from routers import auth, parcels, services, users
from seed import seed

app = FastAPI(title="SwiftShip API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed(db)

API = "/api"                                  # ⚠️ frontend এটাই আশা করে
app.include_router(auth.router,     prefix=API)   # /api/auth/...
app.include_router(services.router, prefix=API)   # /api/services/...
app.include_router(parcels.router,  prefix=API)   # /api/parcels/...
app.include_router(users.router,    prefix=API)   # /api/users/...

@app.get("/")
def health():
    return {"status": "ok", "docs": "/docs"}
```

**requirements.txt**

```
fastapi
uvicorn[standard]
sqlalchemy
pydantic[email]
PyJWT
bcrypt
python-multipart
```

### Deployment (Live Backend Link মার্কের জন্য)

- **Render:** Start command `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Vercel (Python):** `vercel.json` → `{"rewrites":[{"source":"/(.*)","destination":"/api/index.py"}]}`
- SQLite Render-এ ephemeral — demo-র জন্য ঠিক আছে (restart-এ seed আবার হয়ে যাবে)।
  Postgres চাইলে `DATABASE_URL` env দাও এবং `SQLALCHEMY_DATABASE_URI` সেট করো।
- Env vars: `SECRET_KEY`, `FRONTEND_URL`, `DATABASE_URL` (optional)
- Deploy শেষে frontend-এ `VITE_API_URL=https://<backend-host>/api` সেট করে rebuild দাও।

---

## 10. Curl checklist (backend চালু করে এগুলো টেস্ট করো)

```bash
BASE=http://127.0.0.1:8000/api

# 1) login → user + tokens shape
curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"user@swiftship.com","password":"User@123"}'

# 2) bearer দিয়ে নিজের list (envelope check)
TOKEN=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"user@swiftship.com","password":"User@123"}' | python -c "import sys,json;print(json.load(sys.stdin)['tokens']['access_token'])")
curl -s "$BASE/parcels/?page=1&page_size=5&sort_by=created_at&sort_order=desc" -H "Authorization: Bearer $TOKEN"

# 3) public tracking (auth ছাড়া)
curl -s $BASE/parcels/track/SS20260001DEMO

# 4) summary আগে match হচ্ছে কি না (route order test)
curl -s $BASE/parcels/summary -H "Authorization: Bearer $TOKEN"

# 5) services plain array
curl -s $BASE/services/

# 6) admin only — user token দিয়ে 403 আসা উচিত
curl -s -o /dev/null -w '%{http_code}\n' $BASE/parcels/stats -H "Authorization: Bearer $TOKEN"

# 7) validation — ভুল phone দিলে 422 আসা উচিত
curl -s -X POST $BASE/parcels/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"service_id":1,"sender_name":"A","sender_phone":"123","recipient_name":"B", "recipient_phone":"01700000002","pickup_address":"xxxxx","delivery_address":"yyyyy","weight_kg":2}'
```

---

## 11. Frontend-এর দিক থেকে চেকলিস্ট (আগে-পরে)

| Symptom | কারণ | Fix |
|---|---|---|
| My Parcels / All Parcels পেজ সাদা (blank) | ছিল: `StatusBadge` import missing | ✅ ফ্রন্টএন্ডে ঠিক করা হয়েছে |
| প্রতিটা পেজের নিচে ঘুরতে থাকা spinner | ছিল: App-এ stray `<FullPageSpinner/>` | ✅ ঠিক করা হয়েছে |
| Login করার পর refresh দিলে logout হয়ে যেত | refresh token থাকলেও boot-এ refresh হতো না | ✅ `ensureFreshToken()` যোগ করা হয়েছে |
| Pagination-এ একাধিক `…` বাটন | gap logic ভুল ছিল | ✅ ঠিক করা হয়েছে |
| Modal-এ Delete চাপলে modal হারিয়ে যেত | native `<dialog>` নিজে close হয়ে যেত | ✅ `div.modal.modal-open` ভিত্তিক Modal |
| Track বাটনে ক্লিক করলে input ফাঁকা | `location.state` পড়া হতো না | ✅ state থেকে auto-search |
| Mobile-এ logout করা যেত না | bottom nav-এ logout ছিল না | ✅ top bar যোগ করা হয়েছে |

Backend-এ যদি উপরের কনট্রাক্টের কোনো একটা বদলাতে চাও, তাহলে শুধু
`src/api/client.js` / সংশ্লিষ্ট page-এর field নাম বদলালেই হবে — সব API call এক জায়গায় আছে।
