import fs from "node:fs";
import path from "node:path";

export type SpoolStats = { queued: number; bytes: number };

export class FileSpool {
  private fullpath: string;

  constructor(private dir: string, private filename: string, private maxBytes: number) {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    this.fullpath = path.join(dir, filename);
    if (!fs.existsSync(this.fullpath)) fs.writeFileSync(this.fullpath, "", "utf8");
  }

  append(obj: any) {
    const line = JSON.stringify(obj) + "\n";
    fs.appendFileSync(this.fullpath, line, "utf8");

    const st = fs.statSync(this.fullpath);
    if (st.size > this.maxBytes) {
      const bak = this.fullpath + ".bak";
      try { fs.renameSync(this.fullpath, bak); } catch {}
      fs.writeFileSync(this.fullpath, "", "utf8");
    }
  }

  popBatch(maxItems: number): { batch: any[]; remaining: number } {
    if (!fs.existsSync(this.fullpath)) return { batch: [], remaining: 0 };

    const content = fs.readFileSync(this.fullpath, "utf8");
    const lines = content.split("\n").filter(Boolean);

    const batchLines = lines.slice(0, maxItems);
    const remainingLines = lines.slice(maxItems);

    const batch: any[] = [];
    for (const ln of batchLines) {
      try { batch.push(JSON.parse(ln)); } catch {}
    }

    fs.writeFileSync(
      this.fullpath,
      remainingLines.join("\n") + (remainingLines.length ? "\n" : ""),
      "utf8"
    );

    return { batch, remaining: remainingLines.length };
  }

  stats(): SpoolStats {
    if (!fs.existsSync(this.fullpath)) return { queued: 0, bytes: 0 };
    const content = fs.readFileSync(this.fullpath, "utf8");
    const lines = content.split("\n").filter(Boolean);
    const st = fs.statSync(this.fullpath);
    return { queued: lines.length, bytes: st.size };
  }
}
