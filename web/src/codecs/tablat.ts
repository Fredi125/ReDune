/**
 * ReDune codecs — TABLAT.BIN globe latitude table.
 * Port of decode_tablat in tools/bin_decoder.py. 99 × 8-byte records used by the
 * globe projection. The `scale` byte is the per-latitude horizontal radius
 * (≈ 199·cos(latitude), latitude linear in index) — i.e. the sphere
 * foreshortening curve.
 */

export interface TablatRecord {
  index: number;
  latAngle: number;
  yParam: number;
  scale: number;
  flags: number;
  secondary: number;
  extra: number;
}

export function parseTablat(data: Uint8Array): TablatRecord[] {
  if (data.length !== 792) throw new Error(`TABLAT should be 792 bytes, got ${data.length}`);
  const recs: TablatRecord[] = [];
  for (let i = 0; i < 99; i++) {
    const b = i * 8;
    recs.push({
      index: i,
      latAngle: data[b] | (data[b + 1] << 8),
      yParam: data[b + 2],
      scale: data[b + 3],
      flags: data[b + 4],
      secondary: data[b + 5],
      extra: data[b + 6] | (data[b + 7] << 8),
    });
  }
  return recs;
}

/** The per-latitude radius curve (scale bytes), for driving the globe width. */
export function tablatScaleCurve(recs: TablatRecord[]): number[] {
  return recs.map((r) => r.scale);
}
