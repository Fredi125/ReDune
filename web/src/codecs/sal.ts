/**
 * ReDune codecs — SAL scene (room layout) decoder + encoder.
 * Direct port of tools/sal_decoder.py and tools/sal_encoder.py.
 *
 * SAL files (SIET/PALACE/VILG/HARK) define interior room layouts as a stream
 * of drawing commands per section: sprite placements, gradient polygons, and
 * rectangle fills. decode -> encode is byte-identical for all four shipped
 * files (verified in web/test against the Python reference).
 *
 * Section command stream (uint16 LE words, terminated by 0xFFFF):
 *   bit15 clear            -> sprite   (5 bytes): word, x_lo, y, pal
 *   bit15 set, AH==0xC0    -> rect fill (10 bytes): 0xC0xx, x1, y1, x2, y2
 *   bit15 set, AH!=0xC0    -> polygon (variable): header, x/y off, init, verts
 */

export type SalCommand =
  | { type: "sprite"; spriteIndex: number; x: number; y: number; paletteOffset: number; flags: number }
  | { type: "rect_fill"; header: number; x1: number; y1: number; x2: number; y2: number }
  | {
      type: "polygon";
      polyType: number;
      polySubtype: number;
      xOffset: number;
      yOffset: number;
      initX: number;
      initY: number;
      verticesPass1: [number, number][];
      verticesPass2: [number, number][];
    }
  | { type: "terminator" }
  | { type: "truncated" };

export interface SalSection {
  index: number;
  offset: number;
  size: number;
  spriteSlots: number;
  commands: SalCommand[];
}

export interface SalFile {
  sectionCount: number;
  offsets: number[];
  sections: SalSection[];
}

function u16(d: Uint8Array, o: number): number {
  return d[o] | (d[o + 1] << 8);
}

/** Parse the SAL offset table. Throws if the data is not a plausible SAL file. */
export function parseSal(data: Uint8Array): { sectionCount: number; offsets: number[] } {
  if (data.length < 2) throw new Error("SAL file too short");
  const first = u16(data, 0);
  if (first < 2 || first % 2 !== 0 || first > data.length) throw new Error("Not a SAL file (bad offset table)");
  const sectionCount = first >> 1;
  const offsets: number[] = [];
  let prev = -1;
  for (let i = 0; i < sectionCount; i++) {
    const off = u16(data, i * 2);
    if (off < first || off > data.length || off < prev) throw new Error("Not a SAL file (offsets out of range)");
    offsets.push(off);
    prev = off;
  }
  return { sectionCount, offsets };
}

/** Decode a single section [offset, end) into structured commands. */
export function decodeSection(data: Uint8Array, index: number, offset: number, end: number): SalSection {
  const section = data.subarray(offset, end);
  if (section.length < 1) {
    return { index, offset, size: section.length, spriteSlots: 0, commands: [] };
  }
  const spriteSlots = section[0];
  const commands: SalCommand[] = [];
  let pos = 1;

  while (pos + 1 < section.length) {
    const word = u16(section, pos);
    pos += 2;

    if (word === 0xffff) {
      commands.push({ type: "terminator" });
      break;
    }

    if (word & 0x8000) {
      const ah = (word >> 8) & 0xff;
      const al = word & 0xff;
      if (ah === 0xc0) {
        if (pos + 8 <= section.length) {
          const x1 = u16(section, pos);
          const y1 = u16(section, pos + 2);
          const x2 = u16(section, pos + 4);
          const y2 = u16(section, pos + 6);
          pos += 8;
          commands.push({ type: "rect_fill", header: word, x1, y1, x2, y2 });
        } else {
          commands.push({ type: "truncated" });
          break;
        }
      } else {
        const cmd: SalCommand = {
          type: "polygon",
          polyType: ah,
          polySubtype: al,
          xOffset: 0,
          yOffset: 0,
          initX: 0,
          initY: 0,
          verticesPass1: [],
          verticesPass2: [],
        };
        if (pos + 4 <= section.length) {
          let xOff = section[pos++];
          let yOff = section[pos++];
          if (xOff > 127) xOff -= 256;
          if (yOff > 127) yOff -= 256;
          cmd.xOffset = xOff * 16;
          cmd.yOffset = yOff * 16;

          if (pos + 4 <= section.length) {
            cmd.initX = u16(section, pos);
            cmd.initY = u16(section, pos + 2);
            pos += 4;

            let vxRaw = 0;
            while (pos + 4 <= section.length) {
              vxRaw = u16(section, pos);
              const vy = u16(section, pos + 2);
              pos += 4;
              cmd.verticesPass1.push([vxRaw & 0x3fff, vy]);
              if (vxRaw & 0x4000) break;
            }
            if (!(vxRaw & 0x8000)) {
              while (pos + 4 <= section.length) {
                vxRaw = u16(section, pos);
                const vy = u16(section, pos + 2);
                pos += 4;
                cmd.verticesPass2.push([vxRaw & 0x3fff, vy]);
                if (vxRaw & 0x8000) break;
              }
            }
          }
        }
        commands.push(cmd);
      }
    } else {
      const spriteIndex = (word & 0x1ff) - 1;
      const xBit8 = (word >> 9) & 1;
      const flags = (word >> 10) & 0x3f;
      if (pos + 3 <= section.length) {
        const xLo = section[pos];
        const y = section[pos + 1];
        const pal = section[pos + 2];
        pos += 3;
        commands.push({ type: "sprite", spriteIndex, x: (xBit8 << 8) | xLo, y, paletteOffset: pal, flags });
      } else {
        commands.push({ type: "truncated" });
        break;
      }
    }
  }

  return { index, offset, size: section.length, spriteSlots, commands };
}

