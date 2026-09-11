# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportPrivateUsage=false
"""PDFium image-object adapter. Isolates untyped PDFium access."""

from __future__ import annotations

import io
import struct
import zlib
from dataclasses import dataclass

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c


@dataclass(frozen=True)
class ExtractedImage:
    media_type: str
    payload: bytes


@dataclass(frozen=True)
class ImageExtractError:
    stage: str
    reason: str


def extract_embedded_images(
    pdf_bytes: bytes,
) -> list[tuple[int, int, ExtractedImage | ImageExtractError]]:
    """Walk page image objects and extract bytes, skipping zero-area boxes."""
    results: list[tuple[int, int, ExtractedImage | ImageExtractError]] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for page_index, page in enumerate(pdf):
            image_counter = 0
            for obj in page.get_objects(max_depth=16):
                if obj.type != pdfium_c.FPDF_PAGEOBJ_IMAGE:
                    continue
                left, bottom, right, top = obj.get_pos()
                if right - left <= 0 or top - bottom <= 0:
                    continue
                results.append((page_index, image_counter, extract_pdfium_image(obj)))
                image_counter += 1
    finally:
        pdf.close()
    return results


def extract_pdfium_image(image_obj: object) -> ExtractedImage | ImageExtractError:
    """Return native or bitmap bytes, or a staged failure."""
    native = _extract_native_image(image_obj)
    if isinstance(native, ExtractedImage):
        return native
    return _extract_bitmap_png(image_obj)


def _reason(exc: BaseException) -> str:
    detail = str(exc).strip() or type(exc).__name__
    return f"{type(exc).__name__}: {detail}"[:240]


def _extract_native_image(image_obj: object) -> ExtractedImage | ImageExtractError:
    buffer = io.BytesIO()
    try:
        image_obj.extract(buffer)
    except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
        return ImageExtractError("native-extract", _reason(exc))
    payload = buffer.getvalue()
    if not payload:
        return ImageExtractError("native-extract", "empty payload")
    media_type = _media_type_from_bytes(payload)
    if media_type == "application/octet-stream":
        return ImageExtractError("native-format", "unsupported native image format")
    return ExtractedImage(media_type, payload)


def _extract_bitmap_png(image_obj: object) -> ExtractedImage | ImageExtractError:
    bitmap = None
    try:
        try:
            bitmap = image_obj.get_bitmap(render=True)
        except (RuntimeError, OSError, TypeError, ValueError, AttributeError):
            bitmap = image_obj.get_bitmap()
        png = _bitmap_to_png(bitmap)
    except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
        return ImageExtractError("bitmap", _reason(exc))
    except Exception as exc:
        return ImageExtractError("bitmap-unexpected", _reason(exc))
    finally:
        if bitmap is not None:
            close = getattr(bitmap, "close", None)
            if callable(close):
                close()
    if png is None:
        return ImageExtractError("png-encode", "bitmap layout is not a supported PNG mode")
    if not png:
        return ImageExtractError("png-encode", "empty PNG")
    return ExtractedImage("image/png", png)


def _bitmap_to_png(bitmap: object) -> bytes | None:
    width = int(bitmap.width)
    height = int(bitmap.height)
    stride = int(bitmap.stride)
    channels = int(bitmap.n_channels)
    mode = str(bitmap.mode)
    raw = bytes(bitmap.buffer)
    color_type, out_channels, swap_bgr = _png_layout(mode, channels)
    if color_type is None or out_channels is None:
        return None
    rows: list[bytes] = []
    row_bytes = width * channels
    for y in range(height):
        start = y * stride
        row = bytearray(raw[start : start + row_bytes])
        if swap_bgr:
            for index in range(0, len(row), channels):
                row[index], row[index + 2] = row[index + 2], row[index]
        rows.append(b"\x00" + bytes(row[: width * out_channels]))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    idat = zlib.compress(b"".join(rows), 9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _png_layout(mode: str, channels: int) -> tuple[int | None, int | None, bool]:
    if mode in {"L", "Gray"} or channels == 1:
        return 0, 1, False
    if mode == "BGR":
        return 2, 3, True
    if mode == "RGB" or channels == 3:
        return 2, 3, False
    if mode == "BGRA":
        return 6, 4, True
    if mode == "RGBA" or channels == 4:
        return 6, 4, False
    return None, None, False


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(tag)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)


def _media_type_from_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "application/octet-stream"
