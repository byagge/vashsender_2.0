# apps/emails/dkim_service.py

import os
import platform
import subprocess
import shutil
from django.conf import settings
from typing import Optional, Tuple

class DKIMService:
    """Сервис для генерации и управления DKIM ключами с использованием реальных OpenDKIM ключей"""
    
    def __init__(self):
        self.is_windows = platform.system() == 'Windows'
        self.keys_dir = getattr(settings, 'DKIM_KEYS_DIR', '/etc/opendkim/keys')
        self.selector = getattr(settings, 'DKIM_SELECTOR', 'vashsender')
        self.helper_path = getattr(settings, 'DKIM_HELPER_PATH', '/usr/local/bin/provision_dkim.sh')
        # Resolve sudo path dynamically (systemd may have restricted PATH)
        self.sudo_path = shutil.which('sudo') or '/usr/bin/sudo'
    
    def _domain_dir(self, domain: str) -> str:
        return os.path.join(self.keys_dir, domain)
    
    def _public_txt_path(self, domain: str) -> str:
        return os.path.join(self._domain_dir(domain), f'{self.selector}.txt')
    
    def _private_key_path(self, domain: str) -> str:
        return os.path.join(self._domain_dir(domain), f'{self.selector}.private')
    
    def read_public_key(self, domain: str) -> Optional[str]:
        """Читает публичный DKIM ключ из файла {selector}.txt, если существует."""
        public_txt = self._public_txt_path(domain)
        if os.path.exists(public_txt):
            try:
                with open(public_txt, 'r') as f:
                    content = f.read().strip()
                # Извлечём строку, начинающуюся с v=DKIM1 (уберём скобки/кавычки)
                # Файл обычно формата: name IN TXT ( "v=DKIM1; k=rsa; " "p=..." )
                lines = [line.strip() for line in content.replace('(', '').replace(')', '').split('\n')]
                merged = ' '.join(part.strip('"') for line in lines for part in line.split() if part)
                # Найти подстроку начиная с v=DKIM1
                idx = merged.find('v=DKIM1')
                if idx != -1:
                    return merged[idx:]
                return merged
            except Exception as e:
                print(f"Error reading DKIM public key for {domain}: {e}")
                return None
        return None
    
    def generate_keys(self, domain: str) -> Optional[Tuple[str, str]]:
        """
        Обеспечивает наличие реальных DKIM ключей для домена под OpenDKIM.
        1) Если ключи уже есть в {keys_dir}/{domain}, читает и возвращает их
        2) Пытается сгенерировать через opendkim-genkey (если доступно)
        3) Если нет прав — вызывает привилегированный helper-скрипт через sudo
        Никогда не генерирует "искусственные" ключи.
        Возвращает (public_key_text, private_key_path) или None.
        """
        if self.is_windows:
            print(f"DKIM real key provisioning is not supported on Windows for domain: {domain}")
            return None
        
        # 1) Уже существуют?
        existing_public = self.read_public_key(domain)
        existing_private = self._private_key_path(domain)
        if existing_public and os.path.exists(existing_private):
            return existing_public, existing_private
        
        # 2) Пробуем напрямую opendkim-genkey
        try:
            result = subprocess.run(['opendkim-genkey', '--version'], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                generated = self.generate_keys_opendkim(domain)
                if generated:
                    public_key, private_key_path = generated
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
        
        # 3) Пробуем helper через sudo
        helper_generated = self.generate_keys_with_helper(domain)
        if helper_generated:
            return helper_generated
        
        print(f"Failed to provision real DKIM keys for domain: {domain}")
        return None

    def generate_keys_with_helper(self, domain: str) -> Optional[Tuple[str, str]]:
        """Пробует вызвать привилегированный helper-скрипт для провижининга DKIM.
        Ожидается, что скрипт создаст ключи, обновит KeyTable/SigningTable/TrustedHosts и
        выведет публичный ключ в stdout. Возвращает (public_key, private_key_path)."""
        if self.is_windows:
            return None
        try:
            # Вызов через sudo, если доступно в sudoers без пароля
            # Use resolved sudo path; if not available, abort to avoid falling back silently
            if not self.sudo_path or not os.path.exists(self.sudo_path):
                print(f"DKIM helper cannot run because 'sudo' is not available on this system")
                return None
            cmd = [self.sudo_path, self.helper_path, domain, self.selector, self.keys_dir]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"DKIM helper failed for {domain}: {result.stderr.strip()}")
                return None
            public_key = result.stdout.strip()
            private_key_path = os.path.join(self.keys_dir, domain, f"{self.selector}.private")
            if not os.path.exists(private_key_path):
                print(f"DKIM helper did not create private key at {private_key_path}")
                return None
            return public_key, private_key_path
        except Exception as e:
            print(f"Error invoking DKIM helper for {domain}: {e}")
            return None
    
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
                content = f.read().strip()
            # Нормализуем к виду: v=DKIM1; k=rsa; p=...
            lines = [line.strip() for line in content.replace('(', '').replace(')', '').split('\n')]
            merged = ' '.join(part.strip('"') for line in lines for part in line.split() if part)
            idx = merged.find('v=DKIM1')
            public_key = merged[idx:] if idx != -1 else merged
            
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
        raw = public_key.strip()
        # Удаляем комментарии после ;
        if ' ;' in raw:
            raw = raw.split(' ;', 1)[0]
        # Если вдруг попалось "name IN TXT ( "..." "p=..." )" — убираем имя/скобки/кавычки и склеиваем
        cleaned = raw.replace('(', '').replace(')', '')
        parts = []
        for token in cleaned.split():
            token = token.strip().strip('"')
            if token:
                parts.append(token)
        merged = ' '.join(parts)
        # Найти начало с v=DKIM1
        idx = merged.find('v=DKIM1')
        if idx != -1:
            merged = merged[idx:]
        # Убедимся, что есть только один p=...
        # (оставляем как есть — главное, что это чистое значение)
        value = merged
        return f"{name} IN TXT \"{value}\""