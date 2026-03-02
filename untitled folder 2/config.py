import os

USE_CLOUD = True  

LOCAL_DB_PATH = os.path.join(os.path.dirname(__file__), 'meditrack_local.db')

SUPABASE_URL = "https://vmkrqhdfbsyzswmzolrc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZta3JxaGRmYnN5enN3bXpvbHJjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIxOTA5MzUsImV4cCI6MjA4Nzc2NjkzNX0.oY1OyaTthxoOmyZ_QKc79m9ROMZ7ULwUXap9bdLe_cY"

LOCAL_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'app', 'static', 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
MAX_UPLOAD_SIZE_MB = 10

SECRET_KEY = 'meditrack-dev-secret-key'
ENCRYPTION_KEY = 'meditrack-encrypt-key-32bytes!!'

DOCTOR_SESSION_MINUTES = 15
PERMANENT_SESSION_LIFETIME = 60

DEBUG = True
HOST = '0.0.0.0'
PORT = 5000
APP_NAME = 'MediTrack'
VERSION = '1.0.0 - Cloud Enabled'