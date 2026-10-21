import logging

from .config import LogCenterConfig, LogCenterV3Config
from .sender import LogCenterSender
from .senderV3 import LogCenterV3Sender
from .middleware import LogCenterAuditMiddleware

# Biblioteca fica silenciosa por padrao - a aplicacao que usa a SDK decide se
# quer ver esses logs (ex: logging.basicConfig(level=logging.INFO), ou
# logging.getLogger("logcenter_sdk").setLevel(logging.INFO) + um handler).
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = ["LogCenterConfig", "LogCenterSender", "LogCenterAuditMiddleware", "LogCenterV3Config","LogCenterV3Sender"]
__version__ = "0.2.0"