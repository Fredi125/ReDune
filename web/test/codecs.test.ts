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
import { loadSpriteFile, decodeSprite, looksLikeSprite, encodeSpriteFile } from "../src/codecs/sprite";
import { loadSal, encodeSal } from "../src/codecs/sal";
import { loadTextTable, encodeTextTable, exportTextHsq, bytesToEditable, editableToBytes } from "../src/codecs/text";
import { loadDialogue, encodeDialogue } from "../src/codecs/dialogue";
import { decodeDnchar } from "../src/codecs/font";
import { parseDat, extractFile, buildDat, rebuildDat } from "../src/codecs/dat";
import { loadGradientTables, loadGlobe } from "../src/codecs/globdata";
import { parseTablat } from "../src/codecs/tablat";
import { HnmFile } from "../src/codecs/hnm";
import { loadHerad } from "../src/codecs/herad";
import { decodeVoc } from "../src/codecs/voc";
import { heatmapColor, detectMapWidth } from "../src/codecs/map";
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
// DIALOGUE table: entry + record counts must match the Python decoder
// ---------------------------------------------------------------------------
console.log("\nDIALOGUE table:");
{
  const path = join(GD, "DIALOGUE.HSQ");
  if (!existsSync(path)) skip("DIALOGUE", "DIALOGUE.HSQ missing");
  else {
    const df = loadDialogue(read(path));
    const totalRecords = df.entries.reduce((n, e) => n + e.records.length, 0);
    ok("DIALOGUE parses", df.entryCount > 0 && totalRecords > 0, `${df.entryCount} entries, ${totalRecords} records`);
    ok("DIALOGUE re-encode byte-identical", eq(encodeDialogue(df.entries), hsqDec(read(path))), `${df.data.length}B`);
    if (PY) {
      try {
        py(
          `import json,sys;sys.path.insert(0,'.');sys.path.insert(0,'tools')\nfrom dialogue_decompiler import load_dialogue,to_json_obj\nd,c,o=load_dialogue(${JSON.stringify(path)})\nobj=to_json_obj(d,o,'x')\njson.dump({'entries':obj['entry_count'],'records':len(obj['records'])},open('/tmp/redune_dlg.json','w'))`,
        );
        const ref = JSON.parse(readFileSync("/tmp/redune_dlg.json", "utf8"));
        ok("DIALOGUE matches Python", df.entryCount === ref.entries && totalRecords === ref.records, `${df.entryCount}/${totalRecords}`);
      } catch (e) {
        skip("DIALOGUE vs Python", String(e));
      }
    } else skip("DIALOGUE vs Python", "python3 unavailable");
  }
}

// ---------------------------------------------------------------------------
// VOC sound: sample rate + sample count must match the Python decoder
// ---------------------------------------------------------------------------
console.log("\nVOC sound:");
{
  const cand = ["SN1.HSQ", "SN2.HSQ", "SNA.HSQ", "SN5.VOC"].map((f) => join(GD, f)).find((p) => existsSync(p));
  if (!cand) skip("VOC", "no SN* sound file present");
  else {
    const v = decodeVoc(read(cand));
    ok("VOC decodes", v.samples.length > 0 && v.sampleRate > 0, `${v.sampleRate}Hz, ${v.samples.length} samples, ${v.duration.toFixed(2)}s`);
    if (PY) {
      try {
        py(
          `import json,sys;sys.path.insert(0,'.');sys.path.insert(0,'tools')\nfrom lib.compression import hsq_decompress\nfrom sound_decoder import parse_voc, VOC_MAGIC\nraw=open(${JSON.stringify(cand)},'rb').read()\nd=raw if raw[:20]==VOC_MAGIC else hsq_decompress(raw)\ni=parse_voc(bytes(d))\njson.dump({'sr':i['sample_rate'],'total':i['total_samples']},open('/tmp/redune_voc.json','w'))`,
        );
        const ref = JSON.parse(readFileSync("/tmp/redune_voc.json", "utf8"));
        ok("VOC matches Python", v.sampleRate === ref.sr && v.samples.length === ref.total, `sr=${v.sampleRate} n=${v.samples.length}`);
      } catch (e) {
        skip("VOC vs Python", String(e));
      }
    } else skip("VOC vs Python", "python3 unavailable");
  }
}

