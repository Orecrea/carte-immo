"""Chiffrement des fichiers publiés (AES-GCM, clé dérivée du mot de passe par PBKDF2).

Format : {"v":1, "s": sel base64, "i": iv base64, "d": données gzip chiffrées base64}
La carte (navigateur) déchiffre le même format avec WebCrypto.
"""
import base64, gzip, json, os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITER = 150_000


def _cle(mdp: str, sel: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=ITER).derive(mdp.encode())


def chiffrer(obj, mdp: str) -> str:
    sel, iv = os.urandom(16), os.urandom(12)
    brut = gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0)
    d = AESGCM(_cle(mdp, sel)).encrypt(iv, brut, None)
    b = lambda x: base64.b64encode(x).decode()
    return json.dumps({"v": 1, "s": b(sel), "i": b(iv), "d": b(d)})


def dechiffrer(texte: str, mdp: str):
    o = json.loads(texte)
    u = base64.b64decode
    brut = AESGCM(_cle(mdp, u(o["s"]))).decrypt(u(o["i"]), u(o["d"]), None)
    return json.loads(gzip.decompress(brut))
