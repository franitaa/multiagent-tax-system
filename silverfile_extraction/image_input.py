"""Decode and normalize image bytes locally; never invoke an external OCR process."""
import hashlib
import io
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Document, utc_now
from .privacy import SafeInputError

MAX_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000


def prepare_image(data: bytes, *, synthetic_confirmed: bool) -> tuple[Document, bytes]:
    """No disk write. The ORIGINAL synthetic image will be sent to OpenAI."""
    if not synthetic_confirmed:
        raise SafeInputError("Confirm fictional test data and consent to send the image to OpenAI.")
    if not data or len(data) > MAX_BYTES:
        raise SafeInputError("Upload one PNG or JPEG no larger than 12 MB.")
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in {"PNG", "JPEG"}:
            raise SafeInputError("Only PNG and JPEG images are supported.")
        if image.width * image.height > MAX_PIXELS:
            raise SafeInputError("The image is larger than 20 megapixels.")
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        output = io.BytesIO()
        image.save(output, format="PNG")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise SafeInputError("The image cannot be decoded. Try another PNG or JPEG.") from exc
    digest = hashlib.sha256(data).hexdigest()
    # The evidence hash verifies the exact normalized PNG saved and sent to the API.
    # The document ID separately identifies the original upload for deduplication.
    evidence_hash = hashlib.sha256(output.getvalue()).hexdigest()
    doc = Document(document_id=f"doc_{digest}", sha256=evidence_hash, image_width=image.width,
                   image_height=image.height, image_file=f"doc_{digest}.png", tokens=[],
                   ocr_engine="not_used_direct_vision", captured_at=utc_now())
    return doc, output.getvalue()


def save_source(document: Document, png: bytes, directory: Path) -> None:
    """Save the synthetic evidence only AFTER model-response validation."""
    directory.mkdir(parents=True, exist_ok=True)
    if Path(document.image_file).name != document.image_file:
        raise SafeInputError("Invalid source image filename.")
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".png", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(png)
    try:
        os.replace(temporary, directory / document.image_file)
    finally:
        temporary.unlink(missing_ok=True)
