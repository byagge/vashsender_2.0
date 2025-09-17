# apps/emails/dkim_service.py

import os
import platform
import subprocess
import tempfile
import base64
from django.conf import settings
from typing import Optional, Tuple

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

class DKIMService:
    """Сервис для генерации и управления DKIM ключами"""
    
    def __init__(self):
        self.is_windows = platform.system() == 'Windows'
        self.keys_dir = getattr(settings, 'DKIM_KEYS_DIR', '/etc/opendkim/keys')
        self.selector = getattr(settings, 'DKIM_SELECTOR', 'vashsender')
        
    def can_generate_keys(self) -> bool:
        """Проверяет, можно ли генерировать DKIM ключи"""
        # Сначала пробуем OpenDKIM
        if not self.is_windows:
            try:
                result = subprocess.run(['opendkim-genkey', '--version'], 
                                      capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    return True
            except FileNotFoundError:
                pass
        
        # Если OpenDKIM недоступен, пробуем Python cryptography
        return CRYPTOGRAPHY_AVAILABLE
    
    def generate_keys_python(self, domain: str) -> Optional[Tuple[str, str]]:
        """Генерирует DKIM ключи используя Python cryptography"""
        if not CRYPTOGRAPHY_AVAILABLE:
            return None
            
        try:
            # Генерируем RSA ключ
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Получаем публичный ключ
            public_key = private_key.public_key()
            
            # Сериализуем приватный ключ в PEM формате
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')
            
            # Сериализуем публичный ключ в DER формате и кодируем в base64
            public_der = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            public_b64 = base64.b64encode(public_der).decode('utf-8')
            
            # Формируем DKIM публичный ключ
            dkim_public = f"v=DKIM1; k=rsa; p={public_b64}"
            
            return dkim_public, private_pem
            
        except Exception as e:
            print(f"Error generating DKIM keys with Python for {domain}: {e}")
            return None
    
    def generate_keys(self, domain: str) -> Optional[Tuple[str, str]]:
        """
        Генерирует DKIM ключи для домена согласно инструкции:
        - mkdir -p /etc/opendkim/keys/{domain}
        - opendkim-genkey -D /etc/opendkim/keys/{domain} --domain {domain} --selector {selector}
        - append to /etc/opendkim/KeyTable and SigningTable
        - chown opendkim:opendkim -R /etc/opendkim/keys/
        - systemctl restart opendkim
        Возвращает (public_key, private_key_path) или None при ошибке
        """
        if not self.can_generate_keys():
            print(f"DKIM key generation not available for domain: {domain}")
            return None
            
        # Сначала пробуем OpenDKIM
        if not self.is_windows:
            try:
                result = subprocess.run(['opendkim-genkey', '--version'], 
                                      capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    # Пытаемся сгенерировать напрямую в /etc/opendkim/keys/{domain}
                    generated = self.generate_keys_opendkim(domain)
                    if generated:
                        public_key, private_key_path = generated
                        # Обновляем конфиги OpenDKIM
                        self.update_opendkim_config(domain, private_key_path)
                        try:
                            subprocess.run(['chown', 'opendkim:opendkim', '-R', self.keys_dir], check=True)
                        except Exception:
                            pass
                        try:
                            subprocess.run(['systemctl', 'restart', 'opendkim'], check=True)
                        except Exception:
                            pass
                        return public_key, private_key_path
            except FileNotFoundError:
                pass
        
        # Если OpenDKIM недоступен, используем Python
        print(f"Using Python cryptography for DKIM generation for domain: {domain}")
        return self.generate_keys_python(domain)
    
    def generate_keys_opendkim(self, domain: str) -> Optional[Tuple[str, str]]:
        """Генерирует DKIM ключи используя OpenDKIM"""
        try:
            # Создаем каталог домена
            domain_dir = os.path.join(self.keys_dir, domain)
            os.makedirs(domain_dir, exist_ok=True)
            
            # Генерируем ключи
            subprocess.run([
                'opendkim-genkey',
                '-D', domain_dir,
                '--domain', domain,
                '--selector', self.selector
            ], check=True)
            
            # Пути к файлам ключей
            public_txt = os.path.join(domain_dir, f'{self.selector}.txt')
            private_path = os.path.join(domain_dir, f'{self.selector}.private')
            
            # Читаем публичный ключ из .txt (как есть)
            with open(public_txt, 'r') as f:
                public_key = f.read().strip()
            
            # Возвращаем путь к приватному ключу (используется Postfix/DKIM lib)
            return public_key, private_path
            
        except Exception as e:
            print(f"Error generating DKIM keys with OpenDKIM for {domain}: {e}")
            return None
    
    def update_opendkim_config(self, domain: str, private_key_path: str) -> bool:
        """Обновляет конфигурацию OpenDKIM"""
        if self.is_windows:
            return False
            
        try:
            keytable = f"{self.selector}._domainkey.{domain} {domain}:{self.selector}:{private_key_path}\n"
            signingtable = f"*@{domain} {self.selector}._domainkey.{domain}\n"
            trustedhosts = f"{domain}\n"
            
            # Записываем в конфигурационные файлы
            with open('/etc/opendkim/KeyTable', 'a') as f:
                f.write(keytable)
            with open('/etc/opendkim/SigningTable', 'a') as f:
                f.write(signingtable)
            with open('/etc/opendkim/TrustedHosts', 'a') as f:
                f.write(trustedhosts)
            
            # Перезапускаем сервис
            subprocess.run(['systemctl', 'restart', 'opendkim'], check=True)
            return True
            
        except Exception as e:
            print(f"Error updating OpenDKIM config: {e}")
            return False
    
    def get_dns_record(self, domain: str, public_key: str) -> str:
        """Формирует DNS TXT запись для DKIM"""
        if not public_key:
            return ""
            
        name = f"{self.selector}._domainkey.{domain}"
        
        # Очищаем ключ от лишних символов
        key_value = public_key.strip()
        
        # Для реальных ключей извлекаем значение
        if 'p=' in key_value:
            # Ищем строку, содержащую публичный ключ
            lines = key_value.split('\n')
            for line in lines:
                if 'p=' in line:
                    value = line.strip().strip('"')
                    break
            else:
                value = key_value.strip()
        else:
            value = key_value.strip()
            
        return f"{name} IN TXT \"{value}\"" 