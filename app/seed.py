"""Seed the database with demo users, services and sample parcels (run automatically on startup)."""
import datetime
import random

from . import models, security
from .database import SessionLocal

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
        if db.query(models.User).count() > 0:
            return  # already seeded

        # --- Demo users -------------------------------------------------
        admin = models.User(
            full_name="Platform Admin",
            email="admin@swiftship.com",
            phone="01700000001",
            hashed_password=security.hash_password("Admin@123"),
            role="admin",
        )
        user = models.User(
            full_name="Rahim Uddin",
            email="user@swiftship.com",
            phone="01711111111",
            hashed_password=security.hash_password("User@123"),
            role="user",
        )
        karim = models.User(
            full_name="Karim Ahmed",
            email="karim@swiftship.com",
            phone="01722222222",
            hashed_password=security.hash_password("Karim@123"),
            role="user",
        )
        db.add_all([admin, user, karim])
        db.flush()

        # --- Delivery services -------------------------------------------
        standard = models.Service(
            name="Standard Delivery",
            description="Affordable 3-day delivery across all divisions of Bangladesh.",
            base_price=40, price_per_kg=8, eta_days=3,
        )
        express = models.Service(
            name="Express Delivery",
            description="Next-day delivery for urgent shipments.",
            base_price=90, price_per_kg=15, eta_days=1,
        )
        sameday = models.Service(
            name="Same-Day Delivery",
            description="Delivered within 4-6 hours inside Dhaka & Chittagong.",
            base_price=250, price_per_kg=40, eta_days=0,
        )
        international = models.Service(
            name="International Delivery",
            description="Door-to-door delivery to GCC, EU and Southeast Asia.",
            base_price=1500, price_per_kg=120, eta_days=10,
        )
        db.add_all([standard, express, sameday, international])
        db.flush()

        # --- Sample parcels ----------------------------------------------
        now = datetime.datetime.utcnow()
        names = ["Nusrat Jahan", "Tanvir Hasan", "Mehedi Rahman", "Sadia Islam", "Arif Chowdhury",
                 "Farhana Akter", "Jamal Hossain", "Tasnim Roy", "Sabbir Khan", "Lamia Haque"]
        phones = [f"018{i:08d}" for i in range(1, 11)]
        statuses = ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "delivered",
                    "delivered", "in_transit", "pending", "delivered", "cancelled", "in_transit",
                    "out_for_delivery", "delivered", "picked_up", "delivered", "pending", "in_transit"]

        random.seed(42)
        for i, status in enumerate(statuses):
            days_ago = random.randint(0, 30)
            created = now - datetime.timedelta(days=days_ago, hours=random.randint(0, 12))
            updated = created + datetime.timedelta(days=min(days_ago, 3) + random.randint(0, 1))
            updated = min(updated, now)
            owner = [user, user, user, karim][i % 4]
            service = [standard, express, sameday, international][i % 4]
            weight = round(random.uniform(0.5, 12), 1)
            price = round(service.base_price + service.price_per_kg * weight, 2)
            tracking = f"SS{created.strftime('%Y')}{i:04d}DEMO"
            db.add(models.Parcel(
                tracking_number=tracking,
                sender_name=owner.full_name,
                sender_phone=owner.phone,
                recipient_name=names[i % len(names)],
                recipient_phone=phones[i % len(phones)],
                pickup_address=random.choice(DEMO_CITIES),
                delivery_address=random.choice(DEMO_CITIES),
                weight_kg=weight,
                price=price,
                notes=["Fragile — handle with care" if i % 5 == 0 else None][0],
                status=status,
                service_id=service.id,
                owner_id=owner.id,
                created_at=created,
                updated_at=updated,
            ))
        db.commit()
        print(f"Seeded database: 3 users, 4 services, {len(statuses)} parcels")
    finally:
        db.close()
