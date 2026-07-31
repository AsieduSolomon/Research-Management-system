#!/bin/bash
echo "🚀 Building project for Vercel..."

# Install dependencies
echo "📦 Installing dependencies..."
python3 -m pip install -r requirements.txt

# Collect static files
echo "📁 Collecting static files..."
python3 manage.py collectstatic --noinput --clear

# Run migrations (creates SQLite database)
echo "🗄️ Running migrations..."
python3 manage.py makemigrations
python3 manage.py migrate

# Create superuser if needed (optional - for demo)
echo "👤 Creating superuser..."
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'admin123') if not User.objects.filter(username='admin').exists() else None" | python3 manage.py shell

echo "✅ Build completed successfully!"