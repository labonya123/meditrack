"""
app/routes/paramedic.py - Paramedic & Emergency Routes
========================================================
Paramedic dashboard and the public emergency QR scan view.

  /paramedic/dashboard    - Paramedic home with scan button
  /emergency/<token>      - PUBLIC page — no login needed
                            Shows critical emergency info when QR is scanned
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from functools import wraps
from app.database.local_db import execute_query
from app.services.auth_service import log_audit
from app.services.qr_service import validate_qr_token
import json

paramedic_bp = Blueprint('paramedic', __name__)


def paramedic_required(f):
    """
    Decorator ensuring only logged-in paramedics access paramedic pages.
    Note: The /emergency/<token> route is PUBLIC and does NOT use this decorator.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'error')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'paramedic':
            flash('Access denied. Paramedic only.', 'error')
            return redirect(url_for('auth.dashboard_redirect'))
        return f(*args, **kwargs)
    return decorated_function


@paramedic_bp.route('/paramedic/dashboard')
@paramedic_required
def dashboard():
    """
    Paramedic home page — shows a large QR scan button.
    Simple interface designed for use in emergency situations.
    """
    return render_template('paramedic/dashboard.html',
        paramedic_name=session.get('username')
    )


# ─────────────────────────────────────────────
# PUBLIC EMERGENCY VIEW — NO LOGIN REQUIRED
# This is the page that opens when a QR code is scanned
# ─────────────────────────────────────────────

@paramedic_bp.route('/emergency/<token>')
def emergency_view(token):
    """
    PUBLIC emergency page — accessible WITHOUT any login.
    This is what appears when someone scans a patient's QR code.

    Shows ONLY critical emergency information:
    - Full name and blood group
    - Life-threatening allergies (highlighted in red)
    - Active diseases
    - Current medications
    - Emergency contacts

    Does NOT show:
    - Aadhaar, phone number, address
    - Full medical history
    - Uploaded reports

    Parameters:
        token - The secure token from the patient's QR code
    """
    # Validate the QR token and get patient_id
    patient_id = validate_qr_token(token)

    if not patient_id:
        # Invalid or tampered QR code
        return render_template('paramedic/invalid_qr.html'), 404

    # Get the pre-built emergency snapshot (fastest retrieval)
    snapshot = execute_query(
        "SELECT * FROM patient_emergency_snapshot WHERE patient_id = ?",
        (patient_id,), fetchone=True
    )

    # Get basic patient info (only what's needed for emergency)
    patient = execute_query(
        """SELECT patient_id, first_name, last_name, gender, date_of_birth,
                  blood_group, has_chronic_disease, has_life_threat_allergy,
                  is_pregnant, organ_donor_status
           FROM patients WHERE patient_id = ?""",
        (patient_id,), fetchone=True
    )

    if not patient:
        return render_template('paramedic/invalid_qr.html'), 404

    # Parse JSON fields from emergency snapshot
    active_diseases = []
    life_threat_allergies = []
    current_medications = []
    emergency_contacts = []

    if snapshot:
        try:
            active_diseases = json.loads(snapshot.get('active_diseases_json', '[]'))
            life_threat_allergies = json.loads(snapshot.get('life_threat_allergies_json', '[]'))
            current_medications = json.loads(snapshot.get('current_medications_json', '[]'))
            emergency_contacts = json.loads(snapshot.get('emergency_contacts_json', '[]'))
        except Exception:
            pass

    # If snapshot is empty, fetch directly from database (fallback)
    if not active_diseases:
        active_diseases_raw = execute_query(
            """SELECT dm.disease_name, pd.severity, pd.status
               FROM patient_diseases pd
               JOIN disease_master dm ON pd.disease_id = dm.disease_id
               WHERE pd.patient_id = ? AND pd.status = 'Active' AND pd.is_emergency_relevant = 1""",
            (patient_id,), fetch=True
        )
        active_diseases = active_diseases_raw or []

    if not life_threat_allergies:
        life_threat_raw = execute_query(
            """SELECT am.allergy_name, pa.reaction_type, pa.severity
               FROM patient_allergies pa
               JOIN allergy_master am ON pa.allergy_id = am.allergy_id
               WHERE pa.patient_id = ? AND pa.is_life_threatening = 1""",
            (patient_id,), fetch=True
        )
        life_threat_allergies = life_threat_raw or []

    if not current_medications:
        current_meds_raw = execute_query(
            """SELECT mm.generic_name, mm.brand_name, pm.dose, pm.frequency
               FROM patient_medications pm
               JOIN medication_master mm ON pm.medication_id = mm.medication_id
               WHERE pm.patient_id = ? AND pm.is_currently_taking = 1""",
            (patient_id,), fetch=True
        )
        current_medications = current_meds_raw or []

    if not emergency_contacts:
        contacts_raw = execute_query(
            """SELECT name, relationship, phone_number
               FROM emergency_contacts
               WHERE patient_id = ?
               ORDER BY priority_order""",
            (patient_id,), fetch=True
        )
        emergency_contacts = contacts_raw or []

    # Log this emergency access (even though no login — record the QR scan)
    # Use anonymous audit log since no user is logged in
    execute_query(
        """INSERT INTO audit_log (audit_id, user_id, user_role, action, target_patient_id, details, ip_address, timestamp)
           VALUES (?, 'EMERGENCY_SCAN', 'public', 'EMERGENCY_QR_ACCESS', ?, ?, ?, ?)""",
        (
            __import__('uuid').uuid4().__str__(),
            patient_id,
            'Emergency QR code scanned — public access',
            request.remote_addr,
            __import__('datetime').datetime.now().isoformat()
        )
    )

    return render_template('paramedic/emergency_view.html',
        patient=patient,
        active_diseases=active_diseases,
        life_threat_allergies=life_threat_allergies,
        current_medications=current_medications,
        emergency_contacts=emergency_contacts,
        snapshot_time=snapshot.get('last_updated', 'Unknown') if snapshot else 'Unknown'
    )
