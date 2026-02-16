from .core import Aether

# Minimal import dependency of "TinyDB"
from tinydb import TinyDB, Query

__all__ = ["Aether", "TinyDB", "Query"]
__version__ = "0.1.0"