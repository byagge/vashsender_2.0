#!/bin/bash
# БЫСТРОЕ ПРИМЕНЕНИЕ ИСПРАВЛЕНИЙ ДЛЯ GMAIL И MAIL.RU

echo "🔧 ПРИМЕНЕНИЕ ИСПРАВЛЕНИЙ ДЛЯ GMAIL И MAIL.RU"
echo "Время: $(date)"
echo ""

# Проверяем права
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт с правами sudo"
    exit 1
fi

echo "📋 Шаг 1: Остановка сервисов..."
systemctl stop celery
systemctl stop celerybeat

echo "📋 Шаг 2: Очистка очередей Redis..."
redis-cli FLUSHALL

echo "📋 Шаг 3: Настройка Postfix для отключения IPv6..."

# Создаем резервную копию конфигурации Postfix
cp /etc/postfix/main.cf /etc/postfix/main.cf.backup.$(date +%Y%m%d_%H%M%S)

# Добавляем настройки для отключения IPv6
cat >> /etc/postfix/main.cf << EOF

# Отключение IPv6 для исправления проблем с Gmail
inet_protocols = ipv4
smtp_address_preference = ipv4
smtp_host_lookup = dns, native
disable_dns_lookups = no

# Настройки для улучшения доставляемости
smtp_helo_name = mail.vashsender.ru
smtpd_helo_required = yes
smtpd_helo_restrictions = permit_mynetworks, reject_invalid_helo_hostname, reject_non_fqdn_helo_hostname

# Настройки для аутентификации
smtpd_sasl_auth_enable = yes
smtpd_sasl_security_options = noanonymous
smtpd_sasl_local_domain = \$myhostname

# Настройки для TLS
smtpd_tls_security_level = may
smtpd_tls_auth_only = no
smtpd_tls_received_header = yes
EOF

echo "📋 Шаг 4: Перезапуск Postfix..."
systemctl restart postfix

echo "📋 Шаг 5: Проверка статуса Postfix..."
systemctl status postfix --no-pager -l

echo "📋 Шаг 6: Запуск сервисов..."
systemctl start celery
systemctl start celerybeat
systemctl restart gunicorn

echo "📋 Шаг 7: Проверка статуса сервисов..."
echo "Postfix:"
systemctl is-active postfix
echo "Celery:"
systemctl is-active celery
echo "Gunicorn:"
systemctl is-active gunicorn

echo ""
echo "✅ ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ!"
echo ""
echo "📋 СЛЕДУЮЩИЕ ШАГИ:"
echo "1. Настройте DNS записи (см. GMAIL_MAILRU_FIXES.md)"
echo "2. Добавьте PTR запись для IP 146.185.196.123"
echo "3. Протестируйте отправку писем"
echo "4. Проверьте логи: sudo tail -f /var/log/mail.log"
echo ""
echo "📊 Проверка DNS записей:"
echo "dig -x 146.185.196.123"
echo "dig TXT vashsender.ru"
echo "dig TXT _dmarc.vashsender.ru"
echo ""
echo "🧪 Тестирование:"
echo "python manage.py shell -c \"from django.core.mail import send_mail; send_mail('Test', 'Test message', 'noreply@vashsender.ru', ['test@gmail.com'])\""
echo ""
echo "📝 Логи:"
echo "sudo tail -f /var/log/mail.log"
echo "sudo tail -f /var/log/celery.log" 