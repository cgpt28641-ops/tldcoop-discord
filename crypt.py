#!/usr/bin/env python3
"""TLDCoop (Karol 11.11: the repo is public, so the messages are kept ENCRYPTED).

The players' messages, logs and files never go into git in the clear: after each bridge run the runner SEALS every
new file of inbox/ (except state.json, channels.json, users.json: only ids and names) with the PUBLIC key in
vault.pub into vault/<random>.bin and deletes the plain file. No secret is needed on GitHub for that. Only the
holder of the PRIVATE key (Claude / Karol) can open them:

  python3 crypt.py seal [ROOT]                 runner: inbox/* -> vault/*.bin
  python3 crypt.py open [ROOT] [KEYFILE]       local: vault/*.bin -> inbox/* (gitignored); mentions.lst is appended
  python3 crypt.py keygen KEYFILE              new key pair (writes KEYFILE and vault.pub)

Each file: X25519 (ephemeral) + HKDF-SHA256 + AES-256-GCM; inside: its path, the time it was sealed, the bytes.
"""
import json
import os
import sys
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PLAIN = {"inbox/state.json", "inbox/channels.json", "inbox/users.json"}
RAW = serialization.Encoding.Raw


def derive(shared, eph_pub):
    return HKDF(hashes.SHA256(), 32, eph_pub, b"tldcoop-vault").derive(shared)


def seal(root="."):
    pub = X25519PublicKey.from_public_bytes(bytes.fromhex(open(os.path.join(root, "vault.pub")).read().strip()))
    vault = os.path.join(root, "vault")
    os.makedirs(vault, exist_ok=True)
    n = 0
    for base, _, files in os.walk(os.path.join(root, "inbox")):
        for f in files:
            full = os.path.join(base, f)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel in PLAIN:
                continue
            data = open(full, "rb").read()
            head = json.dumps({"path": rel, "t": time.time()}).encode()
            eph = X25519PrivateKey.generate()
            eph_pub = eph.public_key().public_bytes(RAW, serialization.PublicFormat.Raw)
            key = derive(eph.exchange(pub), eph_pub)
            nonce = os.urandom(12)
            body = AESGCM(key).encrypt(nonce, len(head).to_bytes(4, "big") + head + data, None)
            with open(os.path.join(vault, os.urandom(16).hex() + ".bin"), "wb") as fh:
                fh.write(eph_pub + nonce + body)
            os.remove(full)
            n += 1
    print(f"sealed {n}")


def open_all(root=".", keyfile=os.path.expanduser("~/.secrets/tldcoop_vault.key")):
    priv = X25519PrivateKey.from_private_bytes(bytes.fromhex(open(keyfile).read().strip()))
    vault = os.path.join(root, "vault")
    items = []
    for f in os.listdir(vault) if os.path.isdir(vault) else []:
        if not f.endswith(".bin"):
            continue
        raw = open(os.path.join(vault, f), "rb").read()
        eph_pub, nonce, body = raw[:32], raw[32:44], raw[44:]
        key = derive(priv.exchange(X25519PublicKey.from_public_bytes(eph_pub)), eph_pub)
        plain = AESGCM(key).decrypt(nonce, body, None)
        hl = int.from_bytes(plain[:4], "big")
        head = json.loads(plain[4:4 + hl])
        items.append((head["t"], head["path"], plain[4 + hl:]))
    items.sort()
    written = set()
    for _, rel, data in items:
        if rel.startswith("/") or ".." in rel.split("/") or not rel.startswith("inbox/"):
            continue
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if rel == "inbox/mentions.lst":  # every run's list is sealed on its own: one list again, in order
            mode = "ab" if rel in written else "wb"
        else:
            mode = "wb"
        with open(dst, mode) as fh:
            fh.write(data)
        written.add(rel)
    print(f"opened {len(items)}")


def keygen(keyfile, root="."):
    k = X25519PrivateKey.generate()
    os.makedirs(os.path.dirname(os.path.abspath(keyfile)), exist_ok=True)
    with open(keyfile, "w") as fh:
        fh.write(k.private_bytes(RAW, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex() + "\n")
    os.chmod(keyfile, 0o600)
    with open(os.path.join(root, "vault.pub"), "w") as fh:
        fh.write(k.public_key().public_bytes(RAW, serialization.PublicFormat.Raw).hex() + "\n")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"seal": seal, "open": open_all, "keygen": keygen}[cmd](*args)
