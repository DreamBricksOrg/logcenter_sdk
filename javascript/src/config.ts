import path from "node:path";

export type LogCenterConfigInit = {
  baseUrl: string;
  projectId: string;
  apiKey?: string;

  timeoutMs?: number;
  followRedirects?: boolean;

  enabled?: boolean;

  spoolDir?: string;
  spoolFilename?: string;
  spoolMaxBytes?: number;

  flushBatchSize?: number;
  flushIntervalMs?: number;
};

export class LogCenterConfig {
  readonly baseUrl: string;
  readonly projectId: string;
  readonly apiKey?: string;

  readonly timeoutMs: number;
  readonly followRedirects: boolean;

  readonly enabled: boolean;

  readonly spoolDir: string;
  readonly spoolFilename: string;
  readonly spoolMaxBytes: number;

  readonly flushBatchSize: number;
  readonly flushIntervalMs: number;

  constructor(init: LogCenterConfigInit) {
    const base = (init.baseUrl || "").replace(/\/+$/, "");
    const pid = init.projectId || "";
    if (!base || !pid) throw new Error("Missing baseUrl or projectId");

    this.baseUrl = base;
    this.projectId = pid;
    this.apiKey = init.apiKey;

    this.timeoutMs = init.timeoutMs ?? 10_000;
    this.followRedirects = init.followRedirects ?? true;

    this.enabled = init.enabled ?? true;

    this.spoolDir = init.spoolDir ?? process.env.LOGCENTER_SPOOL_DIR ?? ".logcenter";
    this.spoolFilename = init.spoolFilename ?? "spool.jsonl";
    this.spoolMaxBytes = init.spoolMaxBytes ?? 25 * 1024 * 1024;

    this.flushBatchSize = init.flushBatchSize ?? 200;
    this.flushIntervalMs = init.flushIntervalMs ?? 10_000;
  }

  static fromEnv(prefix = "LOGCENTER_"): LogCenterConfig {
    const baseUrl = (process.env[`${prefix}BASE_URL`] || "").replace(/\/+$/, "");
    const projectId = process.env[`${prefix}PROJECT_ID`] || "";
    const apiKey = process.env[`${prefix}API_KEY`] || undefined;

    const timeoutMs = Number(process.env[`${prefix}TIMEOUT_MS`] || "10000");
    const spoolDir = process.env[`${prefix}SPOOL_DIR`] || ".logcenter";
    const spoolMaxBytes = Number(process.env[`${prefix}SPOOL_MAX_BYTES`] || String(25 * 1024 * 1024));
    const flushBatchSize = Number(process.env[`${prefix}FLUSH_BATCH_SIZE`] || "200");
    const flushIntervalMs = Number(process.env[`${prefix}FLUSH_INTERVAL_MS`] || "10000");
    const enabled = (process.env[`${prefix}ENABLED`] || "true").toLowerCase() !== "false";

    return new LogCenterConfig({
      baseUrl,
      projectId,
      apiKey,
      timeoutMs,
      spoolDir: path.normalize(spoolDir),
      spoolMaxBytes,
      flushBatchSize,
      flushIntervalMs,
      enabled,
    });
  }
}
