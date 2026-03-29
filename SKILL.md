---
name: acars-codec
description: >
  Encode and decode ACARS (Aircraft Communications Addressing and Reporting System)
  messages in audio WAV format using MSK (Minimum Shift Keying) modulation at 2400 bps.
  ACARS is the primary digital data link for aircraft worldwide since 1978, used for
  operational messages, flight plans, weather, and telemetry. Use this skill whenever
  the user mentions ACARS, aircraft data link, airline messages, OOOI messages, ARINC
  618, VHF data link, plane text messages, aircraft telemetry, squitter, ACARS decoder,
  or wants to create/analyze aircraft communication WAV files. The generated audio uses
  MSK modulation on baseband tones (like what you'd hear from an SDR), not an actual RF
  carrier. Covers encoding (text to WAV) and decoding (WAV to text).
---

# ACARS Codec

This skill converts between ACARS (Aircraft Communications Addressing and Reporting System)
messages and audio WAV files. ACARS is the industry-standard digital data link for aircraft
communications worldwide, operational since 1978 and still used for operational messages,
flight plans, weather updates, engine data, and crew communications.

The generated WAV files contain baseband MSK-modulated ACARS messages. They represent what
you would hear on an SDR when tuning a VHF ACARS frequency (129.125 MHz, 130.025 MHz, etc.),
and can be decoded by ACARS software decoders (acarsdec, Virtual Radar, acars_sql, etc.).

## Quick reference: the ACARS signal

An ACARS message block consists of:

1. **Preamble** — 128 bits of alternating 1/0 pattern for bit synchronization (11ms at 2400 bps)

2. **Sync character** — One of:
   - `+` (0x2B) = downlink (aircraft to ground)
   - `*` (0x2A) = uplink (ground to aircraft)

3. **SOH** — Start of Header marker (0x01)

4. **Mode** — Single character:
   - `2` = normal message
   - `H` = HF data link message
   - `V` = VHF
   - `A` = ARINC

5. **Aircraft registration** — 7-character ICAO code (e.g., `.N12345` for US, `.N000SQ` for Squitter)

6. **Acknowledgement** — 1 character:
   - `\x15` (NAK) = no previous acknowledgement
   - `y` or `n` = yes/no acknowledgement

7. **Label** — 2-character message type identifier:
   - `_d` = OOOI (out, off, on, in) departure/arrival
   - `H1` = HF data
   - `SA` = ATIS
   - `Q0` = link test
   - `_\x7F` = ping reply
   - Many others defined in ARINC 618

8. **Block ID** — 1 character (0-9 or space for sequence number)

9. **STX** — Start of text (0x02) — signals message body follows

10. **Message text** — Variable length, up to ~220 characters on VHF

11. **ETX/ETB** — End of text (0x03) or end of block (0x17)

12. **BCS** — Block check sequence (CRC-16-CCITT, 2 bytes) over data from SOH through ETX/ETB

13. **DEL** — Suffix marker (0x7F)

## MSK Modulation Details

- **Data rate**: 2400 bps (bits per second)
- **Mark frequency (bit 1)**: 1200 Hz
- **Space frequency (bit 0)**: 1800 Hz
- **Modulation index**: h = 0.5 (defines MSK as "Minimum Shift Keying")
- **Phase continuity**: Continuous phase between symbols
- **Bit period**: 1/2400 = 416.67 microseconds
- **Transmission order**: LSB first for each character (bit 0 first)
- **Parity**: Odd parity added to bit 7 of each character

Each character (8 bits: 7 data + 1 parity) produces 8 sequential MSK tone transitions.
The audio sample rate is 44100 Hz (standard WAV), giving 18.375 samples per bit.

## How to use this skill

There are three Python scripts in the `scripts/` directory:
Use them rather than writing ACARS logic from scratch.

### Encoding (text to ACARS WAV)

```bash
python3 <skill-path>/scripts/acars_encode.py <output.wav> [options]
```

The encoder:
1. Builds an ACARS message from options (registration, label, text)
2. Adds odd parity to each character byte
3. Calculates CRC-16 block check sequence
4. Generates preamble sync pattern
5. MSK-modulates the complete frame
6. Writes a 16-bit mono WAV at 44100 Hz

Options:
- `--registration REG` — Aircraft ICAO code (default `.N12345`)
- `--label LL` — Two-character label (default `_d` for OOOI)
- `--mode M` — Mode character (default `2` for normal)
- `--block-id N` — Block sequence number (default `0`)
- `--text TEXT` — Message text body (default empty)
- `--text-file FILE` — Read message body from file
- `--downlink` — Message is downlink (aircraft→ground), uses `+` sync (default)
- `--uplink` — Message is uplink (ground→aircraft), uses `*` sync
- `--ack CHAR` — Acknowledgement character (default NAK=0x15)
- `--raw-hex HEX` — Raw hex bytes to transmit as complete ACARS block

### Decoding (ACARS WAV to text)

```bash
python3 <skill-path>/scripts/acars_decode.py <input.wav> [output.txt] [options]
```

The decoder:
1. Reads the WAV (any sample rate — resamples to 44100 if needed)
2. MSK-demodulates to extract bits
3. Finds preamble and sync character
4. Extracts message bytes up to ETX/ETB
5. Verifies parity on each byte
6. Verifies CRC-16 block check sequence
7. Parses message fields
8. Outputs decoded message and metadata

Options:
- `--json` — Output as JSON (machine-readable)
- `--verbose` — Include detailed preamble/sync diagnostics

### Testing

```bash
python3 <skill-path>/scripts/acars_test.py [--verbose]
```

Runs full validation suite:
- CRC-16 roundtrips
- Parity encoding/decoding
- MSK modulation/demodulation
- Message field parsing
- Full encode/decode roundtrips
- Edge cases (empty text, max length, special characters)

## Standard ACARS message labels (ARINC 618)

| Label | Meaning                           | Direction  |
|-------|-----------------------------------|------------|
| `_d`  | OOOI (Out/Off/On/In)              | Downlink   |
| `_e`  | Engine/APU data                   | Downlink   |
| `_f`  | Flight planning                   | Both       |
| `_g`  | Gate information                  | Both       |
| `_h`  | Cabin pressurization              | Downlink   |
| `_i`  | Satellite weather                 | Downlink   |
| `_j`  | Crew meal                         | Both       |
| `_k`  | Komm (scheduled checks)           | Both       |
| `_l`  | Learned messages (cabin service)  | Downlink   |
| `_m`  | Maintenance                       | Downlink   |
| `_n`  | Navigation aid status             | Downlink   |
| `_p`  | Pilot info                        | Both       |
| `_r`  | Crew request                      | Downlink   |
| `_s`  | System status                     | Downlink   |
| `_t`  | Technical log                     | Downlink   |
| `_w`  | Weather                           | Downlink   |
| `_x`  | System data                       | Downlink   |
| `_z`  | Printer output                    | Downlink   |
| `H1`  | HF datalink                       | Both       |
| `Q0`  | Link test                         | Both       |
| `SA`  | ATIS                              | Downlink   |
| `QT`  | Squitter (unsolicited data)       | Downlink   |

## Typical workflow

**User wants to encode an ACARS message as audio:**
1. Run the encoder with message text and options
2. Optionally decode the WAV back to verify
3. Deliver the WAV file to the user

**User wants to decode an ACARS recording:**
1. Run the decoder on their WAV
2. Show the parsed message fields
3. Note: Real recordings may have QRM (co-channel interference), fading, or other aircraft
   on the same frequency. The decoder works best on clean single-aircraft signals.

**User wants a roundtrip demonstration:**
1. Encode a test ACARS message to WAV
2. Decode the WAV back to message text
3. Compare original and recovered message
4. Report match quality

**User asks about ACARS format details:**
The quick reference section above covers the message structure, MSK parameters, and common
labels. Key facts: ACARS uses 2400 bps MSK, messages include CRC-16 error checking, parity
is odd on each byte, and the sync character (`+` or `*`) indicates direction.

## Dependencies

The scripts use only `numpy` and the standard library `wave` module.
Install if needed:

```bash
pip install numpy --break-system-packages
```

## References

- ARINC 618 — ACARS Specification (proprietary, defines message structure and labels)
- Typical ACARS frequencies: 129.125 MHz, 130.025 MHz, 130.45 MHz, 131.125 MHz, 131.550 MHz
- Real ACARS uses AM modulation of the MSK onto a VHF carrier; this skill produces baseband
  MSK audio (SDR-type output) suitable for study and simulation
