"""Images embedded in a certificate PDF: the lab's marks, and the QR code.

Everything here returns a ``data:`` URI rather than a path or a URL. That is
what lets ``render_certificate_pdf`` call WeasyPrint without a ``base_url``: the
document carries its own pixels, so it renders identically from a request, a
management command, a test, or a background job, and never depends on
``collectstatic`` having run.

The cost is document size - a few hundred KB per certificate - which is the
right trade for a file that has to be reproducible years later.
"""

import base64
import logging
import mimetypes
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageOps

from django.conf import settings

logger = logging.getLogger(__name__)

ASSET_DIR = Path(__file__).resolve().parent.parent / "static" / "certificates" / "img"

#: Filenames under :data:`ASSET_DIR`, by the name the template asks for.
#:
#: An explicit map rather than the legacy system's extension-probing loader,
#: which tried six spellings per asset and fell through to a substring match on
#: ``"TANZANIA"`` - so a typo in the real filename went unnoticed for months
#: while production quietly used whichever file matched first.
ASSETS = {
    "coat_of_arms": "coat-of-arms.png",
    "tgc_logo": "tgc-logo.png",
    "official_stamp": "official-stamp.png",
}


def _encode(data: bytes, mime: str) -> str:
    """Wrap raw bytes as a ``data:`` URI."""
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


@lru_cache(maxsize=None)
def asset_data_uri(name: str) -> str | None:
    """Return one of the lab's marks as a ``data:`` URI, or None if absent.

    Cached for the life of the process: these files do not change between
    renders, and re-reading a 500KB PNG per certificate is pure waste.

    Returns None rather than raising when a file is missing, so a lab that has
    not supplied its stamp yet still gets a certificate - the template falls
    back to a labelled empty box. A missing asset is logged once, at the first
    render that wanted it.

    Args:
        name: A key of :data:`ASSETS`.
    """
    filename = ASSETS.get(name)
    if filename is None:
        return None

    path = ASSET_DIR / filename
    if not path.is_file():
        logger.warning("Certificate asset %r not found at %s", name, path)
        return None

    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return _encode(path.read_bytes(), mime)


def lab_assets() -> dict[str, str | None]:
    """Every lab mark the template may want, keyed as the template names them."""
    return {name: asset_data_uri(name) for name in ASSETS}


#: Longest edge, in pixels, of a photograph embedded in a certificate.
#:
#: The photo prints into a box about 40mm across. At 300dpi that is roughly
#: 470px, so 900 leaves generous headroom for print while cutting a modern
#: phone photo - 4000px and several megabytes - down to something a document
#: can carry. The bytes are embedded per certificate, so the full-resolution
#: original turned a 250KB document into a 1.9MB one for detail no printer
#: could resolve.
PHOTO_MAX_EDGE = 900


def photo_data_uri(image_field) -> str | None:
    """Return an uploaded image as a ``data:`` URI, or None if there is none.

    Downscaled to :data:`PHOTO_MAX_EDGE` and re-encoded as JPEG. The original
    upload is left untouched on disk - this only governs what goes into the
    document.

    Reads through the storage backend rather than ``.path``, so this keeps
    working when media moves off the local disk - ``.path`` raises
    ``NotImplementedError`` on any remote backend.

    Args:
        image_field: An ``ImageField`` value, which may be empty.
    """
    if not image_field:
        return None

    try:
        with image_field.open("rb") as handle:
            data = handle.read()
    except (OSError, ValueError):
        # A row pointing at a file that is no longer there must not take the
        # whole certificate down; the template renders its placeholder instead.
        logger.warning("Certificate photo unreadable: %s", image_field.name)
        return None

    try:
        with Image.open(BytesIO(data)) as original:
            # Bake in the EXIF orientation before anything else. A phone writes
            # the sensor's pixels and a "rotate me" tag; re-encoding drops the
            # tag, so without this a portrait photograph prints on its side.
            image = ImageOps.exif_transpose(original)

            # Flatten next: a PNG or a phone HEIC can carry transparency, and
            # JPEG has no alpha channel to put it in.
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.thumbnail((PHOTO_MAX_EDGE, PHOTO_MAX_EDGE), Image.LANCZOS)

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85, optimize=True)
            return _encode(buffer.getvalue(), "image/jpeg")
    except (OSError, ValueError):
        # Not something Pillow recognises. Embed it as uploaded rather than
        # dropping the photograph from the document entirely.
        logger.warning("Certificate photo could not be resized: %s", image_field.name)
        mime = mimetypes.guess_type(image_field.name)[0] or "image/jpeg"
        return _encode(data, mime)


def verification_url(certificate_number: str) -> str:
    """The public URL a certificate's QR code points at.

    Args:
        certificate_number: The certificate's own number, e.g. ``CERT-2026-0001``.
    """
    base = settings.CERTIFICATE_VERIFY_BASE_URL.rstrip("/")
    return f"{base}/verify/{certificate_number}/"


def qr_data_uri(payload: str) -> str:
    """Render a QR code for ``payload`` as a PNG ``data:`` URI.

    Error correction is set to M rather than qrcode's default L. A certificate
    is handled, folded and photocopied, and M tolerates roughly 15% damage
    against L's 7% - worth the slightly denser code on a mark that has to scan
    off paper years later.

    Args:
        payload: The text to encode, normally a verification URL.
    """
    code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    code.add_data(payload)
    code.make(fit=True)

    buffer = BytesIO()
    code.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return _encode(buffer.getvalue(), "image/png")
