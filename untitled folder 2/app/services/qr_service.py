"""
app/services/qr_service.py - QR Code Service
=============================================
Handles all QR code generation for patients.
Each patient gets a unique QR code that:
- Encodes a secure token (NOT the patient ID directly)
- Links to the emergency view when scanned
- Is regenerated when patient data changes

The QR code encodes a URL like:
  /emergency/<secure_token>
When scanned, this shows critical emergency info WITHOUT requiring login.
"""

import uuid
import hashlib
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import LOCAL_UPLOAD_FOLDER, SECRET_KEY
from app.database.local_db import execute_query

# Try to import QR code library
try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False


def generate_patient_token(patient_id):
    """
    Generates a secure token for a patient's QR code.
    This token is used in the QR URL instead of the raw patient_id.
    This adds a layer of security — someone can't just guess patient IDs.

    Parameters:
        patient_id - The patient's UUID
    Returns:
        A 32-character secure hex token
    """
    # Combine patient_id with secret key and hash it
    raw = f"{patient_id}{SECRET_KEY}meditrack_qr"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def generate_qr_code(patient_id, base_url="http://localhost:5000"):
    """
    Generates a QR code image for a patient and saves it locally.
    The QR code encodes the emergency access URL with a secure token.

    Parameters:
        patient_id - The patient's UUID
        base_url   - The base URL of the app (default: localhost for Phase 1)
    Returns:
        Dictionary with 'success' True/False and 'qr_path' or 'error'
    """
    # Generate the secure token for this patient
    token = generate_patient_token(patient_id)

    # Build the emergency access URL
    emergency_url = f"{base_url}/emergency/{token}"

    # Create QR codes directory if it doesn't exist
    qr_folder = os.path.join(LOCAL_UPLOAD_FOLDER, 'qr_codes')
    os.makedirs(qr_folder, exist_ok=True)

    qr_filename = f"qr_{patient_id[:8]}.png"
    qr_path = os.path.join(qr_folder, qr_filename)
    qr_relative_path = f"uploads/qr_codes/{qr_filename}"

    if not QR_AVAILABLE:
        # If qrcode library not installed, save a placeholder text file
        # and return a flag so the template can show the URL instead
        with open(qr_path.replace('.png', '.txt'), 'w') as f:
            f.write(f"QR Code URL: {emergency_url}\n")
            f.write("Install 'qrcode[pil]' package to generate actual QR image.")
        return {
            'success': True,
            'qr_path': qr_relative_path,
            'emergency_url': emergency_url,
            'qr_available': False
        }

    try:
        # Create QR code with custom styling
        qr = qrcode.QRCode(
            version=1,                          # Controls size (1 = smallest)
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
            box_size=10,                        # Size of each box in pixels
            border=4,                           # White border width
        )

        # Add the emergency URL as the QR data
        qr.add_data(emergency_url)
        qr.make(fit=True)

        # Create QR image with custom colours
        qr_image = qr.make_image(fill_color="#1a1a2e", back_color="white")

        # Save the QR code image
        qr_image.save(qr_path)

        # Update the patient record with the QR code path
        execute_query(
            "UPDATE patients SET qr_code_path = ? WHERE patient_id = ?",
            (qr_relative_path, patient_id)
        )

        return {
            'success': True,
            'qr_path': qr_relative_path,
            'emergency_url': emergency_url,
            'qr_available': True
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


def validate_qr_token(token):
    """
    Validates a QR token and returns the associated patient_id.
    Used when a doctor or paramedic scans a QR code.

    The system checks all patients to find which one matches this token.
    This is secure because tokens are one-way hashes — they can't be reversed.

    Parameters:
        token - The token from the scanned QR code URL
    Returns:
        patient_id string if valid token found, None otherwise
    """
    # Get all patient IDs and check which one generates this token
    # In production with millions of patients, this should use a token lookup table
    patients = execute_query(
        "SELECT patient_id FROM patients",
        fetch=True
    )

    if not patients:
        return None

    for patient in patients:
        expected_token = generate_patient_token(patient['patient_id'])
        if expected_token == token:
            return patient['patient_id']

    return None  # Token not found — invalid QR code


def get_qr_display_data(patient_id):
    """
    Gets all data needed to display the QR code page to a patient.
    Returns the QR image path and the emergency URL.

    Parameters:
        patient_id - The patient's UUID
    Returns:
        Dictionary with qr_path and emergency_url
    """
    token = generate_patient_token(patient_id)
    emergency_url = f"http://localhost:5000/emergency/{token}"

    # Get QR path from database
    patient = execute_query(
        "SELECT qr_code_path FROM patients WHERE patient_id = ?",
        (patient_id,),
        fetchone=True
    )

    qr_path = patient.get('qr_code_path') if patient else None

    return {
        'qr_path': qr_path,
        'emergency_url': emergency_url,
        'token': token
    }
