"""Opt-in official-release provisioning for English KWS/ASR and Kokoro ONNX.

Run explicitly as the local owner. Refuses unsafe archives, checks published
file lengths, verifies pinned Kokoro SHA-256, and records first-use SHA-256 for
sherpa archives whose upstream GitHub release exposes no digest. First-use
sherpa hashes are NOT independent cryptographic provenance.
"""
from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ASSETS = (
    ("kws", "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
     "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2",
     17626723, None),
    ("asr", "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
     "sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2",
     310414022, None),
    ("kokoro", "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
     "model-files-v1.1/kokoro-v1.0.fp16.onnx", 163527961,
     "f3a290d384fbb27966d462905c71a46cef9e5fd00516b40df32a0b4afe77ac96"),
    ("voices", "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
     "model-files-v1.1/voices-v1.0.bin", 28214398,
     "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
)


def download(url: str, dest: Path, length: int, expected_sha256: str | None) -> str:
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "AURA-Voice-Provision/1.0"})
    with urllib.request.urlopen(request, timeout=70) as response, dest.open("wb") as sink:
        if response.geturl().split(":", 1)[0] != "https":
            raise RuntimeError("HTTPS-only download required")
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > length:
                raise RuntimeError("Asset size exceeds pinned release metadata")
            digest.update(chunk)
            sink.write(chunk)
        if total != length:
            raise RuntimeError(f"Asset size mismatch: {total} != {length}")
    actual = digest.hexdigest()
    if expected_sha256 is not None and actual != expected_sha256:
        raise RuntimeError("Pinned SHA-256 mismatch: " + url.rsplit("/", 1)[-1])
    return actual


def unpack_safe(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:bz2") as tar:
        members = tar.getmembers()
        if len(members) > 350:
            raise RuntimeError("Too many archive members")
        for item in members:
            parts = Path(item.name).parts
            if not parts or any(p in {"..", "."} for p in parts):
                raise RuntimeError("Unsafe archive member path")
            if item.issym() or item.islnk() or item.isdev():
                raise RuntimeError("Archive contains links or devices")
            if not item.isdir() and not item.isfile():
                raise RuntimeError("Unsafe archive member type")
            if item.size > 600_000_000:
                raise RuntimeError("Oversized archive member")
            if item.isfile():
                leaf = Path(item.name).name
                if not (leaf.endswith((".onnx", ".txt", ".model")) or leaf in {"README", "LICENSE"}):
                    continue
                target_file = target / leaf
                if target_file.exists():
                    raise RuntimeError("Duplicate model artifact: " + leaf)
                stream = tar.extractfile(item)
                if stream is None:
                    raise RuntimeError("Archive member extraction failed")
                with stream, target_file.open("wb") as out:
                    shutil.copyfileobj(stream, out, length=1024 * 1024)


def unique(root: Path, pattern: str) -> Path:
    files = list(root.glob(pattern))
    if len(files) > 1 and pattern.endswith(".onnx"):
        files = [p for p in files if "int8" not in p.name.lower()
                 and "quant" not in p.name.lower()]
    if len(files) != 1:
        raise RuntimeError(f"Model layout does not contain exactly one {pattern}: {files}")
    return files[0].resolve()


def write_env(env_path: Path, values: dict[str, str]) -> None:
    original = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = [line for line in original.splitlines()
             if not any(line.startswith(key + "=") for key in values)]
    lines.extend(key + "=" + value for key, value in values.items())
    # Explicit owner-controlled configuration, never written to tracked source.
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accept-model-licenses", action="store_true")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    if not args.accept_model_licenses:
        parser.error("Review model licenses and pass --accept-model-licenses explicitly")
    root = args.destination.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    receipts: dict[str, dict] = {}
    for name, url, length, expected in ASSETS:
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        asset = folder / url.rsplit("/", 1)[-1]
        if not asset.is_file() or asset.stat().st_size != length:
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as f:
                temp = Path(f.name)
            try:
                actual = download(url, temp, length, expected)
                os.replace(temp, asset)
            finally:
                temp.unlink(missing_ok=True)
        else:
            actual = hashlib.sha256(asset.read_bytes()).hexdigest()
            if expected is not None and actual != expected:
                raise RuntimeError("Existing asset checksum mismatch")
        receipts[name] = {"url": url, "sha256": actual,
                          "provenance": "sha256-pinned" if expected else "first-use-sha256-only"}
        if name in {"kws", "asr"}:
            # Safe to rerun; already-extracted source artifacts are immutable
            # relative to their verified archive receipt.
            if not list(folder.glob("encoder*.onnx")):
                unpack_safe(asset, folder)
    kws, asr = root / "kws", root / "asr"
    try:
        import sentencepiece
    except ImportError as exc:
        raise RuntimeError("Install sentencepiece in the Core virtual environment") from exc
    bpe = unique(kws, "*.model")
    sp = sentencepiece.SentencePieceProcessor(model_file=str(bpe))
    pieces = sp.encode("AURA", out_type=str)
    known = {x.split()[0] for x in unique(kws, "tokens.txt").read_text(encoding="utf-8").splitlines() if x.strip()}
    if not pieces or not set(pieces).issubset(known):
        raise RuntimeError("AURA wake phrase cannot be encoded by selected KWS BPE model")
    keyword_file = kws / "keywords.txt"
    keyword_file.write_text(" ".join(pieces) + " @AURA\n", encoding="utf-8")
    env = {
        "AURA_NIRVANA_VOICE_ENABLED": "1",
        "AURA_SHERPA_MODEL_LICENSE_ACCEPTED": "1",
        "AURA_SHERPA_KWS_TOKENS_PATH": str(unique(kws, "tokens.txt")),
        "AURA_SHERPA_KWS_ENCODER_PATH": str(unique(kws, "encoder*.onnx")),
        "AURA_SHERPA_KWS_DECODER_PATH": str(unique(kws, "decoder*.onnx")),
        "AURA_SHERPA_KWS_JOINER_PATH": str(unique(kws, "joiner*.onnx")),
        "AURA_SHERPA_KWS_KEYWORDS_PATH": str(keyword_file.resolve()),
        "AURA_SHERPA_ASR_TOKENS_PATH": str(unique(asr, "tokens.txt")),
        "AURA_SHERPA_ASR_ENCODER_PATH": str(unique(asr, "encoder*.onnx")),
        "AURA_SHERPA_ASR_DECODER_PATH": str(unique(asr, "decoder*.onnx")),
        "AURA_SHERPA_ASR_JOINER_PATH": str(unique(asr, "joiner*.onnx")),
        "AURA_KOKORO_ONNX_ENABLED": "1",
        "AURA_KOKORO_ONNX_MODEL": str((root / "kokoro" / "kokoro-v1.0.fp16.onnx").resolve()),
        "AURA_KOKORO_ONNX_VOICES": str((root / "voices" / "voices-v1.0.bin").resolve()),
        "AURA_TTS_PROVIDER": "kokoro",
    }
    (root / "install-receipts.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")
    write_env(args.env_file, env)
    print("English KWS, English ASR and en-US Kokoro ONNX files provisioned.")
    print("Sherpa release assets have no upstream digest; SHA-256 receipts are TOFU, not pinned provenance.")
    print("Verify the printed SHA-256 receipts independently before production use.")


if __name__ == "__main__":
    main()
