import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CryptoManager:
    """加密管理器，用于加密和解密敏感数据"""

    def __init__(self, password: str = None, salt: bytes = None):
        """
        初始化加密管理器

        Args:
            password: 用于生成密钥的密码，如果为None则使用环境变量或生成随机密码
            salt: 盐值，如果为None则生成随机盐值
        """
        if password is None:
            password = os.environ.get('CRYPTO_PASSWORD', self._generate_random_password())

        if salt is None:
            salt = os.environ.get('CRYPTO_SALT', os.urandom(16)).encode() if isinstance(os.environ.get('CRYPTO_SALT'), str) else os.urandom(16)
            print(f'CRYPTO_SALT {salt}')

        self.salt = salt
        self.key = self._derive_key(password.encode(), salt)
        self.cipher = Fernet(self.key)

    @staticmethod
    def _generate_random_password(length: int = 32) -> str:
        """生成随机密码"""
        return base64.urlsafe_b64encode(os.urandom(length)).decode()[:length]

    def _derive_key(self, password: bytes, salt: bytes) -> bytes:
        """从密码派生密钥"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

    def encrypt(self, data: str) -> str:
        """
        加密字符串数据

        Args:
            data: 要加密的字符串

        Returns:
            加密后的base64字符串
        """
        if not data:
            return data
        encrypted_data = self.cipher.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """
        解密字符串数据

        Args:
            encrypted_data: 加密的base64字符串

        Returns:
            解密后的原始字符串
        """
        if not encrypted_data:
            return encrypted_data
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self.cipher.decrypt(encrypted_bytes)
            return decrypted_data.decode()
        except Exception as e:
            raise ValueError(f"解密失败: {str(e)}")

    def get_salt_base64(self) -> str:
        """获取base64编码的盐值"""
        return base64.urlsafe_b64encode(self.salt).decode()


# 全局加密管理器实例
crypto_manager = None


def get_crypto_manager() -> CryptoManager:
    """获取全局加密管理器实例"""
    global crypto_manager
    if crypto_manager is None:
        crypto_manager = CryptoManager()
    return crypto_manager


def encrypt_sensitive_data(data: str) -> str:
    """
    加密敏感数据

    Args:
        data: 要加密的字符串数据

    Returns:
        加密后的字符串
    """
    if not data:
        return data
    manager = get_crypto_manager()
    return manager.encrypt(data)


def decrypt_sensitive_data(encrypted_data: str) -> str:
    """
    解密敏感数据

    Args:
        encrypted_data: 加密的字符串数据

    Returns:
        解密后的原始字符串
    """
    if not encrypted_data:
        return encrypted_data
    manager = get_crypto_manager()
    return manager.decrypt(encrypted_data)