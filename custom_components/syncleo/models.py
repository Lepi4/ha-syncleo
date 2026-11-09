import asyncio
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .broadcaster import SyncleoVirtualZeroconfBroadcaster
from .transport import SyncleoConnection, TransportManager


@dataclass
class SyncleoDomainData:
    manager: TransportManager
    transport: asyncio.DatagramTransport
    ha_uuid: str


type SyncleoGenericConfigEntry = ConfigEntry[
    SyncleoConnection | SyncleoVirtualZeroconfBroadcaster
]
type SyncleoConfigEntry = ConfigEntry[SyncleoConnection]
