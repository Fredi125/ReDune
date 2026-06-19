/**
 * ReDune codecs — CONDIT bytecode decompiler + recompiler.
 * Direct port of tools/condit_decompiler.py and tools/condit_recompiler.py.
 *
 * The CONDIT system is a stack-based expression evaluator with a DX
 * accumulator that gates dialogue options and story events.
 */

import { hsqDecompress } from "./compression";
import { CONDIT_OPS, CONDIT_VARIABLES, GAME_STAGES } from "./constants";

function u16(d: Uint8Array, o: number): number {
  return d[o] | (d[o + 1] << 8);
}

// ---------------------------------------------------------------------------
// Operand decoding (sub_C1DB)
// ---------------------------------------------------------------------------

type OperandMeta =
  | { kind: "var"; idx: number; byteMode: boolean }
  | { kind: "imm8"; val: number }
  | { kind: "imm16"; val: number }
  | null;

interface OperandRead {
  text: string;
  pos: number;
  meta: OperandMeta;
}

export function readOperand(data: Uint8Array, pos: number): OperandRead {
  if (pos >= data.length) return { text: "<EOF>", pos, meta: null };
  const typeByte = data[pos++];

  if (typeByte < 0x80) {
    if (pos >= data.length) return { text: "<TRUNC>", pos, meta: null };
    const idx = data[pos++];
    const byteMode = typeByte === 0x01;
    const varName = CONDIT_VARIABLES[idx] ?? `0x${idx.toString(16).toUpperCase().padStart(2, "0")}`;
    const prefix = byteMode ? "byte" : "word";
    return { text: `${prefix}[${varName}]`, pos, meta: { kind: "var", idx, byteMode } };
  } else if (typeByte === 0x80) {
    if (pos >= data.length) return { text: "<TRUNC>", pos, meta: null };
    const val = data[pos++];
    return { text: `0x${val.toString(16).toUpperCase().padStart(2, "0")}`, pos, meta: { kind: "imm8", val } };
  } else {
    if (pos + 1 >= data.length) return { text: "<TRUNC>", pos, meta: null };
    const val = u16(data, pos);
    pos += 2;
    return { text: `0x${val.toString(16).toUpperCase().padStart(4, "0")}`, pos, meta: { kind: "imm16", val } };
  }
}

// ---------------------------------------------------------------------------
// Expression decompiler (sub_C266)
// ---------------------------------------------------------------------------

export function decompileEntry(data: Uint8Array, start: number, annotate = true): { expr: string; end: number } {
  let pos = start;
  const stack: [string, string][] = [];

  let r = readOperand(data, pos);
  let accText = r.text;
  let accMeta = r.meta;
  pos = r.pos;

  while (pos < data.length) {
    const b = data[pos++];
    if (b === 0xff) break;
    if (b >= 0x80) {
      const opIdx = b & 0x1f;
      const opInfo = CONDIT_OPS[opIdx];
      const opSym = opInfo ? opInfo[1] : `?${opIdx}`;
      stack.push([accText, opSym]);
      r = readOperand(data, pos);
      accText = r.text;
      accMeta = r.meta;
      pos = r.pos;
    } else {
      const opIdx = b & 0x1f;
      const opInfo = CONDIT_OPS[opIdx];
      const opSym = opInfo ? opInfo[1] : `?${opIdx}`;
      const rhs = readOperand(data, pos);
      pos = rhs.pos;

      let annotation = "";
      if (annotate && opSym === "==" && rhs.meta) {
        if (accMeta && accMeta.kind === "var" && accMeta.idx === 0x2a) {
          if (rhs.meta.kind === "imm8" || rhs.meta.kind === "imm16") {
            const stageName = GAME_STAGES[rhs.meta.val];
            if (stageName) annotation = `/*${stageName}*/`;
          }
        }
      }
      accText = annotation ? `${accText} ${opSym} ${rhs.text}${annotation}` : `${accText} ${opSym} ${rhs.text}`;
    }
  }

  while (stack.length) {
    const [leftText, opSym] = stack.pop()!;
    accText = `(${leftText}) ${opSym} (${accText})`;
  }
  return { expr: accText, end: pos };
}

// ---------------------------------------------------------------------------
// File parsing
// ---------------------------------------------------------------------------

export interface ConditFile {
  data: Uint8Array;
  entryCount: number;
  offsets: number[];
}

