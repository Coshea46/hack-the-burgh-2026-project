"""Independent football metadata APIs; never part of inference timing."""

from .server import PlatformHTTPServer
from .service import PlatformService

__all__ = ["PlatformHTTPServer", "PlatformService"]
