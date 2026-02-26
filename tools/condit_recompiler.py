#!/usr/bin/env python
"""
Dune 1992 CONDIT Bytecode Recompiler
=======================================
Compile human-readable condition expressions back into CONDIT bytecodes.

This is the inverse of condit_decompiler.py. It takes expressions like:
    byte[GameStage] == 0x50
    (byte[GameStage] >= 0x38) & (word[0x10] != 0x00)
and compiles them into the CONDIT bytecode format.

Bytecode encoding (DNCDPRG.EXE sub_C266/C1DB/C204):
  Operands:
    01 XX       → byte variable at DS:[XX]
    00 XX       → word variable at DS:[XX]  (type_byte=0x00)
    80 XX       → immediate byte (0x00-0xFF)
    81+ XXXX    → immediate word (uint16 LE)

  Control bytes:
    0x00-0x0F   → inline op (op_index = byte & 0x1F), read operand, apply
    0x80-0x9F   → separator (push acc + deferred_op, start new sub-expr)
    0xFF        → terminator (unwind stack)

  Operations (off_C246):
    0=EQ(==), 1=LT(<u), 2=GT(>u), 3=NE(!=), 4=LE(<=s), 5=GE(>=s),
    6=ADD(+), 7=SUB(-), 8=AND(&), 9=OR(|)

Usage:
  python condit_recompiler.py "byte[0x2A] == 0x50"
  python condit_recompiler.py "(byte[GameStage] >= 0x38) & (word[0x10] != 0x00)"
  python condit_recompiler.py --file expressions.txt
  python condit_recompiler.py --test CONDIT.HSQ   # Roundtrip test
"""

import struct
import sys
import argparse
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.constants import CONDIT_OPS, CONDIT_VARIABLES


# =============================================================================
# OPERATION LOOKUP
# =============================================================================

# Map operator symbols to op indices
OP_SYMBOLS = {}
for idx, (name, sym, _desc) in CONDIT_OPS.items():
    OP_SYMBOLS[sym] = idx
    OP_SYMBOLS[name.lower()] = idx

# Also add common aliases
OP_SYMBOLS['=='] = 0x00
OP_SYMBOLS['<'] = 0x01
OP_SYMBOLS['<u'] = 0x01
OP_SYMBOLS['>'] = 0x02
OP_SYMBOLS['>u'] = 0x02
OP_SYMBOLS['!='] = 0x03
OP_SYMBOLS['<='] = 0x04
OP_SYMBOLS['<=s'] = 0x04
OP_SYMBOLS['>='] = 0x05
OP_SYMBOLS['>=s'] = 0x05
OP_SYMBOLS['+'] = 0x06
OP_SYMBOLS['-'] = 0x07
OP_SYMBOLS['&'] = 0x08
OP_SYMBOLS['|'] = 0x09

# Reverse variable name lookup
VAR_NAMES = {name: offset for offset, name in CONDIT_VARIABLES.items()}


# =============================================================================
# TOKENIZER
# =============================================================================

TOKEN_PATTERNS = [
    ('LPAREN',   r'\('),
    ('RPAREN',   r'\)'),
    ('BYTEVAR',  r'byte\[[^\]]+\]'),
    ('WORDVAR',  r'word\[[^\]]+\]'),
    ('HEX',      r'0x[0-9A-Fa-f]+'),
    ('SEPOP',    r'\?[0-9]+'),       # deferred op syntax from decompiler: ?16, ?18
    ('DEC',      r'[0-9]+'),
    ('OP',       r'==|!=|<=s|>=s|<=|>=|<u|>u|<|>|\+|-|&|\|'),
    ('SPACE',    r'\s+'),
    ('ANNOT',    r'/\*[^*]*\*/'),  # annotations like /*MetGurney*/
    ('COMMA',    r','),
]

# Regex to extract var name from byte[xxx] or word[xxx]
_VAR_RE = re.compile(r'(?:byte|word)\[([^\]]+)\]')


def tokenize(expr: str) -> list:
    """Tokenize a CONDIT expression string."""
    tokens = []
    combined = '|'.join(f'(?P<{name}>{pat})' for name, pat in TOKEN_PATTERNS)
    regex = re.compile(combined)

    for match in regex.finditer(expr):
        kind = match.lastgroup
        value = match.group()
        if kind == 'SPACE' or kind == 'ANNOT':
            continue
        if kind in ('BYTEVAR', 'WORDVAR'):
            # Extract variable reference from byte[xxx] or word[xxx]
            var_match = _VAR_RE.match(value)
            var_ref = var_match.group(1) if var_match else value
            tokens.append((kind, var_ref))
        else:
            tokens.append((kind, value))

    return tokens


