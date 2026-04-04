#!/bin/bash
# Quick setup script for GitHub deployment
# Run this on PythonAnywhere after cloning the repository

set -e  # Exit on error

echo "🚀 Setting up Club Management Backend on PythonAnywhere..."
echo ""

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Make sure you're in the backend directory!"
    exit 1
fi

echo "📁 Current directory: $(pwd)"
echo ""

# Create virtual environment
echo "🐍 Creating virtual environment..."
python3.10 -m venv venv
echo "✅ Virtual environment created"
echo ""

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet
echo "✅ Pip upgraded"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Create directories
echo "📂 Creating directories..."
mkdir -p instance
mkdir -p uploads
chmod 755 instance
chmod 755 uploads
echo "✅ Directories created"
echo ""

# Initialize database
echo "🗄️  Initializing database..."
python << 'PYTHON_SCRIPT'
from app import create_app, db

app = create_app()
with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully!")
PYTHON_SCRIPT
echo ""

echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Go to PythonAnywhere Web tab"
echo "2. Create new web app (Manual configuration, Python 3.10)"
echo "3. Configure WSGI file (copy from wsgi.py)"
echo "4. Set Virtualenv: $(pwd)/venv"
echo "5. Add static files: /uploads -> $(pwd)/uploads"
echo "6. Click Reload"
echo "7. Test: https://clubmanagment.pythonanywhere.com/api/health"
echo ""
echo "🎉 Ready to deploy!"
