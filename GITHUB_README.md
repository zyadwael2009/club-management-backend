# Club Management Backend

Flask REST API backend for the Club Management mobile app with full Arabic support.

## 🌐 Live API

Production: `https://clubmanagment.pythonanywhere.com/api`

## 🚀 Quick Deploy to PythonAnywhere

### Prerequisites
- PythonAnywhere account (username: `clubmanagment`)
- This repository

### Deployment Steps

1. **Clone on PythonAnywhere**
   ```bash
   # Open Bash console on PythonAnywhere
   cd ~
   git clone https://github.com/YOUR_USERNAME/club-management-backend.git
   cd club-management-backend
   ```

2. **Set up environment**
   ```bash
   python3.10 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Initialize database**
   ```bash
   mkdir -p instance uploads
   python << 'EOF'
   from app import create_app, db
   app = create_app()
   with app.app_context():
       db.create_all()
       print("✅ Database created!")
   EOF
   ```

4. **Configure Web App**
   - Go to Web tab → Add new web app
   - Choose Manual configuration → Python 3.10
   - Set Virtualenv: `/home/clubmanagment/club-management-backend/venv`
   - Configure WSGI file (see `wsgi.py`)
   - Add static files: `/uploads` → `/home/clubmanagment/club-management-backend/uploads`
   - Click Reload

5. **Test**
   ```
   https://clubmanagment.pythonanywhere.com/api/health
   ```

## 📖 Full Documentation

- `DEPLOYMENT_STEPS.txt` - Step-by-step deployment guide
- `PYTHONANYWHERE_DEPLOYMENT.md` - Comprehensive documentation
- `wsgi.py` - WSGI configuration for PythonAnywhere

## 🔄 Updating Deployment

When you make changes:

```bash
# On PythonAnywhere Bash console
cd ~/club-management-backend
git pull origin main
source venv/bin/activate
pip install -r requirements.txt  # if requirements changed
# Then reload web app from Web tab
```

## 🏃 Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run server
python app.py
```

Server runs at `http://localhost:5000`

## 📱 API Endpoints

See `README.md` for complete API documentation.

### Key Endpoints
- `GET /api/health` - Health check
- `GET /api/clubs` - List clubs
- `GET /api/players` - List players
- `GET /api/subgroups` - List subgroups
- `GET /api/matches` - List matches

## 🗄️ Database

- Development: SQLite (auto-created in `instance/`)
- Production: SQLite on PythonAnywhere

## 🔐 Environment Variables

Set in WSGI file on PythonAnywhere:
- `DATABASE_URL` - Database path
- `SECRET_KEY` - Flask secret key
- `UPLOAD_FOLDER` - Upload directory path

## 📄 License

Proprietary - Club Management Application

## 🆘 Support

For deployment issues, see troubleshooting in `DEPLOYMENT_STEPS.txt`
