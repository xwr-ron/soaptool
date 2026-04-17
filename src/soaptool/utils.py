from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, unquote
import hashlib
import os
import posixpath
import re
from lxml import etree


NS_WSDL = "http://schemas.xmlsoap.org/wsdl/"
NS_XSD = "http://www.w3.org/2001/XMLSchema"
NS_SOAP11 = "http://schemas.xmlsoap.org/wsdl/soap/"
NS_SOAPENV = "http://schemas.xmlsoap.org/soap/envelope/"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_fragment(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def normalize_url(url: str) -> str:
    return strip_fragment(url.strip())


def localname(name: str | bytes | None) -> str:
    if name is None:
        return ""
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="ignore")
    if "}" in name:
        return name.rsplit("}", 1)[-1]
    return name


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def guess_filename(url: str, content: bytes | None = None, content_type: str = "") -> str:
    parsed = urlparse(url)
    basename = posixpath.basename(parsed.path)
    if basename and "." in basename:
        return safe_name(basename)

    qs = parse_qs(parsed.query, keep_blank_values=True)
    if "xsd" in qs and qs["xsd"]:
        return safe_name(Path(unquote(qs["xsd"][0])).name)
    if "wsdl" in qs or parsed.query.lower() == "wsdl":
        return "service.wsdl"

    sniff = (content or b"")[:400].decode("utf-8", errors="ignore").lower()
    if "definitions" in sniff or "wsdl:" in sniff:
        return "service.wsdl"
    if "schema" in sniff or "xsd:" in sniff:
        return "schema.xsd"
    if "xml" in content_type.lower():
        return "document.xml"
    return "downloaded.bin"


def url_to_local_path(url: str, base_out: Path, content: bytes | None = None, content_type: str = "") -> Path:
    parsed = urlparse(url)
    host = safe_name(parsed.netloc or "nohost")
    qs = parse_qs(parsed.query, keep_blank_values=True)

    parts = [safe_name(p) for p in parsed.path.split("/") if p]
    dir_parts = list(parts)
    filename = None

    if "xsd" in qs and qs["xsd"]:
        filename = safe_name(Path(unquote(qs["xsd"][0])).name)
    elif "wsdl" in qs or parsed.query.lower() == "wsdl":
        filename = "service.wsdl"
    else:
        basename = posixpath.basename(parsed.path.rstrip("/"))
        if basename and "." in basename:
            filename = safe_name(Path(basename).name)
            dir_parts = parts[:-1]
        else:
            filename = guess_filename(url, content, content_type)

    local_dir = base_out / "original" / host
    for part in dir_parts:
        local_dir /= part
    local_dir.mkdir(parents=True, exist_ok=True)
    return local_dir / filename


def parse_xml_bytes(data: bytes) -> etree._ElementTree | None:
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    try:
        root = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError:
        return None
    return etree.ElementTree(root)


def qname_to_clark(raw: str, nsmap: dict[str | None, str], fallback_ns: str | None = None) -> str:
    raw = raw.strip()
    if raw.startswith("{"):
        return raw
    if ":" in raw:
        prefix, local = raw.split(":", 1)
        ns = nsmap.get(prefix)
        if ns:
            return f"{{{ns}}}{local}"
        if fallback_ns:
            return f"{{{fallback_ns}}}{local}"
        return local
    ns = nsmap.get(None) or fallback_ns
    if ns:
        return f"{{{ns}}}{raw}"
    return raw


def clark_to_prefixed(clark: str, preferred_prefix: str = "ns") -> tuple[str, dict[str, str]]:
    if not clark.startswith("{"):
        return clark, {}
    ns, local = clark[1:].split("}", 1)
    return f"{preferred_prefix}:{local}", {preferred_prefix: ns}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def relpath_posix(path: Path, start: Path) -> str:
    return os.path.relpath(path, start=start).replace(os.sep, "/")
