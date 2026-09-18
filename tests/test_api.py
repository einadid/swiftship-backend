import pytest
from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cors_headers():
    res = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert res.headers.get("access-control-allow-credentials") == "true"


def test_auth_login():
    res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    assert res.status_code == 200
    data = res.json()
    assert "user" in data
    assert "tokens" in data
    assert data["user"]["email"] == "user@swiftship.com"
    assert data["user"]["role"] == "user"
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]
    assert data["tokens"]["token_type"] == "bearer"
    assert data["tokens"]["expires_in"] == 1800


def test_auth_refresh():
    login_res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    refresh_token = login_res.json()["tokens"]["refresh_token"]

    res = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["expires_in"] == 1800


def test_auth_me():
    login_res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    token = login_res.json()["tokens"]["access_token"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "user@swiftship.com"


def test_forgot_and_reset_password():
    res = client.post("/api/auth/forgot-password", json={"email": "user@swiftship.com"})
    assert res.status_code == 200
    data = res.json()
    assert "reset_url" in data
    assert "token=" in data["reset_url"]
    token = data["reset_url"].split("token=")[1]

    # Reset with new password
    reset_res = client.post("/api/auth/reset-password", json={"token": token, "new_password": "NewUser@123"})
    assert reset_res.status_code == 200

    # Login with new password
    login_new = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "NewUser@123"})
    assert login_new.status_code == 200

    # Reset back to User@123
    token_back = login_new.json()["tokens"]["access_token"]
    change_res = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token_back}"},
        json={"current_password": "NewUser@123", "new_password": "User@123"},
    )
    assert change_res.status_code == 200


def test_services_listing():
    # Public active services listing (plain array)
    res = client.get("/api/services/")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert len(items) == 4

    names = {s["name"] for s in items}
    assert "Standard Delivery" in names
    assert "Express Delivery" in names
    assert "Same-Day Delivery" in names
    assert "International Courier" in names


