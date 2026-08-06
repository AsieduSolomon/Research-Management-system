import os
import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-your-secret-key-here-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '.vercel.app']
if os.environ.get('VERCEL_URL'):
    ALLOWED_HOSTS.append(os.environ.get('VERCEL_URL'))

X_FRAME_OPTIONS = 'SAMEORIGIN'

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'research',
    'whitenoise',
    'crispy_forms',
    'crispy_bootstrap5',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'research.context_processors.notification_count',
                'research.context_processors.user_role',
            ],
        },
    },
]

# Django Jazzmin Configuration
JAZZMIN_SETTINGS = {
    "site_title": "STU Research Portal Admin",
    "site_header": "STU Research",
    "site_brand": "STU Research Portal",
    "welcome_sign": "Welcome to STU Research Portal Admin",
    "copyright": "Sunyani Technical University",
    "show_sidebar": True,
    "navigation_expanded": False,
    "default_theme_mode": "light",
    "show_theme_chooser": True,
    "use_google_fonts_cdn": True,
    "show_language_chooser": False,
    "show_ui_builder": True,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
    },
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.group": "fas fa-users",
        "research.User": "fas fa-user-graduate",
        "research.SupervisorProfile": "fas fa-chalkboard-user",
        "research.Proposal": "fas fa-file-alt",
        "research.Allocation": "fas fa-link",
        "research.ProgressReport": "fas fa-chart-line",
        "research.Meeting": "fas fa-calendar-alt",
        "research.Milestone": "fas fa-flag-checkered",
        "research.Notification": "fas fa-bell",
        "research.AuditLog": "fas fa-history",
    },
    "order_with_respect_to": [
        "auth",
        "research",
        "research.User",
        "research.SupervisorProfile",
        "research.Proposal",
        "research.Allocation",
        "research.ProgressReport",
        "research.Meeting",
        "research.Milestone",
        "research.Notification",
        "research.AuditLog",
    ],
    "custom_links": {
        "research": [{
            "name": "Custom Reports",
            "url": "admin_reports",
            "icon": "fas fa-chart-bar",
            "permissions": ["research.view_proposal"]
        }]
    },
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "Support", "url": "https://github.com/farridav/django-jazzmin/issues", "new_window": True},
        {"model": "auth.User"},
    ],
    "usermenu_links": [
        {"name": "Support", "url": "https://github.com/farridav/django-jazzmin/issues", "new_window": True},
        {"model": "auth.user"}
    ],
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small": False,
    "footer_small": False,
    "body_small": False,
    "brand_small": False,
    "navbar_fixed": True,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar_nav_small": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_flat_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "btn_round": True,
    "actions_sticky_top": False,
    "main_bg_color": "#F0F4F8",
    "brand_colour": "#1B4F72",
    "brand_colour_hover": "#0D3B5E",
    "navbar_colour": "#1B4F72",
    "navbar_accent_colour": "#2980B9",
    "sidebar_colour": "#1A252F",
    "sidebar_accent_colour": "#E67E22",
    "sidebar_nav_active_colour": "#E67E22",
    "dark_mode_visually_toggle": True,
    "related_modal_active": True,
    "theme": "flatly",
}

WSGI_APPLICATION = 'project.wsgi.application'
ASGI_APPLICATION = 'project.asgi.application'

# DATABASE CONFIGURATION - PostgreSQL for Production, SQLite for Development
if os.environ.get('DATABASE_URL'):
    # Production database (PostgreSQL on Vercel)
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=0,  # no persistent connections: required for Supabase's PgBouncer pooler + serverless
            ssl_require=True
        )
    }
else:
    # Development database (SQLite)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Channels Configuration (WebSockets)
if os.environ.get('REDIS_URL'):
    # Production Redis
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                "hosts": [os.environ.get('REDIS_URL')],
            },
        },
    }
else:
    # Development in-memory
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Accra'
USE_I18N = True
USE_TZ = True

# Static files configuration
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files - For demonstration, files are stored locally
# Note: This will work on Vercel but files will be lost on redeployment
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'research.User'

# Security settings for production
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True