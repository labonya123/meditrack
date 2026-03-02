"""
run.py - MediTrack Application Entry Point
==========================================
This is the file you run to start MediTrack.
It:
1. Creates the Flask app
2. Seeds the database with sample data (first run only)
3. Starts the web server

HOW TO RUN:
  Windows:  Double-click run.bat  OR  python run.py
  Mac/Linux: ./run.sh  OR  python3 run.py

Then open your browser: http://localhost:5000
"""

import os
import sys

# Make sure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Add project to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from config import HOST, PORT, DEBUG


def main():
    """
    Main function — creates and starts the MediTrack application.
    Seeds the database with sample data on first run.
    """
    print("\n" + "="*55)
    print("  🏥  MediTrack — Emergency Medical Record System")
    print("  Version 1.0.0 — Phase 1 (Cloud-Ready Prototype)")
    print("="*55)

    # Create the Flask application
    app = create_app()

    # Seed database with sample data if empty (first run)
    with app.app_context():
        try:
            from app.database.seed_data import seed_all
            seed_all()
        except Exception as e:
            print(f"⚠️  Seed warning: {e}")

    print(f"\n✅ MediTrack is running!")
    print(f"🌐 Open your browser: http://localhost:{PORT}")
    print(f"\n🔑 Test Accounts:")
    print(f"   Admin:     admin / admin123")
    print(f"   Doctor:    dr_sharma / doctor123")
    print(f"   Paramedic: paramedic1 / para123")
    print(f"   Patient:   rahul_kumar / patient123")
    print(f"   Patient:   priya_devi / patient123")
    print(f"\n⏹  Press CTRL+C to stop the server")
    print("="*55 + "\n")

    # Start the Flask development server
    app.run(host=HOST, port=PORT, debug=DEBUG)


if __name__ == '__main__':
    main()