// ---------------------------------------------------------------------------
// DNCHAR font: glyph widths + bitmaps must match the Python decoder
// ---------------------------------------------------------------------------
console.log("\nDNCHAR font:");
{
  const path = join(GD, "DNCHAR.BIN");
  if (!existsSync(path)) skip("font", "DNCHAR.BIN missing");
  else {
    const glyphs = decodeDnchar(read(path));
    ok("font decodes 256 glyphs", glyphs.length === 256);
    if (PY) {
      try {
        py(
          `import json,sys;sys.path.insert(0,'tools')\nfrom bin_decoder import decode_dnchar\ng=decode_dnchar(open(${JSON.stringify(path)},'rb').read())\njson.dump([[c['width'],list(c['rows'])] for c in g],open('/tmp/redune_font.json','w'))`,
        );
        const ref: [number, number[]][] = JSON.parse(readFileSync("/tmp/redune_font.json", "utf8"));
        let mism = 0;
        for (let i = 0; i < 256; i++) {
          if (glyphs[i].width !== ref[i][0] || glyphs[i].rows.join(",") !== ref[i][1].join(",")) mism++;
        }
        ok("font matches Python (256 glyphs)", mism === 0, `${mism} mismatch`);
      } catch (e) {
        skip("font vs Python", String(e));
      }
    } else skip("font vs Python", "python3 unavailable");
  }
}

// ---------------------------------------------------------------------------
// MAP heatmap: gradient + width detection match the Python renderer
// ---------------------------------------------------------------------------
console.log("\nMAP heatmap:");
{
  ok("map width detect (50681)", detectMapWidth(50681) === 320, `${detectMapWidth(50681)}`);
  const anchors: [number, [number, number, number]][] = [
    [0x00, [0, 0, 0]],
    [0x3f, [0, 0, 255]],
    [0x7f, [0, 255, 0]],
    [0xbf, [255, 255, 0]],
    [0xff, [255, 255, 255]],
  ];
  const good = anchors.every(([v, c]) => {
    const r = heatmapColor(v);
    return r[0] === c[0] && r[1] === c[1] && r[2] === c[2];
  });
  ok("map heatmap gradient anchors", good);
  if (PY) {
    try {
      py(
        `import json,sys;sys.path.insert(0,'tools')\nfrom map_decoder import map_heatmap_color\njson.dump([list(map_heatmap_color(v)) for v in range(256)],open('/tmp/redune_map.json','w'))`,
      );
      const ref: [number, number, number][] = JSON.parse(readFileSync("/tmp/redune_map.json", "utf8"));
      let mism = 0;
      for (let v = 0; v < 256; v++) {
        const r = heatmapColor(v);
        if (r[0] !== ref[v][0] || r[1] !== ref[v][1] || r[2] !== ref[v][2]) mism++;
      }
      ok("map heatmap matches Python (256 values)", mism === 0, `${mism} mismatch`);
    } catch (e) {
      skip("map vs Python", String(e));
    }
  } else skip("map vs Python", "python3 unavailable");
}

