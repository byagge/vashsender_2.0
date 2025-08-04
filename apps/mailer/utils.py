import re
import dns.resolver
import requests
import socket
from .models import Contact

# Более строгое регулярное выражение для email
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$')

# Дополнительные проверки
MAX_EMAIL_LENGTH = 254  # RFC 5321
MAX_LOCAL_LENGTH = 64   # RFC 5321
MAX_DOMAIN_LENGTH = 253 # RFC 5321

# Кэш для загруженных disposable-доменов
DISPOSABLE_DOMAINS = None

# Кэш для DNS запросов
DNS_CACHE = {}

# Список зарезервированных доменов верхнего уровня
RESERVED_TLDS = {
    'test', 'example', 'invalid', 'localhost', 'local', 'internal', 'intranet',
    'private', 'corp', 'home', 'lan', 'workgroup', 'dev', 'development'
}

# Список зарезервированных доменов второго уровня
RESERVED_SLDS = {
    'example.com', 'example.org', 'example.net', 'test.com', 'test.org',
    'invalid.com', 'localhost.com', 'dummy.com', 'fake.com', 'spam.com'
}

# Важные домены для SMTP проверки
IMPORTANT_DOMAINS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'yandex.ru', 'mail.ru', 'rambler.ru', 'bk.ru',
    'icloud.com', 'protonmail.com', 'zoho.com', 'aol.com',
    'live.com', 'msn.com', 'me.com', 'mac.com'
}

def load_disposable_domains():
    """
    Загружает список disposable-доменов только один раз при первом вызове.
    """
    global DISPOSABLE_DOMAINS
    if DISPOSABLE_DOMAINS is not None:
        return DISPOSABLE_DOMAINS

    # Базовый список известных disposable доменов на случай, если не удастся загрузить
    basic_disposable = {
        '10minutemail.com', 'guerrillamail.com', 'mailinator.com', 'tempmail.org',
        'yopmail.com', 'throwaway.email', 'temp-mail.org', 'sharklasers.com',
        'getairmail.com', 'mailnesia.com', 'maildrop.cc', 'mailcatch.com'
    }
    
    url = "https://raw.githubusercontent.com/disposable/disposable-email-domains/master/domains.txt"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            DISPOSABLE_DOMAINS = set(
                line.strip().lower()
                for line in response.text.splitlines()
                if line.strip() and not line.startswith('#')
            )
        else:
            DISPOSABLE_DOMAINS = basic_disposable
    except Exception as e:
        DISPOSABLE_DOMAINS = basic_disposable

    return DISPOSABLE_DOMAINS

def parse_emails(file_stream, filename=None):
    raw = file_stream.read()
    try:
        text = raw.decode('utf-8', errors='ignore')
    except AttributeError:
        text = raw if isinstance(raw, str) else raw.decode('utf-8', errors='ignore')
    
    emails = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            # Убираем лишние символы и приводим к нижнему регистру
            email = line.lower().strip('.,;:!?()[]{}"\'').strip()
            if email:
                emails.append(email)
    
    return emails

def is_syntax_valid(email: str) -> bool:
    """
    Строгая проверка синтаксиса email согласно RFC 5321/5322
    """
    if not email or not isinstance(email, str):
        return False
    
    # Проверка длины
    if len(email) > MAX_EMAIL_LENGTH:
        return False
    
    # Проверка регулярным выражением
    if not EMAIL_REGEX.match(email):
        return False
    
    # Разбор на части
    try:
        local_part, domain = email.split('@', 1)
    except ValueError:
        return False
    
    # Проверка длины частей
    if len(local_part) > MAX_LOCAL_LENGTH or len(domain) > MAX_DOMAIN_LENGTH:
        return False
    
    # Проверка локальной части
    if not local_part or local_part.startswith('.') or local_part.endswith('.'):
        return False
    
    # Проверка домена
    if not domain or domain.startswith('.') or domain.endswith('.'):
        return False
    
    # Проверка на двойные точки
    if '..' in local_part or '..' in domain:
        return False
    
    # Проверка на недопустимые символы в домене
    if not re.match(r'^[a-zA-Z0-9.-]+$', domain):
        return False
    
    return True

