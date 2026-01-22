import { LogCenterConfig } from "./config.js";
import { LogCenterHttpClient, type LogCreatePayload } from "./client.js";
import { FileSpool } from "./spool.js";

function utcIso(): string {
  return new Date().toISOString();
}

export class LogCenterSender {
  readonly cfg: LogCenterConfig;
  private http: LogCenterHttpClient;
  private spool: FileSpool;

  private timer: NodeJS.Timeout | null = null;
  private stopping = false;

  constructor(cfg: LogCenterConfig) {
    this.cfg = cfg;
    this.http = new LogCenterHttpClient(cfg);
    this.spool = new FileSpool(cfg.spoolDir, cfg.spoolFilename, cfg.spoolMaxBytes);
  }

  private buildPayload(
    level: string,
    message: string,
    opts?: {
      timestamp?: string;
      tags?: string[];
      data?: Record<string, any>;
      requestId?: string;
      status?: string;
      projectId?: string;
    }
  ): LogCreatePayload {
    const lvl = (level || "INFO").toUpperCase();
    const ts = opts?.timestamp || utcIso();
    const status = opts?.status ?? (["ERROR", "CRITICAL", "FATAL"].includes(lvl) ? "ERROR" : "OK");

    const payload: LogCreatePayload = {
      project_id: opts?.projectId || this.cfg.projectId,
      level: lvl,
      message,
      timestamp: ts,
      status,
    };
    if (opts?.tags?.length) payload.tags = opts.tags;
    if (opts?.data && Object.keys(opts.data).length) payload.data = opts.data;
    if (opts?.requestId) payload.request_id = opts.requestId;
    return payload;
  }

  async send(
    level: string,
    message: string,
    opts?: {
      timestamp?: string;
      tags?: string[];
      data?: Record<string, any>;
      requestId?: string;
      status?: string;
      projectId?: string;
      spoolOnFail?: boolean;
    }
  ): Promise<boolean> {
    if (!this.cfg.enabled) return false;

    const payload = this.buildPayload(level, message, opts);
    const spoolOnFail = opts?.spoolOnFail ?? true;

    try {
      const res = await this.http.postLog(payload);
      const ok = res.statusCode >= 200 && res.statusCode < 300;
      if (ok) return true;
    } catch {}

    if (spoolOnFail) this.spool.append(payload);
    return false;
  }

  sendSync(level: string, message: string, opts?: Parameters<LogCenterSender["send"]>[2]): boolean {
    this.send(level, message, opts).catch(() => {});
    return true;
  }

  async flushSpool(maxBatches = 10): Promise<{ sent: number; failed: number; remaining: number }> {
    let sent = 0;
    let failed = 0;

    for (let i = 0; i < maxBatches; i++) {
      const { batch } = this.spool.popBatch(this.cfg.flushBatchSize);
      if (!batch.length) break;

      for (const payload of batch) {
        let ok = false;
        try {
          const res = await this.http.postLog(payload);
          ok = res.statusCode >= 200 && res.statusCode < 300;
        } catch {
          ok = false;
        }

        if (ok) {
          sent += 1;
          continue;
        }

        failed += 1;
        this.spool.append(payload);
        return { sent, failed, remaining: this.spool.stats().queued };
      }
    }

    return { sent, failed, remaining: this.spool.stats().queued };
  }

  startBackgroundFlush(): void {
    if (this.timer) return;
    this.stopping = false;

    let backoff = this.cfg.flushIntervalMs;

    const tick = async () => {
      if (this.stopping) return;

      const res = await this.flushSpool(5);
      if (res.failed > 0) backoff = Math.min(backoff * 2, 120_000);
      else backoff = this.cfg.flushIntervalMs;

      this.timer = setTimeout(() => tick().catch(() => {}), backoff);
    };

    this.timer = setTimeout(() => tick().catch(() => {}), this.cfg.flushIntervalMs);
  }

  async stopBackgroundFlush(): Promise<void> {
    this.stopping = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  spoolStats() {
    return this.spool.stats();
  }
}
