from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
import hashlib

# AES 密钥（支持你随时修改）
AES_KEY = b"ViXtel*408^n"  # 原始 12 字节，自动用 MD5 补齐为 16 字节

# 补齐为 16 字节密钥
def get_fixed_key(key: bytes) -> bytes:
    return hashlib.md5(key).digest()

# 加密：明文 → Base64 AES 密文
def aes_encrypt(plain_text: str, key: bytes = AES_KEY) -> str:
    fixed_key = get_fixed_key(key)
    cipher = AES.new(fixed_key, AES.MODE_ECB)
    ct_bytes = cipher.encrypt(pad(plain_text.encode('utf-8'), AES.block_size))
    return base64.b64encode(ct_bytes).decode('utf-8')

# 解密：Base64 AES 密文 → 明文
def aes_decrypt(cipher_text: str, key: bytes = AES_KEY) -> str:
    fixed_key = get_fixed_key(key)
    cipher = AES.new(fixed_key, AES.MODE_ECB)
    pt = unpad(cipher.decrypt(base64.b64decode(cipher_text)), AES.block_size)
    return pt.decode('utf-8')