def has_mx_record(domain: str) -> bool:
    """
    Проверка наличия MX-записей с таймаутом и кэшированием
    """
    # Проверяем кэш
    if domain in DNS_CACHE:
        return DNS_CACHE[domain]
    
    try:
        # Устанавливаем таймаут для DNS-запросов
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3  # Уменьшаем таймаут для ускорения
        resolver.lifetime = 5
        
        answers = resolver.resolve(domain, 'MX')
        result = len(answers) > 0
        DNS_CACHE[domain] = result
        return result
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout, Exception) as e:
        DNS_CACHE[domain] = False
        return False

def has_a_record(domain: str) -> bool:
    """
    Проверка наличия A-записей (IP адресов)
    """
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 10
        
        answers = resolver.resolve(domain, 'A')
        return len(answers) > 0
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout, Exception):
        return False

def is_reserved_domain(domain: str) -> bool:
    """
    Проверка на зарезервированные домены
    """
    domain_lower = domain.lower()
    
    # Проверка TLD
    tld = domain_lower.split('.')[-1]
    if tld in RESERVED_TLDS:
        return True
    
    # Проверка SLD
    if domain_lower in RESERVED_SLDS:
        return True
    
    # Проверка на IP-адреса
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', domain):
        return True
    
    return False

def is_disposable_domain(domain: str) -> bool:
    """
    Проверка на disposable домены
    """
    try:
        disposable_domains = load_disposable_domains()
        result = domain.lower() in disposable_domains
        return result
    except Exception as e:
        return False

def is_important_domain(domain: str) -> bool:
    """
    Проверка, является ли домен важным для SMTP проверки
    """
    return domain.lower() in IMPORTANT_DOMAINS

def check_smtp_connection(email: str) -> dict:
    """
    Глубокая SMTP проверка существования email адреса
    """
    try:
        domain = email.split('@', 1)[1]
        
        # Получаем MX записи
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3
        resolver.lifetime = 5
        mx_records = resolver.resolve(domain, 'MX')
        mx_host = str(sorted(mx_records, key=lambda x: x.preference)[0].exchange)
        
        # Подключаемся к SMTP серверу
        with socket.create_connection((mx_host, 25), timeout=5) as sock:
            sock.settimeout(10)  # Увеличиваем таймаут для чтения
            
            # Читаем приветствие сервера
            response = sock.recv(1024).decode('utf-8', errors='ignore')
            if not response.startswith('220'):
                return {'valid': False, 'error': 'SMTP сервер недоступен'}
            
            # Отправляем EHLO (более современный протокол)
            sock.send(b'EHLO test.com\r\n')
            response = sock.recv(1024).decode('utf-8', errors='ignore')
            
            if not response.startswith('250'):
                # Пробуем HELO если EHLO не поддерживается
                sock.send(b'HELO test.com\r\n')
                response = sock.recv(1024).decode('utf-8', errors='ignore')
                if not response.startswith('250'):
                    return {'valid': False, 'error': 'SMTP сервер недоступен'}
            
            # Проверяем MAIL FROM
            sock.send(b'MAIL FROM:<test@test.com>\r\n')
            response = sock.recv(1024).decode('utf-8', errors='ignore')
            
            if not response.startswith('250'):
                return {'valid': False, 'error': 'SMTP сервер отклоняет отправителей'}
            
            # Проверяем RCPT TO - это ключевая проверка существования email
            sock.send(f'RCPT TO:<{email}>\r\n'.encode())
            response = sock.recv(1024).decode('utf-8', errors='ignore')
            
            # Анализируем ответ сервера
            if response.startswith('250'):
                return {'valid': True, 'error': None}
            elif response.startswith('550'):
                # 550 - пользователь не существует
                return {'valid': False, 'error': 'Email адрес не существует'}
            elif response.startswith('553'):
                # 553 - недопустимый адрес получателя
                return {'valid': False, 'error': 'Email адрес недопустим'}
            elif response.startswith('554'):
                # 554 - транзакция не удалась
                return {'valid': False, 'error': 'Email адрес отклонен сервером'}
            elif response.startswith('421'):
                # 421 - сервер недоступен
                return {'valid': False, 'error': 'SMTP сервер временно недоступен'}
            elif response.startswith('450'):
                # 450 - временная ошибка
                return {'valid': False, 'error': 'Временная ошибка SMTP сервера'}
            elif response.startswith('452'):
                # 452 - недостаточно места
                return {'valid': False, 'error': 'SMTP сервер перегружен'}
            else:
                # Неизвестный ответ - считаем валидным для безопасности
                return {'valid': True, 'error': None, 'warning': f'Неизвестный ответ SMTP: {response[:100]}'}
                
    except dns.resolver.NXDOMAIN:
        return {'valid': False, 'error': 'Домен не существует'}
    except dns.resolver.NoAnswer:
        return {'valid': False, 'error': 'Домен не имеет MX записей'}
    except dns.resolver.Timeout:
        return {'valid': False, 'error': 'Таймаут DNS запроса'}
    except socket.timeout:
        return {'valid': False, 'error': 'Таймаут подключения к SMTP серверу'}
    except ConnectionRefusedError:
        return {'valid': False, 'error': 'SMTP сервер отказал в подключении'}
    except Exception as e:
        return {'valid': False, 'error': f'Ошибка SMTP проверки: {str(e)}'}

