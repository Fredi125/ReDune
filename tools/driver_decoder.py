#!/usr/bin/env python
"""
Dune 1992 Sound-Driver Decoder
================================
The ``DN*.HSQ`` files are HSQ-compressed real-mode (8086) sound drivers, one per
sound device. They are the *authoritative* source for how Dune programs each
chip — better than any third-party player, because this is the code that
actually shipped. This tool decompresses a driver, disassembles it (via
``objdump -m i8086``), and auto-locates the device-programming landmarks:

  * the entry **jump table** (the driver's call API),
  * the chip **I/O ports** it writes (``MOV DX, imm``),
  * for AdLib/OPL2 drivers: the **register-write routine** (port 0x388/0x389 with
    the mandatory post-write delay loops), the 9-channel **operator-slot tables**,
    and the 12-note **F-number table** that maps note → OPL frequency.

This recovers the exact OPL2 register map Dune uses (see docs/adlib_driver.md).

Usage:
  python driver_decoder.py gamedata/DNADL.HSQ           # annotated report
  python driver_decoder.py gamedata/DNADL.HSQ --asm     # + full disassembly
  python driver_decoder.py gamedata/DNMID.HSQ           # MT-32/MPU-401 driver
"""

import argparse
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
from compression import hsq_decompress  # noqa: E402

# OPL2 (YM3812) landmarks -----------------------------------------------------
OPL_ADDR_PORT = 0x388            # register-select port
OPL_DATA_PORT = 0x389            # data port
# Canonical 9-channel operator → register-offset tables. Modulator and carrier
# operator of channel c live at base+MOD_SLOTS[c] and base+CAR_SLOTS[c].
MOD_SLOTS = bytes([0x00, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x10, 0x11, 0x12])
CAR_SLOTS = bytes([0x03, 0x04, 0x05, 0x0B, 0x0C, 0x0D, 0x13, 0x14, 0x15])

# Known device I/O ports → human label (high byte 0x03/0x02 etc.).
KNOWN_PORTS = {
    0x388: "OPL2/AdLib register select",
    0x389: "OPL2/AdLib data",
    0x330: "MPU-401 / MT-32 data (UART)",
    0x331: "MPU-401 / MT-32 command/status",
    0x320: "Sound Blaster (base)",
    0x224: "Sound Blaster (alt base)",
    0x226: "Sound Blaster DSP reset",
    0x22C: "Sound Blaster DSP write",
    0x22E: "Sound Blaster DSP read",
    0x42: "PIT timer channel 0",
    0x43: "PIT mode/command",
    0x61: "PC speaker gate",
    0x20: "PIC1 command / EOI (IRQ setup)",
    0x21: "PIC1 interrupt mask",
    0xA0: "PIC2 command / EOI (IRQ setup)",
    0xA1: "PIC2 interrupt mask",
}


def decompress_driver(path: str) -> bytes:
    raw = open(path, 'rb').read()
    # HSQ files have a 6-byte header whose bytes sum to 0xAB (mod 256).
    if len(raw) >= 6 and (sum(raw[:6]) & 0xFF) == 0xAB:
        return bytes(hsq_decompress(raw))
    return raw


def parse_jump_table(d: bytes) -> list:
    """Leading run of `E9 lo hi` (JMP rel16) entry points."""
    entries = []
    pos = 0
    while pos + 3 <= len(d) and d[pos] == 0xE9:
        rel = struct.unpack_from('<h', d, pos + 1)[0]
        target = (pos + 3 + rel) & 0xFFFF
        entries.append((pos, target))
        pos += 3
    return entries


def find_seq(d: bytes, seq: bytes) -> list:
    out, i = [], 0
    while True:
        j = d.find(seq, i)
        if j < 0:
            break
        out.append(j)
        i = j + 1
    return out


