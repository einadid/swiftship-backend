"""Seed the database with demo users, services and sample parcels (run automatically on startup)."""
import datetime
import random

from sqlalchemy import func, select

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
        # --- Demo users -------------------------------------------------
        admin = db.scalar(select(models.User).where(models.User.email == "admin@swiftship.com"))
        if not admin:
            admin = models.User(
                full_name="Admin User",
                email="admin@swiftship.com",
                phone="01700000001",
                hashed_password=security.hash_password("Admin@123"),
                role="admin",
                is_active=True,
            )
            db.add(admin)

        user = db.scalar(select(models.User).where(models.User.email == "user@swiftship.com"))
        if not user:
            user = models.User(
                full_name="Rahim Uddin",
                email="user@swiftship.com",
                phone="01700000002",
                hashed_password=security.hash_password("User@123"),
                role="user",
                is_active=True,
            )
            db.add(user)

        karim = db.scalar(select(models.User).where(models.User.email == "karim@swiftship.com"))
        if not karim:
            karim = models.User(
                full_name="Karim Ahmed",
                email="karim@swiftship.com",
                phone="01700000003",
                hashed_password=security.hash_password("Karim@123"),
                role="user",
                is_active=True,
            )
            db.add(karim)

        db.flush()

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
                srv = models.Service(name=name, description=desc, base_price=base_p, price_per_kg=kg_p, eta_days=eta)
                db.add(srv)
                db.flush()
            else:
                # Update pricing and metadata to match contract
                srv.description = desc
                srv.base_price = base_p
                srv.price_per_kg = kg_p
                srv.eta_days = eta
            services_map[name] = srv

        db.flush()
        srv_list = list(services_map.values())

        # Ensure demo parcel SS20260001DEMO exists and is delivered
        demo_p = db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == "SS20260001DEMO"))
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if not demo_p:
            sameday = services_map.get("Same-Day Delivery", srv_list[0])
            demo_p = models.Parcel(
                tracking_number="SS20260001DEMO",
                sender_name=user.full_name,
                sender_phone=user.phone,
                recipient_name="Tanvir Hasan",
                recipient_phone="01811111111",
                pickup_address="House 12, Road 5, Dhanmondi, Dhaka",
                delivery_address="Banani, Dhaka",
                weight_kg=1.5,
                price=round(sameday.base_price + sameday.price_per_kg * 1.5, 2),
                notes="Fragile parcel — handle with care",
                status="delivered",
                service_id=sameday.id,
                owner_id=user.id,
                created_at=now - datetime.timedelta(days=2),
                updated_at=now - datetime.timedelta(hours=3),
            )
            db.add(demo_p)
        else:
            demo_p.status = "delivered"

        # If few parcels exist, seed a full set
        if db.scalar(select(func.count(models.Parcel.id))) < 5:
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
                days_ago = random.randint(1, 28)
                created = now - datetime.timedelta(days=days_ago, hours=random.randint(1, 10))
                updated = created + datetime.timedelta(days=min(days_ago, 3))
                owner = user if i % 3 != 0 else karim
                service = srv_list[i % len(srv_list)]
                weight = round(random.uniform(0.8, 8.0), 1)
                price = round(service.base_price + service.price_per_kg * weight, 2)
                t_num = f"SS2026{i + 2:04d}DEMO"
                if not db.scalar(select(models.Parcel).where(models.Parcel.tracking_number == t_num)):
                    db.add(models.Parcel(
                        tracking_number=t_num,
                        sender_name=owner.full_name,
                        sender_phone=owner.phone,
                        recipient_name=names[i % len(names)],
                        recipient_phone=phones[i % len(phones)],
                        pickup_address=random.choice(DEMO_CITIES),
                        delivery_address=random.choice(DEMO_CITIES),
                        weight_kg=weight,
                        price=price,
                        notes="Handle with care" if i % 4 == 0 else None,
                        status=status,
                        service_id=service.id,
                        owner_id=owner.id,
                        created_at=created,
                        updated_at=updated,
                    ))

        db.commit()
    finally:
        db.close()
