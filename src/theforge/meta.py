"""Identity of The Forge as a contract producer."""

from theforge import __version__
from theforge.contracts.types import Producer

VERSION = __version__
PRODUCER = Producer(id="theforge", version=VERSION)
