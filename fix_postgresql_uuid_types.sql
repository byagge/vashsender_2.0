-- Исправление типов UUID в PostgreSQL для VashSender

-- 1. Исправляем campaigns_emailtracking.id
-- Проверяем текущий тип
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'campaigns_emailtracking' 
AND column_name = 'id';

-- Меняем тип с text на uuid (если значения валидные UUID)
ALTER TABLE campaigns_emailtracking 
ALTER COLUMN id TYPE uuid USING id::uuid;

-- 2. Проверяем campaigns_campaign.id
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'campaigns_campaign' 
AND column_name = 'id';

-- Если нужно, исправляем и его
-- ALTER TABLE campaigns_campaign 
-- ALTER COLUMN id TYPE uuid USING id::uuid;

-- 3. Проверяем другие таблицы с UUID полями
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE data_type IN ('text', 'character varying') 
AND column_name = 'id' 
AND table_name LIKE '%campaigns%';

-- 4. Проверяем внешние ключи
SELECT 
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
      AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
AND (tc.table_name LIKE '%campaigns%' OR ccu.table_name LIKE '%campaigns%');
