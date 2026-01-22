import { request } from "undici";
import type { LogCenterConfig } from "./config.js";

export type LogCreatePayload = {
  project_id: string;
  status: string;
  level: string;
  message: string;
  timestamp: string;
  tags?: string[];
  data?: Record<string, any>;
  request_id?: string;
};

export class LogCenterHttpClient {
  constructor(private cfg: LogCenterConfig) {}

  async postLog(payload: LogCreatePayload): Promise<{ statusCode: number; bodyText: string }> {
    // Mantém "/" no final pra evitar 307: /logs -> /logs/
    const url = `${this.cfg.baseUrl}/logs/`;

    const headers: Record<string, string> = { "content-type": "application/json" };
    if (this.cfg.apiKey) headers["x-api-key"] = this.cfg.apiKey;

    const res = await request(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    const bodyText = await res.body.text();
    return { statusCode: res.statusCode, bodyText };
  }
}
