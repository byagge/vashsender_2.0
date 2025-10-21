#!/usr/bin/env python
"""
Скрипт для исправления типов UUID в PostgreSQL.
Выполняет SQL команды для изменения типов полей с text на uuid.
"""

import os
import sys
import django
from django.conf import settings

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.production')
django.setup()

from django.db import connection

def fix_uuid_types():
    """
    Исправляет типы UUID в PostgreSQL.
    """
    print("=== Исправление типов UUID в PostgreSQL ===")
    
    with connection.cursor() as cursor:
        # 1. Проверяем текущие типы
        print("1. Проверяем текущие типы полей...")
        cursor.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name LIKE '%campaigns%' 
            AND column_name = 'id'
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        print("Таблицы с полем id:")
        for table_name, column_name, data_type in tables:
            print(f"  {table_name}.{column_name}: {data_type}")
        
        # 2. Исправляем campaigns_emailtracking.id
        print("\n2. Исправляем campaigns_emailtracking.id...")
        try:
            cursor.execute("""
                ALTER TABLE campaigns_emailtracking 
                ALTER COLUMN id TYPE uuid USING id::uuid;
            """)
            print("✓ campaigns_emailtracking.id исправлен на UUID")
        except Exception as e:
            print(f"✗ Ошибка при исправлении campaigns_emailtracking.id: {e}")
        
        # 3. Проверяем campaigns_campaign.id
        print("\n3. Проверяем campaigns_campaign.id...")
        cursor.execute("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'campaigns_campaign' 
            AND column_name = 'id';
        """)
        
        result = cursor.fetchone()
        if result:
            data_type = result[0]
            print(f"campaigns_campaign.id тип: {data_type}")
            
            if data_type != 'uuid':
                try:
                    cursor.execute("""
                        ALTER TABLE campaigns_campaign 
                        ALTER COLUMN id TYPE uuid USING id::uuid;
                    """)
                    print("✓ campaigns_campaign.id исправлен на UUID")
                except Exception as e:
                    print(f"✗ Ошибка при исправлении campaigns_campaign.id: {e}")
        
        # 4. Проверяем другие таблицы
        print("\n4. Проверяем другие таблицы...")
        cursor.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE data_type IN ('text', 'character varying') 
            AND column_name = 'id' 
            AND table_name LIKE '%campaigns%';
        """)
        
        other_tables = cursor.fetchall()
        if other_tables:
            print("Другие таблицы с text id:")
            for table_name, column_name, data_type in other_tables:
                print(f"  {table_name}.{column_name}: {data_type}")
                
                try:
                    cursor.execute(f"""
                        ALTER TABLE {table_name} 
                        ALTER COLUMN {column_name} TYPE uuid USING {column_name}::uuid;
                    """)
                    print(f"✓ {table_name}.{column_name} исправлен на UUID")
                except Exception as e:
                    print(f"✗ Ошибка при исправлении {table_name}.{column_name}: {e}")
        
        # 5. Финальная проверка
        print("\n5. Финальная проверка...")
        cursor.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name LIKE '%campaigns%' 
            AND column_name = 'id'
            ORDER BY table_name;
        """)
        
        final_tables = cursor.fetchall()
        print("Итоговые типы полей:")
        for table_name, column_name, data_type in final_tables:
            print(f"  {table_name}.{column_name}: {data_type}")
        
        print("\n=== Исправление завершено ===")

if __name__ == '__main__':
    fix_uuid_types()
