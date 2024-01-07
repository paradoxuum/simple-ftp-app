from typing import Optional

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import (
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class NetworkEncryption:
    def __init__(self) -> None:
        self._enabled = False
        self.padding = padding.PKCS7(128)

        self._private_key: Optional[EllipticCurvePrivateKey] = None
        self.public_key: Optional[EllipticCurvePublicKey] = None
        self._shared_key: Optional[bytes] = None

        self._derived_key: Optional[bytes] = None
        self._cipher: Optional[Cipher] = None

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def generate_keys(self) -> EllipticCurvePublicKey:
        self._private_key = ec.generate_private_key(ec.SECP384R1())
        self.public_key = self._private_key.public_key()
        return self.public_key

    def exchange_keys(self, public_key: EllipticCurvePublicKey) -> None:
        if self._private_key is None:
            raise Exception("Keys have not been generated")

        self._shared_key = self._private_key.exchange(ec.ECDH(), public_key)
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"encrypted packet message",
        ).derive(self._shared_key)

        cbc_vec = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=None,
            info=b"CBC vector",
        ).derive(self._shared_key)

        self._cipher = Cipher(algorithms.AES(derived_key), modes.CBC(cbc_vec))

    def encrypt(self, message: bytes) -> bytes:
        if not self._enabled or self._cipher is None:
            return message

        encryptor = self._cipher.encryptor()
        padder = self.padding.padder()

        padded_data = padder.update(message) + padder.finalize()
        return encryptor.update(padded_data) + encryptor.finalize()

    def decrypt(self, message: bytes) -> bytes:
        if not self._enabled or self._cipher is None:
            return message

        decryptor = self._cipher.decryptor()
        unpadder = self.padding.unpadder()

        decrypted_bytes = decryptor.update(message) + decryptor.finalize()
        unpadded_bytes = unpadder.update(decrypted_bytes) + unpadder.finalize()
        return unpadded_bytes
