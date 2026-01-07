from __future__ import annotations


class LogCenterError(Exception):
    pass


class LogCenterConfigError(LogCenterError):
    pass


class SpoolCorruptedError(LogCenterError):
    pass
