#!/usr/bin/env python3
"""
Shared module for ACARS (Aircraft Communications Addressing and Reporting System)
encoding/decoding.

Contains:
  - ACARS message structure (preamble, sync, SOH, mode, registration, etc.)
  - CRC-16-CCITT calculation
  - Parity (odd) encoding/decoding
  - MSK (Minimum Shift Keying) modulation/demodulation
  - Message assembly and parsing

ACARS signal structure:
  [Preamble (128 bits)] [Sync char +/*] [SOH] [Mode] [Registration] [Ack]
  [Label] [Block ID] [STX] [Message text] [ETX/ETB] [CRC-16] [DEL]

  All characters include odd parity on bit 7.
  CRC-16-CCITT computed over bytes from SOH through ETX/ETB.
  Data rate: 2400 bps with continuous-phase MSK at 1200 Hz (0) / 1800 Hz (1).
"""

import numpy as np
import struct

# ============================================================================
# Constants
# ============================================================================

SAMPLE_RATE = 44100          # CD-quality audio sample rate
DATA_RATE = 2400.0           # ACARS data rate in bits per second
MARK_FREQ = 1200.0           # MSK frequency for bit 1 (space)
SPACE_FREQ = 1800.0          # MSK frequency for bit 0 (mark)
PREAMBLE_BITS = 128          # Alternating 10101010... for bit sync

# ACARS sync characters
SYNC_DOWNLINK = 0x2B  # '+' (aircraft to ground)
SYNC_UPLINK = 0x2A    # '*' (ground to aircraft)

# Control characters
SOH = 0x01  # Start of Header
STX = 0x02  # Start of Text
ETX = 0x03  # End of Text
ETB = 0x17  # End of Block
DEL = 0x7F  # Suffix marker

# NAK = no acknowledgement
NAK = 0x15

# ============================================================================
# Common ACARS message labels (ARINC 618)
# ============================================================================

LABELS = {
    '_d': 'OOOI',
    '_e': 'Engine/APU',
    '_f': 'Flight plan',
    '_g': 'Gate info',
    '_h': 'Cabin pressurization',
    '_i': 'Satellite weather',
    '_m': 'Maintenance',
    '_p': 'Pilot info',
    '_s': 'System status',
    '_w': 'Weather',
    'H1': 'HF datalink',
    'Q0': 'Link test',
    'SA': 'ATIS',
    'QT': 'Squitter',
}

# ============================================================================
# Parity Functions
# ============================================================================

def compute_parity(byte_val):
    """Add odd parity to bit 7 of a byte (7 data bits + 1 parity bit)."""
    # Count 1s in lower 7 bits
    bits = byte_val & 0x7F
    ones = bin(bits).count('1')
    # Odd parity: set bit 7 if even number of 1s in data
    if ones % 2 == 0:
        return bits | 0x80
    else:
        return bits


def strip_parity(byte_val):
    """Remove parity bit and return lower 7 bits."""
    return byte_val & 0x7F


def verify_parity(byte_val):
    """Check if byte has correct odd parity. Returns True if valid."""
    ones = bin(byte_val).count('1')
    # Odd parity: total 1s (including parity bit) should be odd
    return ones % 2 == 1


# ============================================================================
# CRC-16-CCITT
# ============================================================================

def crc16_ccitt(data):
    """
    Calculate CRC-16-CCITT (polynomial 0x1021) over a byte sequence.
    Used by ACARS for block check sequence.
    Returns two bytes [high, low].
    """
    crc = 0x0000
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            crc = (crc << 1) & 0xFFFF
            if crc & 0x10000:
                crc ^= 0x1021
    return [(crc >> 8) & 0xFF, crc & 0xFF]


# ============================================================================
# Bit/Byte Conversion
# ============================================================================

def bytes_to_bits(data):
    """
    Convert bytes to bit stream (LSB first, 8 bits per byte including parity).
    Each byte is transmitted LSB first (bit 0 first).
    """
    bits = []
    for byte in data:
        for i in range(8):
            bits.append((byte >> i) & 1)
    return bits


def bits_to_bytes(bits):
    """
    Convert bit stream (LSB first) back to bytes.
    Expects bits in groups of 8 (LSB first).
    """
    data = []
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            if i + j < len(bits):
                byte |= (bits[i + j] << j)
        data.append(byte & 0xFF)
    return bytes(data)


# ============================================================================
# MSK Modulation / Demodulation
# ============================================================================

