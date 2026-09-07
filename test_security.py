"""
SkyGuard AI v2 - Phase 4 Server Security & RBAC Test Suite
------------------------------------------------------------
Tests server-side authentication, password hashing, JWT token creation, token expiration,
invalid token rejection, Role-Based Access Control (ADMIN, OPERATOR, ANALYST, VIEWER),
user creation authorization, audit logging, public endpoint accessibility, and API compatibility.
"""

import sys
import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# Ensure UTF-8 output encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"

from auth import (
    hash_password, verify_password, create_access_token, decode_access_token,
    init_demo_users, authenticate_user, log_audit_event, AUDIT_LOGS, IN_MEMORY_USERS
)


def make_request(url: str, method: str = "GET", payload: dict = None, token: str = None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    data_bytes = json.dumps(payload).encode("utf-8") if payload else None
    try:
        with urllib.request.urlopen(req, data=data_bytes) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = json.loads(e.read().decode("utf-8")) if e.fp else {}
        return e.code, err_body


def run_security_tests():
    print("=" * 70)
    print(" 🧪 SkyGuard AI v2 - Phase 4 Server Security & RBAC Test Suite")
    print("=" * 70)

    init_demo_users()

    # TEST 1: Password Hashing & Verification
    print("\n1. Cryptographic Password Hashing & Verification Test:")
    hashed = hash_password("MySecurePass123!")
    assert verify_password("MySecurePass123!", hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    print("  [PASS] Password hashing & verification functioning correctly.")

    # TEST 2: Successful Login API Test
    print("\n2. Successful Login Endpoint Test (admin):")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/auth/login", method="POST", payload={"username": "admin", "password": "AdminPass2026!"})
    assert status_code == 200, f"Expected 200, got {status_code}: {resp}"
    assert "access_token" in resp
    assert resp["role"] == "ADMIN"
    admin_token = resp["access_token"]
    print(f"  [PASS {status_code}] Login successful -> Role: {resp['role']}, JWT Token generated.")

    # TEST 3: Invalid Password Rejection Test
    print("\n3. Invalid Password Rejection Test:")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/auth/login", method="POST", payload={"username": "admin", "password": "WrongPassword!"})
    assert status_code == 401, f"Expected 401, got {status_code}: {resp}"
    print(f"  [PASS {status_code}] Invalid password rejected with HTTP 401.")

    # TEST 4: Unknown Username Rejection Test
    print("\n4. Unknown Username Rejection Test:")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/auth/login", method="POST", payload={"username": "unknown_user_999", "password": "Pass123!"})
    assert status_code == 401, f"Expected 401, got {status_code}: {resp}"
    print(f"  [PASS {status_code}] Unknown user rejected with HTTP 401.")

    # TEST 5: Inactive User Rejection Test
    print("\n5. Inactive User Rejection Test:")
    IN_MEMORY_USERS["inactive_user"] = {
        "id": 99,
        "username": "inactive_user",
        "email": "inactive@skyguard.gov.in",
        "password_hash": hash_password("Secret123!"),
        "role": "VIEWER",
        "active": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    status_code, resp = make_request(f"{BASE_URL}/api/v1/auth/login", method="POST", payload={"username": "inactive_user", "password": "Secret123!"})
    assert status_code == 401, f"Expected 401, got {status_code}: {resp}"
    print(f"  [PASS {status_code}] Inactive user rejected with HTTP 401.")

    # TEST 6: JWT Token Decoding & Expiration Inspection
    print("\n6. JWT Token Payload & Claims Inspection Test:")
    decoded = decode_access_token(admin_token)
    assert decoded["sub"] == "admin"
    assert decoded["role"] == "ADMIN"
    assert "exp" in decoded
    print(f"  [PASS] JWT claims validated -> Sub: {decoded['sub']}, Role: {decoded['role']}.")

    # TEST 7: Authenticated User Profile Endpoint Test (/auth/me)
    print("\n7. Authenticated User Profile Endpoint Test (/auth/me):")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/auth/me", method="GET", token=admin_token)
    assert status_code == 200, f"Expected 200, got {status_code}: {resp}"
    assert resp["username"] == "admin"
    assert "password_hash" not in resp
    print(f"  [PASS {status_code}] User profile retrieved -> Username: {resp['username']}, Email: {resp['email']} (Password hash omitted).")

    # TEST 8: Malformed & Invalid JWT Token Test
    print("\n8. Invalid JWT Token Rejection Test:")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/auth/me", method="GET", token="invalid.bearer.token.123")
    assert status_code == 401, f"Expected 401, got {status_code}: {resp}"
    print(f"  [PASS {status_code}] Invalid JWT token rejected with HTTP 401.")

    # TEST 9: Expired JWT Token Rejection Test
    print("\n9. Expired JWT Token Rejection Test:")
    expired_token = create_access_token(data={"sub": "admin", "role": "ADMIN"}, expires_delta=timedelta(seconds=-10))
    status_code, resp = make_request(f"{BASE_URL}/api/v1/auth/me", method="GET", token=expired_token)
    assert status_code == 401, f"Expected 401, got {status_code}: {resp}"
    print(f"  [PASS {status_code}] Expired JWT token rejected with HTTP 401.")

    # TEST 10: Role Login Tests for OPERATOR, ANALYST, VIEWER
    print("\n10. Role Login Tests (OPERATOR, ANALYST, VIEWER):")
    _, op_resp = make_request(f"{BASE_URL}/api/v1/auth/login", method="POST", payload={"username": "operator", "password": "OperatorPass2026!"})
    op_token = op_resp["access_token"]

    _, an_resp = make_request(f"{BASE_URL}/api/v1/auth/login", method="POST", payload={"username": "analyst", "password": "AnalystPass2026!"})
    an_token = an_resp["access_token"]

    _, vi_resp = make_request(f"{BASE_URL}/api/v1/auth/login", method="POST", payload={"username": "viewer", "password": "ViewerPass2026!"})
    vi_token = vi_resp["access_token"]
    print("  [PASS] Tokens successfully issued for OPERATOR, ANALYST, and VIEWER roles.")

    # TEST 11: ADMIN User Creation Authorization Test
    print("\n11. ADMIN User Creation Authorization Test (POST /users):")
    new_user_payload = {
        "username": "new_operator_01",
        "email": "newop@skyguard.gov.in",
        "password": "NewOpPassword2026!",
        "role": "OPERATOR"
    }
    status_code, resp = make_request(f"{BASE_URL}/api/v1/users", method="POST", payload=new_user_payload, token=admin_token)
    assert status_code == 201, f"Expected 201, got {status_code}: {resp}"
    assert resp["username"] == "new_operator_01"
    print(f"  [PASS {status_code}] ADMIN successfully created user '{resp['username']}' with role '{resp['role']}'.")

    # TEST 12: Non-ADMIN User Creation Denial Test (HTTP 403 Forbidden)
    print("\n12. Non-ADMIN User Creation Denial Test (ANALYST role):")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/users", method="POST", payload=new_user_payload, token=an_token)
    assert status_code == 403, f"Expected 403, got {status_code}: {resp}"
    print(f"  [PASS {status_code}] ANALYST role denied user creation with HTTP 403 Forbidden.")

    # TEST 13: Security Audit Log Access Test (ADMIN only)
    print("\n13. Security Audit Log Endpoint Test (GET /security/audit-logs):")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/security/audit-logs", method="GET", token=admin_token)
    assert status_code == 200, f"Expected 200, got {status_code}: {resp}"
    assert "audit_logs" in resp
    assert len(resp["audit_logs"]) >= 1
    print(f"  [PASS {status_code}] ADMIN retrieved {resp['count']} security audit log events.")

    # TEST 14: Non-ADMIN Audit Log Access Denial Test (VIEWER role)
    print("\n14. Non-ADMIN Audit Log Access Denial Test (VIEWER role):")
    status_code, resp = make_request(f"{BASE_URL}/api/v1/security/audit-logs", method="GET", token=vi_token)
    assert status_code == 403, f"Expected 403, got {status_code}: {resp}"
    print(f"  [PASS {status_code}] VIEWER role denied audit logs with HTTP 403 Forbidden.")

    # TEST 15: Public Unauthenticated Health Endpoint Accessibility Test
    print("\n15. Public Endpoint Unauthenticated Accessibility Test:")
    status_code, resp = make_request(f"{BASE_URL}/health", method="GET")
    assert status_code == 200, f"Expected 200, got {status_code}: {resp}"
    assert resp["status"] == "healthy"
    print(f"  [PASS {status_code}] Public /health endpoint accessible without authentication token.")

    # TEST 16: Existing REST Endpoints Backward Compatibility Test
    print("\n16. Existing REST Endpoints Backward Compatibility Test:")
    status_code, resp = make_request(f"{BASE_URL}/stations", method="GET")
    assert status_code == 200
    status_code2, resp2 = make_request(f"{BASE_URL}/summary", method="GET")
    assert status_code2 == 200
    print(f"  [PASS 200] /stations & /summary remain 100% backward compatible for demo applications.")

    print("\n" + "=" * 70)
    print(" 🎉 PHASE 4 SERVER SECURITY & RBAC TEST SUITE COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_security_tests()
