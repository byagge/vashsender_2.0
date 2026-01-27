from .base import *
import os

# SECURITY WARNING: don't run with debug turned on in production!
SECRET_KEY = 'django-insecure-change-this-in-production'
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'vashsender.ru', 'regvshsndr.ru', 'www.vashsender.ru', 'www.regvshsndr.ru', '146.185.196.52']

# Надёжные источники для CSRF-проверки
CSRF_TRUSTED_ORIGINS = [
    'https://vashsender.ru',
    'https://www.vashsender.ru',
    'https://regvshsndr.ru',
    'https://www.regvshsndr.ru',
    'https://api.regvshsndr.ru',
    'https://admin.regvshsndr.ru',
]

# Безопасные куки (рекомендуется при HTTPS)
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

try:
    from .local import *
except ImportError:
    pass