# -----------------------------------------------------------------
# MaaSakhi Full End-to-End Test Suite
# Tests:
#   1. Database Connection & Hierarchy Seeding
#   2. Web Portals (Homepage, Admin, BMO, Supervisor, ASHA, Login)
#   3. Analytics, NHM CSV & Monthly PDF Generation
#   4. WhatsApp Chatbot: Patient Onboarding, Critical Symptom AI Triage, Schemes
#   5. Alert Handling, Visit Logging, Escalation Engine, and Resolution
#   6. Postpartum, Delivery, PNC & Child Immunization
#   7. Automated Cron Endpoints (/cron/escalate, /cron/reminders)
# -----------------------------------------------------------------

import os
import sys
import json
from datetime import datetime, date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

print("=" * 60)
print("[START] STARTING MAASAKHI END-TO-END VERIFICATION")
print("=" * 60)

# Import app and database
import app as app_module
from app import app
from database import (
    engine, get_patient, get_all_patients,
    get_alert_by_id, get_district_stats,
    verify_admin, verify_supervisor, verify_bmo,
    get_asha_by_phone
)

# Mock send_whatsapp during test suite execution to prevent Twilio trial quota exhaustion
mocked_wa_messages = []
def _mock_send_wa(to, body):
    mocked_wa_messages.append({"to": to, "body": body})
    print(f"  [Twilio Mock] Dispatched WhatsApp -> {to}")

app_module.send_whatsapp = _mock_send_wa

import escalation
import reminders
escalation.send_whatsapp = _mock_send_wa
reminders.send_whatsapp = _mock_send_wa

passed_tests = 0
failed_tests = 0

def assert_test(condition, test_name, extra_info=""):
    global passed_tests, failed_tests
    if condition:
        passed_tests += 1
        print(f"  [PASS] {test_name}")
    else:
        failed_tests += 1
        print(f"  [FAIL] {test_name} | {extra_info}")

client = app.test_client()

# =================================================================
# 1. DATABASE & SEED DATA INTEGRITY
# =================================================================
print("\n[1/5] Verifying Database Connectivity & Hierarchy Seeding...")
assert_test(engine is not None, "SQLAlchemy Database Engine is initialized")

stats = get_district_stats()
assert_test(isinstance(stats, dict) and "total_ashas" in stats, "get_district_stats() returns valid schema")
assert_test(stats.get("total_ashas", 0) >= 1, "Default ASHA workers seeded in database", f"Got: {stats}")
assert_test(stats.get("total_supervisors", 0) >= 1, "Default ASHA supervisors seeded in database", f"Got: {stats}")
assert_test(stats.get("total_bmos", 0) >= 1, "Default BMOs seeded in database", f"Got: {stats}")

admin_user = verify_admin("admin", "maasakhi2026")
assert_test(admin_user is not None and admin_user.get("role") == "admin", "Admin authentication verified")

asha_user = get_asha_by_phone("9999999991")
assert_test(asha_user is not None and asha_user.get("name") == "Sunita Devi", "ASHA Worker (Sunita Devi) verified")

sup_user = verify_supervisor("9876543220")
assert_test(sup_user is not None and sup_user.get("name") == "Anita Sharma", "Supervisor (Anita Sharma) verified")

bmo_user = verify_bmo("9876543230")
assert_test(bmo_user is not None and bmo_user.get("name") == "Dr. Rajesh Kumar", "BMO (Dr. Rajesh Kumar) verified")


# =================================================================
# 2. WEB PORTALS & AUTHENTICATION
# =================================================================
print("\n[2/5] Verifying Web Portals, Dashboards & Export Functions...")

# 2.1 Homepage
res = client.get("/")
assert_test(res.status_code == 200 and b"MaaSakhi" in res.data, "GET / (Homepage loads successfully)")

# 2.2 Login Page
res = client.get("/login")
assert_test(res.status_code == 200, "GET /login (Unified login page loads)")

# 2.3 Unified Login Form Submit (ASHA)
res = client.post("/login", data={"phone": "9999999991"}, follow_redirects=False)
assert_test(res.status_code == 302 and "/dashboard/ASHA01" in res.headers.get("Location", ""), "POST /login (ASHA worker redirects to dashboard)")

# 2.4 ASHA Dashboard
res = client.get("/dashboard/ASHA01")
assert_test(res.status_code == 200 and b"Sunita Devi" in res.data, "GET /dashboard/ASHA01 (ASHA Dashboard loads)")

