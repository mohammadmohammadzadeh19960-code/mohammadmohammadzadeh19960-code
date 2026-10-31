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
import tempfile


def verify_readme_references(source: str, root: Path | None = None) -> None:
    """Validate local README links/images without networking or private-token access."""
    from urllib.parse import unquote, urlsplit

    root = (root if root is not None else Path.cwd()).resolve()
    refs = re.findall(r"!?\[[^\]\n]*\]\(([^)\s]+)", source)
    refs.extend(re.findall(r"""(?i)\b(?:href|src)\s*=\s*["']([^"']+)["']""", source))
    local_count = 0
    for ref in refs:
        parsed = urlsplit(ref)
        if parsed.scheme:
            if parsed.scheme.lower() not in ("http", "https", "mailto", "tel"):
                raise ValueError("Unsupported README link scheme")
            continue
        if parsed.netloc or not parsed.path:
            continue
        path = unquote(parsed.path)
        if path.startswith("/") or ".." in Path(path).parts:
            raise ValueError("README local link escapes repository")
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError(f"README local target missing or outside repository: {path}")
        local_count += 1

    images = re.findall(r"<img\b[^>]*>", source, flags=re.IGNORECASE | re.DOTALL)
    for tag in images:
        alt = re.search(r"""(?i)\balt\s*=\s*["']([^"']+)["']""", tag)
        if not alt or len(alt.group(1).strip()) < 8:
            raise ValueError("README image is missing meaningful alt text")
    print(f"PROFILE_README_REFS_PASS refs={local_count} images={len(images)}")


def self_test() -> None:
    """Adversarial local fixtures: valid references pass, unsafe changes fail closed."""
    with tempfile.TemporaryDirectory() as location:
        root = Path(location)
        (root / "assets").mkdir()
        (root / "assets" / "header.webp").write_bytes(b"fixture only")
        (root / "guide.md").write_text("ok", encoding="utf-8")
        valid = ('<img src="assets/header.webp" alt="Verified engineering artwork"> '
                 '[Guide](guide.md) [GitHub](https://github.com)')
        verify_readme_references(valid, root=root)
        cases = {
            "missing-file": "[Missing](nonexistent.md)",
            "path-traversal": "[Outside](../outside.md)",
            "encoded-traversal": "[Encoded](%2e%2e%2foutside.md)",
            "absolute-path": "[Absolute](/etc/passwd)",
            "unsupported-scheme": '<a href="javascript:alert">Unsafe</a>',
            "missing-image-alt": '<img src="assets/header.webp">',
            "short-image-alt": '<img src="assets/header.webp" alt="x">',
            "missing-image-target": '<img src="assets/missing.webp" alt="Descriptive image text">',
        }
        for name, text in cases.items():
            try:
                verify_readme_references(text, root=root)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected rejection: " + name)
    print("PROFILE_REF_SELFTEST_PASS cases=9")


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
    verify_readme_references(source)
    print(f"PROFILE_ARTWORK_PASS image={image_path} bytes={len(payload)} blob={blob_sha}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--image")
    parser.add_argument("--blob-sha")
    parser.add_argument("--retired-path")
    args = parser.parse_args()
    if not args.self_test and not all((args.image, args.blob_sha, args.retired_path)):
        parser.error("--image, --blob-sha, and --retired-path are required")
    try:
        if args.self_test:
            self_test()
        else:
            verify(args.image, args.blob_sha, args.retired_path)
    except (ValueError, OSError, AssertionError) as exc:
        print(f"PROFILE_ARTWORK_FAIL {exc}", file=sys.stderr)
        sys.exit(1)
