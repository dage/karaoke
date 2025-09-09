#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any
from tqdm import tqdm
from boto3.s3.transfer import TransferConfig

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
from dotenv import load_dotenv, find_dotenv


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"


def _load_env() -> None:
    # Load variables from project .env if present
    load_dotenv(find_dotenv())


def _env_path() -> Path | None:
    path = find_dotenv()
    return Path(path) if path else None


def _is_var_commented(env_text: str, var_name: str) -> bool:
    prefix = f"# {var_name}="
    alt_prefix = f"#{var_name}="
    for line in env_text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(prefix) or stripped.startswith(alt_prefix):
            return True
    return False


def _validate_aws_env() -> dict:
    required = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
        "S3_BUCKET_NAME",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        hints: list[str] = []
        env_file = _env_path()
        env_text = ""
        if env_file and env_file.exists():
            try:
                env_text = env_file.read_text(encoding="utf-8")
            except Exception:
                env_text = ""

        for name in missing:
            if env_text and _is_var_commented(env_text, name):
                hints.append(f"- {name} appears commented out in .env. Please uncomment and set a value.")
            else:
                hints.append(f"- Set {name}=... in your .env file.")

        msg = [
            "Missing required environment variables for S3 upload:",
            ", ".join(missing),
        ] + hints
        raise RuntimeError("\n".join(msg))

    return {name: os.environ[name] for name in required}


def _generate_folder_name(prefix: str = "karaoke_") -> str:
    # Simple unique-ish id: yyyymmdd-hhmmss + short random suffix from time
    ts = time.strftime("%Y%m%d-%H%M%S")
    # add milliseconds entropy
    suffix = str(int((time.time() % 1) * 1000000)).rjust(6, "0")
    return f"{prefix}{ts}_{suffix}"


def _build_s3_client(aws_access_key_id: str, aws_secret_access_key: str, aws_region: str):
    timeout_cfg = Config(connect_timeout=20, read_timeout=300, retries={"max_attempts": 3})
    return boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=aws_region,
        config=timeout_cfg,
    )


def _s3_base_url(bucket: str, region: str) -> str:
    # Virtual-hosted–style URL. For most regions: https://{bucket}.s3.{region}.amazonaws.com
    # us-east-1 historically omits region in hostname; but modern form works with region as well.
    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com"
    return f"https://{bucket}.s3.{region}.amazonaws.com"


def _ensure_prefix_exists(s3_client, bucket: str, prefix: str) -> None:
    # Create a zero-byte object as a folder marker so the prefix appears in consoles
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    try:
        s3_client.put_object(Bucket=bucket, Key=prefix)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        raise RuntimeError(f"Failed to create folder '{prefix}' in bucket '{bucket}': {code}") from e


def _rewrite_manifest_with_absolute_urls(
    manifest: Dict[str, Any],
    base_http_url: str,
    folder_prefix: str,
) -> Dict[str, Any]:
    # base_http_url like https://bucket.s3.region.amazonaws.com
    # folder_prefix like karaoke_20240101-010101_123456
    def to_url(rel: str) -> str:
        key = f"{folder_prefix}/{rel}" if not rel.startswith("/") else f"{folder_prefix}{rel}"
        return f"{base_http_url}/{key}"

    result = dict(manifest)  # shallow copy
    # These keys in local manifest are relative file names inside output/
    for k in ("words", "sentences", "audio_file"):
        v = manifest.get(k)
        if isinstance(v, str) and v:
            result[k] = to_url(v)
    return result


def _upload_with_progress(s3, local_path: Path, bucket: str, key: str, *, extra_args: dict | None = None) -> None:
    size = local_path.stat().st_size
    transfer_cfg = TransferConfig(
        multipart_threshold=64 * 1024,   # 64KB threshold
        multipart_chunksize=64 * 1024,   # 64KB parts
        max_concurrency=1,               # simplest, serial callbacks
        use_threads=False,
    )
    with tqdm(
        total=size,
        desc=local_path.name,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        leave=False,
        file=sys.stderr,
    ) as pbar:
        def _cb(n: int) -> None:
            pbar.update(n)

        s3.upload_file(
            str(local_path),
            bucket,
            key,
            Callback=_cb,
            ExtraArgs=(extra_args or {}),
            Config=transfer_cfg,
        )


