/**
 * Validates the TypeScript codec ports against the Python reference
 * implementation, using the real game files in ../gamedata.
 *
 * Run: npm test   (from web/)
 */
import { strict as assert } from "node:assert";
import { execFileSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";

import { hsqDecompress, hsqCompress, f7Decompress, f7Compress } from "../src/codecs/compression";
import { loadCondit, conditEntries, compileExpr, bytesToHex } from "../src/codecs/condit";
import { DuneSave } from "../src/codecs/save";
import { loadSpriteFile, decodeSprite, looksLikeSprite } from "../src/codecs/sprite";
import { loadSal, encodeSal } from "../src/codecs/sal";
import { loadTextTable, encodeTextTable, exportTextHsq, bytesToEditable, editableToBytes } from "../src/codecs/text";
import { hsqDecompress as hsqDec } from "../src/codecs/compression";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, "..", "..");
const GD = join(ROOT, "gamedata");

let passed = 0;
let failed = 0;
let skipped = 0;

function ok(name: string, cond: boolean, detail = "") {
  if (cond) {
    passed++;
    console.log(`  ✓ ${name}${detail ? "  (" + detail + ")" : ""}`);
  } else {
    failed++;
    console.error(`  ✗ FAIL: ${name}${detail ? "  (" + detail + ")" : ""}`);
  }
}
function skip(name: string, why: string) {
  skipped++;
  console.warn(`  ⊘ skip: ${name} — ${why}`);
}

