# PythonAnywhere Deployment Guide

## Prerequisites
1. Create a free account at https://www.pythonanywhere.com
2. Username should be: `clubmanagment`

## Deployment Steps

### 1. Upload Backend Code

#### Option A: Using Git (Recommended)
```bash
# On PythonAnywhere Bash console:
cd ~
git clone <your-repo-url> club-management
cd club-management/backend
```

#### Option B: Manual Upload
1. Zip the `backend` folder locally
2. Go to PythonAnywhere > Files
3. Upload the zip file
4. Unzip it in the home directory

### 2. Set Up Virtual Environment
```bash
# In PythonAnywhere Bash console:
cd ~/club-management/backend
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Web App
1. Go to **Web** tab in PythonAnywhere
2. Click **Add a new web app**
3. Choose **Manual configuration**
4. Select **Python 3.10**
5. Click **Next**

### 4. Configure WSGI File
1. In the **Web** tab, find the **Code** section
2. Click on the **WSGI configuration file** link
3. Replace the entire content with:

```python
import sys
import os

# Add your project directory to the sys.path
project_home = '/home/clubmanagment/club-management/backend'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['DATABASE_URL'] = 'sqlite:////home/clubmanagment/club-management/backend/instance/club_management.db'
os.environ['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
os.environ['UPLOAD_FOLDER'] = '/home/clubmanagment/club-management/backend/uploads'

# Import the Flask app
from app import create_app
application = create_app()
```

### 5. Configure Virtualenv
1. In the **Web** tab, find the **Virtualenv** section
2. Enter: `/home/clubmanagment/club-management/backend/venv`
3. Click the checkmark to save

### 6. Configure Static Files
1. In the **Web** tab, find the **Static files** section
2. Add a new static file mapping:
   - URL: `/uploads`
   - Directory: `/home/clubmanagment/club-management/backend/uploads`

### 7. Create Required Directories
```bash
# In PythonAnywhere Bash console:
cd ~/club-management/backend
mkdir -p instance
mkdir -p uploads
```

### 8. Initialize Database
```bash
# In PythonAnywhere Bash console:
cd ~/club-management/backend
source venv/bin/activate
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all(); print('Database created!')"
```

### 9. Reload Web App
1. Go to the **Web** tab
2. Click the **Reload** button (big green button)

### 10. Test Your API
Visit: https://clubmanagment.pythonanywhere.com/api/health

You should see:
```json
{
  "status": "healthy",
  "message": "Club Management API is running"
}
```

## Important Notes

### Free Account Limitations
- The app will sleep after 3 months of inactivity
- Limited CPU seconds per day
- One web app only
- HTTP only (HTTPS requires paid account)

### Database
- Using SQLite (included in the deployment)
- Database file location: `/home/clubmanagment/club-management/backend/instance/club_management.db`
- For production, consider upgrading to MySQL (available on paid plans)

### Uploads Folder
- Make sure the uploads folder has write permissions
- Files uploaded through the API will be stored in `/home/clubmanagment/club-management/backend/uploads`

### Environment Variables
- All environment variables are set in the WSGI file
- Change `SECRET_KEY` to a secure random string in production

### CORS
- The backend is configured to allow all origins (`*`)
- For production, update `CORS_ORIGINS` in `config.py` to only allow your app's domain

## Troubleshooting

### If you see "Something went wrong :("
1. Check the **Error log** in the Web tab
2. Common issues:
   - Missing dependencies in requirements.txt
   - Wrong Python version
   - Database permissions
   - Import errors in WSGI file

### Database Errors
```bash
# Reset the database:
cd ~/club-management/backend
rm instance/club_management.db
source venv/bin/activate
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```

### Check Logs
- Error log: Shows Python errors and tracebacks
- Server log: Shows HTTP requests
- Both available in the **Web** tab

## Updating Your App

When you make changes:
```bash
# Pull latest changes (if using Git)
cd ~/club-management/backend
git pull

# Reinstall dependencies if requirements.txt changed
source venv/bin/activate
pip install -r requirements.txt

# Reload the web app from the Web tab
```

## Alternative: Quick Deploy Script

If you want to automate the initial setup, create a file `deploy.sh` on PythonAnywhere:

```bash
#!/bin/bash
cd ~/club-management/backend
source venv/bin/activate
pip install -r requirements.txt
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
echo "Deployment complete! Remember to reload the web app."
```

Make it executable and run:
```bash
chmod +x deploy.sh
./deploy.sh
```

## Next Step: Update Flutter App

After deployment, update the API URL in your Flutter app:
File: `lib/services/api_service.dart`

Change:
```dart
static const String _baseUrl = 'http://192.168.1.7:5000/api';
```

To:
```dart
static const String _baseUrl = 'https://clubmanagment.pythonanywhere.com/api';
```

Then rebuild your Flutter app.
