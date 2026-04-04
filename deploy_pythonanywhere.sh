#!/bin/bash
# PythonAnywhere Deployment Script
# Run this script on PythonAnywhere Bash console after uploading the backend folder

set -e  # Exit on error

echo "🚀 Starting Club Management Backend Deployment..."

# Define paths
PROJECT_DIR="$HOME/club-management/backend"
VENV_DIR="$PROJECT_DIR/venv"

# Check if project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Error: Project directory not found at $PROJECT_DIR"
    echo "Please upload the backend folder first!"
    exit 1
fi

cd "$PROJECT_DIR"
echo "📁 Working directory: $(pwd)"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Creating virtual environment..."
    python3.10 -m venv venv
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt --quiet

# Create necessary directories
echo "📂 Creating directories..."
mkdir -p instance
mkdir -p uploads

# Initialize database
echo "🗄️  Initializing database..."
python << EOF
from app import create_app, db

app = create_app()
with app.app_context():
    db.create_all()
    print("✅ Database tables created successfully!")
EOF

echo ""
echo "✅ Deployment script completed successfully!"
echo ""
echo "📝 Next steps:"
echo "1. Go to PythonAnywhere Web tab"
echo "2. Configure WSGI file (copy contents from wsgi.py)"
echo "3. Set Virtualenv to: $VENV_DIR"
echo "4. Add static files mapping: /uploads -> $PROJECT_DIR/uploads"
echo "5. Click the green 'Reload' button"
echo "6. Test: https://clubmanagment.pythonanywhere.com/api/health"
echo ""
