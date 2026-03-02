from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from functools import wraps
from app.database.local_db import execute_query
from app.services.auth_service import log_audit
from app.services.sync_service import get_sync_status
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')

# ─────────────────────────────────────────────
# SECURITY DECORATOR
# Ensures only logged-in patients can access these pages
# ─────────────────────────────────────────────

def patient_required(f):
    """
    Decorator that checks if the current user is a logged-in patient.
    If not, redirects to login page.
    Apply this to any route that only patients should access.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'patient':
            flash('Access denied. This page is for patients only.', 'error')
            return redirect(url_for('auth.dashboard_redirect'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_patient():
    """
    Helper function to get the patient record for the currently logged-in user.
    Returns the patient dictionary or None if not found.
    """
    return execute_query(
        "SELECT * FROM patients WHERE user_id = ?",
        (session['user_id'],),
        fetchone=True
    )


# ─────────────────────────────────────────────
# PATIENT DASHBOARD
# ─────────────────────────────────────────────

@patient_bp.route('/dashboard')
@patient_required
def dashboard():
    """
    Patient home page — shows a summary of:
    - Personal info
    - Recent prescriptions
    - Active diseases
    - Current medications
    - Quick links to all features
    """
    patient = get_current_patient()
    if not patient:
        flash('Patient record not found. Please contact admin.', 'error')
        return redirect(url_for('auth.logout'))

    patient_id = patient['patient_id']

    # Get count of active diseases
    active_diseases = execute_query(
        "SELECT COUNT(*) as cnt FROM patient_diseases WHERE patient_id = ? AND status = 'Active'",
        (patient_id,), fetchone=True
    )

    # Get count of current medications
    current_meds = execute_query(
        "SELECT COUNT(*) as cnt FROM patient_medications WHERE patient_id = ? AND is_currently_taking = 1",
        (patient_id,), fetchone=True
    )

    # Get most recent prescription
    recent_prescription = execute_query(
        "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY prescription_date DESC LIMIT 1",
        (patient_id,), fetchone=True
    )

    # Get count of uploaded reports
    reports_count = execute_query(
        "SELECT COUNT(*) as cnt FROM medical_reports WHERE patient_id = ?",
        (patient_id,), fetchone=True
    )

    # Get sync status for display
    sync_info = get_sync_status()

    return render_template('patient/dashboard.html',
        patient=patient,
        active_diseases_count=active_diseases['cnt'] if active_diseases else 0,
        current_meds_count=current_meds['cnt'] if current_meds else 0,
        recent_prescription=recent_prescription,
        reports_count=reports_count['cnt'] if reports_count else 0,
        sync_info=sync_info
    )


# ─────────────────────────────────────────────
# MEDICAL HISTORY
# ─────────────────────────────────────────────

@patient_bp.route('/history')
@patient_required
def history():
    """
    Shows the patient's complete medical history including:
    - All diagnosed diseases (past and present)
    - All allergies
    - Hospitalization records
    - Surgery records
    """
    patient = get_current_patient()
    patient_id = patient['patient_id']

    # Get all diseases with their master info
    diseases = execute_query(
        """SELECT pd.*, dm.disease_name, dm.icd10_code, dm.risk_level, dm.is_chronic
           FROM patient_diseases pd
           JOIN disease_master dm ON pd.disease_id = dm.disease_id
           WHERE pd.patient_id = ?
           ORDER BY pd.diagnosed_date DESC""",
        (patient_id,), fetch=True
    )

    # Get all allergies with their master info
    allergies = execute_query(
        """SELECT pa.*, am.allergy_name, ac.category_name
           FROM patient_allergies pa
           JOIN allergy_master am ON pa.allergy_id = am.allergy_id
           LEFT JOIN allergy_categories ac ON am.allergy_category_id = ac.allergy_category_id
           WHERE pa.patient_id = ?
           ORDER BY pa.is_life_threatening DESC""",
        (patient_id,), fetch=True
    )

    # Get all hospitalizations
    hospitalizations = execute_query(
        "SELECT * FROM hospitalizations WHERE patient_id = ? ORDER BY admission_date DESC",
        (patient_id,), fetch=True
    )

    # Get all surgeries
    surgeries = execute_query(
        "SELECT * FROM surgeries WHERE patient_id = ? ORDER BY surgery_date DESC",
        (patient_id,), fetch=True
    )

    # Log that patient viewed their own history
    log_audit(session['user_id'], 'patient', 'VIEW_HISTORY',
              target_patient_id=patient_id,
              details='Patient viewed own medical history',
              ip_address=request.remote_addr)

    return render_template('patient/history.html',
        patient=patient,
        diseases=diseases or [],
        allergies=allergies or [],
        hospitalizations=hospitalizations or [],
        surgeries=surgeries or []
    )


# ─────────────────────────────────────────────
# PRESCRIPTIONS
# ─────────────────────────────────────────────

@patient_bp.route('/prescriptions')
@patient_required
def prescriptions():
    """
    Shows all prescriptions written for this patient.
    Most recent prescriptions appear first.
    """
    patient = get_current_patient()
    patient_id = patient['patient_id']

    # Get all prescriptions with doctor username
    all_prescriptions = execute_query(
        """SELECT p.*, u.username as doctor_username
           FROM prescriptions p
           JOIN users u ON p.doctor_user_id = u.user_id
           WHERE p.patient_id = ?
           ORDER BY p.prescription_date DESC""",
        (patient_id,), fetch=True
    )

    # Parse medications JSON for each prescription
    import json
    for prescription in (all_prescriptions or []):
        try:
            prescription['medications_list'] = json.loads(prescription.get('medications_json', '[]'))
        except Exception:
            prescription['medications_list'] = []

    log_audit(session['user_id'], 'patient', 'VIEW_PRESCRIPTIONS',
              target_patient_id=patient_id,
              details='Patient viewed prescriptions',
              ip_address=request.remote_addr)

    return render_template('patient/prescriptions.html',
        patient=patient,
        prescriptions=all_prescriptions or []
    )


# ─────────────────────────────────────────────
# FILE UPLOADS
# ─────────────────────────────────────────────

@patient_bp.route('/upload', methods=['GET', 'POST'])
@patient_required
def upload_report():
    """
    GET:  Shows the upload form for medical reports
    POST: Handles file upload — saves locally first, marks for cloud sync

    Accepted file types: PDF, PNG, JPG, JPEG
    Max size: 10MB (set in config.py)
    """
    patient = get_current_patient()
    patient_id = patient['patient_id']

    if request.method == 'POST':
        # Check if a file was included in the request
        if 'report_file' not in request.files:
            flash('No file selected. Please choose a file to upload.', 'error')
            return redirect(request.url)

        file = request.files['report_file']
        description = request.form.get('description', '').strip()

        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(request.url)

        # Check file extension is allowed
        from config import ALLOWED_EXTENSIONS
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if file_ext not in ALLOWED_EXTENSIONS:
            flash(f'File type not allowed. Please upload: {", ".join(ALLOWED_EXTENSIONS)}', 'error')
            return redirect(request.url)

        # Create patient-specific upload folder
        from config import LOCAL_UPLOAD_FOLDER
        patient_upload_folder = os.path.join(LOCAL_UPLOAD_FOLDER, 'reports', patient_id[:8])
        os.makedirs(patient_upload_folder, exist_ok=True)

        # Generate unique filename to prevent overwrites
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_path = os.path.join(patient_upload_folder, unique_filename)

        # Save file locally
        file.save(file_path)

        # Relative path for database storage
        relative_path = f"uploads/reports/{patient_id[:8]}/{unique_filename}"

        # Record upload in database
        report_id = str(uuid.uuid4())
        execute_query(
            """INSERT INTO medical_reports
               (report_id, patient_id, file_name, file_path, file_type, upload_date, description, sync_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (report_id, patient_id, filename, relative_path, file_ext,
             datetime.now().isoformat(), description)
        )

        log_audit(session['user_id'], 'patient', 'UPLOAD_REPORT',
                  target_patient_id=patient_id,
                  details=f'Uploaded report: {filename}',
                  ip_address=request.remote_addr)

        flash('Report uploaded successfully! It will sync to cloud when internet is available.', 'success')
        return redirect(url_for('patient.view_reports'))

    return render_template('patient/uploads.html', patient=patient)