// ---------------------------------------------------------------------------
// GLOBDATA gradient tables (SAL polygon shading) — match the Python parser
// ---------------------------------------------------------------------------
console.log("\nGLOBDATA gradient tables:");
{
  const path = join(GD, "GLOBDATA.HSQ");
  if (!existsSync(path)) skip("globdata", "GLOBDATA.HSQ missing");
  else {
    const tables = loadGradientTables(read(path));
    ok("gradient tables parse", tables.length === 55, `${tables.length} tables`);
    const globe = loadGlobe(read(path));
    ok("globe scanlines parse", globe.length === 64, `${globe.length} latitude blocks`);
    if (PY) {
      try {
        py(
          `import json,sys;sys.path.insert(0,'tools')\nfrom globdata_decoder import parse_gradient_tables, parse_globe_scanlines\nfrom compression import hsq_decompress\nraw=open(${JSON.stringify(path)},'rb').read()\nd=hsq_decompress(raw) if (sum(raw[:6])&0xFF)==0xAB else raw\n_,gs=parse_gradient_tables(d)\nsl=parse_globe_scanlines(d,gs)\njson.dump([[s['ramp_max'], s['ramp']] for s in sl],open('/tmp/redune_globe.json','w'))`,
        );
        const ref: [number, number[]][] = JSON.parse(readFileSync("/tmp/redune_globe.json", "utf8"));
        const gok = ref.length === globe.length && globe.every((s, i) => s.rampMax === ref[i][0] && s.ramp.join(",") === ref[i][1].join(","));
        ok("globe scanlines match Python", gok, `${ref.length} blocks`);
      } catch (e) {
        skip("globe vs Python", String(e));
      }
    }
    if (PY) {
      try {
        py(
          `import json,sys;sys.path.insert(0,'tools')\nfrom globdata_decoder import parse_gradient_tables\nfrom compression import hsq_decompress\nraw=open(${JSON.stringify(path)},'rb').read()\nd=hsq_decompress(raw) if (sum(raw[:6])&0xFF)==0xAB else raw\nt,_=parse_gradient_tables(d)\nr=[x for x in t if x['length']>0]\njson.dump([x['values'] for x in r],open('/tmp/redune_grad.json','w'))`,
        );
        const ref: number[][] = JSON.parse(readFileSync("/tmp/redune_grad.json", "utf8"));
        let mism = 0;
        for (let i = 0; i < Math.min(ref.length, tables.length); i++) {
          if (tables[i].values.join(",") !== ref[i].join(",")) mism++;
        }
        ok("gradient tables match Python", mism === 0 && ref.length === tables.length, `${mism} mismatch`);
      } catch (e) {
        skip("globdata vs Python", String(e));
      }
    } else skip("globdata vs Python", "python3 unavailable");
  }
}

// ---------------------------------------------------------------------------
// TABLAT globe latitude table — match the Python decoder
// ---------------------------------------------------------------------------
console.log("\nTABLAT latitude table:");
{
  const path = join(GD, "TABLAT.BIN");
  if (!existsSync(path)) skip("tablat", "TABLAT.BIN missing");
  else {
    const recs = parseTablat(read(path));
    ok("TABLAT parses 99 records", recs.length === 99);
    if (PY) {
      try {
        py(
          `import json,sys;sys.path.insert(0,'tools')\nfrom bin_decoder import decode_tablat\nr=decode_tablat(open(${JSON.stringify(path)},'rb').read())\njson.dump([[x['scale'],x['secondary'],x['lat_angle']] for x in r],open('/tmp/redune_tablat.json','w'))`,
        );
        const ref: number[][] = JSON.parse(readFileSync("/tmp/redune_tablat.json", "utf8"));
        const tok = ref.length === recs.length && recs.every((r, i) => r.scale === ref[i][0] && r.secondary === ref[i][1] && r.latAngle === ref[i][2]);
        ok("TABLAT matches Python", tok);
      } catch (e) {
        skip("TABLAT vs Python", String(e));
      }
    }
  }
}

// ---------------------------------------------------------------------------
// DUNE.DAT archive: parse / extract / build (byte-identical vs Python) / replace
// (validated against a synthetic archive since the real DUNE.DAT isn't shipped)
// ---------------------------------------------------------------------------
console.log("\nDUNE.DAT archive:");
{
  const srcs = ["CONDIT.HSQ", "PALACE.SAL", "DNCHAR.BIN"].map((f) => join(GD, f));
  if (!PY) skip("DAT", "python3 unavailable");
  else if (!srcs.every(existsSync)) skip("DAT", "source files missing");
  else {
    try {
      py(
        `import sys;sys.path.insert(0,'.');sys.path.insert(0,'tools')\nfrom dat_decoder import build_dat\nbuild_dat([('CONDIT.HSQ','gamedata/CONDIT.HSQ',0),('PALACE.SAL','gamedata/PALACE.SAL',1),('DNCHAR.BIN','gamedata/DNCHAR.BIN',0)],'/tmp/redune_test.dat')`,
      );
      const datBytes = read("/tmp/redune_test.dat");
      const dat = parseDat(datBytes);
      ok("DAT parses entries", dat.entries.length === 3 && dat.entries[0].name === "CONDIT.HSQ" && dat.entries[1].flag === 1, `${dat.entries.length} files`);

      const condit = read(srcs[0]);
      ok("DAT extract matches source", eq(extractFile(dat, dat.entries[0]), condit));

      const files = [
        { name: "CONDIT.HSQ", data: read(srcs[0]), flag: 0 },
        { name: "PALACE.SAL", data: read(srcs[1]), flag: 1 },
        { name: "DNCHAR.BIN", data: read(srcs[2]), flag: 0 },
      ];
      ok("DAT build byte-identical to Python", eq(buildDat(files), datBytes), `${datBytes.length}B`);

      const repl = new Map([["PALACE.SAL", Uint8Array.from([1, 2, 3, 4, 5])]]);
      const rebuilt = parseDat(rebuildDat(dat, repl));
      const pal = rebuilt.entries.find((e) => e.name === "PALACE.SAL")!;
      ok(
        "DAT replace round-trips",
        eq(extractFile(rebuilt, pal), Uint8Array.from([1, 2, 3, 4, 5])) && eq(extractFile(rebuilt, rebuilt.entries[0]), condit),
      );
    } catch (e) {
      ok("DAT", false, String(e));
    }
  }
}

