from flask import Flask
from datetime import timedelta
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import SECRET_KEY, LOCAL_UPLOAD_FOLDER, PERMANENT_SESSION_LIFETIME, DEBUG


def create_app():
    """
    Creates and configures the Flask application.
    This is the 'app factory' pattern — best practice for Flask apps.

    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)

    # ─── App Configuration ───
    app.secret_key = SECRET_KEY
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload size
    app.config['UPLOAD_FOLDER'] = LOCAL_UPLOAD_FOLDER
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=PERMANENT_SESSION_LIFETIME)
    app.config['DEBUG'] = DEBUG

    # ─── Initialise Database ───
    # Creates all tables if they don't exist
    from app.database.local_db import init_db
    with app.app_context():
        init_db()

    # ─── Register Blueprints (Route Groups) ───
    from app.routes.auth import auth_bp
    from app.routes.patient import patient_bp
    from app.routes.doctor import doctor_bp
    from app.routes.admin import admin_bp
    from app.routes.paramedic import paramedic_bp

    app.register_blueprint(auth_bp)       # /login, /logout, /register
    app.register_blueprint(patient_bp)    # /patient/*
    app.register_blueprint(doctor_bp)     # /doctor/*
    app.register_blueprint(admin_bp)      # /admin/*
    app.register_blueprint(paramedic_bp)  # /paramedic/*, /emergency/*

    # ─── Create upload directories if they don't exist ───
    os.makedirs(LOCAL_UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(LOCAL_UPLOAD_FOLDER, 'qr_codes'), exist_ok=True)
    os.makedirs(os.path.join(LOCAL_UPLOAD_FOLDER, 'reports'), exist_ok=True)

    return app
