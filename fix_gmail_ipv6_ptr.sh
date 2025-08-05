#!/bin/bash
# ИСПРАВЛЕНИЕ ПРОБЛЕМЫ GMAIL IPv6 PTR

echo "🔧 ИСПРАВЛЕНИЕ ПРОБЛЕМЫ GMAIL IPv6 PTR"
echo "Время: $(date)"
echo ""

# Проверяем права
if [ "$EUID" -ne 0 ]; then
    echo "❌ Запустите скрипт с правами sudo"
    exit 1
fi

echo "📋 Шаг 1: Проверка текущих настроек Postfix..."

# Проверяем текущую конфигурацию
if grep -q "inet_protocols" /etc/postfix/main.cf; then
    echo "✅ inet_protocols уже настроен"
    grep "inet_protocols" /etc/postfix/main.cf
else
    echo "❌ inet_protocols не настроен"
fi

echo ""
echo "📋 Шаг 2: Создание резервной копии..."
cp /etc/postfix/main.cf /etc/postfix/main.cf.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Резервная копия создана"

echo ""
echo "📋 Шаг 3: Настройка Postfix для отключения IPv6..."

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

echo "✅ Настройки добавлены в /etc/postfix/main.cf"

echo ""
echo "📋 Шаг 4: Перезапуск Postfix..."
systemctl restart postfix

echo ""
echo "📋 Шаг 5: Проверка статуса Postfix..."
systemctl status postfix --no-pager -l

echo ""
echo "📋 Шаг 6: Проверка конфигурации..."
postconf -n | grep -E "(inet_protocols|smtp_address_preference)"

echo ""
echo "📋 Шаг 7: Проверка IPv6 адресов..."
echo "IPv6 адреса сервера:"
ip -6 addr show | grep inet6 || echo "IPv6 адреса не найдены"

echo ""
echo "📋 Шаг 8: Проверка PTR записи..."
echo "PTR запись для текущего IP:"
dig -x $(curl -s ifconfig.me) +short || echo "PTR запись не найдена"

echo ""
echo "✅ ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ!"
echo ""
echo "📋 СЛЕДУЮЩИЕ ШАГИ:"
echo "1. Добавьте PTR запись в DNS провайдере:"
echo "   $(curl -s ifconfig.me).in-addr.arpa. IN PTR mail.vashsender.ru."
echo ""
echo "2. Проверьте DNS записи:"
echo "   dig -x $(curl -s ifconfig.me)"
echo "   dig TXT vashsender.ru"
echo ""
echo "3. Протестируйте отправку:"
echo "   python manage.py shell -c \"from django.core.mail import send_mail; send_mail('Test Gmail', 'Test message', 'noreply@vashsender.ru', ['test@gmail.com'])\""
echo ""
echo "4. Проверьте логи:"
echo "   sudo tail -f /var/log/mail.log"
echo ""
echo "⚠️  ВАЖНО: PTR запись должна быть добавлена в DNS провайдере!" 