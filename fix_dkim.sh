#!/bin/bash

# Скрипт для исправления DKIM подписи
# Запускать из виртуального окружения: source venv/bin/activate && ./fix_dkim.sh

echo "🔧 Исправление DKIM подписи для VashSender"
echo "================================================"

# Проверяем, что мы в виртуальном окружении
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "❌ Виртуальное окружение не активировано"
    echo "Запустите: source venv/bin/activate"
    exit 1
fi

echo "✅ Виртуальное окружение активировано: $VIRTUAL_ENV"

# Проверяем настройки Django
echo ""
echo "📋 Проверка настроек Django..."
python3 check_django_settings.py

# Исправляем DKIM
echo ""
echo "📋 Исправление DKIM..."
python3 fix_dkim_signing.py

echo ""
echo "🎉 Готово! Теперь отправьте тестовую кампанию и проверьте заголовки письма."
