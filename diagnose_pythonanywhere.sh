#!/bin/bash
# Diagnostic script for PythonAnywhere deployment
# Run this on PythonAnywhere Bash console to check your setup

echo "🔍 PythonAnywhere Deployment Diagnostics"
echo "=========================================="
echo ""

# Check current directory
echo "📁 Current directory:"
pwd
echo ""

# Find app.py
echo "🔎 Looking for app.py..."
APP_PATH=$(find ~ -name "app.py" -type f 2>/dev/null | head -n 1)
if [ -z "$APP_PATH" ]; then
    echo "❌ app.py not found!"
    echo "   Make sure you've cloned or uploaded the repository."
    exit 1
else
    echo "✅ Found app.py at: $APP_PATH"
    PROJECT_DIR=$(dirname "$APP_PATH")
    echo "✅ Project directory: $PROJECT_DIR"
fi
echo ""

# Check if we can cd to project
echo "📂 Checking project directory..."
if cd "$PROJECT_DIR" 2>/dev/null; then
    echo "✅ Successfully entered project directory"
    echo "   Current location: $(pwd)"
else
    echo "❌ Cannot access project directory"
    exit 1
fi
echo ""

# List project files
echo "📋 Project files:"
ls -la | grep -E "app.py|models.py|config.py|requirements.txt|routes"
echo ""

# Check virtual environment
echo "🐍 Checking virtual environment..."
if [ -d "venv" ]; then
    echo "✅ venv directory exists"
    VENV_PATH="$(pwd)/venv"
    echo "   Path: $VENV_PATH"
else
    echo "❌ venv directory not found"
    echo "   Run: python3.10 -m venv venv"
fi
echo ""

# Check if venv has packages
if [ -d "venv/lib/python3.10/site-packages/flask" ]; then
    echo "✅ Flask is installed in venv"
else
    echo "❌ Flask not found in venv"
    echo "   Run: source venv/bin/activate && pip install -r requirements.txt"
fi
echo ""

# Check database
echo "🗄️  Checking database..."
if [ -f "instance/club_management.db" ]; then
    echo "✅ Database exists"
    echo "   Path: $(pwd)/instance/club_management.db"
else
    echo "❌ Database not found"
    echo "   Run: mkdir -p instance && python -c 'from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()'"
fi
echo ""

# Check uploads directory
echo "📤 Checking uploads directory..."
if [ -d "uploads" ]; then
    echo "✅ Uploads directory exists"
    echo "   Path: $(pwd)/uploads"
else
    echo "❌ Uploads directory not found"
    echo "   Run: mkdir -p uploads && chmod 755 uploads"
fi
echo ""

# Test import
echo "🧪 Testing Python import..."
if source venv/bin/activate 2>/dev/null && python -c "from app import create_app; print('✅ Import successful!')" 2>/dev/null; then
    echo "✅ Can import app successfully"
else
    echo "❌ Cannot import app"
    echo "   This usually means:"
    echo "   1. Virtual environment not activated"
    echo "   2. Dependencies not installed"
    echo "   Run: source venv/bin/activate && pip install -r requirements.txt"
fi
echo ""

# Show WSGI configuration
echo "📝 Your WSGI configuration should be:"
echo "========================================"
cat << EOF

import sys
import os

project_home = '$(pwd)'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['DATABASE_URL'] = 'sqlite:///$(pwd)/instance/club_management.db'
os.environ['SECRET_KEY'] = 'your-secret-key-change-this'
os.environ['UPLOAD_FOLDER'] = '$(pwd)/uploads'

from app import create_app
application = create_app()

EOF
echo "========================================"
echo ""

echo "📋 Summary:"
echo "==========="
echo "Project path: $(pwd)"
echo "Virtualenv path: $(pwd)/venv"
echo "Database path: $(pwd)/instance/club_management.db"
echo "Uploads path: $(pwd)/uploads"
echo ""

echo "🎯 Next steps:"
echo "1. Go to PythonAnywhere Web tab"
echo "2. Click on WSGI configuration file"
echo "3. Copy the configuration shown above"
echo "4. Set Virtualenv to: $(pwd)/venv"
echo "5. Add static files: /uploads → $(pwd)/uploads"
echo "6. Click Reload"
echo ""

echo "✅ Diagnostic complete!"