// ---------------------------------------------------------------------------
// HNM video: per-frame framebuffer checksums must match the Python decoder
// ---------------------------------------------------------------------------
console.log("\nHNM video:");
{
  const path = ["FORT.HNM", "CRYO2.HNM", "DEAD3.HNM"].map((f) => join(GD, f)).find((p) => existsSync(p));
  if (!path) skip("HNM", "no .HNM present");
  else {
    const h = new HnmFile(read(path));
    const fb = new Uint8Array(64000);
    const pal = h.palette.slice();
    const N = Math.min(h.frameCount, 40);
    const sums: number[] = [];
    for (let i = 0; i < N; i++) {
      h.decodeFrame(i, fb, pal);
      let s = 0;
      for (let k = 0; k < fb.length; k++) s += fb[k];
      sums.push(s);
    }
    ok("HNM decodes frames", h.frameCount > 0 && sums.some((s) => s > 0), `${h.frameCount} frames`);
    if (PY) {
      try {
        py(
          `import json,sys;sys.path.insert(0,'tools')\nfrom hnm_decoder import HnmFile\nh=HnmFile(open(${JSON.stringify(path)},'rb').read())\nfb=bytearray(64000); pal=bytearray(h.palette)\nN=min(h.frame_count,40); s=[]\nfor i in range(N):\n h.decode_frame(i,fb,pal); s.append(sum(fb))\njson.dump({'frames':h.frame_count,'sums':s},open('/tmp/redune_hnm.json','w'))`,
        );
        const ref = JSON.parse(readFileSync("/tmp/redune_hnm.json", "utf8"));
        const match = h.frameCount === ref.frames && sums.length === ref.sums.length && sums.every((s, i) => s === ref.sums[i]);
        ok("HNM matches Python (framebuffer checksums)", match, `${N} frames checked`);
      } catch (e) {
        skip("HNM vs Python", String(e));
      }
    } else skip("HNM vs Python", "python3 unavailable");
  }
}

// ---------------------------------------------------------------------------
// HERAD music: MIDI export must be byte-identical to the Python converter
// (OPL2 / AGD / M32 variants)
// ---------------------------------------------------------------------------
console.log("\nHERAD music -> MIDI:");
for (const f of ["ARRAKIS.HSQ", "ARRAKIS.AGD", "ARRAKIS.M32"]) {
  const path = join(GD, f);
  if (!existsSync(path)) {
    skip(`HERAD ${f}`, "file missing");
    continue;
  }
  const { info, midi, instruments } = loadHerad(read(path), f);
  ok(`HERAD ${f} decodes`, midi.length > 0 && midi[0] === 0x4d, `${info.format}, ${info.tracks.length} tracks, ${midi.length}B MIDI`);
  if (f.endsWith(".HSQ")) {
    const instOk = instruments.length > 0 && instruments.every((x) => x.modWave <= 3 && x.carWave <= 3 && x.modMul <= 15 && x.carMul <= 15 && x.modOut <= 63 && x.carOut <= 63);
    ok(`HERAD ${f} instruments parse`, instOk, `${instruments.length} FM patches`);
  }
  if (PY) {
    try {
      const ref = "/tmp/redune_herad.mid";
      py(
        `import sys;sys.path.insert(0,'tools')\nfrom herad_decoder import export_midi\nfrom compression import hsq_decompress\nraw=open(${JSON.stringify(path)},'rb').read()\nd=hsq_decompress(raw) if (len(raw)>=6 and (sum(raw[:6])&0xFF)==0xAB) else raw\nexport_midi(${JSON.stringify(path)}, bytes(d), ${JSON.stringify(ref)})`,
      );
      ok(`HERAD ${f} MIDI matches Python`, eq(midi, read(ref)));
    } catch (e) {
      skip(`HERAD ${f} vs Python`, String(e));
    }
  } else skip(`HERAD ${f} vs Python`, "python3 unavailable");
}