def resolve_var(name: str) -> int:
    """Resolve a variable name or hex offset to a numeric DS offset."""
    name = name.strip()
    if name in VAR_NAMES:
        return VAR_NAMES[name]
    return int(name, 0)


def resolve_imm(value_str: str) -> int:
    """Resolve a numeric literal to an integer."""
    return int(value_str, 0)


# =============================================================================
# OPERAND ENCODER
# =============================================================================

def encode_operand(kind: str, value: str) -> bytes:
    """
    Encode an operand into CONDIT bytecode.

    Returns bytes for the encoded operand.
    """
    if kind == 'BYTEVAR':
        offset = resolve_var(value)
        return bytes([0x01, offset & 0xFF])
    elif kind == 'WORDVAR':
        offset = resolve_var(value)
        return bytes([0x00, offset & 0xFF])
    elif kind in ('HEX', 'DEC'):
        val = resolve_imm(value)
        if val <= 0xFF:
            return bytes([0x80, val])
        else:
            return bytes([0x81]) + struct.pack('<H', val & 0xFFFF)
    else:
        raise ValueError(f"Cannot encode operand: {kind} {value}")


# =============================================================================
# EXPRESSION COMPILER
# =============================================================================

def compile_expr(expr: str) -> bytes:
    """
    Compile a CONDIT expression string into bytecode.

    Supported formats:
      Simple:     byte[GameStage]
      Comparison: byte[GameStage] == 0x50
      Chained:    byte[GameStage] == 0x50 & word[0x10] != 0x00
      Nested:     (byte[GameStage] >= 0x38) & (word[0x10] != 0x00)

    Nested expressions use separator bytes (0x80+) to push to stack.
    """
    tokens = tokenize(expr)
    if not tokens:
        raise ValueError("Empty expression")

    out = bytearray()
    pos = [0]  # mutable index for recursive parser

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume(expected_kind=None):
        if pos[0] >= len(tokens):
            return None
        tok = tokens[pos[0]]
        if expected_kind and tok[0] != expected_kind:
            raise ValueError(f"Expected {expected_kind}, got {tok[0]} '{tok[1]}'")
        pos[0] += 1
        return tok

    def is_operand(tok):
        return tok and tok[0] in ('BYTEVAR', 'WORDVAR', 'HEX', 'DEC')

    def is_op(tok):
        return tok and tok[0] in ('OP', 'SEPOP')

    def parse_atom():
        """Parse a single operand or parenthesized sub-expression."""
        tok = peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")

        if tok[0] == 'LPAREN':
            consume()  # eat '('
            result = parse_expression()
            consume('RPAREN')  # eat ')'
            return result
        elif is_operand(tok):
            consume()
            return encode_operand(tok[0], tok[1])
        else:
            raise ValueError(f"Unexpected token: {tok[0]} '{tok[1]}'")

    def parse_expression():
        """Parse an expression with optional inline ops and separators."""
        result = bytearray()

        # First operand
        first = parse_atom()
        result.extend(first)

        # Optional chain of operations
        while peek() and is_op(peek()):
            op_tok = consume()

            if op_tok[0] == 'SEPOP':
                # ?NN from decompiler output — either separator or inline op
                raw_op = int(op_tok[1][1:])  # strip '?' prefix

                next_tok = peek()
                if next_tok and next_tok[0] == 'LPAREN':
                    # Separator: push current, start sub-expression
                    sep_byte = 0x80 | (raw_op & 0x1F)
                    result.append(sep_byte)
                    consume()  # eat '('
                    sub = parse_expression()
                    result.extend(sub)
                    consume('RPAREN')  # eat ')'
                elif next_tok and is_operand(next_tok):
                    # Inline op with raw index
                    result.append(raw_op & 0x1F)
                    operand = parse_atom()
                    result.extend(operand)
                else:
                    # Default to separator
                    sep_byte = 0x80 | (raw_op & 0x1F)
                    result.append(sep_byte)
                    operand = parse_atom()
                    result.extend(operand)
            else:
                # Standard operator
                op_idx = OP_SYMBOLS.get(op_tok[1])
                if op_idx is None:
                    raise ValueError(f"Unknown operator: '{op_tok[1]}'")

                next_tok = peek()
                if next_tok and next_tok[0] == 'LPAREN':
                    # Sub-expression → use separator
                    sep_byte = 0x80 | (op_idx & 0x1F)
                    result.append(sep_byte)
                    consume()  # eat '('
                    sub = parse_expression()
                    result.extend(sub)
                    consume('RPAREN')  # eat ')'
                else:
                    # Inline operation
                    result.append(op_idx & 0x1F)
                    operand = parse_atom()
                    result.extend(operand)

        return bytes(result)

    bytecode = bytearray(parse_expression())
    bytecode.append(0xFF)  # terminator

    return bytes(bytecode)


