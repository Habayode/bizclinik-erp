"""QR code rendering helper.

Thin wrapper over the optional `qrcode` library so callers can render a QR PNG
for a FIRS e-invoice. If `qrcode` (with the Pillow image backend) isn't
installed, we raise a clear ImportError with the exact pip hint rather than a
cryptic stack trace.
"""
from __future__ import annotations

import io


_PIP_HINT = (
    "QR rendering needs the 'qrcode' library with the Pillow backend. "
    "Install it with:  pip install qrcode[pil]"
)


def make_qr_png_bytes(data: str) -> bytes:
    """Render `data` as a QR code and return the PNG bytes.

    Raises ImportError (with a pip hint) if `qrcode[pil]` isn't available.
    """
    try:
        import qrcode  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only when missing
        raise ImportError(_PIP_HINT) from exc

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    try:
        img = qr.make_image(fill_color="black", back_color="white")
    except Exception as exc:  # Pillow missing → qrcode raises at render time
        raise ImportError(_PIP_HINT) from exc

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
