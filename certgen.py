"""Self-signed certificate generation – pure standard library.

Lets the app serve HTTPS on a local network with **no external tool and no
dependency** (no OpenSSL CLI, no `cryptography`), so it works on Windows,
macOS and Linux alike.

One RSA-2048 key and a 10-year certificate are generated on first use and
cached next to the app. The certificate covers ``localhost``, the machine's
hostname and all of its LAN addresses, so browsers can reach it by IP.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import math
import os
import secrets
import socket
import stat

# ------------------------------------------------------------------ ASN.1 DER

def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    out = b""
    while n:
        out = bytes([n & 0xFF]) + out
        n >>= 8
    return bytes([0x80 | len(out)]) + out


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _der_len(len(value)) + value


def _int(value: int) -> bytes:
    if value == 0:
        return _tlv(0x02, b"\x00")
    body = value.to_bytes((value.bit_length() + 7) // 8, "big")
    if body[0] & 0x80:
        body = b"\x00" + body
    return _tlv(0x02, body)


def _seq(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _set(*items: bytes) -> bytes:
    return _tlv(0x31, b"".join(items))


def _null() -> bytes:
    return b"\x05\x00"


def _bool(value: bool) -> bytes:
    return _tlv(0x01, b"\xff" if value else b"\x00")


def _bit(data: bytes, unused: int = 0) -> bytes:
    return _tlv(0x03, bytes([unused]) + data)


def _octet(data: bytes) -> bytes:
    return _tlv(0x04, data)


def _utf8(text: str) -> bytes:
    return _tlv(0x0C, text.encode("utf-8"))


def _utc(when: datetime.datetime) -> bytes:
    return _tlv(0x17, when.strftime("%y%m%d%H%M%SZ").encode())


def _ctx(number: int, data: bytes, constructed: bool = False) -> bytes:
    return _tlv((0xA0 if constructed else 0x80) | number, data)


def _oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    body = bytes([40 * parts[0] + parts[1]])
    for part in parts[2:]:
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.insert(0, (part & 0x7F) | 0x80)
            part >>= 7
        body += bytes(chunk)
    return _tlv(0x06, body)


SHA256_RSA = _seq(_oid("1.2.840.113549.1.1.11"), _null())
RSA_ENCRYPTION = _seq(_oid("1.2.840.113549.1.1.1"), _null())
OID_CN = "2.5.4.3"
OID_BASIC = "2.5.29.19"
OID_KEYUSAGE = "2.5.29.15"
OID_EKU = "2.5.29.37"
OID_SAN = "2.5.29.17"
OID_SERVER_AUTH = "1.3.6.1.5.5.7.3.1"


# ------------------------------------------------------------------ RSA

_SMALL_PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53,
                 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113,
                 127, 131, 137, 139, 149, 151, 157, 163, 167, 173, 179, 181,
                 191, 193, 197, 199, 211, 223, 227, 229, 233, 239, 241, 251,
                 257, 263, 269, 271, 277, 281, 283, 293, 307, 311, 313, 317,
                 331, 337, 347, 349, 353, 359, 367, 373, 379, 383, 389, 397,
                 401, 409, 419, 421, 431, 433, 439, 443, 449, 457, 461, 463,
                 467, 479, 487, 491, 499, 503, 509, 521, 523, 541, 547, 557,
                 563, 569, 571, 577, 587, 593, 599, 601, 607, 613, 617, 619,
                 631, 641, 643, 647, 653, 659, 661, 673, 677, 683, 691, 701,
                 709, 719, 727, 733, 739, 743, 751, 757, 761, 769, 773, 787,
                 797, 809, 811, 821, 823, 827, 829, 839, 853, 857, 859, 863,
                 877, 881, 883, 887, 907, 911, 919, 929, 937, 941, 947, 953,
                 967, 971, 977, 983, 991, 997]


def _is_probable_prime(n: int, rounds: int = 20) -> bool:
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def generate_rsa(bits: int = 2048) -> dict:
    e = 65537
    half = bits // 2
    while True:
        p = _gen_prime(half)
        q = _gen_prime(half)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        phi = (p - 1) * (q - 1)
        if math.gcd(e, phi) != 1:
            continue
        d = pow(e, -1, phi)
        return {
            "n": n, "e": e, "d": d, "p": p, "q": q,
            "dP": d % (p - 1), "dQ": d % (q - 1), "qInv": pow(q, -1, p),
        }


def _sign(key: dict, data: bytes) -> bytes:
    size = (key["n"].bit_length() + 7) // 8
    digest = hashlib.sha256(data).digest()
    prefix = bytes.fromhex("3031300d060960864801650304020105000420")
    block = prefix + digest
    padded = b"\x00\x01" + b"\xff" * (size - len(block) - 3) + b"\x00" + block
    return pow(int.from_bytes(padded, "big"), key["d"], key["n"]).to_bytes(size, "big")


def _rsa_private_der(key: dict) -> bytes:
    return _seq(_int(0), _int(key["n"]), _int(key["e"]), _int(key["d"]),
                _int(key["p"]), _int(key["q"]), _int(key["dP"]),
                _int(key["dQ"]), _int(key["qInv"]))


# ------------------------------------------------------------------ certificate

def _name(common_name: str) -> bytes:
    return _seq(_set(_seq(_oid(OID_CN), _utf8(common_name))))


def _subject_public_key(n: int, e: int) -> bytes:
    return _seq(RSA_ENCRYPTION, _bit(_seq(_int(n), _int(e))))


def _subject_alt_names(hosts: list[str], ips: list[str]) -> bytes:
    items = b""
    for host in hosts:
        items += _ctx(2, host.encode("ascii", "ignore"))
    for ip in ips:
        try:
            items += _ctx(7, socket.inet_aton(ip))
        except OSError:
            continue
    return _seq(items)


def _extension(oid: str, critical: bool, value: bytes) -> bytes:
    parts = [_oid(oid)]
    if critical:
        parts.append(_bool(True))
    parts.append(_octet(value))
    return _seq(*parts)


def _certificate(key: dict, common_name: str, hosts: list[str], ips: list[str],
                 days: int) -> bytes:
    now = datetime.datetime.utcnow()
    validity = _seq(_utc(now - datetime.timedelta(days=1)),
                    _utc(now + datetime.timedelta(days=days)))
    subject = _name(common_name)
    extensions = _seq(
        _extension(OID_BASIC, True, _seq()),
        _extension(OID_KEYUSAGE, True, _bit(b"\xa0", 5)),
        _extension(OID_EKU, False, _seq(_oid(OID_SERVER_AUTH))),
        _extension(OID_SAN, False, _subject_alt_names(hosts, ips)),
    )
    tbs = _seq(
        _ctx(0, _int(2), constructed=True),      # version v3
        _int(secrets.randbits(64) | 1),          # serial
        SHA256_RSA,
        subject,                                 # issuer
        validity,
        subject,                                 # subject
        _subject_public_key(key["n"], key["e"]),
        _ctx(3, extensions, constructed=True),
    )
    return _seq(tbs, SHA256_RSA, _bit(_sign(key, tbs)))


def _pem(label: str, der: bytes) -> str:
    blob = base64.b64encode(der).decode("ascii")
    lines = [blob[i:i + 64] for i in range(0, len(blob), 64)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"


# ------------------------------------------------------------------ public

def local_ips() -> list[str]:
    ips = {"127.0.0.1"}
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.3)
        probe.connect(("8.8.8.8", 80))          # routing lookup only, no traffic
        ips.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ips)


def ensure_certificate(cert_path: str, key_path: str, days: int = 3650) -> tuple[str, str]:
    """Create the certificate/key pair if it is not there yet."""
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path
    os.makedirs(os.path.dirname(cert_path) or ".", exist_ok=True)

    raw_names = ("localhost", "localhost.localdomain", socket.gethostname(), socket.getfqdn())
    hosts = sorted({h for h in raw_names
                    if h and not h.endswith(".arpa") and ":" not in h
                    and not h.replace(".", "").isdigit()})
    ips = local_ips()
    common_name = socket.gethostname() or "salarycalc.local"

    key = generate_rsa(2048)
    der = _certificate(key, common_name, hosts, ips, days)

    with open(cert_path, "w", encoding="ascii") as fh:
        fh.write(_pem("CERTIFICATE", der))
    with open(key_path, "w", encoding="ascii") as fh:
        fh.write(_pem("RSA PRIVATE KEY", _rsa_private_der(key)))
    try:
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return cert_path, key_path