# 2.5 Supervisor Dashboard
res = client.get("/supervisor/SUP01")
assert_test(res.status_code == 200 and b"Supervisor Dashboard" in res.data, "GET /supervisor/SUP01 (Supervisor Dashboard loads)")

# 2.6 BMO Dashboard
res = client.get("/bmo/BMO01")
assert_test(res.status_code == 200 and b"BMO Dashboard" in res.data, "GET /bmo/BMO01 (BMO Dashboard loads)")

# 2.7 Admin Login & Dashboard
login_res = client.post("/admin/login", data={"username": "admin", "password": "maasakhi2026"}, follow_redirects=False)
assert_test(login_res.status_code == 302 and "/admin" in login_res.headers.get("Location", ""), "POST /admin/login (Admin authenticated & redirects)")

res = client.get("/admin")
assert_test(res.status_code == 200 and b"MaaSakhi Admin" in res.data, "GET /admin (Admin Command Center loads)")

# 2.8 Admin API Endpoints
res = client.get("/admin/api/trends")
assert_test(res.status_code == 200 and res.is_json, "GET /admin/api/trends (Returns JSON analytics)")

res = client.get("/admin/api/village-risks")
assert_test(res.status_code == 200 and res.is_json, "GET /admin/api/village-risks (Returns JSON risk scores)")

# 2.9 NHM CSV Export
res = client.get("/admin/export/nhm-csv")
assert_test(res.status_code == 200 and "text/csv" in res.content_type, "GET /admin/export/nhm-csv (Exports valid CSV)")

# 2.10 Monthly PDF Report Generation
res = client.get("/admin/export/monthly-pdf")
assert_test(res.status_code == 200 and res.data.startswith(b"%PDF"), "GET /admin/export/monthly-pdf (Generates valid binary PDF)")


# =================================================================
# 3. WHATSAPP BOT: REGISTRATION, AI TRIAGE & SCHEMES
# =================================================================
print("\n[3/5] Verifying WhatsApp Bot: Patient Onboarding, AI Triage & Schemes...")

import time
test_phone = f"whatsapp:+9198765{int(time.time()) % 100000:05d}"

def send_wa(body):
    return client.post("/whatsapp", data={
        "From": test_phone,
        "Body": body,
        "ProfileName": "Pooja"
    })

# Step 1: Greeting
res = send_wa("Namaste")
assert_test(res.status_code == 200 and (b"MaaSakhi" in res.data or b"Namaste" in res.data), "WhatsApp Turn 1: Welcome greeting sent")

# Step 2: Name
res = send_wa("Pooja Sharma")
assert_test(res.status_code == 200, "WhatsApp Turn 2: Name registered, asks for language")

# Step 3: Language
res = send_wa("Hindi")
assert_test(res.status_code == 200, "WhatsApp Turn 3: Language selected, asks for pregnancy week")

# Step 4: Pregnancy Week
res = send_wa("26")
assert_test(res.status_code == 200, "WhatsApp Turn 4: Week 26 registered, asks for village")

# Step 5: Village Registration (maps to Rampur Khera -> ASHA01)
res = send_wa("Rampur Khera")
assert_test(res.status_code == 200, "WhatsApp Turn 5: Village registered, asks for address")

# Step 6: Address Registration (completes registration)
res = send_wa("Near Govt School, Ward 4")
assert_test(res.status_code == 200, "WhatsApp Turn 6: Address saved, registration complete")

# Verify patient in database
p = get_patient(test_phone)
assert_test(p is not None and p.get("name") == "Pooja Sharma" and p.get("asha_id") == "ASHA01",
            "Patient record created in database with accurate ASHA linkage")

# Step 6: Critical Symptom Reporting (AI Triage)
res = send_wa("Mujhe tez pet dard ho raha hai aur bahut zyada bleeding ho rahi hai")
assert_test(res.status_code == 200 and (b"alert" in res.data.lower() or b"108" in res.data or b"doctor" in res.data or b"\xe0\xa4\x85\xe0\xa4\xb8\xe0\xa5\x8d\xe0\xa4\xaa\xe0\xa4\xa4\xe0\xa4\xbe\xe0\xa4\xb2" in res.data),
            "WhatsApp Turn 6: Critical symptom triaged, emergency advisory returned")

# Step 7: Scheme Query
res = send_wa("Janani Suraksha Yojana kya hai?")
assert_test(res.status_code == 200 and (b"Janani" in res.data or b"JSY" in res.data or b"1400" in res.data or b"\xe0\xa4\xaf\xe0\xa5\x8b\xe0\xa4\x9c\xe0\xa4\xa8\xe0\xa4\xbe" in res.data),
            "WhatsApp Turn 7: Scheme inquiry successfully answered")

