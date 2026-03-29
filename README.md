# ACARS Codec

A complete implementation of the ACARS (Aircraft Communications Addressing and Reporting System)
codec for encoding and decoding aircraft communications messages in audio WAV format.

## Overview

ACARS is the primary digital data link system for aircraft communications worldwide, operational
since 1978. This codec implements the complete ACARS message structure with MSK (Minimum Shift
Keying) modulation at 2400 bps, suitable for VHF frequencies like 129.125 MHz and 130.025 MHz.

The generated audio files contain baseband MSK-modulated ACARS signals that sound like what you
would hear on an SDR tuned to an ACARS frequency.

## Features

- **Encoding**: Convert ACARS messages to baseband MSK audio WAV files
- **Decoding**: Extract ACARS messages from WAV audio with full parsing and verification
- **Full Protocol Support**: Preamble, sync, header, text, CRC-16 block check, parity
- **Flexible Message Generation**: Custom registration, label, mode, acknowledgement
- **Error Detection**: Parity verification and CRC-16 validation on decode
- **Multiple Labels**: Support for common ACARS label types (OOOI, ATIS, HF data, etc.)

## File Structure

```
acars/
├── SKILL.md                 # Skill definition and documentation
├── README.md                # This file
└── scripts/
    ├── acars_common.py      # Shared ACARS utilities and protocol
    ├── acars_encode.py      # Encoder: message text → WAV
    ├── acars_decode.py      # Decoder: WAV → message text
    └── acars_test.py        # Test suite
```

## Installation

Install dependencies:

```bash
pip install numpy scipy --break-system-packages
```

The scripts use `numpy`, `scipy`, and Python's standard library `wave` module.

## Quick Start

### Encoding (Message to WAV)

```bash
python3 scripts/acars_encode.py output.wav \
    --registration .N12345 \
    --label _d \
    --text "OUT OF KJFK 14:32Z"
```

### Decoding (WAV to Message)

```bash
python3 scripts/acars_decode.py output.wav
```

### Running Tests

```bash
python3 scripts/acars_test.py
```

All tests should pass.

## Command-Line Usage

### acars_encode.py

```
usage: acars_encode.py <output.wav> [options]

positional arguments:
  output                Output WAV file

options:
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
```

### acars_decode.py

```
usage: acars_decode.py <input.wav> [output.txt] [options]

positional arguments:
  input                Input WAV file
  output               Output text file (optional)

options:
  --json               Output as JSON (machine-readable)
  --verbose            Show detailed diagnostics
```

## Message Format

ACARS messages consist of:

1. **Preamble** (128 bits) - alternating 1/0 pattern for synchronization
2. **Sync character** - `+` for downlink, `*` for uplink
3. **SOH** (0x01) - Start of header
4. **Mode** - single character (typically `2`)
5. **Registration** - 7-character aircraft ICAO code (e.g., `.N12345`)
6. **Acknowledgement** - 1 character (NAK=0x15 if none)
7. **Label** - 2-character message type (e.g., `_d` for OOOI)
8. **Block ID** - sequence number (0-9 or space)
9. **STX** (0x02) - Start of text
10. **Message text** - variable length (up to ~220 chars on VHF)
11. **ETX** (0x03) - End of text
12. **CRC-16** - 2-byte block check sequence (CCITT polynomial)
13. **DEL** (0x7F) - End marker

All bytes include odd parity on bit 7.

## MSK Modulation

- **Data rate**: 2400 bits per second
- **Mark frequency (0 bits)**: 1200 Hz
- **Space frequency (1 bits)**: 1800 Hz
- **Modulation index**: h = 0.5 (defines MSK)
- **Phase continuity**: Continuous phase between symbols
- **Audio sample rate**: 44100 Hz (standard WAV)
- **Transmission order**: LSB first for each byte

## Common Message Labels

| Label | Meaning                    | Direction |
|-------|----------------------------|-----------|
| `_d`  | OOOI (Out/Off/On/In)       | Downlink  |
| `_e`  | Engine/APU data            | Downlink  |
| `_m`  | Maintenance                | Downlink  |
| `_s`  | System status              | Downlink  |
| `_w`  | Weather                    | Downlink  |
| `H1`  | HF datalink                | Both      |
| `Q0`  | Link test                  | Both      |
| `SA`  | ATIS                       | Downlink  |
| `QT`  | Squitter (unsolicited)     | Downlink  |

## Examples

### Encode an OOOI departure message:

```bash
python3 scripts/acars_encode.py departure.wav \
    --registration .N12345 \
    --label _d \
    --text "OUT OF KJFK AT 14:32Z CRUISING FL350"
```

### Decode and display as JSON:

```bash
python3 scripts/acars_decode.py departure.wav --json
```

### Encode and immediately decode to verify:

```bash
# Encode
python3 scripts/acars_encode.py test.wav --text "TEST MESSAGE"

# Decode
python3 scripts/acars_decode.py test.wav
```

### Send a system status message (uplink):

```bash
python3 scripts/acars_encode.py uplink.wav \
    --uplink \
    --registration .N99999 \
    --label _s \
    --text "ACU SYSTEM OK"
```

## Python API

Import and use the codec in your own Python code:

```python
from acars_common import (
    build_acars_message,
    parse_acars_message,
    bytes_to_bits,
    bits_to_bytes,
    msk_modulate,
    msk_demodulate,
    crc16_ccitt,
    compute_parity,
)

# Build a message
msg_bytes = build_acars_message(
    registration='.N12345',
    label='_d',
    text='OUT OF KJFK 14:32Z'
)

# Parse a message
result = parse_acars_message(msg_bytes)
print(f"Registration: {result['registration']}")
print(f"Text: {result['text']}")
print(f"CRC valid: {result['crc_valid']}")
```

## Testing

Run the comprehensive test suite:

```bash
python3 scripts/acars_test.py
```

Tests cover:
- Parity encoding/decoding
- CRC-16-CCITT calculation
- Bit/byte conversion (LSB first)
- MSK modulation and demodulation
- Message assembly and parsing
- Full encode/decode roundtrips
- Edge cases (empty text, max length, special characters)

## References

- ARINC 618 - ACARS Specification (proprietary standard)
- VHF ACARS frequencies: 129.125 MHz, 130.025 MHz, 130.45 MHz, 131.125 MHz, 131.550 MHz
- Real ACARS transmissions use AM modulation of the MSK onto a VHF RF carrier

## License

This codec is provided as educational material for understanding and working with ACARS
data link signals.
