# PythonAnywhere Deployment Checklist

## ✅ Pre-Deployment (On Your Computer)

- [ ] Backend folder is ready in: `d:\Programming\club managment\backend`
- [ ] All files are present: app.py, models.py, config.py, requirements.txt, routes/
- [ ] Test locally to ensure backend works
- [ ] Create a ZIP file of the backend folder

## ✅ PythonAnywhere Account Setup

- [ ] Created account at https://www.pythonanywhere.com
- [ ] Username is: **clubmanagment**
- [ ] Email verified
- [ ] Logged in successfully

## ✅ File Upload

- [ ] Uploaded backend.zip to PythonAnywhere Files tab
- [ ] Opened Bash console
- [ ] Created directory: `mkdir -p ~/club-management`
- [ ] Unzipped: `cd ~/club-management && unzip ~/backend.zip`
- [ ] Verified files: `ls -la backend/` shows app.py, models.py, etc.

## ✅ Virtual Environment

```bash
cd ~/club-management/backend
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- [ ] Virtual environment created at: `/home/clubmanagment/club-management/backend/venv`
- [ ] All dependencies installed without errors
- [ ] Flask version confirmed: `flask --version`

## ✅ Database Initialization

```bash
cd ~/club-management/backend
source venv/bin/activate
python << 'EOF'
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print("✅ Database created!")
EOF
```

- [ ] Database file created: `ls instance/club_management.db`
- [ ] No errors in database creation

## ✅ Web App Configuration

### Create Web App
- [ ] Went to "Web" tab
- [ ] Clicked "Add a new web app"
- [ ] Accepted domain: clubmanagment.pythonanywhere.com
- [ ] Selected "Manual configuration"
- [ ] Chose Python 3.10
- [ ] Web app created successfully

### WSGI Configuration
- [ ] Clicked on WSGI configuration file link
- [ ] Deleted all existing content
- [ ] Pasted WSGI configuration from wsgi.py
- [ ] Verified paths:
  - [ ] project_home = `/home/clubmanagment/club-management/backend`
  - [ ] DATABASE_URL points to correct path
  - [ ] UPLOAD_FOLDER points to correct path
- [ ] Clicked "Save" button

### Virtual Environment Path
- [ ] In Web tab, found "Virtualenv:" section
- [ ] Entered: `/home/clubmanagment/club-management/backend/venv`
- [ ] Path accepted (green checkmark)

### Static Files
- [ ] In Web tab, found "Static files:" section
- [ ] Added mapping:
  - URL: `/uploads`
  - Directory: `/home/clubmanagment/club-management/backend/uploads`
- [ ] Static file mapping saved

## ✅ Directory Permissions

```bash
mkdir -p ~/club-management/backend/uploads
mkdir -p ~/club-management/backend/instance
chmod 755 ~/club-management/backend/uploads
chmod 755 ~/club-management/backend/instance
```

- [ ] Uploads directory created
- [ ] Instance directory created
- [ ] Permissions set correctly

## ✅ Web App Reload

- [ ] Went to Web tab
- [ ] Clicked big green "Reload clubmanagment.pythonanywhere.com" button
- [ ] Saw "Reloaded successfully" message
- [ ] No errors in error log

## ✅ Testing

### Health Check
- [ ] Visited: https://clubmanagment.pythonanywhere.com/api/health
- [ ] Response shows: `{"status":"healthy","message":"Club Management API is running"}`

### Create Test Club
```bash
curl -X POST https://clubmanagment.pythonanywhere.com/api/clubs \
  -H "Content-Type: application/json" \
  -d '{"name":"نادي الاختبار","description":"للتجربة"}'
```
- [ ] Club created successfully
- [ ] Received club ID in response

### List Clubs
- [ ] Visited: https://clubmanagment.pythonanywhere.com/api/clubs
- [ ] Clubs list returned successfully

### Create Test Player
```bash
curl -X POST https://clubmanagment.pythonanywhere.com/api/players \
  -H "Content-Type: application/json" \
  -d '{"fullName":"محمد أحمد","paymentStatus":"paid","notes":"لاعب تجريبي"}'
```
- [ ] Player created successfully
- [ ] Received player ID in response

## ✅ Flutter App Update

### Update API Base URL
- [ ] Opened: `lib/services/api_service.dart`
- [ ] Changed `_baseUrl` from `http://192.168.1.7:5000/api` to `https://clubmanagment.pythonanywhere.com/api`
- [ ] Saved file

### Rebuild App
```bash
cd d:\Programming\club managment
flutter clean
flutter pub get
flutter build apk
```
- [ ] App built successfully
- [ ] No compilation errors
- [ ] APK generated

### Test App
- [ ] Installed APK on Android device
- [ ] App connects to PythonAnywhere backend
- [ ] Can create clubs
- [ ] Can create players
- [ ] Can create subgroups
- [ ] Can create matches
- [ ] All features working

## ✅ Post-Deployment

### Documentation
- [ ] Noted PythonAnywhere username: clubmanagment
- [ ] Noted API URL: https://clubmanagment.pythonanywhere.com/api
- [ ] Saved error log location for future reference
- [ ] Documented any custom configurations

### Backup
```bash
# On PythonAnywhere
cd ~/club-management/backend
cp instance/club_management.db instance/backup_$(date +%Y%m%d).db
```
- [ ] Initial database backup created

### Monitoring
- [ ] Checked error log (Web tab > Error log)
- [ ] Checked server log (Web tab > Server log)
- [ ] No unexpected errors

## 📝 Important URLs

- **API Base**: https://clubmanagment.pythonanywhere.com/api
- **Health Check**: https://clubmanagment.pythonanywhere.com/api/health
- **PythonAnywhere Dashboard**: https://www.pythonanywhere.com/user/clubmanagment/
- **Web Tab**: https://www.pythonanywhere.com/user/clubmanagment/webapps/
- **Files Tab**: https://www.pythonanywhere.com/user/clubmanagment/files/
- **Consoles Tab**: https://www.pythonanywhere.com/user/clubmanagment/consoles/

## 🚨 Troubleshooting Quick Reference

### Problem: "Something went wrong :("
1. Check error log in Web tab
2. Verify WSGI file paths
3. Ensure virtualenv path is correct
4. Check requirements are installed

### Problem: 404 Not Found
1. Verify web app is running
2. Check URL is correct
3. Ensure routes are registered in app.py

### Problem: 500 Internal Server Error
1. Check error log for Python traceback
2. Verify database file exists
3. Check file permissions
4. Ensure all imports work

### Quick Fix: Reset Everything
```bash
cd ~/club-management/backend
source venv/bin/activate
rm -rf instance/club_management.db
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```
Then reload web app.

## ✅ Deployment Complete!

Date: _________________
Deployed by: _________________
API URL: https://clubmanagment.pythonanywhere.com/api
Status: _________________

Notes:
_________________________________________________________________________
_________________________________________________________________________
_________________________________________________________________________
