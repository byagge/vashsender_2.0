#!/usr/bin/env python3
"""
Скрипт для постепенного увеличения объема рассылок
Помогает избежать попадания в спам при массовых рассылках
"""

import os
import sys
import django
from datetime import datetime, timedelta

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.mailer.models import Contact

def get_optimal_settings(volume):
    """Получение оптимальных настроек для объема"""
    
    if volume <= 100:
        return {
            'batch_size': 10,
            'rate_limit': 2,
            'retry_delay': 60,
            'description': 'Малые рассылки (до 100 писем)'
        }
    elif volume <= 500:
        return {
            'batch_size': 20,
            'rate_limit': 5,
            'retry_delay': 120,
            'description': 'Средние рассылки (100-500 писем)'
        }
    elif volume <= 1000:
        return {
            'batch_size': 30,
            'rate_limit': 8,
            'retry_delay': 180,
            'description': 'Большие рассылки (500-1000 писем)'
        }
    elif volume <= 5000:
        return {
            'batch_size': 50,
            'rate_limit': 10,
            'retry_delay': 300,
            'description': 'Очень большие рассылки (1000-5000 писем)'
        }
    else:
        return {
            'batch_size': 100,
            'rate_limit': 15,
            'retry_delay': 600,
            'description': 'Массовые рассылки (5000+ писем)'
        }

def calculate_send_time(volume, settings):
    """Расчет времени отправки"""
    batches = (volume + settings['batch_size'] - 1) // settings['batch_size']
    time_per_batch = settings['batch_size'] / settings['rate_limit']
    total_time = batches * time_per_batch
    return total_time

def get_recommendations(volume, settings):
    """Получение рекомендаций для объема"""
    recommendations = []
    
    if volume > 5000:
        recommendations.extend([
            "Разделите рассылку на несколько частей по 1000-2000 писем",
            "Отправляйте части с интервалом 2-4 часа",
            "Используйте внешний SMTP (Yandex, Gmail, SendGrid)",
            "Мониторьте статистику доставляемости в реальном времени"
        ])
    elif volume > 1000:
        recommendations.extend([
            "Отправляйте в нерабочее время (ночь, выходные)",
            "Разделите на 2-3 части",
            "Используйте внешний SMTP",
            "Проверьте качество списка контактов"
        ])
    elif volume > 500:
        recommendations.extend([
            "Отправляйте в нерабочеe время",
            "Мониторьте статистику доставляемости",
            "Используйте качественные шаблоны писем",
            "Добавьте ссылку для отписки"
        ])
    else:
        recommendations.extend([
            "Настройки подходят для текущего объема",
            "Мониторьте статистику доставляемости",
            "Используйте качественные шаблоны писем"
        ])
    
    return recommendations

def main():
    print("📊 Калькулятор объема рассылок")
    print("=" * 50)
    
    while True:
        try:
            volume = int(input("\nВведите количество писем для рассылки: "))
            if volume > 0:
                break
            else:
                print("❌ Количество должно быть больше 0")
        except ValueError:
            print("❌ Введите корректное число")
    
    settings = get_optimal_settings(volume)
    send_time = calculate_send_time(volume, settings)
    
    print(f"\n📈 Рекомендуемые настройки для {volume} писем:")
    print(f"   Категория: {settings['description']}")
    print(f"   EMAIL_BATCH_SIZE: {settings['batch_size']}")
    print(f"   EMAIL_RATE_LIMIT: {settings['rate_limit']}")
    print(f"   EMAIL_RETRY_DELAY: {settings['retry_delay']}")
    
    print(f"\n⏱️  Примерное время отправки: {send_time:.1f} секунд ({send_time/60:.1f} минут)")
    
    # Рекомендации
    recommendations = get_recommendations(volume, settings)
    print(f"\n💡 Рекомендации:")
    for i, rec in enumerate(recommendations, 1):
        print(f"   {i}. {rec}")
    
    # Создание конфигурационного файла
    config_content = f"""# КОНФИГУРАЦИЯ ДЛЯ РАССЫЛКИ {volume} ПИСЕМ
# Скопируйте эти настройки в файл .env

# Оптимизированные настройки для {volume} писем
EMAIL_BATCH_SIZE={settings['batch_size']}
EMAIL_RATE_LIMIT={settings['rate_limit']}
EMAIL_RETRY_DELAY={settings['retry_delay']}

# Время отправки: {send_time:.1f} секунд ({send_time/60:.1f} минут)
# Категория: {settings['description']}
"""
    
    try:
        with open(f'config_{volume}_emails.txt', 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        print(f"\n✅ Конфигурация сохранена в config_{volume}_emails.txt")
        
    except Exception as e:
        print(f"❌ Ошибка сохранения конфигурации: {e}")

if __name__ == "__main__":
    main() 