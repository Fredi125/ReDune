/**
 * ReDune codecs — CONDIT bytecode *evaluator* (the runtime, not the decompiler).
 *
 * Faithful port of the sub_C266 execution model documented in docs/condit_vm.md:
 * a stack machine with a DX accumulator. This is what actually gates events and
 * dialogue at play time — evaluate a condition against a variable store and you
 * learn whether an option is currently available.
 *
 *   1. read first operand → DX
 *   2. loop: 0xFF ends; byte<0x80 = inline op (DX = op(DX, AX)); byte>=0x80 =
 *      separator (push (DX, op); start a new sub-expression in DX)
 *   3. unwind the stack: DX = op(saved, DX)
 *   4. DX != 0  ⇒  condition TRUE
 *
 * Operator index = (controlByte & 0x1F) >> 1 (off_C246 is a word-pointer table).
 */
import { readOperand, type ConditFile } from "./condit";
import { compileExpr } from "./condit";

/** A CONDIT variable store: DS-variable index → 16-bit value. */
export type VarStore = Map<number, number>;

function operandValue(meta: ReturnType<typeof readOperand>["meta"], store: VarStore): number {
  if (!meta) return 0;
  if (meta.kind === "var") {
    const v = store.get(meta.idx) ?? 0;
    return meta.byteMode ? v & 0xff : v & 0xffff;
  }
  return meta.val & 0xffff;
}

const toS16 = (v: number): number => ((v & 0xffff) ^ 0x8000) - 0x8000;

/** Apply one operation (matches off_C246). Comparisons return 0xFFFF / 0x0000. */
function applyOp(op: number, dx: number, ax: number): number {
  const a = dx & 0xffff;
  const b = ax & 0xffff;
  switch (op) {
    case 0: return a === b ? 0xffff : 0; // EQ
    case 1: return a < b ? 0xffff : 0; // LT (unsigned)
    case 2: return a > b ? 0xffff : 0; // GT (unsigned)
    case 3: return a !== b ? 0xffff : 0; // NE
    case 4: return toS16(a) <= toS16(b) ? 0xffff : 0; // LE (signed)
    case 5: return toS16(a) >= toS16(b) ? 0xffff : 0; // GE (signed)
    case 6: return (a + b) & 0xffff; // ADD
    case 7: return (a - b) & 0xffff; // SUB
    case 8: return a & b; // AND
    case 9: return a | b; // OR
    default: return 0; // 0x0A-0x0F are NOP (dx = 0) in the jump table
  }
}

/**
 * Evaluate a CONDIT bytecode chain starting at `start`. Returns the 16-bit DX
 * result (non-zero ⇒ true).
 */
export function evalBytecode(data: Uint8Array, start: number, store: VarStore): number {
  let pos = start;
  const stack: [number, number][] = []; // [savedDX, opIndex]

  let r = readOperand(data, pos);
  pos = r.pos;
  let dx = operandValue(r.meta, store);

  while (pos < data.length) {
    const b = data[pos++];
    if (b === 0xff) break;
    const op = (b & 0x1f) >> 1;
    if (b >= 0x80) {
      stack.push([dx, op]);
      r = readOperand(data, pos);
      pos = r.pos;
      dx = operandValue(r.meta, store);
    } else {
      r = readOperand(data, pos);
      pos = r.pos;
      dx = applyOp(op, dx, operandValue(r.meta, store));
    }
  }
  while (stack.length) {
    const [saved, op] = stack.pop()!;
    dx = applyOp(op, saved, dx);
  }
  return dx & 0xffff;
}

/** True if CONDIT entry `idx` evaluates true against `store` (empty ⇒ always true). */
export function evalCondit(cf: ConditFile, idx: number, store: VarStore): boolean {
  if (idx < 0 || idx >= cf.offsets.length) return false;
  const off = cf.offsets[idx];
  const end = idx + 1 < cf.offsets.length ? cf.offsets[idx + 1] : cf.data.length;
  let empty = true;
  for (let i = off; i < end; i++) {
    if (cf.data[i] !== 0) {
      empty = false;
      break;
    }
  }
  if (empty) return true; // no condition ⇒ always available
  return (evalBytecode(cf.data, off, store) & 0xffff) !== 0;
}

/** Convenience: compile an expression and evaluate it (used in tests/playground). */
export function evalExpr(expr: string, store: VarStore): boolean {
  return (evalBytecode(compileExpr(expr), 0, store) & 0xffff) !== 0;
}