@patient_bp.route('/reports')
@patient_required
def view_reports():
    """
    Shows all medical reports uploaded by the patient.
    Displays file name, upload date, description, and sync status.
    """
    patient = get_current_patient()
    patient_id = patient['patient_id']

    reports = execute_query(
        "SELECT * FROM medical_reports WHERE patient_id = ? ORDER BY upload_date DESC",
        (patient_id,), fetch=True
    )

    return render_template('patient/reports.html',
        patient=patient,
        reports=reports or []
    )


# ─────────────────────────────────────────────
# QR CODE
# ─────────────────────────────────────────────

@patient_bp.route('/qr-code')
@patient_required
def qr_code():
    """
    Shows the patient's personal QR code.
    Patient can show this to a doctor to grant 15-minute access,
    or to a paramedic for emergency access.
    Also provides a print button for making a physical QR card.
    """
    patient = get_current_patient()
    patient_id = patient['patient_id']

    from app.services.qr_service import get_qr_display_data, generate_qr_code

    # Get existing QR data
    qr_data = get_qr_display_data(patient_id)

    # Regenerate QR if it doesn't exist
    if not qr_data['qr_path']:
        generate_qr_code(patient_id)
        qr_data = get_qr_display_data(patient_id)

    log_audit(session['user_id'], 'patient', 'VIEW_QR_CODE',
              target_patient_id=patient_id,
              details='Patient viewed own QR code',
              ip_address=request.remote_addr)

    return render_template('patient/qr_code.html',
        patient=patient,
        qr_data=qr_data
    )
