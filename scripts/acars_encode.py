#!/usr/bin/env python3
"""
ACARS Encoder — Convert ACARS messages to audio WAV using MSK modulation.

Produces a standards-compliant ACARS MSK transmission:
  1. Preamble (128 bits alternating 10101010...)
  2. Sync character (+ for downlink, * for uplink)
  3. Message header and body with CRC-16 block check
  4. All bytes include odd parity

The resulting WAV sounds like ACARS baseband (what you'd hear on an SDR tuned
to 129.125 MHz or another ACARS frequency).

Usage:
    python3 acars_encode.py <output.wav> [options]

Options:
    --registration REG    Aircraft ICAO code (default .N12345)
    --label LL           Two-character message label (default _d)
    --mode M             Mode character (default 2)
    --block-id N         Block sequence number (default 0)
    --text TEXT          Message text body
    --text-file FILE     Read message text from file
    --downlink           Downlink message +, aircraft→ground (default)
    --uplink             Uplink message *, ground→aircraft
    --ack CHAR           Acknowledgement character (default NAK)
    --raw-hex HEX        Raw hex bytes to transmit
"""

import sys
import wave
import os
import numpy as np
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acars_common import (
    SAMPLE_RATE, DATA_RATE, MARK_FREQ, SPACE_FREQ,
    build_acars_message, bytes_to_bits, msk_modulate,
)


def generate_silence(duration, sample_rate):
    """Generate silence (zeros) for a duration in seconds."""
    return np.zeros(int(duration * sample_rate))


def encode_message(registration, label, mode, block_id, text, ack, downlink, output_path):
    """Encode an ACARS message as a WAV file."""

    print(f"ACARS Encoder")
    print(f"=============")
    print(f"Registration: {registration}")
    print(f"Label: {label}")
    print(f"Mode: {mode}")
    print(f"Block ID: {block_id}")
    print(f"Direction: {'Downlink (+)' if downlink else 'Uplink (*)'}")
    print(f"Message text: {repr(text[:60])}{'...' if len(text) > 60 else ''}")
    print()

    # Build message
    msg_bytes = build_acars_message(
        mode=mode,
        registration=registration,
        label=label,
        block_id=block_id,
        text=text,
        ack=ack,
        downlink=downlink
    )

    print(f"Message bytes: {len(msg_bytes)}")
    print(f"  Preamble: 16 bytes (128 bits)")
    print(f"  Header + text + CRC: {len(msg_bytes) - 16} bytes")
    print()

    # Convert to bits (LSB first)
    bits = bytes_to_bits(msg_bytes)
    print(f"Total bits: {len(bits)}")

    # MSK modulate
    print(f"MSK Modulating...")
    print(f"  Data rate: {DATA_RATE} bps")
    print(f"  Mark frequency (0): {MARK_FREQ} Hz")
    print(f"  Space frequency (1): {SPACE_FREQ} Hz")
    print(f"  Modulation index h: 0.5 (MSK)")
    print()

    audio = msk_modulate(bits, SAMPLE_RATE, DATA_RATE, MARK_FREQ, SPACE_FREQ)

    # Add brief silence before and after
    silence_before = generate_silence(0.1, SAMPLE_RATE)
    silence_after = generate_silence(0.1, SAMPLE_RATE)
    audio = np.concatenate([silence_before, audio, silence_after])

    # Normalize
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.90

    # Convert to 16-bit PCM
    pcm = (audio * 32767).astype(np.int16)

    # Write WAV
    with wave.open(output_path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())

    print(f"Encoded to: {output_path}")
    print(f"Duration: {len(audio) / SAMPLE_RATE:.2f} seconds")
    print(f"Done.")


def main():
    parser = argparse.ArgumentParser(description='ACARS Encoder: text to MSK WAV')
    parser.add_argument('output', help='Output WAV file')
    parser.add_argument('--registration', default='.N12345', help='Aircraft ICAO code')
    parser.add_argument('--label', default='_d', help='Two-char message label')
    parser.add_argument('--mode', default='2', help='Mode character')
    parser.add_argument('--block-id', default='0', help='Block sequence number')
    parser.add_argument('--text', default='', help='Message text body')
    parser.add_argument('--text-file', help='Read message text from file')
    parser.add_argument('--downlink', action='store_true', default=True,
                        help='Downlink (aircraft→ground, default)')
    parser.add_argument('--uplink', action='store_true', help='Uplink (ground→aircraft)')
    parser.add_argument('--ack', default=None, help='Acknowledgement character')
    parser.add_argument('--raw-hex', help='Raw hex bytes to transmit')

    args = parser.parse_args()

    # Determine direction
    downlink = not args.uplink

    # Get message text
    text = args.text
    if args.text_file:
        with open(args.text_file, 'r') as f:
            text = f.read()

    # Handle raw hex mode
    if args.raw_hex:
        try:
            raw_bytes = bytes.fromhex(args.raw_hex)
            # For raw hex, write directly to WAV
            bits = [int(b) for b in ''.join(format(byte, '08b') for byte in raw_bytes)]
            audio = msk_modulate(bits, SAMPLE_RATE, DATA_RATE, MARK_FREQ, SPACE_FREQ)
            silence_before = generate_silence(0.1, SAMPLE_RATE)
            silence_after = generate_silence(0.1, SAMPLE_RATE)
            audio = np.concatenate([silence_before, audio, silence_after])
            peak = np.max(np.abs(audio))
            if peak > 0:
                audio = audio / peak * 0.90
            pcm = (audio * 32767).astype(np.int16)
            with wave.open(args.output, 'w') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(pcm.tobytes())
            print(f"Raw hex encoded to: {args.output}")
            return
        except Exception as e:
            print(f"Error with raw hex: {e}", file=sys.stderr)
            sys.exit(1)

    encode_message(
        registration=args.registration,
        label=args.label,
        mode=args.mode,
        block_id=args.block_id,
        text=text,
        ack=args.ack,
        downlink=downlink,
        output_path=args.output
    )


if __name__ == '__main__':
    main()
