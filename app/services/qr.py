"""QR code image generation for event deep links.

Not listed explicitly in the original `services/` tree, added alongside
`export.py` for the same reason: it is self-contained logic the `admin`
handler should not have to know the details of.
"""
from __future__ import annotations

import io

import qrcode
from qrcode.image.pil import PilImage


def build_qr_png(link: str) -> io.BytesIO:
    """Render `link` as a scannable PNG, ready to send via Telegram or print."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(link)
    qr.make(fit=True)
    image: PilImage = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
