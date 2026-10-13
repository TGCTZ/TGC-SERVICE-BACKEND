"""PKCS#12 digital signing for GePG XML (SHA256withRSA).

Signs the content between ``<Gepg>`` and ``</Gepg>`` (excluding the signature
element) with the private key, matching GePG's expected scheme.
"""

import base64
from functools import lru_cache
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from defusedxml.ElementTree import fromstring as parse_xml

from django.conf import settings


@lru_cache(maxsize=1)
def _load_private_key():
    """Load and cache the private key from the PKCS#12 file."""
    path = Path(settings.GEPG_PRIVATE_KEY_PATH)
    if not path.exists():
        raise FileNotFoundError(f"GePG private key not found: {path}")
    password = (settings.GEPG_CERTIFICATE_PASSWORD or "").encode("utf-8")
    private_key, _cert, _extra = pkcs12.load_key_and_certificates(
        path.read_bytes(), password
    )
    return private_key


def _inner_content(xml: str) -> str:
    """Return the content between <Gepg>..</Gepg>, excluding any signature."""
    if "<signature>" in xml and "</signature>" in xml:
        start = xml.find("<signature>")
        end = xml.find("</signature>") + len("</signature>")
        xml = xml[:start] + xml[end:]
    if "<Gepg>" in xml:
        inner_start = xml.find("<Gepg>") + len("<Gepg>")
        inner_end = xml.rfind("</Gepg>")
        return xml[inner_start:inner_end].strip()
    return xml.strip()


def sign_content(xml: str) -> str:
    """Return the base64 SHA256withRSA signature of an XML payload's inner content."""
    signature = _load_private_key().sign(
        _inner_content(xml).encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")


def sign_payload(xml: str) -> str:
    """Replace the signature placeholder in an XML payload with a real signature.

    Raises when the configured identity cannot sign; live requests must never
    silently leave the placeholder in place.
    """
    signature = sign_content(xml)
    placeholder = "<signature>SignatureGoesHere</signature>"
    if placeholder in xml:
        return xml.replace(placeholder, f"<signature>{signature}</signature>")
    return xml.replace("</Gepg>", f"  <signature>{signature}</signature>\n</Gepg>")


def sign_if_enabled(xml: str) -> str:
    """Sign XML or fail closed when a live gateway request would be unsigned."""
    if settings.GEPG_USE_DIGITAL_SIGNATURE:
        return sign_payload(xml)
    if not settings.DEBUG and not settings.GEPG_SIMULATE:
        raise RuntimeError("GePG digital signing is required outside development.")
    return xml


@lru_cache(maxsize=1)
def _load_gateway_public_key():
    """Load the registered GePG public certificate from PFX, PEM, or DER."""
    path = Path(settings.GEPG_PUBLIC_CERT_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"GePG public certificate not found: {path}")
    data = path.read_bytes()
    password = (settings.GEPG_PUBLIC_CERTIFICATE_PASSWORD or "").encode("utf-8")
    try:
        _key, certificate, _chain = pkcs12.load_key_and_certificates(data, password)
    except ValueError:
        try:
            certificate = x509.load_pem_x509_certificate(data)
        except ValueError:
            certificate = x509.load_der_x509_certificate(data)
    if certificate is None:
        raise ValueError("GePG public certificate file contains no certificate.")
    return certificate.public_key()


def verify_payload(xml: str) -> bool:
    """Verify a GePG signature over the exact inner XML payload."""
    try:
        root = parse_xml(xml)
        signature_text = root.findtext("signature")
        if not signature_text:
            return False
        signature = base64.b64decode(signature_text, validate=True)
        _load_gateway_public_key().verify(
            signature,
            _inner_content(xml).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (ValueError, InvalidSignature, TypeError):
        return False
    return True