def validate_email_production(email: str) -> dict:
    """
    Продакшен-валидация: быстрая + точная с проверкой существования email
    """
    result = {
        'email': email,
        'is_valid': False,
        'status': Contact.INVALID,
        'confidence': 'low',
        'errors': [],
        'warnings': []
    }
    
    # УРОВЕНЬ 1: Быстрые проверки (0.1 сек)
    if not is_syntax_valid(email):
        result['errors'].append('Неверный синтаксис email адреса')
        return result
    
    try:
        domain = email.split('@', 1)[1].lower()
    except (ValueError, IndexError):
        result['errors'].append('Не удалось извлечь домен')
        return result
    
    if is_reserved_domain(domain):
        result['errors'].append('Зарезервированный домен')
        return result
    
    if is_disposable_domain(domain):
        result['status'] = Contact.BLACKLIST
        result['confidence'] = 'high'
        result['warnings'].append('Временный email домен')
        return result
    
    # УРОВЕНЬ 2: DNS проверки (0.5 сек) - с обработкой ошибок
    try:
        if not has_mx_record(domain):
            result['errors'].append('Домен не имеет MX записей (не может принимать почту)')
            return result
    except Exception as e:
        result['errors'].append(f'Ошибка проверки DNS: {str(e)}')
        return result
    
    # УРОВЕНЬ 3: SMTP проверка существования email (2-5 сек)
    # Проверяем ВСЕ домены, а не только важные
    try:
        smtp_result = check_smtp_connection(email)
        if not smtp_result['valid']:
            result['errors'].append(smtp_result['error'])
            return result
        result['confidence'] = 'very_high'
    except Exception as e:
        # Если SMTP проверка не удалась, считаем email валидным на основе DNS
        result['warnings'].append(f'SMTP проверка пропущена: {str(e)}')
        result['confidence'] = 'medium'
    
    result['is_valid'] = True
    result['status'] = Contact.VALID
    return result