/** Decode a whole SAL file. */
export function loadSal(data: Uint8Array): SalFile {
  const { sectionCount, offsets } = parseSal(data);
  const sections: SalSection[] = [];
  for (let i = 0; i < sectionCount; i++) {
    const end = i + 1 < sectionCount ? offsets[i + 1] : data.length;
    sections.push(decodeSection(data, i, offsets[i], end));
  }
  return { sectionCount, offsets, sections };
}

// ---------------------------------------------------------------------------
// Encoder (inverse) — byte-identical with the shipped files
// ---------------------------------------------------------------------------

function pushU16(out: number[], v: number) {
  out.push(v & 0xff, (v >> 8) & 0xff);
}

export function encodeSection(section: SalSection): number[] {
  const out: number[] = [];
  out.push(section.spriteSlots & 0xff);
  let hasTerminator = false;

  for (const cmd of section.commands) {
    switch (cmd.type) {
      case "sprite": {
        const spriteIndex = (cmd.spriteIndex + 1) & 0x1ff;
        const x = cmd.x & 0x1ff;
        const xBit8 = (x >> 8) & 1;
        const flags = cmd.flags & 0x3f;
        pushU16(out, (flags << 10) | (xBit8 << 9) | spriteIndex);
        out.push(x & 0xff, cmd.y & 0xff, cmd.paletteOffset & 0xff);
        break;
      }
      case "rect_fill": {
        pushU16(out, cmd.header & 0xffff);
        pushU16(out, cmd.x1 & 0xffff);
        pushU16(out, cmd.y1 & 0xffff);
        pushU16(out, cmd.x2 & 0xffff);
        pushU16(out, cmd.y2 & 0xffff);
        break;
      }
      case "polygon": {
        pushU16(out, ((cmd.polyType & 0xff) << 8) | (cmd.polySubtype & 0xff));
        out.push(Math.floor(cmd.xOffset / 16) & 0xff);
        out.push(Math.floor(cmd.yOffset / 16) & 0xff);
        pushU16(out, cmd.initX & 0xffff);
        pushU16(out, cmd.initY & 0xffff);
        const p1 = cmd.verticesPass1;
        const p2 = cmd.verticesPass2;
        for (let k = 0; k < p1.length; k++) {
          let raw = p1[k][0] & 0x3fff;
          if (k === p1.length - 1) {
            raw |= 0x4000;
            if (p2.length === 0) raw |= 0x8000;
          }
          pushU16(out, raw);
          pushU16(out, p1[k][1] & 0xffff);
        }
        for (let k = 0; k < p2.length; k++) {
          let raw = p2[k][0] & 0x3fff;
          if (k === p2.length - 1) raw |= 0x8000;
          pushU16(out, raw);
          pushU16(out, p2[k][1] & 0xffff);
        }
        break;
      }
      case "terminator":
        pushU16(out, 0xffff);
        hasTerminator = true;
        break;
      case "truncated":
        break;
    }
  }
  if (!hasTerminator) pushU16(out, 0xffff);
  return out;
}

/** Encode a list of sections into a complete .SAL byte array (rebuilds the table). */
export function encodeSal(sections: SalSection[]): Uint8Array {
  const encoded = sections.map(encodeSection);
  const tableSize = encoded.length * 2;
  const out: number[] = [];
  let pos = tableSize;
  for (const blob of encoded) {
    pushU16(out, pos & 0xffff);
    pos += blob.length;
  }
  for (const blob of encoded) out.push(...blob);
  return Uint8Array.from(out);
}

/** Count primitives in a section (for list summaries). */
export function sectionCounts(s: SalSection) {
  let sprites = 0;
  let polys = 0;
  let rects = 0;
  for (const c of s.commands) {
    if (c.type === "sprite") sprites++;
    else if (c.type === "polygon") polys++;
    else if (c.type === "rect_fill") rects++;
  }
  return { sprites, polys, rects };
}