def _curl_verify(url: str) -> None:
    if not shutil.which("curl"):
        sys.stderr.write("curl not found; skipping public access check.\n")
        sys.stderr.flush()
        return
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tmp_path = tmp.name
    tmp.close()
    try:
        completed = subprocess.run(
            ["curl", "-sS", "-L", "-o", tmp_path, "-w", "%{http_code}", url],
            capture_output=True,
            text=True,
        )
        http_code = (completed.stdout or "").strip()
        if http_code == "200":
            print(f"✅ Publicly accessible (HTTP 200). Saved to: {tmp_path}")
        else:
            print(f"❌ Not publicly accessible (HTTP {http_code}).")
    finally:
        # Keep the file for debugging on success; remove on failure to avoid clutter
        pass


def _curl_headers(
    url: str,
    *,
    extra_headers: dict[str, str] | None = None,
    method: str = "HEAD",
) -> tuple[int, dict[str, str]]:
    """Return (status_code, headers) using curl for reliability and parity with CLI checks.

    Follows redirects and returns the final response headers. Header keys are lower-cased.
    """
    if not shutil.which("curl"):
        return (0, {})
    cmd: list[str] = ["curl", "-sS", "-D", "-", "-o", "/dev/null", "-L"]
    if method.upper() == "HEAD":
        cmd.append("-I")
    if extra_headers:
        for k, v in extra_headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
    cmd.append(url)
    completed = subprocess.run(cmd, capture_output=True, text=True)
    raw = completed.stdout
    status_code = 0
    headers: dict[str, str] = {}
    # Parse the last header block (after redirects)
    for line in raw.splitlines():
        line = line.strip("\r\n")
        if not line:
            continue
        if line.startswith("HTTP/"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                status_code = int(parts[1])
            headers = {}
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return status_code, headers


def _normalize_content_type(value: str) -> str:
    return (value or "").split(";")[0].strip().lower()


def _check_s3_asset(
    url: str,
    *,
    expected_types: list[str],
    origin: str = "https://example.dev",
) -> list[str]:
    """Run a set of header-level validations against an S3-hosted asset.

    - Verifies Content-Type via HEAD
    - Verifies CORS (Access-Control-Allow-Origin) presence for HEAD with Origin
    - Verifies Range support (206 + Content-Range for Range: bytes=0-1)
    Returns a list of human-readable issue strings.
    """
    issues: list[str] = []

    # Basic HEAD
    status, headers = _curl_headers(url, method="HEAD")
    if status == 0 and not headers:
        issues.append("curl not found; cannot perform header checks")
        return issues
    ct = _normalize_content_type(headers.get("content-type", ""))
    if ct not in [et.lower() for et in expected_types]:
        issues.append(
            f"Wrong Content-Type '{headers.get('content-type', '')}' for {url} (expected one of: {', '.join(expected_types)})"
        )

    # CORS on HEAD with Origin
    status_o, headers_o = _curl_headers(url, extra_headers={"Origin": origin}, method="HEAD")
    allow_origin = headers_o.get("access-control-allow-origin")
    if allow_origin not in ("*", origin):
        issues.append(
            f"Missing or invalid Access-Control-Allow-Origin for {url} on HEAD with Origin (got: {allow_origin!r})"
        )

    # Range request (HEAD with Range works on S3; expect 206 + Content-Range)
    status_r, headers_r = _curl_headers(
        url,
        extra_headers={"Origin": origin, "Range": "bytes=0-1"},
        method="HEAD",
    )
    content_range = headers_r.get("content-range", "")
    if status_r != 206 or not content_range.startswith("bytes 0-1/"):
        issues.append(
            f"Range check failed for {url}: expected 206 with Content-Range 'bytes 0-1/...', got {status_r} and '{content_range}'"
        )

    return issues


def upload_output_and_get_manifest() -> tuple[str, dict]:
    """Upload files under output/ to S3 and return (manifest_url, rewritten_manifest).

    This function performs the same upload work as the CLI, but returns values
    for programmatic use. Caller is responsible for any post-upload validation.
    Raises on errors.
    """
    _load_env()

    if not OUTPUT_DIR.exists() or not OUTPUT_DIR.is_dir():
        raise RuntimeError(f"output directory not found at {OUTPUT_DIR}")

    env_vals = _validate_aws_env()
    bucket = env_vals["S3_BUCKET_NAME"]
    region = env_vals["AWS_REGION"]
    s3 = _build_s3_client(
        env_vals["AWS_ACCESS_KEY_ID"],
        env_vals["AWS_SECRET_ACCESS_KEY"],
        env_vals["AWS_REGION"],
    )

    folder = _generate_folder_name("karaoke_")
    _ensure_prefix_exists(s3, bucket, folder)

    base_http = _s3_base_url(bucket, region)

    # Collect files under output/
    local_files: list[Path] = [p for p in OUTPUT_DIR.iterdir() if p.is_file()]

    # Load local manifest.json so we can rewrite a temp copy with absolute URLs
    local_manifest_path = OUTPUT_DIR / "manifest.json"
    if not local_manifest_path.exists():
        raise RuntimeError(f"manifest not found at {local_manifest_path}")
    with local_manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    rewritten = _rewrite_manifest_with_absolute_urls(manifest, base_http, folder)

    # Create temp file for manifest
    temp_manifest_path = Path(tempfile.gettempdir()) / f"manifest_{folder}.json"
    with temp_manifest_path.open("w", encoding="utf-8") as f:
        json.dump(rewritten, f, ensure_ascii=False, indent=2)

    # Upload all files first, excluding manifest.json; we'll upload temp manifest last
    for path in local_files:
        if path.name == "manifest.json":
            continue
        key = f"{folder}/{path.name}"
        # Status to stderr so stdout remains clean for the final manifest URL
        sys.stderr.write(f"Uploading {path} -> s3://{bucket}/{key}\n")
        sys.stderr.flush()

        # Set appropriate ContentType based on file extension
        extra_args = {}
        if path.suffix.lower() == ".mp3":
            extra_args["ContentType"] = "audio/mpeg"
        elif path.suffix.lower() in {".txt", ".tsv"}:
            extra_args["ContentType"] = "text/plain"

        _upload_with_progress(s3, path, bucket, key, extra_args=extra_args)

    # Upload rewritten manifest
    manifest_key = f"{folder}/manifest.json"
    sys.stderr.write(f"Uploading manifest -> s3://{bucket}/{manifest_key}\n")
    sys.stderr.flush()
    _upload_with_progress(
        s3,
        temp_manifest_path,
        bucket,
        manifest_key,
        extra_args={"ContentType": "application/json"},
    )

    # Remove temp manifest
    try:
        temp_manifest_path.unlink(missing_ok=True)
    except Exception:
        pass

    manifest_url = f"{base_http}/{manifest_key}"
    return manifest_url, rewritten


def main() -> int:
    try:
        # Early checks to preserve historical exit codes
        if not OUTPUT_DIR.exists() or not OUTPUT_DIR.is_dir():
            print(f"Error: output directory not found at {OUTPUT_DIR}")
            return 2
        local_manifest_path = OUTPUT_DIR / "manifest.json"
        if not local_manifest_path.exists():
            print(f"Error: manifest not found at {local_manifest_path}")
            return 3

        manifest_url, rewritten = upload_output_and_get_manifest()

        print(f"\nManifest URL: {manifest_url}")
        _curl_verify(manifest_url)

        # Additional validation: check audio and text assets directly on S3 using curl header analysis
        problems: list[str] = []
        audio_url = rewritten.get("audio_file")
        words_url = rewritten.get("words")
        sentences_url = rewritten.get("sentences")

        if isinstance(audio_url, str) and audio_url:
            problems += _check_s3_asset(
                audio_url,
                expected_types=[
                    "audio/mpeg",
                    "audio/mp3",
                ],
            )

        if isinstance(words_url, str) and words_url:
            problems += _check_s3_asset(
                words_url,
                expected_types=[
                    "text/plain",
                ],
            )

        if isinstance(sentences_url, str) and sentences_url:
            problems += _check_s3_asset(
                sentences_url,
                expected_types=[
                    "text/plain",
                ],
            )

        if problems:
            print("Validation issues detected:")
            for p in problems:
                print(f"❌ {p}")
            return 20
        else:
            print("✅ All asset header checks passed (Content-Type, CORS, Range).")
        return 0

    except (NoCredentialsError, ClientError) as e:
        print(f"AWS error: {e}")
        return 10
    except RuntimeError as e:
        print(f"Error: {e}")
        return 11
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 12


if __name__ == "__main__":
    raise SystemExit(main())
