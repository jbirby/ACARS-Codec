#!/usr/bin/env python3
"""
ACARS Decoder — Decode ACARS messages from WAV audio files.

Reads MSK-modulated ACARS audio and extracts the message:
  1. Finds preamble sync pattern
  2. Demodulates MSK to bits
  3. Extracts message bytes
  4. Verifies parity on each byte
  5. Verifies CRC-16 block check
  6. Parses and displays message fields

Usage:
    python3 acars_decode.py <input.wav> [output.txt] [options]

Options:
    --json      Output as JSON (machine-readable)
    --verbose   Show detailed sync diagnostics
"""

import sys
import wave
import json
import os
import numpy as np
import argparse
from scipy import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acars_common import (
    SAMPLE_RATE, DATA_RATE, MARK_FREQ, SPACE_FREQ,
    bits_to_bytes, msk_demodulate, parse_acars_message,
    PREAMBLE_BITS, LABELS,
)


def find_preamble_and_sync(bits, verbose=False):
    """
    Find preamble (alternating 10101010...) and sync character.
    Returns (preamble_end_idx, sync_char) or (None, None) if not found.
    """
    # Look for 128 alternating bits (10101010...)
    preamble_pattern = [i % 2 for i in range(PREAMBLE_BITS)]

    # Search for pattern in bits
    best_match_idx = None
    best_match_score = 0

    for start_idx in range(0, len(bits) - PREAMBLE_BITS, 10):
        # Check how many bits match the pattern
        match_count = sum(1 for i in range(PREAMBLE_BITS)
                         if bits[start_idx + i] == preamble_pattern[i])
        if match_count > best_match_score:
            best_match_score = match_count
            best_match_idx = start_idx

    if best_match_idx is None or best_match_score < PREAMBLE_BITS - 10:
        if verbose:
            print(f"Warning: weak preamble match (score {best_match_score}/{PREAMBLE_BITS})")

    if best_match_idx is not None:
        preamble_end = best_match_idx + PREAMBLE_BITS
        # Extract sync character (next 8 bits after preamble)
        if preamble_end + 8 <= len(bits):
            sync_bits = bits[preamble_end:preamble_end+8]
            sync_byte = bits_to_bytes(sync_bits)[0]
            if verbose:
                print(f"Preamble found at bit {best_match_idx} (score {best_match_score}/{PREAMBLE_BITS})")
                print(f"Sync byte: 0x{sync_byte:02x} ({chr(sync_byte)})")
            return preamble_end, sync_byte
    else:
        if verbose:
            print("Warning: no preamble found, starting from beginning")
        return 0, None


def decode_wav(input_path, output_path=None, json_output=False, verbose=False):
    """Decode an ACARS WAV file."""

    print(f"ACARS Decoder")
    print(f"=============")
    print(f"Input: {input_path}")
    print()

    # Read WAV
    try:
        with wave.open(input_path, 'rb') as w:
            frames = w.readframes(w.getnframes())
            sample_rate = w.getframerate()
            num_channels = w.getnchannels()
    except Exception as e:
        print(f"Error reading WAV: {e}", file=sys.stderr)
        sys.exit(1)

    # Convert to float
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    if num_channels > 1:
        # Mono mix
        audio = audio.reshape(-1, num_channels)
        audio = np.mean(audio, axis=1)

    # Resample if necessary
    if sample_rate != SAMPLE_RATE:
        print(f"Resampling from {sample_rate} Hz to {SAMPLE_RATE} Hz...")
        num_samples = int(len(audio) * SAMPLE_RATE / sample_rate)
        audio = signal.resample(audio, num_samples)

    print(f"Audio: {len(audio)} samples ({len(audio) / SAMPLE_RATE:.2f} sec)")
    print(f"Sample rate: {SAMPLE_RATE} Hz")

    # Skip silence at the beginning
    threshold = 0.02
    signal_start = 0
    for i, sample in enumerate(audio):
        if abs(sample) > threshold:
            signal_start = i
            break

    if signal_start > 0:
        print(f"Signal begins at sample {signal_start} ({signal_start / SAMPLE_RATE:.3f} sec), skipping silence")
        audio = audio[signal_start:]
    print()

    # MSK demodulate
    print(f"MSK Demodulating...")
    print(f"  Data rate: {DATA_RATE} bps")
    print(f"  Mark frequency (0): {MARK_FREQ} Hz")
    print(f"  Space frequency (1): {SPACE_FREQ} Hz")
    print()

    bits = msk_demodulate(audio, SAMPLE_RATE, DATA_RATE, MARK_FREQ, SPACE_FREQ)
    print(f"Extracted {len(bits)} bits")
    print()

    # Find preamble and sync
    preamble_end, sync_byte = find_preamble_and_sync(bits, verbose=verbose)
    if preamble_end is not None:
        bits = bits[preamble_end:]
    else:
        if verbose:
            print("Using bits from start")
        bits = bits

    print(f"Extracting message bytes...")
    # Extract all bytes from bits
    data_bytes = bits_to_bytes(bits)
    print(f"Extracted {len(data_bytes)} bytes")
    print()

    # Parse message
    print(f"Parsing ACARS message...")
    result = parse_acars_message(data_bytes)
    print()

    if result['error']:
        print(f"Parse error: {result['error']}")
        if not json_output:
            return

    # Display results
    if not json_output:
        print(f"Sync: {result['sync']} ({'downlink' if result['sync'] == '+' else 'uplink'})")
        print(f"Mode: {result['mode']}")
        print(f"Registration: {result['registration']}")
        print(f"Acknowledgement: {result['ack']}")
        print(f"Label: {result['label']}", end='')
        if result['label'] in LABELS:
            print(f" ({LABELS[result['label']]})")
        else:
            print()
        print(f"Block ID: {result['block_id']}")
        print(f"Message text: {repr(result['text'])}")
        print()
        print(f"Parity valid: {result['parity_valid']}")
        print(f"CRC valid: {result['crc_valid']}")
        print()

    # Output
    if json_output:
        output = {
            'sync': result['sync'],
            'mode': result['mode'],
            'registration': result['registration'],
            'ack': result['ack'],
            'label': result['label'],
            'block_id': result['block_id'],
            'text': result['text'],
            'parity_valid': result['parity_valid'],
            'crc_valid': result['crc_valid'],
            'error': result['error'],
        }
        json_str = json.dumps(output, indent=2)
        if output_path:
            with open(output_path, 'w') as f:
                f.write(json_str)
            print(f"JSON output written to: {output_path}")
        else:
            print(json_str)
    else:
        if output_path:
            with open(output_path, 'w') as f:
                f.write(result['text'] if result['text'] else "")
            print(f"Message text written to: {output_path}")
        else:
            print(result['text'] if result['text'] else "(empty)")


def main():
    parser = argparse.ArgumentParser(description='ACARS Decoder: MSK WAV to message')
    parser.add_argument('input', help='Input WAV file')
    parser.add_argument('output', nargs='?', help='Output text/JSON file (optional)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--verbose', action='store_true', help='Verbose diagnostics')

    args = parser.parse_args()

    decode_wav(args.input, args.output, args.json, args.verbose)


if __name__ == '__main__':
    main()