export function loadCondit(raw: Uint8Array, isRaw = false): ConditFile {
  let data: Uint8Array;
  try {
    data = isRaw ? raw : hsqDecompress(raw);
  } catch {
    data = raw;
  }
  if (data.length < 2) throw new Error("CONDIT file too short");
  const firstOffset = u16(data, 0);
  const entryCount = firstOffset >> 1;
  const offsets: number[] = [];
  for (let i = 0; i < entryCount; i++) {
    if (i * 2 + 1 >= data.length) break;
    offsets.push(u16(data, i * 2));
  }
  return { data, entryCount, offsets };
}

export interface ConditEntry {
  index: number;
  offset: number;
  sizeTable: number;
  sizeExec: number;
  overflow: boolean;
  empty: boolean;
  expr: string;
  rawHex: string;
}

export function conditEntries(cf: ConditFile, annotate = true): ConditEntry[] {
  const { data, offsets } = cf;
  const result: ConditEntry[] = [];
  for (let i = 0; i < offsets.length; i++) {
    const off = offsets[i];
    const tableEnd = i + 1 < offsets.length ? offsets[i + 1] : data.length;
    const chunk = data.subarray(off, tableEnd);
    const empty = chunk.every((b) => b === 0);
    if (empty) {
      result.push({ index: i, offset: off, sizeTable: tableEnd - off, sizeExec: 0, overflow: false, empty: true, expr: "", rawHex: "" });
      continue;
    }
    const { expr, end } = decompileEntry(data, off, annotate);
    const rawLen = Math.min(end - off, 64);
    const rawHex = Array.from(data.subarray(off, off + rawLen))
      .map((b) => b.toString(16).toUpperCase().padStart(2, "0"))
      .join(" ");
    result.push({
      index: i,
      offset: off,
      sizeTable: tableEnd - off,
      sizeExec: end - off,
      overflow: end > tableEnd,
      empty: false,
      expr,
      rawHex,
    });
  }
  return result;
}

// ---------------------------------------------------------------------------
// Recompiler (inverse) — port of tools/condit_recompiler.py
// ---------------------------------------------------------------------------

const OP_SYMBOLS: Record<string, number> = {};
for (const idx of Object.keys(CONDIT_OPS).map(Number)) {
  const [name, sym] = CONDIT_OPS[idx];
  OP_SYMBOLS[sym] = idx;
  OP_SYMBOLS[name.toLowerCase()] = idx;
}
Object.assign(OP_SYMBOLS, {
  "==": 0x00, "<": 0x01, "<u": 0x01, ">": 0x02, ">u": 0x02, "!=": 0x03,
  "<=": 0x04, "<=s": 0x04, ">=": 0x05, ">=s": 0x05,
  "+": 0x06, "-": 0x07, "&": 0x08, "|": 0x09,
});

const VAR_NAMES: Record<string, number> = {};
for (const off of Object.keys(CONDIT_VARIABLES).map(Number)) {
  VAR_NAMES[CONDIT_VARIABLES[off]] = off;
}

type Token = { kind: string; value: string };

const TOKEN_PATTERNS: [string, string][] = [
  ["LPAREN", "\\("],
  ["RPAREN", "\\)"],
  ["BYTEVAR", "byte\\[[^\\]]+\\]"],
  ["WORDVAR", "word\\[[^\\]]+\\]"],
  ["HEX", "0x[0-9A-Fa-f]+"],
  ["SEPOP", "\\?[0-9]+"],
  ["DEC", "[0-9]+"],
  ["OP", "==|!=|<=s|>=s|<=|>=|<u|>u|<|>|\\+|-|&|\\|"],
  ["SPACE", "\\s+"],
  ["ANNOT", "/\\*[^*]*\\*/"],
  ["COMMA", ","],
];

const VAR_RE = /(?:byte|word)\[([^\]]+)\]/;

