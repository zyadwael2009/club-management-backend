"""
WSGI Configuration for PythonAnywhere

IMPORTANT: Copy this ENTIRE file content into your WSGI configuration file
Location: Web tab → Code section → WSGI configuration file

BEFORE USING:
1. Find your project directory on PythonAnywhere by running:
   cd ~ && find . -name "app.py" -type f
   
2. The directory containing app.py is your project_home
   Example: if you see ./club-management-backend/app.py
   Then project_home = '/home/clubmanagment/club-management-backend'

3. Update the project_home variable below with YOUR actual path
"""

import sys
import os

# ============================================================
# UPDATE THIS PATH TO MATCH YOUR PROJECT LOCATION
# ============================================================
# Run this command on PythonAnywhere to find it:
#   cd ~ && find . -name "app.py" -type f
# 
# Common paths:
#   /home/clubmanagment/club-management-backend  (if cloned from GitHub)
#   /home/clubmanagment/backend  (if uploaded directly)
# ============================================================

project_home = '/home/clubmanagment/club-management-backend'

# Add project to Python path
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['DATABASE_URL'] = f'sqlite:///{project_home}/instance/club_management.db'
os.environ['SECRET_KEY'] = 'your-super-secret-key-change-this-to-random-string'
os.environ['UPLOAD_FOLDER'] = f'{project_home}/uploads'

# Import the Flask app
from app import create_app
application = create_app()

# Debug information (will appear in error log)
print(f"[WSGI] Project home: {project_home}")
print(f"[WSGI] Python path: {sys.path}")
print(f"[WSGI] Database URL: {os.environ.get('DATABASE_URL')}")
print(f"[WSGI] Upload folder: {os.environ.get('UPLOAD_FOLDER')}")
print(f"[WSGI] App created successfully!")
