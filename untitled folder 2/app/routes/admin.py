from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from functools import wraps
from app.database.local_db import execute_query
from app.services.auth_service import log_audit, create_user
from app.services.encrypt_service import anonymise_patient
from app.services.sync_service import get_sync_status
import uuid
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """
    Decorator that ensures only logged-in admins can access admin pages.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in.', 'error')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            flash('Access denied. Admin only.', 'error')
            return redirect(url_for('auth.dashboard_redirect'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """
    Admin home — shows overall system statistics:
    - Total patients registered
    - Total doctors and paramedics
    - Pending sync records
    - Recent audit log entries
    """
    # Count users by role
    stats = {}
    for role in ['patient', 'doctor', 'paramedic']:
        result = execute_query(
            "SELECT COUNT(*) as cnt FROM users WHERE role = ? AND is_active = 1",
            (role,), fetchone=True
        )
        stats[role] = result['cnt'] if result else 0

    # Get recent audit log (last 10 entries) — anonymised
    recent_audit = execute_query(
        """SELECT al.*, u.username, u.role
           FROM audit_log al
           JOIN users u ON al.user_id = u.user_id
           ORDER BY al.timestamp DESC LIMIT 10""",
        fetch=True
    )

    sync_info = get_sync_status()

    return render_template('admin/dashboard.html',
        stats=stats,
        recent_audit=recent_audit or [],
        sync_info=sync_info
    )


@admin_bp.route('/users')
@admin_required
def manage_users():
    """
    Shows all users in the system.
    For patients: names are shown for management purposes.
    Health data shown to admin is always anonymised.
    """
    all_users = execute_query(
        "SELECT user_id, username, role, is_active, created_at, last_login FROM users ORDER BY role, created_at DESC",
        fetch=True
    )
    return render_template('admin/manage_users.html', users=all_users or [])


@admin_bp.route('/add-user', methods=['GET', 'POST'])
@admin_required
def add_user():
    """
    GET:  Shows form to create doctor/paramedic accounts
    POST: Creates the new account

    Only admins can create doctor and paramedic accounts.
    Patients register themselves.
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', '')

        # Only allow creating doctor or paramedic accounts here
        if role not in ['doctor', 'paramedic']:
            flash('You can only create Doctor or Paramedic accounts here.', 'error')
            return redirect(request.url)

        result = create_user(username, password, role)

        if result['success']:
            log_audit(session['user_id'], 'admin', 'CREATE_USER',
                      details=f'Created {role} account: {username}',
                      ip_address=request.remote_addr)
            flash(f'{role.capitalize()} account created successfully!', 'success')
            return redirect(url_for('admin.manage_users'))
        else:
            flash(result['error'], 'error')

    return render_template('admin/add_user.html')


@admin_bp.route('/deactivate/<user_id>', methods=['POST'])
@admin_required
def deactivate_user(user_id):
    """
    Deactivates a user account so they can no longer log in.
    Does NOT delete the account — data is preserved.

    Parameters:
        user_id - The user to deactivate
    """
    # Prevent admin from deactivating themselves
    if user_id == session['user_id']:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.manage_users'))

    execute_query(
        "UPDATE users SET is_active = 0 WHERE user_id = ?",
        (user_id,)
    )

    log_audit(session['user_id'], 'admin', 'DEACTIVATE_USER',
              details=f'Deactivated user: {user_id}',
              ip_address=request.remote_addr)

    flash('User account deactivated.', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/data-overview')
@admin_required
def data_overview():
    """
    Shows anonymised health statistics for disease/health trend monitoring.

    IMPORTANT: All patient data shown here is ANONYMISED.
    - No names, no phone numbers, no Aadhaar
    - Only health trends and geographic patterns
    This is for future pandemic/disease tracking (Phase 2 will expand this)
    """
    # Get anonymised disease distribution
    disease_stats = execute_query(
        """SELECT dm.disease_name, dm.risk_level, COUNT(*) as patient_count
           FROM patient_diseases pd
           JOIN disease_master dm ON pd.disease_id = dm.disease_id
           WHERE pd.status = 'Active'
           GROUP BY dm.disease_name, dm.risk_level
           ORDER BY patient_count DESC""",
        fetch=True
    )

    # Get geographic distribution (district level — no personal info)
    district_stats = execute_query(
        """SELECT district, state, COUNT(*) as patient_count,
           SUM(has_chronic_disease) as chronic_count
           FROM patients
           GROUP BY district, state
           ORDER BY patient_count DESC""",
        fetch=True
    )

    # Get blood group distribution
    blood_group_stats = execute_query(
        """SELECT blood_group, COUNT(*) as count
           FROM patients
           WHERE blood_group IS NOT NULL
           GROUP BY blood_group
           ORDER BY count DESC""",
        fetch=True
    )

    log_audit(session['user_id'], 'admin', 'VIEW_ANONYMISED_DATA',
              details='Admin viewed anonymised health overview',
              ip_address=request.remote_addr)

    return render_template('admin/data_overview.html',
        disease_stats=disease_stats or [],
        district_stats=district_stats or [],
        blood_group_stats=blood_group_stats or []
    )


@admin_bp.route('/sync', methods=['POST'])
@admin_required
def trigger_sync():
    """
    Manually triggers a sync of all pending local data to cloud.
    Called when admin clicks 'Sync Now' button.
    """
    from app.services.sync_service import sync_to_cloud
    result = sync_to_cloud()

    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['message'], 'warning')

    return redirect(url_for('admin.dashboard'))