# =============================================================================
# ROUNDTRIP TEST
# =============================================================================

def roundtrip_test(condit_path: str):
    """
    Test roundtrip: decompile CONDIT entries, recompile, compare bytecodes.
    """
    from lib.compression import hsq_decompress

    with open(condit_path, 'rb') as f:
        raw = f.read()

    try:
        data = hsq_decompress(raw)
    except Exception:
        data = raw

    first_offset = struct.unpack_from('<H', data, 0)[0]
    entry_count = first_offset // 2
    offsets = [struct.unpack_from('<H', data, i * 2)[0] for i in range(entry_count)]

    # Import decompiler
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from condit_decompiler import decompile_entry

    passed = 0
    failed = 0
    skipped = 0

    for i in range(entry_count):
        off = offsets[i]
        table_end = offsets[i + 1] if i + 1 < entry_count else len(data)
        chunk = data[off:table_end]
        if all(b == 0 for b in chunk):
            skipped += 1
            continue

        # Decompile
        expr_text, end_pos = decompile_entry(data, off, annotate=False)
        original = data[off:end_pos]

        # Try to recompile
        try:
            recompiled = compile_expr(expr_text)
            if recompiled == original:
                passed += 1
            else:
                failed += 1
                if failed <= 10:
                    print(f"  MISMATCH entry [{i}]:")
                    print(f"    Expr:     {expr_text}")
                    orig_hex = ' '.join(f'{b:02X}' for b in original)
                    recomp_hex = ' '.join(f'{b:02X}' for b in recompiled)
                    print(f"    Original: {orig_hex}")
                    print(f"    Recomp:   {recomp_hex}")
        except Exception as e:
            failed += 1
            if failed <= 10:
                print(f"  ERROR entry [{i}]: {e}")
                print(f"    Expr: {expr_text}")

    total = passed + failed
    print(f"\n=== Roundtrip Results ===")
    print(f"  Passed:  {passed}/{total}")
    print(f"  Failed:  {failed}/{total}")
    print(f"  Skipped: {skipped} (empty entries)")
    if total > 0:
        print(f"  Rate:    {100 * passed / total:.1f}%")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(
        description='Dune 1992 CONDIT Bytecode Recompiler',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('expr', nargs='?', default=None,
                   help='Expression to compile (e.g. "byte[0x2A] == 0x50")')
    p.add_argument('--file', type=str, default=None, metavar='FILE',
                   help='Read expressions from file (one per line)')
    p.add_argument('--test', type=str, default=None, metavar='CONDIT.HSQ',
                   help='Roundtrip test against CONDIT.HSQ')
    args = p.parse_args()

    if args.test:
        roundtrip_test(args.test)
    elif args.file:
        with open(args.file) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                try:
                    bytecode = compile_expr(line)
                    hex_str = ' '.join(f'{b:02X}' for b in bytecode)
                    print(f"[{line_num}] {hex_str}  ← {line}")
                except Exception as e:
                    print(f"[{line_num}] ERROR: {e}  ← {line}")
    elif args.expr:
        try:
            bytecode = compile_expr(args.expr)
            hex_str = ' '.join(f'{b:02X}' for b in bytecode)
            print(f"  Bytecode: {hex_str}")
            print(f"  Length:   {len(bytecode)} bytes")
        except Exception as e:
            print(f"  ERROR: {e}")
            sys.exit(1)
    else:
        p.print_help()


if __name__ == '__main__':
    main()