def test_services_all_requires_admin():
    user_res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    user_token = user_res.json()["tokens"]["access_token"]

    admin_res = client.post("/api/auth/login", json={"email": "admin@swiftship.com", "password": "Admin@123"})
    admin_token = admin_res.json()["tokens"]["access_token"]

    # Without auth or with normal user -> 401 or 403
    res_anon = client.get("/api/services/?all=true")
    assert res_anon.status_code == 401

    res_user = client.get("/api/services/?all=true", headers={"Authorization": f"Bearer {user_token}"})
    assert res_user.status_code == 403

    res_admin = client.get("/api/services/?all=true", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    assert isinstance(res_admin.json(), list)


def test_service_delete_conflict():
    admin_res = client.post("/api/auth/login", json={"email": "admin@swiftship.com", "password": "Admin@123"})
    admin_token = admin_res.json()["tokens"]["access_token"]

    res_del = client.delete("/api/services/1", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_del.status_code == 409
    assert "Service is used by existing parcels" in res_del.json()["detail"]


def test_public_tracking():
    # Track demo parcel
    res = client.get("/api/parcels/track/SS20260001DEMO")
    assert res.status_code == 200
    data = res.json()
    assert data["tracking_number"] == "SS20260001DEMO"
    assert data["status"] == "delivered"
    assert "history" in data
    assert len(data["history"]) == 5
    # All 5 steps should be done since delivered
    assert all(step["done"] for step in data["history"])

    # 404 for non-existent parcel
    res_nf = client.get("/api/parcels/track/NONEXISTENT9999")
    assert res_nf.status_code == 404
    assert "No parcel found" in res_nf.json()["detail"]


def test_parcel_summary():
    user_res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    token = user_res.json()["tokens"]["access_token"]

    res = client.get("/api/parcels/summary", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "active" in data
    assert "delivered" in data
    assert "cancelled" in data
    assert "total_spent" in data


def test_admin_stats_protection():
    user_res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    user_token = user_res.json()["tokens"]["access_token"]

    admin_res = client.post("/api/auth/login", json={"email": "admin@swiftship.com", "password": "Admin@123"})
    admin_token = admin_res.json()["tokens"]["access_token"]

    res_user = client.get("/api/parcels/stats", headers={"Authorization": f"Bearer {user_token}"})
    assert res_user.status_code == 403

    res_admin = client.get("/api/parcels/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "total_parcels" in data
    assert "active_parcels" in data
    assert "total_revenue" in data
    assert "by_status" in data
    for st in ["pending", "picked_up", "in_transit", "out_for_delivery", "delivered", "cancelled"]:
        assert st in data["by_status"]
    assert "recent_parcels" in data


def test_parcel_listing_envelope_and_isolation():
    user_res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    user_token = user_res.json()["tokens"]["access_token"]

    admin_res = client.post("/api/auth/login", json={"email": "admin@swiftship.com", "password": "Admin@123"})
    admin_token = admin_res.json()["tokens"]["access_token"]

    res_user = client.get("/api/parcels/?page=1&page_size=5", headers={"Authorization": f"Bearer {user_token}"})
    assert res_user.status_code == 200
    user_data = res_user.json()
    assert "items" in user_data
    assert "total" in user_data
    assert "page" in user_data
    assert "page_size" in user_data
    assert "total_pages" in user_data

    # Every item returned to user must be owned by user
    for item in user_data["items"]:
        assert item["owner"]["email"] == "user@swiftship.com"
        assert "service" in item
        assert "name" in item["service"]

    # Admin sees all items
    res_admin = client.get("/api/parcels/?page=1&page_size=10", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    admin_data = res_admin.json()
    assert admin_data["total"] >= user_data["total"]


def test_parcel_crud_and_status_pipeline():
    user_res = client.post("/api/auth/login", json={"email": "user@swiftship.com", "password": "User@123"})
    user_token = user_res.json()["tokens"]["access_token"]

    admin_res = client.post("/api/auth/login", json={"email": "admin@swiftship.com", "password": "Admin@123"})
    admin_token = admin_res.json()["tokens"]["access_token"]

    # Validation failure: bad phone -> 422
    bad_payload = {
        "service_id": 1,
        "sender_name": "Rahim",
        "sender_phone": "123",
        "recipient_name": "Karim",
        "recipient_phone": "01700000002",
        "pickup_address": "Dhanmondi, Dhaka",
        "delivery_address": "Gulshan, Dhaka",
        "weight_kg": 2.0,
    }
    res_bad = client.post("/api/parcels/", headers={"Authorization": f"Bearer {user_token}"}, json=bad_payload)
    assert res_bad.status_code == 422

    # Create parcel
    good_payload = {
        "service_id": 1,
        "sender_name": "Rahim Uddin",
        "sender_phone": "01700000002",
        "recipient_name": "Sabbir Rahman",
        "recipient_phone": "01812345678",
        "pickup_address": "House 12, Road 5, Dhanmondi, Dhaka",
        "delivery_address": "House 20, Road 2, Banani, Dhaka",
        "weight_kg": 2.5,
        "notes": "Fragile items inside",
    }
    res_create = client.post("/api/parcels/", headers={"Authorization": f"Bearer {user_token}"}, json=good_payload)
    assert res_create.status_code == 201
    created = res_create.json()
    assert created["tracking_number"].startswith("SS2026")
    assert created["status"] == "pending"
    # Standard delivery: base 60 + 20 * 2.5 = 110.0
    assert created["price"] == 110.0
    parcel_id = created["id"]

    # User can edit while pending
    res_edit = client.put(
        f"/api/parcels/{parcel_id}",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"weight_kg": 3.0},
    )
    assert res_edit.status_code == 200
    updated = res_edit.json()
    # 60 + 20 * 3 = 120.0
    assert updated["price"] == 120.0

    # Admin changes status to in_transit
    res_status = client.patch(
        f"/api/parcels/{parcel_id}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "in_transit"},
    )
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "in_transit"

    # Now user CANNOT edit because it's not pending -> 400
    res_user_edit_blocked = client.put(
        f"/api/parcels/{parcel_id}",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"recipient_name": "Should Fail"},
    )
    assert res_user_edit_blocked.status_code == 400
    assert "Only pending parcels can be edited" in res_user_edit_blocked.json()["detail"]

    # User CANNOT delete because it's not pending -> 400
    res_user_delete_blocked = client.delete(
        f"/api/parcels/{parcel_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res_user_delete_blocked.status_code == 400
    assert "Only pending parcels can be deleted" in res_user_delete_blocked.json()["detail"]

    # Admin CAN delete it
    res_admin_delete = client.delete(
        f"/api/parcels/{parcel_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_delete.status_code == 204


def test_user_management_by_admin():
    admin_res = client.post("/api/auth/login", json={"email": "admin@swiftship.com", "password": "Admin@123"})
    admin_token = admin_res.json()["tokens"]["access_token"]
    admin_id = admin_res.json()["user"]["id"]

    # List users (envelope)
    res_users = client.get("/api/users/?page=1&page_size=10", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_users.status_code == 200
    data = res_users.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 2

    user_karim = next(u for u in data["items"] if u["email"] == "karim@swiftship.com")

    # Admin cannot block self
    res_self = client.patch(
        f"/api/users/{admin_id}/active",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_active": False},
    )
    assert res_self.status_code == 400

    # Admin blocks Karim
    res_block = client.patch(
        f"/api/users/{user_karim['id']}/active",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_active": False},
    )
    assert res_block.status_code == 200
    assert res_block.json()["is_active"] is False

    # Blocked user login -> 403
    res_karim_login = client.post("/api/auth/login", json={"email": "karim@swiftship.com", "password": "Karim@123"})
    assert res_karim_login.status_code == 403
    assert "Account is blocked" in res_karim_login.json()["detail"]

    # Admin unblocks Karim
    res_unblock = client.patch(
        f"/api/users/{user_karim['id']}/active",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"is_active": True},
    )
    assert res_unblock.status_code == 200
    assert res_unblock.json()["is_active"] is True
