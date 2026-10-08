#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a one-bar X0X/BB Gen break loop for a SLOOP FM-1 USER sample slot.

Usage:
  python tools/import_x0x_loop.py input.wav output.wav --bpm 120
  python tools/fm1_sample_upload.py load 1 X0X output.wav

SLOOP's existing USER-slot uploader converts this WAV to mono 22050 Hz IMA ADPCM.
The firmware's USER sample format stores zones as one-shots; this helper prepares
the audio only. Tempo-sync playback, slicing, stutter and BB Gen are firmware work.
"""
import argparse
import struct
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sampleio as sio  # noqa: E402

RATE = sio.SLOT_RATE


def write_wav(path: Path, samples):
    pcm = b"".join(
        struct.pack("<h", max(-32768, min(32767, int(round(v * 32767)))))
        for v in samples
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, RATE, RATE * 2, 2, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


def prepare(source: Path, output: Path, bpm: float):
    if not 30.0 <= bpm <= 300.0:
        raise ValueError("BPM must be between 30 and 300")
    sr, samples = sio.read_any_wav(source)
    if not samples or sr <= 0:
        raise ValueError(f"{source}: no usable audio")
    x = sio.resample(samples, sr, RATE)
    wanted = int(round(RATE * 240.0 / bpm))
    if len(x) < wanted * 0.90:
        actual = len(x) / RATE
        raise ValueError(
            f"audio is too short for one bar at {bpm:g} BPM "
            f"({actual:.2f}s available, {wanted / RATE:.2f}s required); "
            "provide a full bar or correct --bpm"
        )
    x = x[:wanted]
    peak = max((abs(v) for v in x), default=0.0)
    if peak < 1e-9:
        raise ValueError(f"{source}: audio is silent")
    # Leave headroom and prevent clipping when encoding the user slot.
    x = [max(-0.95, min(0.95, v * (0.95 / peak))) for v in x]
    write_wav(output, x)
    return len(x), wanted / RATE


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="source WAV from an X0X/BB Gen break")
    ap.add_argument("output", type=Path, help="prepared one-bar WAV")
    ap.add_argument("--bpm", type=float, required=True, help="source loop BPM")
    args = ap.parse_args()
    try:
        n, seconds = prepare(args.input, args.output, args.bpm)
    except (OSError, ValueError, struct.error) as e:
        ap.error(str(e))
    # The existing slot uploader encodes at 22050 Hz; an IMA slot uses about
    # half a byte per decoded sample, so report the expected data footprint.
    encoded = (n + 1) // 2
    if encoded > sio.SLOT_MAX_DATA:
        ap.error(
            f"one bar is {encoded} B of estimated ADPCM, exceeding the "
            f"{sio.SLOT_MAX_DATA} B USER-slot data budget; raise BPM or shorten the loop"
        )
    print(f"Prepared {args.output}: {n} samples, {seconds:.3f}s at {args.bpm:g} BPM")
    print(f"Estimated IMA ADPCM payload: {encoded} B / {sio.SLOT_MAX_DATA} B")
    print(f"Upload with: python tools/fm1_sample_upload.py load 1 X0X {args.output}")


if __name__ == "__main__":
    main()
