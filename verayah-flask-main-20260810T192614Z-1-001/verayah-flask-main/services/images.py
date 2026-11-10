"""Safe handling of uploaded photos: check they really decode, then shrink them.

Phone photos are often 3-10 MB and 4000+ pixels wide. The shop only ever shows
them a few hundred pixels wide, so we re-save them as a web-sized JPEG. That
keeps the shop fast and the disk small, fixes sideways phone photos (EXIF
rotation) and drops hidden metadata such as GPS location.
"""
import logging
from io import BytesIO

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
    HAVE_PIL = True
except ImportError:          # Pillow not installed on this server: fall back to the old behaviour
    HAVE_PIL = False

log = logging.getLogger(__name__)

FALLBACK_MAX_BYTES = 5 * 1024 * 1024   # without Pillow we can't shrink, so keep the old 5 MB limit
MAX_SIDE = 1600          # longest edge, in pixels, of a saved photo
MAX_PIXELS = 60_000_000  # refuse absurdly large images (decompression bombs)
JPEG_QUALITY = 85

if HAVE_PIL:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2
else:
    log.warning("Pillow is not installed: uploaded photos will not be shrunk. "
                "Run: pip install -r requirements.txt")


class BadImage(ValueError):
    """The upload is not an image we can safely use."""


def _open(stream):
    try:
        img = Image.open(stream)
        if img.width * img.height > MAX_PIXELS:
            raise BadImage("That photo is too large in pixels. Please use a smaller one.")
        img.load()  # decode fully now, so a corrupt file fails here and not later
        return img
    except BadImage:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise BadImage("That file could not be read as a photo. Please try another one (JPG, PNG or WEBP).")


def _size(stream):
    stream.seek(0, 2)
    n = stream.tell()
    stream.seek(0)
    return n


def _ext_from_signature(head):
    if head.startswith(b"\x89PNG"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def check(stream):
    """Raise BadImage if the upload can't be used. Leaves the stream rewound."""
    if not HAVE_PIL:
        if _size(stream) > FALLBACK_MAX_BYTES:
            raise BadImage("That photo is over 5 MB. Please use a smaller one.")
        return
    try:
        _open(stream)
    finally:
        stream.seek(0)


def optimise(stream):
    """Return (BytesIO, 'jpg') holding a web-sized, correctly rotated JPEG of the upload."""
    if not HAVE_PIL:
        stream.seek(0)
        raw = stream.read()
        return BytesIO(raw), _ext_from_signature(raw[:12])
    img = _open(stream)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))  # transparent areas become white
        flat.paste(rgba, mask=rgba.getchannel("A"))
        img = flat
    else:
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = BytesIO()
    img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    out.seek(0)
    return out, "jpg"