def msk_modulate(bits, sample_rate, data_rate, mark_freq, space_freq):
    """
    MSK (Minimum Shift Keying) modulate a bit stream.
    Continuous-phase FSK with modulation index h=0.5.

    Args:
        bits: list of 0/1 values
        sample_rate: samples per second (e.g., 44100)
        data_rate: bits per second (e.g., 2400)
        mark_freq: frequency for bit 0 (space) in Hz
        space_freq: frequency for bit 1 (mark) in Hz

    Returns:
        audio: numpy array of samples [-1, 1]
    """
    samples_per_bit = sample_rate / data_rate
    num_samples = int(np.ceil(len(bits) * samples_per_bit))

    # Generate phase trajectory for continuous-phase MSK
    # Frequency deviation: ±(space_freq - mark_freq) / 2
    freq_deviation = (space_freq - mark_freq) / 2.0
    center_freq = (mark_freq + space_freq) / 2.0

    phase = 0.0
    audio = np.zeros(num_samples)

    sample_idx = 0
    for bit_idx, bit in enumerate(bits):
        # Determine frequency for this bit
        if bit == 0:
            freq = mark_freq
        else:
            freq = space_freq

        # Generate samples for this bit period
        bit_start_sample = int(bit_idx * samples_per_bit)
        bit_end_sample = int((bit_idx + 1) * samples_per_bit)

        for sample_idx in range(bit_start_sample, bit_end_sample):
            if sample_idx < num_samples:
                # Time within this bit period
                t = (sample_idx - bit_start_sample) / sample_rate
                # Continuous phase accumulation
                phase += 2 * np.pi * freq * (1.0 / sample_rate)
                audio[sample_idx] = np.sin(phase)

    return audio


def msk_demodulate(audio, sample_rate, data_rate, mark_freq, space_freq):
    """
    MSK demodulate an audio signal to extract bits.
    Uses zero-crossing and amplitude-based tone detection.

    Args:
        audio: numpy array of samples
        sample_rate: samples per second
        data_rate: bits per second
        mark_freq: frequency for bit 0
        space_freq: frequency for bit 1

    Returns:
        bits: list of 0/1 values
    """
    audio = np.array(audio, dtype=np.float32)
    samples_per_bit = int(sample_rate / data_rate)
    num_bits = int(len(audio) / samples_per_bit)

    bits = []
    for bit_idx in range(num_bits):
        bit_start = bit_idx * samples_per_bit
        bit_end = min(bit_start + samples_per_bit, len(audio))

        if bit_end - bit_start < samples_per_bit // 2:
            break

        segment = audio[bit_start:bit_end]

        # Skip silent segments
        segment_power = np.sum(segment ** 2)
        if segment_power < 0.00001:
            bits.append(1)  # Default to space (1800 Hz) when silent
            continue

        # For each frequency, generate reference signal and compute correlation
        t = np.arange(len(segment)) / sample_rate

        # Matched filter approach: correlate with sine at each frequency
        mark_corr_i = np.abs(np.sum(segment * np.cos(2 * np.pi * mark_freq * t)))
        mark_corr_q = np.abs(np.sum(segment * np.sin(2 * np.pi * mark_freq * t)))
        mark_mag = np.sqrt(mark_corr_i ** 2 + mark_corr_q ** 2)

        space_corr_i = np.abs(np.sum(segment * np.cos(2 * np.pi * space_freq * t)))
        space_corr_q = np.abs(np.sum(segment * np.sin(2 * np.pi * space_freq * t)))
        space_mag = np.sqrt(space_corr_i ** 2 + space_corr_q ** 2)

        # Normalize by segment length and frequency to make comparison fair
        mark_mag /= len(segment)
        space_mag /= len(segment)

        # Bit is 0 if mark (1200 Hz) is stronger, 1 if space (1800 Hz) is stronger
        if mark_mag > space_mag:
            bits.append(0)
        else:
            bits.append(1)

    return bits


# ============================================================================
# Message Assembly
# ============================================================================

def build_acars_message(mode='2', registration='.N12345', label='_d',
                       block_id='0', text='', ack=None, downlink=True):
    """
    Build a complete ACARS message block.

    Args:
        mode: single character (default '2' for normal)
        registration: 7-char aircraft code (default '.N12345')
        label: 2-char label (default '_d' for OOOI)
        block_id: single character sequence number (default '0')
        text: message body text
        ack: acknowledgement character (default NAK=0x15)
        downlink: True for downlink (+), False for uplink (*)

    Returns:
        bytes: complete ACARS message with preamble, parity, CRC, DEL
    """
    if ack is None:
        ack = chr(NAK)

    # Ensure strings are proper length
    if len(registration) < 7:
        registration = registration.ljust(7)[:7]
    if len(label) < 2:
        label = label.ljust(2)[:2]
    if len(block_id) < 1:
        block_id = '0'
    else:
        block_id = block_id[0]

    # Build message bytes (before parity is added)
    msg = bytearray()
    msg.append(SYNC_DOWNLINK if downlink else SYNC_UPLINK)
    msg.append(SOH)
    msg.append(ord(mode))
    msg.extend(registration.encode('ascii')[:7])
    msg.append(ord(ack) if isinstance(ack, str) else ack)
    msg.extend(label.encode('ascii')[:2])
    msg.append(ord(block_id))
    msg.append(STX)
    msg.extend(text.encode('ascii')[:220])  # Max ~220 chars on VHF
    msg.append(ETX)

    # Calculate CRC over SOH through ETX (indices 1 to end)
    crc_data = msg[1:]  # From SOH onwards
    crc = crc16_ccitt(crc_data)

    msg.extend(crc)
    msg.append(DEL)

    # Add parity to all bytes
    msg_with_parity = bytearray(compute_parity(b) for b in msg)

    # Generate preamble: 128 alternating bits (10101010...)
    preamble_bits = [i % 2 for i in range(PREAMBLE_BITS)]

    # Convert preamble bits to bytes
    preamble_bytes = bits_to_bytes(preamble_bits)

    # Add parity to preamble
    preamble_with_parity = bytearray(compute_parity(b) for b in preamble_bytes)

    # Complete message: preamble + message
    complete = preamble_with_parity + msg_with_parity

    return bytes(complete)


