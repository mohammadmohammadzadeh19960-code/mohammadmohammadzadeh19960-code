#!/usr/bin/env python3
"""Fail-closed profile artwork check; standard library only.

Checks that the GitHub README uses the exact approved original image blob.
A deliberate image replacement requires updating the expected blob in CI.
"""
import argparse
import hashlib
from pathlib import Path
import re
import sys


def verify(image_path: str, expected_sha: str, retired_path: str) -> None:
    image = Path(image_path)
    if image.is_absolute() or ".." in image.parts or image.suffix.lower() != ".webp":
        raise ValueError("Image must be a local repository WebP file")
    if image.is_symlink() or not image.is_file():
        raise ValueError("Approved image missing or redirected")
    payload = image.read_bytes()
    if not (50_000 <= len(payload) <= 2_000_000):
        raise ValueError("Unexpected approved image size")
    if payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        raise ValueError("Image is not WebP")
    if int.from_bytes(payload[4:8], "little") + 8 != len(payload):
        raise ValueError("Broken WebP RIFF length")
    blob_sha = hashlib.sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload
    ).hexdigest()
    if blob_sha != expected_sha:
        raise ValueError(f"Approved image byte identity changed ({blob_sha})")
    source = Path("README.md").read_text(encoding="utf-8")
    img_tags = re.findall(r"<img\b[^>]*>", source, flags=re.IGNORECASE | re.DOTALL)
    matches = []
    for tag in img_tags:
        src = re.search(r"""\bsrc\s*=\s*["']([^"']+)["']""", tag, re.IGNORECASE)
        if src and src.group(1) == image_path:
            matches.append(tag)
    if len(matches) != 1:
        raise ValueError("README must display the approved banner exactly once")
    alt = re.search(r"""\balt\s*=\s*["']([^"']+)["']""", matches[0], re.IGNORECASE)
    if not alt or len(alt.group(1).strip()) < 15:
        raise ValueError("The banner needs a meaningful accessible description")
    if retired_path and retired_path in source:
        raise ValueError("README still references a superseded image")
    print(f"PROFILE_ARTWORK_PASS image={image_path} bytes={len(payload)} blob={blob_sha}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--blob-sha", required=True)
    parser.add_argument("--retired-path", required=True)
    args = parser.parse_args()
    try:
        verify(args.image, args.blob_sha, args.retired_path)
    except (ValueError, OSError) as exc:
        print(f"PROFILE_ARTWORK_FAIL {exc}", file=sys.stderr)
        sys.exit(1)
