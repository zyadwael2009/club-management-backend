"""
WSGI Configuration for PythonAnywhere Deployment

This file should be copied to PythonAnywhere's WSGI configuration file.
Access it from: Web > Code > WSGI configuration file
"""

import sys
import os

# Add your project directory to the sys.path
# CHANGE 'clubmanagment' to your PythonAnywhere username if different
project_home = '/home/clubmanagment/club-management-backend'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['DATABASE_URL'] = 'sqlite:////home/clubmanagment/club-management-backend/instance/club_management.db'
os.environ['SECRET_KEY'] = 'your-super-secret-key-change-this-to-random-string-in-production'
os.environ['UPLOAD_FOLDER'] = '/home/clubmanagment/club-management-backend/uploads'

# Import the Flask app
from app import create_app
application = create_app()