# ============================================================================
# Message Parsing
# ============================================================================

def parse_acars_message(data_bytes):
    """
    Parse an ACARS message block into its components.
    Expects raw bytes with parity bits included.

    Args:
        data_bytes: bytes from ACARS transmission (with parity)

    Returns:
        dict with keys:
            'sync': sync character ('+' or '*')
            'mode': mode character
            'registration': 7-char aircraft code
            'ack': acknowledgement character
            'label': 2-char label
            'block_id': block sequence character
            'text': message body text
            'crc_valid': True if CRC-16 matches
            'parity_valid': True if all parity bits correct
            'error': error message if parsing failed
    """
    result = {
        'sync': None,
        'mode': None,
        'registration': None,
        'ack': None,
        'label': None,
        'block_id': None,
        'text': None,
        'crc_valid': False,
        'parity_valid': True,
        'error': None,
    }

    if len(data_bytes) < 20:
        result['error'] = 'Message too short'
        return result

    # Verify all parity bits
    for byte in data_bytes:
        if not verify_parity(byte):
            result['parity_valid'] = False
            break

    # Strip parity bits
    data = bytearray(strip_parity(b) for b in data_bytes)

    # Find sync character (skip preamble which is 16 bytes of 0xaa)
    # The preamble is alternating 10101010... which becomes 0xaa (binary 10101010)
    # Look for sync character after the expected preamble position
    sync_idx = None

    # Check if we have a preamble starting at index 0
    if (len(data) >= 17 and
        all(data[i] == 0xaa for i in range(16)) and
        data[16] in (SYNC_DOWNLINK, SYNC_UPLINK)):
        sync_idx = 16
    else:
        # Search for sync character elsewhere
        for i in range(16, min(len(data), 100)):
            if data[i] in (SYNC_DOWNLINK, SYNC_UPLINK):
                # Make sure it's not part of preamble
                if i >= 16 or not all(data[j] == 0xaa for j in range(i)):
                    sync_idx = i
                    break

        # If still not found, search from beginning (no preamble case)
        if sync_idx is None:
            for i in range(len(data)):
                if data[i] in (SYNC_DOWNLINK, SYNC_UPLINK):
                    sync_idx = i
                    break

    if sync_idx is None:
        result['error'] = 'Sync character not found'
        return result

    idx = sync_idx

    # Parse fixed fields
    result['sync'] = '+' if data[idx] == SYNC_DOWNLINK else '*'
    idx += 1

    if idx >= len(data) or data[idx] != SOH:
        result['error'] = 'SOH marker missing'
        return result
    idx += 1

    if idx >= len(data):
        result['error'] = 'Incomplete header'
        return result
    result['mode'] = chr(data[idx])
    idx += 1

    if idx + 7 > len(data):
        result['error'] = 'Incomplete registration'
        return result
    result['registration'] = data[idx:idx+7].decode('ascii', errors='replace')
    idx += 7

    if idx >= len(data):
        result['error'] = 'Incomplete acknowledgement'
        return result
    result['ack'] = chr(data[idx])
    idx += 1

    if idx + 2 > len(data):
        result['error'] = 'Incomplete label'
        return result
    result['label'] = data[idx:idx+2].decode('ascii', errors='replace')
    idx += 2

    if idx >= len(data):
        result['error'] = 'Incomplete block ID'
        return result
    result['block_id'] = chr(data[idx])
    idx += 1

    if idx >= len(data) or data[idx] != STX:
        result['error'] = 'STX marker missing'
        return result
    idx += 1

    # Extract message text until ETX
    text_start = idx
    while idx < len(data) and data[idx] not in (ETX, ETB):
        idx += 1

    if idx >= len(data):
        result['error'] = 'ETX/ETB marker missing'
        return result

    result['text'] = data[text_start:idx].decode('ascii', errors='replace')

    # ETX/ETB
    etx_idx = idx
    idx += 1

    # CRC check
    if idx + 2 <= len(data):
        crc_bytes = data[idx:idx+2]
        # Recalculate CRC over SOH through ETX (inclusive)
        # Find the SOH position
        soh_idx = sync_idx + 1
        crc_data = data[soh_idx:etx_idx+1]  # SOH through ETX (inclusive)
        calculated_crc = crc16_ccitt(crc_data)
        result['crc_valid'] = (crc_bytes[0] == calculated_crc[0] and
                              crc_bytes[1] == calculated_crc[1])
        idx += 2

    # DEL marker
    if idx < len(data) and data[idx] == DEL:
        pass  # Expected end marker

    return result