function read(file: string): Uint8Array {
  return new Uint8Array(readFileSync(file));
}
function eq(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
function py(script: string): void {
  execFileSync("python3", ["-c", script], { cwd: ROOT, maxBuffer: 1 << 28 });
}
function havePython(): boolean {
  try {
    execFileSync("python3", ["--version"], { cwd: ROOT });
    return true;
  } catch {
    return false;
  }
}

const PY = havePython();
const HAS_GD = existsSync(GD);

console.log(`ReDune codec tests  (root=${ROOT}, python=${PY}, gamedata=${HAS_GD})\n`);

// ---------------------------------------------------------------------------
// HSQ
// ---------------------------------------------------------------------------
console.log("HSQ compression:");
for (const f of ["CONDIT.HSQ", "DIALOGUE.HSQ", "CHAN.HSQ"]) {
  const path = join(GD, f);
  if (!existsSync(path)) {
    skip(`HSQ ${f}`, "file missing");
    continue;
  }
  const raw = read(path);
  let dec: Uint8Array;
  try {
    dec = hsqDecompress(raw);
  } catch (e) {
    ok(`HSQ decode ${f}`, false, String(e));
    continue;
  }

  // self-consistency: re-compress, decode again -> identical
  const rec = hsqCompress(dec);
  const dec2 = hsqDecompress(rec);
  ok(`HSQ ${f} re-compress roundtrip`, eq(dec, dec2), `${dec.length}B`);

  // cross-check vs Python reference
  if (PY) {
    try {
      const ref = "/tmp/redune_ref_hsq.bin";
      py(
        `import sys;sys.path.insert(0,'lib')\nfrom compression import hsq_decompress\nopen(${JSON.stringify(ref)},'wb').write(bytes(hsq_decompress(open(${JSON.stringify(path)},'rb').read())))`,
      );
      ok(`HSQ ${f} matches Python decode`, eq(dec, read(ref)));
    } catch (e) {
      skip(`HSQ ${f} vs Python`, String(e));
    }
  } else {
    skip(`HSQ ${f} vs Python`, "python3 unavailable");
  }
}

// ---------------------------------------------------------------------------
// F7 (save files)
// ---------------------------------------------------------------------------
console.log("\nF7 RLE (save files):");
{
  const candidates = ["SampleSave.SAV", "Stilgar.SAV", "ModMe.SAV"].map((f) => join(ROOT, f));
  const savePath = candidates.find((p) => existsSync(p));
  if (!savePath) {
    skip("F7 decode", "no .SAV present");
  } else {
    const raw = read(savePath);
    const dec = f7Decompress(raw);
    const recomp = f7Compress(dec);
    const dec2 = f7Decompress(recomp);
    ok("F7 decompress/compress roundtrip", eq(dec, dec2), `${dec.length}B`);

    if (PY) {
      try {
        const refD = "/tmp/redune_ref_f7d.bin";
        const refC = "/tmp/redune_ref_f7c.bin";
        py(
          `import sys;sys.path.insert(0,'lib')\nfrom compression import f7_decompress,f7_compress\nraw=open(${JSON.stringify(savePath)},'rb').read()\nd=f7_decompress(raw)\nopen(${JSON.stringify(refD)},'wb').write(bytes(d))\nopen(${JSON.stringify(refC)},'wb').write(bytes(f7_compress(d)))`,
        );
        ok("F7 decompress matches Python", eq(dec, read(refD)));
        ok("F7 compress matches Python", eq(recomp, read(refC)));
      } catch (e) {
        skip("F7 vs Python", String(e));
      }
    } else {
      skip("F7 vs Python", "python3 unavailable");
    }
  }
}

// ---------------------------------------------------------------------------
// Save parsing
// ---------------------------------------------------------------------------
console.log("\nSave parsing:");
{
  const savePath = ["SampleSave.SAV", "Stilgar.SAV"].map((f) => join(ROOT, f)).find((p) => existsSync(p));
  if (!savePath) {
    skip("save parse", "no .SAV present");
  } else {
    const sav = new DuneSave(read(savePath));
    ok("save parses globals", sav.gameStage >= 0 && sav.gameStage <= 0xff, `stage=0x${sav.gameStage.toString(16)}, day=${sav.day}, spice=${sav.spice}`);
    // edit roundtrip: changing a value and re-serializing then re-reading
    const origSpice = sav.spice;
    sav.spice = (origSpice + 123) & 0xffff;
    const sav2 = new DuneSave(sav.serialize());
    ok("save edit survives re-serialize", sav2.spice === ((origSpice + 123) & 0xffff));

    if (PY) {
      try {
        py(
          `import sys,json;sys.path.insert(0,'.')\nsys.path.insert(0,'tools')\nfrom lib.compression import f7_decompress\nimport struct\nd=f7_decompress(open(${JSON.stringify(savePath)},'rb').read())\nfrom lib.constants import SAVE_OFFSETS as O\nj={'stage':d[O['game_stage']],'spice':struct.unpack_from('<H',d,O['spice'])[0],'dt':struct.unpack_from('<H',d,O['datetime'])[0]}\njson.dump(j,open('/tmp/redune_save.json','w'))`,
        );
        const ref = JSON.parse(readFileSync("/tmp/redune_save.json", "utf8"));
        const sav0 = new DuneSave(read(savePath));
        ok("save globals match Python", sav0.gameStage === ref.stage && sav0.spice === ref.spice && sav0.datetimeRaw === ref.dt);
      } catch (e) {
        skip("save vs Python", String(e));
      }
    } else {
      skip("save vs Python", "python3 unavailable");
    }
  }
}

// ---------------------------------------------------------------------------
// CONDIT decompiler + recompiler
// ---------------------------------------------------------------------------
console.log("\nCONDIT decompiler/recompiler:");
{
  const path = join(GD, "CONDIT.HSQ");
  if (!existsSync(path)) {
    skip("CONDIT", "CONDIT.HSQ missing");
  } else {
    const cf = loadCondit(read(path));
    ok("CONDIT entry count", cf.entryCount === 713, `${cf.entryCount} entries`);

    const entries = conditEntries(cf, false).filter((e) => !e.empty);

    // recompiler roundtrip rate (Python reports ~63.7%)
    let rtPass = 0;
    let rtTotal = 0;
    for (const e of entries) {
      const original = cf.data.subarray(e.offset, e.offset + e.sizeExec);
      rtTotal++;
      try {
        const recompiled = compileExpr(e.expr);
        if (eq(recompiled, original)) rtPass++;
      } catch {
        /* counts as fail */
      }
    }
    const rate = rtPass / rtTotal;
    ok("CONDIT recompiler roundtrip rate >= 60%", rate >= 0.6, `${(rate * 100).toFixed(1)}% (${rtPass}/${rtTotal})`);

    if (PY) {
      try {
        py(
          `import json,sys,struct\nsys.path.insert(0,'.')\nsys.path.insert(0,'tools')\nfrom lib.compression import hsq_decompress\nfrom condit_decompiler import decompile_entry\nd=hsq_decompress(open(${JSON.stringify(path)},'rb').read())\nn=struct.unpack_from('<H',d,0)[0]//2\noffs=[struct.unpack_from('<H',d,i*2)[0] for i in range(n)]\nres=[]\nfor i in range(n):\n off=offs[i]; te=offs[i+1] if i+1<n else len(d)\n if all(b==0 for b in d[off:te]): continue\n expr,end=decompile_entry(d,off,False)\n res.append([i,expr])\njson.dump(res,open('/tmp/redune_condit.json','w'))`,
        );
        const ref: [number, string][] = JSON.parse(readFileSync("/tmp/redune_condit.json", "utf8"));
        const tsMap = new Map(conditEntries(cf, false).filter((e) => !e.empty).map((e) => [e.index, e.expr]));
        let mism = 0;
        for (const [idx, expr] of ref) {
          if (tsMap.get(idx) !== expr) {
            if (mism < 3) console.error(`     mismatch @${idx}: py='${expr}' ts='${tsMap.get(idx)}'`);
            mism++;
          }
        }
        ok("CONDIT decompile matches Python (all entries)", mism === 0, `${ref.length} entries, ${mism} mismatch`);
      } catch (e) {
        skip("CONDIT vs Python", String(e));
      }
    } else {
      skip("CONDIT vs Python", "python3 unavailable");
    }

    // a known compile example
    const bc = compileExpr("byte[GameStage] == 0x50");
    ok("CONDIT compile example", bytesToHex(bc) === "01 2A 00 80 50 FF", bytesToHex(bc));
  }
}

// ---------------------------------------------------------------------------
// Sprite decoding
// ---------------------------------------------------------------------------
console.log("\nSprite decoding:");
{
  const path = ["CHAN.HSQ", "MAP2.HSQ", "PERS.HSQ"].map((f) => join(GD, f)).find((p) => existsSync(p));
  if (!path) {
    skip("sprite", "no sprite HSQ present");
  } else {
    const sf = loadSpriteFile(read(path));
    ok("sprite file parses", sf.count > 0, `${sf.count} sprites, ${sf.palette.size} colors`);
    const s0 = decodeSprite(sf.data, 0);
    let sum = 0;
    for (const p of s0.pixels) sum += p;

    if (PY) {
      try {
        py(
          `import json,sys\nsys.path.insert(0,'tools')\nimport sprite_decoder as S\nd=S.hsq_decompress(open(${JSON.stringify(path)},'rb').read())\nn=S.count_sprites(d)\nspr=S.decode_sprite(d,0)\njson.dump({'n':n,'w':spr['width'],'h':spr['height'],'len':len(spr['pixels']),'sum':int(sum(spr['pixels']))},open('/tmp/redune_sprite.json','w'))`,
        );
        const ref = JSON.parse(readFileSync("/tmp/redune_sprite.json", "utf8"));
        ok(
          "sprite 0 matches Python",
          sf.count === ref.n && s0.width === ref.w && s0.height === ref.h && s0.pixels.length === ref.len && sum === ref.sum,
          `${s0.width}x${s0.height}, sum=${sum}`,
        );
      } catch (e) {
        skip("sprite vs Python", String(e));
      }
    } else {
      skip("sprite vs Python", "python3 unavailable");
    }
  }
}

// ---------------------------------------------------------------------------
// SAL room layout: decode -> encode must be byte-identical (all 4 files)
// ---------------------------------------------------------------------------
console.log("\nSAL room layouts:");
for (const f of ["SIET.SAL", "PALACE.SAL", "VILG.SAL", "HARK.SAL"]) {
  const path = join(GD, f);
  if (!existsSync(path)) {
    skip(`SAL ${f}`, "file missing");
    continue;
  }
  const orig = read(path);
  const sal = loadSal(orig);
  const re = encodeSal(sal.sections);
  ok(`SAL ${f} byte-identical round-trip`, eq(orig, re), `${sal.sectionCount} sections, ${orig.length}B`);
}

// ---------------------------------------------------------------------------
// String tables (PHRASE / COMMAND): lossless edit form + round-trip
// ---------------------------------------------------------------------------
console.log("\nString tables (PHRASE / COMMAND):");
for (const f of ["PHRASE11.HSQ", "COMMAND1.HSQ"]) {
  const path = join(GD, f);
  if (!existsSync(path)) {
    skip(`text ${f}`, "file missing");
    continue;
  }
  const raw = read(path);
  const decompressed = hsqDec(raw);
  const tbl = loadTextTable(raw);

  // editable text form is lossless per entry
  const lossless = tbl.entries.every((e) => eq(editableToBytes(bytesToEditable(e.raw)), e.raw));
  ok(`${f} editable form is lossless`, lossless, `${tbl.count} strings`);

  // rebuild decompressed bytes from unedited entries -> byte-identical
  ok(`${f} table rebuild byte-identical`, eq(encodeTextTable(tbl.entries), decompressed));

  // full pipeline: edit-export -> decompress -> identical to original
  ok(`${f} export+decompress round-trip`, eq(hsqDec(exportTextHsq(tbl.entries)), decompressed));
}

// ---------------------------------------------------------------------------
// File-type detection (sprite vs CONDIT) — prevents the CONDIT studio from
// silently decoding a sprite sheet (e.g. BARO.HSQ) as bytecode.
// ---------------------------------------------------------------------------
console.log("\nFile-type detection:");
{
  const baro = join(GD, "BARO.HSQ");
  const condit = join(GD, "CONDIT.HSQ");
  if (existsSync(baro)) ok("BARO.HSQ detected as sprite", looksLikeSprite(hsqDec(read(baro))));
  else skip("BARO sprite detect", "BARO.HSQ missing");
  if (existsSync(condit)) ok("CONDIT.HSQ NOT detected as sprite", !looksLikeSprite(hsqDec(read(condit))));
  else skip("CONDIT non-sprite detect", "CONDIT.HSQ missing");
}

// ---------------------------------------------------------------------------
console.log(`\n${passed} passed, ${failed} failed, ${skipped} skipped`);
assert.equal(failed, 0, `${failed} codec test(s) failed`);
console.log("All codec tests passed.\n");
