#!/bin/bash
echo "🚀 Building project for Vercel..."

# Install dependencies
echo "📦 Installing dependencies..."
python3 -m pip install -r requirements.txt

# Collect static files
echo "📁 Collecting static files..."
python3 manage.py collectstatic --noinput --clear

# Run migrations
echo "🗄️ Running migrations..."
python3 manage.py makemigrations
python3 manage.py migrate

# Create superuser
echo "👤 Creating superuser..."
python3 -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = 'admin'
email = 'admin@research.com'
password = 'Admin123!'
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print('✅ Superuser created successfully!')
else:
    print('ℹ️ Superuser already exists.')
"

echo "✅ Build completed successfully!"