"""PKCS#12 digital signing for GePG XML (SHA256withRSA).

Signs the content between ``<Gepg>`` and ``</Gepg>`` (excluding the signature
element) with the private key, matching GePG's expected scheme.
"""

import base64
import logging
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

from django.conf import settings

logger = logging.getLogger(__name__)


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

    Returns the payload unchanged (with placeholder) if signing fails, so a
    signing error never silently drops the request.
    """
    try:
        signature = sign_content(xml)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("GePG signing failed: %s", exc)
        return xml
    placeholder = "<signature>SignatureGoesHere</signature>"
    if placeholder in xml:
        return xml.replace(placeholder, f"<signature>{signature}</signature>")
    return xml.replace("</Gepg>", f"  <signature>{signature}</signature>\n</Gepg>")


def sign_if_enabled(xml: str) -> str:
    """Sign the payload when GEPG_USE_DIGITAL_SIGNATURE is on; otherwise pass through."""
    return sign_payload(xml) if settings.GEPG_USE_DIGITAL_SIGNATURE else xml
