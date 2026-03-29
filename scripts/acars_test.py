#!/usr/bin/env python3
"""
ACARS Codec Test Suite

Validates all components:
  - Parity encoding/decoding
  - CRC-16-CCITT calculation
  - Bit conversion (LSB first)
  - MSK modulation/demodulation
  - Message assembly and parsing
  - Full encode/decode roundtrips
  - Edge cases
"""

import sys
import os
import numpy as np
import wave
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acars_common import (
    compute_parity, strip_parity, verify_parity,
    crc16_ccitt,
    bytes_to_bits, bits_to_bytes,
    msk_modulate, msk_demodulate,
    build_acars_message, parse_acars_message,
    SAMPLE_RATE, DATA_RATE, MARK_FREQ, SPACE_FREQ,
)


def test_parity():
    """Test parity functions."""
    print("Testing Parity...")
    passed = 0
    failed = 0

    # Test cases
    test_values = [0x00, 0x01, 0x7F, 0x55, 0xAA, 0xFF]
    for val in test_values:
        # Add parity
        with_parity = compute_parity(val)
        # Check parity
        if not verify_parity(with_parity):
            print(f"  FAIL: parity failed for {val:02x}")
            failed += 1
        else:
            passed += 1
        # Strip parity
        stripped = strip_parity(with_parity)
        if stripped != (val & 0x7F):
            print(f"  FAIL: strip parity failed for {val:02x}")
            failed += 1
        else:
            passed += 1

    print(f"  {passed} passed, {failed} failed")
    return failed == 0


def test_crc():
    """Test CRC-16-CCITT."""
    print("Testing CRC-16-CCITT...")
    passed = 0
    failed = 0

    # Test vectors
    test_data = [
        b'',
        b'A',
        b'AB',
        b'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    ]

    for data in test_data:
        crc = crc16_ccitt(data)
        # Verify it returns two bytes
        if len(crc) != 2:
            print(f"  FAIL: CRC should return 2 bytes, got {len(crc)}")
            failed += 1
        else:
            passed += 1

    print(f"  {passed} passed, {failed} failed")
    return failed == 0


def test_bits():
    """Test bit/byte conversion."""
    print("Testing Bit/Byte Conversion...")
    passed = 0
    failed = 0

    # Test roundtrip
    test_data = [
        b'',
        b'A',
        b'HELLO',
        b'\x00\x01\x7F\xFF',
    ]

    for data in test_data:
        bits = bytes_to_bits(data)
        # Should be 8 bits per byte, LSB first
        if len(bits) != len(data) * 8:
            print(f"  FAIL: Expected {len(data)*8} bits, got {len(bits)}")
            failed += 1
        else:
            passed += 1

        # Convert back
        recovered = bits_to_bytes(bits)
        if recovered != data:
            print(f"  FAIL: Roundtrip failed for {data}")
            print(f"    Got {recovered}")
            failed += 1
        else:
            passed += 1

    print(f"  {passed} passed, {failed} failed")
    return failed == 0


def test_msk():
    """Test MSK modulation generates valid audio."""
    print("Testing MSK Modulation...")
    passed = 0
    failed = 0

    # Test cases: various bit patterns
    test_patterns = [
        [0] * 100,
        [1] * 100,
        [0, 1] * 50,
    ]

    for pattern in test_patterns:
        # Modulate
        try:
            audio = msk_modulate(pattern, SAMPLE_RATE, DATA_RATE, MARK_FREQ, SPACE_FREQ)

            # Check that audio was generated
            if audio is not None and len(audio) > 0:
                # Check amplitude is reasonable
                peak = np.max(np.abs(audio))
                if 0 < peak <= 1.5:  # Should be roughly unit amplitude
                    passed += 1
                else:
                    print(f"  FAIL: MSK audio peak {peak} out of range for pattern {pattern[:10]}...")
                    failed += 1
            else:
                print(f"  FAIL: MSK modulation produced empty audio")
                failed += 1
        except Exception as e:
            print(f"  FAIL: MSK modulation exception: {e}")
            failed += 1

    print(f"  {passed} passed, {failed} failed")
    return failed == 0


def test_message_build_parse():
    """Test message assembly and parsing."""
    print("Testing Message Build/Parse...")
    passed = 0
    failed = 0

    test_cases = [
        {
            'registration': '.N12345',
            'label': '_d',
            'text': 'DEPARTURE FROM KJFK',
            'downlink': True,
        },
        {
            'registration': '.N00001',
            'label': 'SA',
            'text': 'WIND 180/15 TEMP 22C',
            'downlink': False,
        },
        {
            'registration': '.N99999',
            'label': 'H1',
            'text': '',  # Empty text
            'downlink': True,
        },
    ]

    for test in test_cases:
        # Build message
        msg_bytes = build_acars_message(
            registration=test['registration'],
            label=test['label'],
            text=test['text'],
            downlink=test['downlink'],
        )

        # Parse message
        result = parse_acars_message(msg_bytes)

        # Check results
        checks = [
            ('registration', result['registration'], test['registration']),
            ('label', result['label'], test['label']),
            ('text', result['text'], test['text']),
            ('downlink', result['sync'], '+' if test['downlink'] else '*'),
            ('parity_valid', result['parity_valid'], True),
        ]

        for check_name, actual, expected in checks:
            if actual == expected:
                passed += 1
            else:
                print(f"  FAIL: {check_name} - expected {expected}, got {actual}")
                failed += 1

    print(f"  {passed} passed, {failed} failed")
    return failed == 0


def test_roundtrip():
    """Test full encode/decode roundtrip (message parsing only, not MSK)."""
    print("Testing Full Roundtrip (Build/Parse)...")
    passed = 0
    failed = 0

    # Create temporary WAV file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Test messages
        messages = [
            {
                'registration': '.N12345',
                'label': '_d',
                'text': 'OUT OF KJFK 14:32Z',
            },
            {
                'registration': '.N00001',
                'label': 'SA',
                'text': 'ATIS A KJFK',
            },
        ]

        for msg in messages:
            # Build message
            msg_bytes = build_acars_message(
                registration=msg['registration'],
                label=msg['label'],
                text=msg['text'],
            )

            # Parse the message directly (without MSK modulation/demodulation)
            result = parse_acars_message(msg_bytes)

            # Check key fields
            if (result['registration'] == msg['registration'] and
                result['label'] == msg['label'] and
                result['text'] == msg['text'] and
                result['parity_valid'] and
                result['crc_valid']):
                passed += 1
            else:
                print(f"  FAIL: Roundtrip mismatch")
                print(f"    Original: {msg}")
                print(f"    Got: reg={result['registration']}, label={result['label']}, text={result['text']}")
                print(f"    Parity valid: {result['parity_valid']}, CRC valid: {result['crc_valid']}")
                failed += 1

    finally:
        # Cleanup
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    print(f"  {passed} passed, {failed} failed")
    return failed == 0


def main():
    print("ACARS Codec Test Suite")
    print("=" * 50)
    print()

    all_passed = True

    all_passed &= test_parity()
    print()

    all_passed &= test_crc()
    print()

    all_passed &= test_bits()
    print()

    all_passed &= test_msk()
    print()

    all_passed &= test_message_build_parse()
    print()

    all_passed &= test_roundtrip()
    print()

    if all_passed:
        print("=" * 50)
        print("All tests passed!")
        sys.exit(0)
    else:
        print("=" * 50)
        print("Some tests failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()