// ---------------------------------------------------------------------------
// NPC / smuggler save data: TS offsets must match the Python decoder
// ---------------------------------------------------------------------------
console.log("\nNPC / smuggler save data:");
{
  const savePath = ["SampleSave.SAV", "Stilgar.SAV"].map((f) => join(ROOT, f)).find((p) => existsSync(p));
  if (!savePath) skip("npc/smuggler", "no .SAV present");
  else if (!PY) skip("npc/smuggler", "python3 unavailable");
  else {
    try {
      py(
        `import json,sys;sys.path.insert(0,'.')\nfrom lib.compression import f7_decompress\nd=f7_decompress(open(${JSON.stringify(savePath)},'rb').read())\nN=0x53F4;S=0x54F6\nnpc=[[d[N+i*16],d[N+i*16+6]] for i in range(16)]\nsm=[[d[S+i*17+4],d[S+i*17+9]] for i in range(6)]\njson.dump({'npc':npc,'sm':sm},open('/tmp/redune_ns.json','w'))`,
      );
      const ref = JSON.parse(readFileSync("/tmp/redune_ns.json", "utf8"));
      const sav = new DuneSave(read(savePath));
      const npcs = sav.allNpcs();
      const sm = sav.allSmugglers();
      const npcOk = ref.npc.every((p: number[], i: number) => npcs[i].spriteId === p[0] && npcs[i].forDialogue === p[1]);
      const smOk = ref.sm.every((p: number[], i: number) => sm[i].harvesters === p[0] && sm[i].priceHarvesters === p[1]);
      ok("NPC/smuggler offsets match Python", npcOk && smOk);
    } catch (e) {
      skip("npc/smuggler vs Python", String(e));
    }
  }
}

// ---------------------------------------------------------------------------
// Sprite encoder: re-encode (raw) must decode back to identical sprites
// ---------------------------------------------------------------------------
console.log("\nSprite encoder (round-trip):");
{
  const path = ["CHAN.HSQ", "BARO.HSQ", "PERS.HSQ"].map((f) => join(GD, f)).find((p) => existsSync(p));
  if (!path) skip("sprite encode", "no sprite HSQ present");
  else {
    const sf = loadSpriteFile(read(path));
    const sprites = [];
    for (let i = 0; i < sf.count; i++) {
      const s = decodeSprite(sf.data, i);
      sprites.push({ width: s.width, height: s.height, paletteOffset: s.paletteOffset, pixels: s.pixels });
    }
    const encoded = encodeSpriteFile({ paletteBytes: sf.paletteBytes, hasExtra: sf.hasExtra, sprites });
    const sf2 = loadSpriteFile(encoded, true);
    let okAll = sf2.count === sf.count && sf2.palette.size === sf.palette.size;
    for (let i = 0; i < sf.count && okAll; i++) {
      const a = decodeSprite(sf.data, i);
      const b = decodeSprite(sf2.data, i);
      if (a.width !== b.width || a.height !== b.height || a.paletteOffset !== b.paletteOffset || !eq(a.pixels, b.pixels)) okAll = false;
    }
    ok("sprite re-encode decodes identically", okAll, `${sf.count} sprites`);
  }
}

// ---------------------------------------------------------------------------
console.log(`\n${passed} passed, ${failed} failed, ${skipped} skipped`);
assert.equal(failed, 0, `${failed} codec test(s) failed`);
console.log("All codec tests passed.\n");
