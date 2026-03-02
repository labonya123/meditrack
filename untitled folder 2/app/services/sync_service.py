import os
import sys
from datetime import datetime

# Fix import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config import USE_CLOUD, SUPABASE_URL, SUPABASE_KEY
from app.database.local_db import execute_query


# -------------------------------------------------
# Check Internet Connectivity
# -------------------------------------------------
def check_internet():
    try:
        import requests
        response = requests.get("https://www.google.com", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


# -------------------------------------------------
# Get Sync Status (For UI)
# -------------------------------------------------
def get_sync_status():

    tables = [
        "patients",
        "patient_diseases",
        "patient_allergies",
        "patient_medications",
        "hospitalizations",
        "surgeries",
        "medical_reports",
        "emergency_contacts",
        "prescriptions"
    ]

    pending_count = 0

    for table in tables:
        try:
            result = execute_query(
                f"SELECT COUNT(*) as cnt FROM {table} WHERE sync_status = 'pending'",
                fetchone=True
            )
            if result:
                pending_count += result.get("cnt", 0)
        except Exception:
            pass

    if not USE_CLOUD:
        return {
            "online": False,
            "pending_count": pending_count,
            "status": "cloud_disabled",
            "message": "Cloud sync not configured",
            "icon": "💾"
        }

    if not check_internet():
        return {
            "online": False,
            "pending_count": pending_count,
            "status": "offline",
            "message": f"Offline — {pending_count} records waiting",
            "icon": "🔴"
        }

    if pending_count == 0:
        return {
            "online": True,
            "pending_count": 0,
            "status": "synced",
            "message": "All data synced ✓",
            "icon": "✅"
        }

    return {
        "online": True,
        "pending_count": pending_count,
        "status": "pending",
        "message": f"{pending_count} records ready to sync",
        "icon": "🔄"
    }


# -------------------------------------------------
# Sync Pending Records to Supabase
# -------------------------------------------------
def sync_to_cloud():

    if not USE_CLOUD:
        return {
            "success": False,
            "message": "Cloud sync not enabled.",
            "synced_count": 0
        }

    if not check_internet():
        return {
            "success": False,
            "message": "No internet connection.",
            "synced_count": 0
        }

    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        tables = [
            "patients",
            "patient_diseases",
            "patient_allergies",
            "patient_medications",
            "hospitalizations",
            "surgeries",
            "medical_reports",
            "emergency_contacts",
            "prescriptions"
        ]

        total_synced = 0

        for table in tables:

            pending_records = execute_query(
                f"SELECT * FROM {table} WHERE sync_status = 'pending'",
                fetch=True
            )

            if not pending_records:
                continue

            for record in pending_records:
                try:
                    record_data = dict(record)
                    record_data.pop("sync_status", None)

                    supabase.table(table).upsert(record_data).execute()

                    primary_key = list(record.keys())[0]

                    execute_query(
                        f"UPDATE {table} SET sync_status = 'synced' WHERE {primary_key} = ?",
                        (record[primary_key],)
                    )

                    total_synced += 1

                except Exception:
                    continue

        # ----------------------------
        # Log Sync History
        # ----------------------------
        execute_query(
            "INSERT INTO sync_logs (synced_count, status, timestamp) VALUES (?, ?, ?)",
            (total_synced, "success", datetime.now().isoformat())
        )

        return {
            "success": True,
            "message": f"Successfully synced {total_synced} records.",
            "synced_count": total_synced,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:

        execute_query(
            "INSERT INTO sync_logs (synced_count, status, timestamp) VALUES (?, ?, ?)",
            (0, "failed", datetime.now().isoformat())
        )

        return {
            "success": False,
            "message": f"Sync failed: {str(e)}",
            "synced_count": 0
        }