export function tokenize(expr: string): Token[] {
  const combined = TOKEN_PATTERNS.map(([name, pat]) => `(?<${name}>${pat})`).join("|");
  const regex = new RegExp(combined, "g");
  const tokens: Token[] = [];
  let m: RegExpExecArray | null;
  while ((m = regex.exec(expr)) !== null) {
    if (m.index === regex.lastIndex) regex.lastIndex++; // guard against zero-width
    const groups = m.groups ?? {};
    let kind = "";
    for (const [name] of TOKEN_PATTERNS) {
      if (groups[name] !== undefined) {
        kind = name;
        break;
      }
    }
    const value = m[0];
    if (kind === "SPACE" || kind === "ANNOT") continue;
    if (kind === "BYTEVAR" || kind === "WORDVAR") {
      const vm = VAR_RE.exec(value);
      tokens.push({ kind, value: vm ? vm[1] : value });
    } else {
      tokens.push({ kind, value });
    }
  }
  return tokens;
}

function parseIntAuto(s: string): number {
  s = s.trim();
  if (s.startsWith("0x") || s.startsWith("0X")) return parseInt(s, 16);
  return parseInt(s, 10);
}

function resolveVar(name: string): number {
  name = name.trim();
  if (name in VAR_NAMES) return VAR_NAMES[name];
  return parseIntAuto(name);
}

function encodeOperand(kind: string, value: string): number[] {
  if (kind === "BYTEVAR") return [0x01, resolveVar(value) & 0xff];
  if (kind === "WORDVAR") return [0x00, resolveVar(value) & 0xff];
  if (kind === "HEX" || kind === "DEC") {
    const val = parseIntAuto(value);
    if (val <= 0xff) return [0x80, val];
    return [0x81, val & 0xff, (val >> 8) & 0xff];
  }
  throw new Error(`Cannot encode operand: ${kind} ${value}`);
}

/** Compile a CONDIT expression string into bytecode. Throws on parse error. */
export function compileExpr(expr: string): Uint8Array {
  const tokens = tokenize(expr);
  if (!tokens.length) throw new Error("Empty expression");
  const pos = { i: 0 };

  const peek = (): Token | null => (pos.i < tokens.length ? tokens[pos.i] : null);
  const consume = (expected?: string): Token | null => {
    if (pos.i >= tokens.length) return null;
    const tok = tokens[pos.i];
    if (expected && tok.kind !== expected) throw new Error(`Expected ${expected}, got ${tok.kind} '${tok.value}'`);
    pos.i++;
    return tok;
  };
  const isOperand = (t: Token | null) => !!t && ["BYTEVAR", "WORDVAR", "HEX", "DEC"].includes(t.kind);
  const isOp = (t: Token | null) => !!t && (t.kind === "OP" || t.kind === "SEPOP");

  const parseAtom = (): number[] => {
    const tok = peek();
    if (!tok) throw new Error("Unexpected end of expression");
    if (tok.kind === "LPAREN") {
      consume();
      const res = parseExpression();
      consume("RPAREN");
      return res;
    } else if (isOperand(tok)) {
      consume();
      return encodeOperand(tok.kind, tok.value);
    }
    throw new Error(`Unexpected token: ${tok.kind} '${tok.value}'`);
  };

  const parseExpression = (): number[] => {
    const result: number[] = [];
    result.push(...parseAtom());
    while (isOp(peek())) {
      const opTok = consume()!;
      if (opTok.kind === "SEPOP") {
        const rawOp = parseInt(opTok.value.slice(1), 10);
        const next = peek();
        if (next && next.kind === "LPAREN") {
          result.push(0x80 | (rawOp & 0x1f));
          consume();
          result.push(...parseExpression());
          consume("RPAREN");
        } else if (isOperand(next)) {
          result.push(rawOp & 0x1f);
          result.push(...parseAtom());
        } else {
          result.push(0x80 | (rawOp & 0x1f));
          result.push(...parseAtom());
        }
      } else {
        const opIdx = OP_SYMBOLS[opTok.value];
        if (opIdx === undefined) throw new Error(`Unknown operator: '${opTok.value}'`);
        const next = peek();
        if (next && next.kind === "LPAREN") {
          result.push(0x80 | (opIdx & 0x1f));
          consume();
          result.push(...parseExpression());
          consume("RPAREN");
        } else {
          result.push(opIdx & 0x1f);
          result.push(...parseAtom());
        }
      }
    }
    return result;
  };

  const bytecode = parseExpression();
  bytecode.push(0xff);
  return Uint8Array.from(bytecode);
}

export function bytesToHex(b: Uint8Array): string {
  return Array.from(b).map((x) => x.toString(16).toUpperCase().padStart(2, "0")).join(" ");
}
