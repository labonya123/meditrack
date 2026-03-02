from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.services.auth_service import authenticate_user, create_user, log_audit
from app.database.local_db import execute_query
import uuid
from datetime import datetime

# Create Blueprint — a way to group related routes together
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    """
    Home page — redirects to dashboard if logged in, otherwise to login.
    """
    if 'user_id' in session:
        return redirect(url_for('auth.dashboard_redirect'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    GET:  Shows the login form
    POST: Processes login credentials
    On success: Redirects to the correct dashboard based on role
    On failure: Shows error message and stays on login page
    """
    # If already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('auth.dashboard_redirect'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Validate inputs are not empty
        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('auth/login.html')

        # Attempt to authenticate
        user = authenticate_user(username, password)

        if user:
            # Store user info in session
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['role'] = user['role']
            session.permanent = True

            # Log this login to audit trail
            log_audit(
                user_id=user['user_id'],
                user_role=user['role'],
                action='LOGIN',
                details=f"User {username} logged in",
                ip_address=request.remote_addr
            )

            flash(f"Welcome back, {username}!", 'success')
            return redirect(url_for('auth.dashboard_redirect'))
        else:
            # Log failed login attempt
            flash('Invalid username or password. Please try again.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """
    Logs out the current user by clearing their session.
    Redirects to login page after logout.
    """
    if 'user_id' in session:
        # Log the logout action before clearing session
        log_audit(
            user_id=session['user_id'],
            user_role=session.get('role', 'unknown'),
            action='LOGOUT',
            details=f"User {session.get('username')} logged out",
            ip_address=request.remote_addr
        )

    # Clear all session data
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/dashboard')
def dashboard_redirect():
    """
    Redirects logged-in users to their role-specific dashboard.
    Doctor → /doctor/dashboard
    Patient → /patient/dashboard
    Admin → /admin/dashboard
    Paramedic → /paramedic/dashboard
    """
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    role = session.get('role')

    if role == 'patient':
        return redirect(url_for('patient.dashboard'))
    elif role == 'doctor':
        return redirect(url_for('doctor.dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'paramedic':
        return redirect(url_for('paramedic.dashboard'))
    else:
        flash('Unknown role. Please contact admin.', 'error')
        return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    GET:  Shows the patient self-registration form
    POST: Creates a new patient account

    Only patients can self-register.
    Doctors, admins, and paramedics are created by admin only.
    """
    if request.method == 'POST':
        # Get all form fields
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        gender = request.form.get('gender', '')
        date_of_birth = request.form.get('date_of_birth', '')
        blood_group = request.form.get('blood_group', '')
        phone_number = request.form.get('phone_number', '').strip()
        village_name = request.form.get('village_name', '').strip()
        district = request.form.get('district', '').strip()
        state = request.form.get('state', '').strip()

        # ─── Validation ───
        errors = []
        if not username:
            errors.append('Username is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if not first_name or not last_name:
            errors.append('Full name is required.')
        if not date_of_birth:
            errors.append('Date of birth is required.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html', form_data=request.form)

        # ─── Create User Account ───
        result = create_user(username, password, 'patient')

        if not result['success']:
            flash(result['error'], 'error')
            return render_template('auth/register.html', form_data=request.form)

        user_id = result['user_id']

        # ─── Encrypt sensitive data ───
        from app.services.encrypt_service import encrypt_phone, hash_aadhaar
        encrypted_phone = encrypt_phone(phone_number) if phone_number else None
        aadhaar_raw = request.form.get('aadhaar', '').strip()
        aadhaar_hashed = hash_aadhaar(aadhaar_raw) if aadhaar_raw else None

        # ─── Create Patient Record ───
        patient_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        execute_query(
            """INSERT INTO patients
               (patient_id, user_id, first_name, last_name, gender, date_of_birth,
                blood_group, phone_number_encrypted, aadhaar_hash, village_name,
                district, state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, user_id, first_name, last_name, gender, date_of_birth,
             blood_group, encrypted_phone, aadhaar_hashed, village_name,
             district, state, now, now)
        )

        # ─── Generate QR Code for this patient ───
        from app.services.qr_service import generate_qr_code
        generate_qr_code(patient_id)

        # ─── Create initial emergency snapshot ───
        execute_query(
            """INSERT INTO patient_emergency_snapshot
               (patient_id, blood_group, active_diseases_json, life_threat_allergies_json,
                current_medications_json, emergency_contacts_json, last_updated)
               VALUES (?, ?, '[]', '[]', '[]', '[]', ?)""",
            (patient_id, blood_group, now)
        )

        # Log the registration
        log_audit(
            user_id=user_id,
            user_role='patient',
            action='REGISTER',
            target_patient_id=patient_id,
            details=f"New patient registered: {first_name} {last_name}",
            ip_address=request.remote_addr
        )

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')
