import type { Request, Response, NextFunction } from "express";
import type { LogCenterSender } from "../sender.js";

export function logcenterAuditMiddleware(sender: LogCenterSender) {
  return function (req: Request, res: Response, next: NextFunction) {
    res.on("finish", () => {
      if (res.statusCode >= 500) {
        sender.sendSync("ERROR", "HTTP 5xx response", {
          status: "ERROR",
          data: {
            method: req.method,
            path: (req as any).originalUrl || req.url,
            status: res.statusCode,
          },
          tags: ["http", "5xx"],
          spoolOnFail: true,
        });
      }
    });

    try {
      next();
    } catch (exc: any) {
      sender.sendSync("ERROR", "Unhandled exception in request", {
        status: "ERROR",
        data: {
          method: req.method,
          path: (req as any).originalUrl || req.url,
          exception_class: exc?.constructor?.name || "Error",
        },
        tags: ["http", "exception"],
        spoolOnFail: true,
      });
      throw exc;
    }
  };
}
