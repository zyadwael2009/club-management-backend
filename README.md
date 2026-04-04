# Club Management API

Flask REST API backend for the Club Management mobile app with full Arabic support.

## 🌐 Live Deployment

**Production URL**: https://clubmanagment.pythonanywhere.com/api

**Health Check**: https://clubmanagment.pythonanywhere.com/api/health

## Quick Start (Local Development)

### 1. Create virtual environment
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the server
```bash
python app.py
```

Server will start at `http://localhost:5000`

## 🚀 Deploy to PythonAnywhere

### Quick Deploy

See detailed documentation:
- **DEPLOYMENT_STEPS.txt** - Step-by-step guide
- **DEPLOYMENT_CHECKLIST.md** - Complete checklist
- **PYTHONANYWHERE_DEPLOYMENT.md** - Full documentation

### Quick Commands (on PythonAnywhere)

```bash
# Setup
cd ~/club-management/backend
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Initialize database
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```

Then configure WSGI file from `wsgi.py` and reload web app.

## API Endpoints

### Health Check
- `GET /api/health` - Check if API is running

### Clubs (الأندية)
- `GET /api/clubs` - List all clubs
- `GET /api/clubs/<id>` - Get club by ID
- `POST /api/clubs` - Create club
- `PUT /api/clubs/<id>` - Update club
- `DELETE /api/clubs/<id>` - Delete club

### Players (اللاعبون)
- `GET /api/players` - List players (?club_id=xxx&subgroup_id=xxx)
- `GET /api/players/<id>` - Get player by ID
- `GET /api/players/qr/<qr_code>` - Get player by QR code
- `GET /api/players/search?q=xxx` - Search players
- `GET /api/players/filter?payment_status=paid` - Filter players
- `POST /api/players` - Create player
- `PUT /api/players/<id>` - Update player
- `DELETE /api/players/<id>` - Delete player

### Subgroups (المجموعات الفرعية)
- `GET /api/subgroups` - List all subgroups
- `GET /api/subgroups/<id>` - Get subgroup by ID
- `GET /api/subgroups/club/<club_id>` - Get club's subgroups
- `POST /api/subgroups` - Create subgroup
- `PUT /api/subgroups/<id>` - Update subgroup
- `DELETE /api/subgroups/<id>` - Delete subgroup

### Matches (المباريات)
- `GET /api/matches` - List all matches
- `GET /api/matches/<id>` - Get match by ID
- `GET /api/matches/club/<club_id>` - Get club's matches
- `GET /api/matches/player/<id>/stats` - Get player match statistics
- `POST /api/matches` - Create match (with playerIds array)
- `PUT /api/matches/<id>` - Update match
- `DELETE /api/matches/<id>` - Delete match

### Check-ins (تسجيل الحضور)
- `GET /api/checkins` - List check-ins (?club_id=xxx&limit=50)
- `GET /api/checkins/player/<player_id>` - Player's check-in history
- `POST /api/checkins` - Create check-in (QR code-based)

### Images (الصور)
- `POST /api/images` - Upload image (multipart/form-data)
- `GET /api/images/<filename>` - Get image
- `DELETE /api/images/<filename>` - Delete image

## Environment Variables

- `DATABASE_URL` - Database connection (defaults to SQLite)
- `SECRET_KEY` - Flask secret key
- `PORT` - Server port (default: 5000)
- `CORS_ORIGINS` - Allowed origins (default: *)
- `UPLOAD_FOLDER` - Upload directory path

## Database Schema

### Models
- **Club** - Club information with logo
- **Player** - Player with payment status, subgroup assignment, and QR code
- **Subgroup** - Type (أكاديمية/نادي) + birth year grouping
- **Match** - Match records with type (ودي/رسمي), score, and player participation
- **CheckIn** - Attendance records

## 📱 Flutter App Integration

Update API URL in Flutter app:

```dart
// lib/services/api_service.dart
static const String _baseUrl = 'https://clubmanagment.pythonanywhere.com/api';
```

## 🐛 Troubleshooting

### Reset Database
```bash
cd ~/club-management/backend
rm instance/club_management.db
source venv/bin/activate
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
```

### Check Deployment
- View error logs in PythonAnywhere Web tab
- Test health endpoint
- Verify WSGI configuration

## Development

Uses SQLite for local development, can use PostgreSQL/MySQL for production.
