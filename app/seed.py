"""Seed the database with demo users, services and sample parcels (run automatically on startup).

Fixes applied:
- Idempotent: safe to run multiple times (checks existence before insert)
- Handles race conditions (flush + re-query)
- Ensures demo tracking number SS20260001DEMO always exists and is delivered
- Uses transaction rollback on error to avoid partial state
- Creates data directory if missing (handled in database.py too)
"""
import datetime
import random
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import models, security
from .database import SessionLocal

logger = logging.getLogger(__name__)

DEMO_CITIES = [
    "12/4 Gulshan Avenue, Dhaka 1212",
    "House 7, Road 11, Banani, Dhaka 1213",
    "Station Road, Mirpur 10, Dhaka 1216",
    "BSCCL Road, Chittagong 4100",
    "Kazla Gate, Sylhet 3100",
    "Zindabazar, Rajshahi 6200",
    "Rajbari Road, Khulna 9100",
    "GPO Main Road, Rangpur 5400",
]


def seed_data():
    db = SessionLocal()
    try:
        # --- Demo users -------------------------------------------------
        def get_or_create_user(email, full_name, phone, password, role):
            existing = db.scalar(select(models.User).where(models.User.email == email))
            if existing:
                return existing
            try:
                u = models.User(
                    full_name=full_name,
                    email=email,
                    phone=phone,
                    hashed_password=security.hash_password(password),
                    role=role,
                    is_active=True,
                )
                db.add(u)
                db.flush()
                return u
            except IntegrityError:
                db.rollback()
                return db.scalar(select(models.User).where(models.User.email == email))

        admin = get_or_create_user("admin@swiftship.com", "Admin User", "01700000001", "Admin@123", "admin")
        user = get_or_create_user("user@swiftship.com", "Rahim Uddin", "01700000002", "User@123", "user")
        karim = get_or_create_user("karim@swiftship.com", "Karim Ahmed", "01700000003", "Karim@123", "user")

        # Re-fetch to ensure IDs are loaded
        db.flush()
        if not admin or not user or not karim:
            # Fallback re-query
            admin = db.scalar(select(models.User).where(models.User.email == "admin@swiftship.com"))
            user = db.scalar(select(models.User).where(models.User.email == "user@swiftship.com"))
            karim = db.scalar(select(models.User).where(models.User.email == "karim@swiftship.com"))

        # --- Delivery services (exactly 4 required by contract) -----------
        desired_services = [
            ("Standard Delivery", "Regular nationwide delivery across all divisions", 60.0, 20.0, 5),
            ("Express Delivery", "Faster delivery within 48 hours", 120.0, 35.0, 2),
            ("Same-Day Delivery", "Within Dhaka city, same day delivery (4-6 hours)", 200.0, 50.0, 0),
            ("International Courier", "Air freight to 40+ countries worldwide", 1500.0, 850.0, 12),
        ]

        services_map = {}
        for name, desc, base_p, kg_p, eta in desired_services:
            srv = db.scalar(select(models.Service).where(models.Service.name == name))
            if not srv:
                try:
                    srv = models.Service(name=name, description=desc, base_price=base_p, price_per_kg=kg_p, eta_days=eta, is_active=True)
                    db.add(srv)
                    db.flush()
                except IntegrityError:
                    db.rollback()
                    srv = db.scalar(select(models.Service).where(models.Service.name == name))
            else:
                # Update pricing and metadata to match contract
                srv.description = desc
                srv.base_price = base_p
                srv.price_per_kg = kg_p
                srv.eta_days = eta
                srv.is_active = True
            if srv:
                services_map[name] = srv

        db.flush()
        srv_list = list(services_map.values())
        if not srv_list:
            logger.warning("No services found after seed, aborting parcel seed")
            db.commit()
            return

        # Ensure demo parcel SS20260001DEMO exists and is delivered
        demo_p = db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == "SS20260001DEMO"))
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if not demo_p:
            sameday = services_map.get("Same-Day Delivery", srv_list[0])
            # Ensure user exists
            owner_id = user.id if user else (admin.id if admin else 1)
            owner_name = user.full_name if user else "Demo User"
            owner_phone = user.phone if user else "01700000002"
            try:
                demo_p = models.Parcel(
                    tracking_number="SS20260001DEMO",
                    sender_name=owner_name,
                    sender_phone=owner_phone,
                    recipient_name="Tanvir Hasan",
                    recipient_phone="01811111111",
                    pickup_address="House 12, Road 5, Dhanmondi, Dhaka",
                    delivery_address="Banani, Dhaka",
                    weight_kg=1.5,
                    price=round(sameday.base_price + sameday.price_per_kg * 1.5, 2),
                    notes="Fragile parcel — handle with care",
                    status="delivered",
                    service_id=sameday.id,
                    owner_id=owner_id,
                    created_at=now - datetime.timedelta(days=2),
                    updated_at=now - datetime.timedelta(hours=3),
                )
                db.add(demo_p)
                db.flush()
            except IntegrityError:
                db.rollback()
                demo_p = db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == "SS20260001DEMO"))
        else:
            # Always ensure demo parcel is delivered for public tracking test
            if demo_p.status != "delivered":
                demo_p.status = "delivered"
                db.flush()

        # If few parcels exist, seed a full set
        total_parcels = db.scalar(select(func.count(models.Parcel.id))) or 0
        if total_parcels < 5:
            names = ["Nusrat Jahan", "Tanvir Hasan", "Mehedi Rahman", "Sadia Islam", "Arif Chowdhury",
                     "Farhana Akter", "Jamal Hossain", "Tasnim Roy", "Sabbir Khan", "Lamia Haque"]
            phones = [f"018{i:08d}" for i in range(11, 25)]
            statuses = [
                "pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "delivered",
                "delivered", "in_transit", "pending", "delivered", "cancelled", "in_transit",
                "out_for_delivery", "delivered", "picked_up", "delivered", "pending", "in_transit",
            ]
            random.seed(42)
            for i, status in enumerate(statuses):
                t_num = f"SS2026{i + 2:04d}DEMO"
                if db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == t_num)):
                    continue
                days_ago = random.randint(1, 28)
                created = now - datetime.timedelta(days=days_ago, hours=random.randint(1, 10))
                updated = created + datetime.timedelta(days=min(days_ago, 3))
                # Alternate owners: 2/3 user, 1/3 karim
                owner_obj = user if (i % 3 != 0) else karim
                if not owner_obj:
                    owner_obj = user or admin
                service = srv_list[i % len(srv_list)]
                weight = round(random.uniform(0.8, 8.0), 1)
                price = round(service.base_price + service.price_per_kg * weight, 2)
                try:
                    db.add(models.Parcel(
                        tracking_number=t_num,
                        sender_name=owner_obj.full_name,
                        sender_phone=owner_obj.phone,
                        recipient_name=names[i % len(names)],
                        recipient_phone=phones[i % len(phones)],
                        pickup_address=random.choice(DEMO_CITIES),
                        delivery_address=random.choice(DEMO_CITIES),
                        weight_kg=weight,
                        price=price,
                        notes="Handle with care" if i % 4 == 0 else None,
                        status=status,
                        service_id=service.id,
                        owner_id=owner_obj.id,
                        created_at=created,
                        updated_at=updated,
                    ))
                    db.flush()
                except IntegrityError:
                    db.rollback()
                    continue

        db.commit()
        logger.info("Database seeded successfully")
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        db.rollback()
    finally:
        db.close()