def classify_email(email: str) -> str:
    """
    Глубокая классификация email адресов с проверкой существования:
    1) Синтаксис → INVALID
    2) Зарезервированные домены → INVALID  
    3) Временные/дроп-домены → BLACKLIST
    4) Нет MX записей → INVALID (MX обязательны для email)
    5) SMTP проверка существования → VALID/INVALID
    """
    # 1. Синтаксическая проверка
    if not is_syntax_valid(email):
        return Contact.INVALID
    
    # 2. Извлечение домена
    try:
        domain = email.split('@', 1)[1].lower()
    except (ValueError, IndexError):
        return Contact.INVALID
    
    # 3. Проверка на зарезервированные домены
    if is_reserved_domain(domain):
        return Contact.INVALID
    
    # 4. Проверка на disposable домены
    if is_disposable_domain(domain):
        return Contact.BLACKLIST
    
    # 5. Проверка MX записей (обязательны для email)
    if not has_mx_record(domain):
        return Contact.INVALID
    
    # 6. SMTP проверка существования email
    try:
        smtp_result = check_smtp_connection(email)
        if smtp_result['valid']:
            return Contact.VALID
        else:
            return Contact.INVALID
    except Exception:
        # Если SMTP проверка не удалась, считаем валидным на основе DNS
        return Contact.VALID

def validate_email_strict(email: str) -> dict:
    """
    Расширенная валидация с детальной информацией
    """
    result = {
        'email': email,
        'is_valid': False,
        'status': Contact.INVALID,
        'errors': [],
        'warnings': []
    }
    
    # Синтаксическая проверка
    if not is_syntax_valid(email):
        result['errors'].append('Неверный синтаксис email адреса')
        return result
    
    try:
        domain = email.split('@', 1)[1].lower()
    except (ValueError, IndexError):
        result['errors'].append('Не удалось извлечь домен')
        return result
    
    # Проверка зарезервированных доменов
    if is_reserved_domain(domain):
        result['errors'].append('Зарезервированный домен')
        return result
    
    # Проверка disposable доменов
    if is_disposable_domain(domain):
        result['status'] = Contact.BLACKLIST
        result['warnings'].append('Временный email домен')
        return result
    
    # Проверка MX записей (обязательны для email)
    if not has_mx_record(domain):
        result['errors'].append('Домен не имеет MX записей (не может принимать почту)')
        return result
    
    # Дополнительная проверка A записей (для информации)
    if not has_a_record(domain):
        result['warnings'].append('Домен не имеет A записей (IP адресов)')
    
    result['is_valid'] = True
    result['status'] = Contact.VALID
    return result

def validate_email_fast(email: str) -> dict:
    """
    Быстрая валидация email для импорта - только базовые проверки без DNS для большинства доменов
    """
    if not email or not isinstance(email, str):
        return {'is_valid': False, 'status': Contact.INVALID, 'reason': 'Empty or invalid input'}
    
    email = email.lower().strip()
    
    # Базовая проверка синтаксиса
    if not is_syntax_valid(email):
        return {'is_valid': False, 'status': Contact.INVALID, 'reason': 'Invalid syntax'}
    
    try:
        local_part, domain = email.split('@', 1)
    except ValueError:
        return {'is_valid': False, 'status': Contact.INVALID, 'reason': 'Invalid format'}
    
    # Проверка зарезервированных доменов
    if is_reserved_domain(domain):
        return {'is_valid': False, 'status': Contact.INVALID, 'reason': 'Reserved domain'}
    
    # Проверка disposable доменов
    if is_disposable_domain(domain):
        return {'is_valid': False, 'status': Contact.BLACKLIST, 'reason': 'Disposable domain'}
    
    # Проверяем только важные домены (основные почтовые провайдеры)
    if domain in IMPORTANT_DOMAINS:
        # Для важных доменов делаем быструю проверку MX
        if not has_mx_record(domain):
            return {'is_valid': False, 'status': Contact.INVALID, 'reason': 'No MX record'}
    else:
        # Для остальных доменов просто проверяем базовую структуру
        # и считаем валидными (DNS проверка будет позже при отправке)
        if len(domain) < 3 or '.' not in domain:
            return {'is_valid': False, 'status': Contact.INVALID, 'reason': 'Invalid domain structure'}
    
    return {'is_valid': True, 'status': Contact.VALID, 'reason': 'Valid email'}
