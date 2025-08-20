import os
import hashlib
import uuid
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from .config import settings

STORAGE_DIR = Path("backend/storage")
STORAGE_DIR.mkdir(exist_ok=True)


def compute_sha256(data: bytes) -> str:
    """Compute SHA256 hash of data"""
    return hashlib.sha256(data).hexdigest()


def generate_safe_filename() -> str:
    """Generate a safe random filename"""
    return f"{uuid.uuid4()}.bin"


def encrypt_file_data(plaintext: bytes) -> tuple[str, str]:
    """
    Encrypt file data using AES-256-GCM
    Returns: (cipher_path, sha256_hex)
    """
    # Compute SHA256 of plaintext
    sha256_hex = compute_sha256(plaintext)
    
    # Generate random nonce (12 bytes for GCM)
    nonce = os.urandom(12)
    
    # Create cipher
    cipher = Cipher(
        algorithms.AES(settings.aes_key),
        modes.GCM(nonce),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    
    # Encrypt data
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    
    # Create file with format: nonce(12) + ciphertext + tag(16)
    encrypted_data = nonce + ciphertext + encryptor.tag
    
    # Save to storage
    cipher_filename = generate_safe_filename()
    cipher_path = STORAGE_DIR / cipher_filename
    
    with open(cipher_path, "wb") as f:
        f.write(encrypted_data)
    
    return str(cipher_filename), sha256_hex


def decrypt_file_data(cipher_filename: str) -> bytes:
    """
    Decrypt file data using AES-256-GCM
    Returns: plaintext bytes
    """
    cipher_path = STORAGE_DIR / cipher_filename
    
    if not cipher_path.exists():
        raise FileNotFoundError(f"Encrypted file not found: {cipher_filename}")
    
    with open(cipher_path, "rb") as f:
        encrypted_data = f.read()
    
    # Extract components: nonce(12) + ciphertext + tag(16)
    nonce = encrypted_data[:12]
    tag = encrypted_data[-16:]
    ciphertext = encrypted_data[12:-16]
    
    # Create cipher
    cipher = Cipher(
        algorithms.AES(settings.aes_key),
        modes.GCM(nonce, tag),
        backend=default_backend()
    )
    decryptor = cipher.decryptor()
    
    # Decrypt data
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    
    return plaintext