def find_ports_from_asm(asm: str) -> list:
    """Chip ports actually used, parsed from real disassembly: for `out dx,*` /
    `in *,dx` we resolve DX from the most recent `mov dx,imm`; immediate forms
    (`out 0x43,al`) are taken directly. Far more reliable than scanning opcode
    bytes, which collide with data and instruction operands.
    """
    import re
    found = {}
    cur_dx = None
    mov_dx = re.compile(r"mov\s+dx,(0x[0-9a-f]+|\d+)")
    out_imm = re.compile(r"out\s+(0x[0-9a-f]+|\d+),a[lx]")
    in_imm = re.compile(r"in\s+a[lx],(0x[0-9a-f]+|\d+)")
    for line in asm.splitlines():
        if "\t" not in line:
            continue
        text = line.split("\t")[-1].strip()
        m = mov_dx.search(text)
        if m:
            cur_dx = int(m.group(1), 0)
            continue
        if ("out    dx" in text or "out dx" in text or "in     al,dx" in text or "in al,dx" in text) and cur_dx is not None:
            if 0x20 <= cur_dx <= 0x3FF:
                found.setdefault(cur_dx, 0)
                found[cur_dx] += 1
            continue
        m = out_imm.search(text) or in_imm.search(text)
        if m:
            port = int(m.group(1), 0)
            if 0x20 <= port <= 0x3FF:
                found.setdefault(port, 0)
                found[port] += 1
    return sorted(found.items())


def find_opl_write_routine(d: bytes):
    """Locate `MOV DX,0x388` followed by OUT (0xEE) and delay IN-runs (0xEC)."""
    sig = b'\xBA' + struct.pack('<H', OPL_ADDR_PORT)  # mov dx, 0x388
    for off in find_seq(d, sig):
        window = d[off:off + 48]
        if 0xEE in window and window.count(0xEC) >= 4:
            return off
    return None


def find_fnum_table(d: bytes):
    """12 ascending uint16 F-numbers in the OPL range (one octave)."""
    for off in range(0, len(d) - 24):
        vals = [struct.unpack_from('<H', d, off + 2 * k)[0] for k in range(12)]
        if all(0x140 <= v <= 0x2C0 for v in vals) and all(vals[k] < vals[k + 1] for k in range(11)):
            return off, vals
    return None, None


def disassemble(path_bin: str, start: int = 0, stop: int = None) -> str:
    cmd = ['objdump', '-D', '-b', 'binary', '-mi8086', '-M', 'intel',
           '--start-address', hex(start)]
    if stop is not None:
        cmd += ['--stop-address', hex(stop)]
    cmd.append(path_bin)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        return f"(objdump unavailable: {e})"


def analyze(path: str, show_asm: bool) -> int:
    name = os.path.basename(path)
    d = decompress_driver(path)
    print(f"=== {name} — {len(d)} bytes (decompressed 8086 code) ===\n")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(d)
        tmp = tf.name
    try:
        asm = disassemble(tmp)
    finally:
        os.unlink(tmp)

    jt = parse_jump_table(d)
    if jt:
        print(f"Entry jump table: {len(jt)} API entries")
        for i, (at, tgt) in enumerate(jt):
            print(f"  [{i}] 0x{at:04x}: jmp 0x{tgt:04x}")
        print()

    ports = find_ports_from_asm(asm)
    if ports:
        print("Device I/O ports (resolved from disassembly):")
        for port, n in ports:
            label = KNOWN_PORTS.get(port, "")
            print(f"  0x{port:03x}  ×{n:<2} {('— ' + label) if label else ''}")
        print()

    is_opl = any(p == OPL_ADDR_PORT for p, _ in ports)
    if is_opl:
        print("OPL2/AdLib register map (ground truth from this driver):")
        wr = find_opl_write_routine(d)
        if wr is not None:
            print(f"  register-write routine @0x{wr:04x}: OUT 0x388,reg → IN×n delay → OUT 0x389,val → IN×n delay")
        for label, seq in (("modulator", MOD_SLOTS), ("carrier", CAR_SLOTS)):
            for at in find_seq(d, seq):
                print(f"  {label} operator-slot table @0x{at:04x}: {' '.join(f'{b:02x}' for b in seq)}")
        foff, fvals = find_fnum_table(d)
        if foff is not None:
            print(f"  F-number table @0x{foff:04x} (note%12 → fnum; block = note//12, written to 0xA0/0xB0):")
            print(f"    {', '.join(f'0x{v:03x}' for v in fvals)}")
        print("  → instrument regs: 0x20|0x40|0x60|0x80|0xE0 + operator slot; 0xC0 + channel (see docs/adlib_driver.md)")
        print()

    if show_asm:
        print(asm)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='Dune 1992 sound-driver (DN*.HSQ) decoder')
    p.add_argument('driver', help='Driver file (e.g. gamedata/DNADL.HSQ)')
    p.add_argument('--asm', action='store_true', help='Also print the full disassembly')
    args = p.parse_args()
    if not os.path.exists(args.driver):
        print(f"File not found: {args.driver}", file=sys.stderr)
        return 1
    return analyze(args.driver, args.asm)


if __name__ == '__main__':
    sys.exit(main())