# Step 8: Recovery Confirmation
res = send_wa("Ab dard theek ho gaya hai")
assert_test(res.status_code == 200, "WhatsApp Turn 8: Patient recovery confirmation recorded")


# =================================================================
# 4. CLINICAL ACTIONS, ESCALATION & RESOLUTION
# =================================================================
print("\n[4/5] Verifying ASHA Visit Logging, Alert Lifecycle & Escalation...")

# Check if an alert was generated for Pooja Sharma
from database import get_all_asha_alerts, update_alert_status, get_alert_by_id, log_escalation

alerts = get_all_asha_alerts("ASHA01")
assert_test(len(alerts) >= 1, "ASHA01 received alert from critical symptom triage")

if alerts:
    target_alert = alerts[0]
    alert_id = target_alert["id"]

    # 4.1 ASHA marks alert attended
    res = client.post(f"/dashboard/ASHA01/attend/{alert_id}")
    assert_test(res.status_code == 302, f"ASHA marks alert {alert_id} attended")

    # 4.2 ASHA logs home visit
    res = client.post(f"/dashboard/ASHA01/log-visit/{alert_id}", data={
        "outcome": "Stabilized",
        "notes": "Visited home, vitals stable, oral rehydration given.",
        "referred_to": "PHC Rampur"
    })
    assert_test(res.status_code == 302, f"ASHA logs physical visit for alert {alert_id}")

    # 4.3 Supervisor manual escalation to BMO
    res = client.post(f"/supervisor/SUP01/escalate/{alert_id}")
    assert_test(res.status_code == 302, f"Supervisor escalates alert {alert_id} to BMO")

    # 4.4 BMO resolves alert
    res = client.post(f"/bmo/BMO01/resolve/{alert_id}", data={
        "notes": "Reviewed at PHC, medication prescribed, safe."
    })
    assert_test(res.status_code == 302, f"BMO marks alert {alert_id} as Resolved")

    # Verify status in database
    resolved_alert = get_alert_by_id(alert_id)
    assert_test(resolved_alert.get("status") == "Resolved", f"Alert {alert_id} is marked 'Resolved' in DB")


# =================================================================
# 5. MATERNAL CARE RECORDS & AUTOMATED CRON
# =================================================================
print("\n[5/5] Verifying ANC, Postpartum, Delivery, Immunization & Cron...")

# 5.1 ANC Record
res = client.post("/dashboard/ASHA01/log-anc", data={
    "phone": test_phone,
    "visit_number": 2,
    "notes": "BP 118/76, Weight 58kg, IFA tablets distributed"
})
assert_test(res.status_code == 302, "ASHA logs ANC checkup #2")

# 5.2 Delivery Registration
res = client.post("/dashboard/ASHA01/register-delivery", data={
    "phone": test_phone,
    "delivery_date": str(date.today()),
    "delivery_mode": "Normal",
    "facility": "Govt Hospital Rampur",
    "child_name": "Aarav",
    "gender": "Male",
    "birth_weight": "3.1"
})
assert_test(res.status_code == 302, "ASHA registers successful delivery and newborn")

# 5.3 PNC Followup Checkup
res = client.post(f"/dashboard/ASHA01/log-pnc/{test_phone}", data={
    "day_number": 1,
    "notes": "Mother and newborn healthy, exclusive breastfeeding initiated"
})
assert_test(res.status_code == 302, "ASHA logs Day 1 PNC checkup")

# 5.4 Cron: Auto-escalation
res = client.get("/cron/escalate", headers={"X-Cron-Secret": "maasakhicronsecret"})
assert_test(res.status_code == 200 and res.is_json, "Cron: /cron/escalate triggered successfully")

# 5.5 Cron: Reminders (PNC & Immunization)
res = client.get("/cron/reminders", headers={"X-Cron-Secret": "maasakhicronsecret"})
assert_test(res.status_code == 200 and res.is_json, "Cron: /cron/reminders triggered successfully")

print("\n" + "=" * 60)
print("[DONE] END-TO-END VERIFICATION COMPLETE")
print(f"Total Tests Run: {passed_tests + failed_tests}")
print(f"Passed: {passed_tests} | Failed: {failed_tests}")
print("=" * 60)

if failed_tests > 0:
    sys.exit(1)
sys.exit(0)
