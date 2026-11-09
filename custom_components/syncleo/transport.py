# Adapted from pysyncleo 0.4.1 (MIT); see PYSYNCLEO-LICENSE.txt.
import asyncio
import logging
import time
from collections.abc import Callable

from pysyncleo.commands import (
    CmdHandshake,
    CmdInitDiagnostic,
    CmdPing,
    CmdTimeSync,
    UdpCommand,
)
from pysyncleo.const import (
    MAX_RECONNECT_ATTEMPTS,
    MAX_SEND_RETRIES,
    PING_INTERVAL,
    RECONNECT_INTERVAL,
    RETRY_TIMEOUT,
)
from pysyncleo.encoding import CryptoV2Encoder, PlainEncoder
from pysyncleo.enums import ConnectionState, FrameType, UdpCommandType
from pysyncleo.models import SyncleoUdpDevice, UnackedMessage

_LOGGER = logging.getLogger(__name__)

# An ACK confirms delivery only, not completion of the handshake.
HANDSHAKE_TIMEOUT = 10.0


class SyncleoConnection:
    def __init__(
        self,
        device: SyncleoUdpDevice,
        transport: asyncio.DatagramTransport,
        command_factory: Callable[[bytes, UdpCommand], UdpCommand | None] | None = None,
    ):
        self.device = device
        self.transport = transport
        self.command_factory = command_factory
        self.state = ConnectionState.NOT_CONNECTED

        self.inseq = 0
        self.outseq = 0
        self._unacked_seq: dict[int, UnackedMessage] = {}
        self._callbacks: set[Callable[[UdpCommand], None]] = set()
        self._state_callbacks: set[Callable[[ConnectionState], None]] = set()
        self._loop_task: asyncio.Task | None = None
        self._last_activity = time.monotonic()
        self._handshake_started: float | None = None
        self._last_reconnect_attempt = 0.0
        self._reconnect_attempts = 0
        self.encoder = (
            PlainEncoder(self.device)
            if self.device.protocol < 2
            else CryptoV2Encoder(self.device)
        )

    def _send_bytes(self, data: bytes):
        _LOGGER.debug(f"TX [{self.device.inet_address[0]}]: {data.hex()}")
        self._last_activity = time.monotonic()
        self.transport.sendto(data, self.device.inet_address)

    def register_callback(self, callback: Callable[[UdpCommand], None]) -> None:
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable[[UdpCommand], None]) -> None:
        self._callbacks.discard(callback)

    def register_state_callback(
        self, callback: Callable[[ConnectionState], None]
    ) -> None:
        self._state_callbacks.add(callback)

    def unregister_state_callback(
        self, callback: Callable[[ConnectionState], None]
    ) -> None:
        self._state_callbacks.discard(callback)

    def _set_state(self, new_state: ConnectionState):
        if self.state != new_state:
            self.state = new_state
            for callback in list(self._state_callbacks):
                try:
                    callback(new_state)
                except Exception as e:  # noqa: BLE001
                    _LOGGER.warning(f"Error in state callback {callback}: {e}")

    def _notify_callbacks(self, cmd: UdpCommand) -> None:
        for callback in list(self._callbacks):
            try:
                callback(cmd)
            except Exception as e:  # noqa: BLE001
                _LOGGER.warning(f"Error in callback {callback}: {e}")

    async def connect(self):
        if self.state in (ConnectionState.CONNECTED, ConnectionState.CONNECTING):
            _LOGGER.info(
                "Connection to %s is already %s. Skipping connect().",
                self.device.inet_address[0],
                self.state.name,
            )
            return

        # Every new session starts without packets or crypto state from the old one.
        self._unacked_seq.clear()
        self.inseq = 0
        self.encoder = (
            PlainEncoder(self.device)
            if self.device.protocol < 2
            else CryptoV2Encoder(self.device)
        )
        self._handshake_started = time.monotonic()
        self._set_state(ConnectionState.CONNECTING)
        self.outseq = 0

        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._session_loop())

        _LOGGER.info(f"Initiating Handshake with {self.device.inet_address[0]}...")

        handshake_frame = self.encoder.generate_handshake()

        self._unacked_seq[0] = UnackedMessage(
            frame=handshake_frame, attempts=1, last_sent=time.monotonic()
        )
        self._send_bytes(handshake_frame)

    def disconnect(self):
        self._handshake_started = None
        self._unacked_seq.clear()
        self._set_state(ConnectionState.DISCONNECTED)
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None

    async def _run_initialization(self, mode: int):
        await asyncio.sleep(0.5)

        _LOGGER.info("Sending Time Sync...")
        current_unix_time = int(time.time())
        await self.send_command(CmdTimeSync(current_unix_time))

        if mode == 1:
            _LOGGER.info("Mode 1 detected: Triggering Diagnostic Init...")
            await asyncio.sleep(0.2)
            await self.send_command(CmdInitDiagnostic())

    async def send_command(self, cmd: UdpCommand):
        if self.state != ConnectionState.CONNECTED:
            _LOGGER.warning("Cannot send command, device not connected.")
            return

        if cmd.command_type is None:
            _LOGGER.error("Cannot send command: command_type is not defined.")
            return

        self.outseq = (self.outseq + 1) % 256
        seq = self.outseq

        payload = bytes([cmd.command_type.value]) + cmd.serialize()
        frame = self.encoder.encode(seq, FrameType.CMD, payload)

        self._unacked_seq[seq] = UnackedMessage(
            frame=frame, attempts=1, last_sent=time.monotonic()
        )
        self._send_bytes(frame)

    def feed_datagram(self, data: bytes):
        _LOGGER.debug(f"RX [{self.device.inet_address[0]}]: {data.hex()}")
        self._last_activity = time.monotonic()

        try:
            seq, frame_type, payload = self.encoder.decode(data)
        except ValueError as e:
            if self.state == ConnectionState.CONNECTED:
                _LOGGER.warning(
                    f"Discarding unreadable frame (stale key or stray packet): {e}"
                )
            else:
                _LOGGER.debug(
                    f"Discarding unreadable frame during when state {self.state}: {e}"
                )
            return
        except Exception as e:  # noqa: BLE001
            _LOGGER.error(f"Failed to process frame: {e}")
            return

        self.inseq = seq

        if frame_type == FrameType.ACK:
            if seq in self._unacked_seq:
                del self._unacked_seq[seq]
            return

        if frame_type == FrameType.CMD:
            should_ignore = False
            ack_frame = self.encoder.encode(seq, FrameType.ACK, b"")

            parsed_cmd = UdpCommand.from_bytes(payload)
            if not parsed_cmd:
                self._send_bytes(ack_frame)
                return

            if self.command_factory and (
                custom_cmd := self.command_factory(payload, parsed_cmd)
            ):
                parsed_cmd = custom_cmd

            if self.state == ConnectionState.CONNECTING:
                if isinstance(parsed_cmd, CmdHandshake):
                    _LOGGER.info(
                        f"Device Connected! "
                        f"Protocol: v{parsed_cmd.protocol_version} | "
                        f"Firmware: {parsed_cmd.fw_major}.{parsed_cmd.fw_minor} | "
                        f"Mode: {parsed_cmd.mode}"
                    )
                    self._send_bytes(ack_frame)
                    if 0 in self._unacked_seq:
                        del self._unacked_seq[0]

                    self._reconnect_attempts = 0
                    self._set_state(ConnectionState.CONNECTED)

                    asyncio.create_task(self._run_initialization(parsed_cmd.mode))
                    return
                else:
                    _LOGGER.info(
                        f"Device sent command {parsed_cmd} while we are in connecting state. Ignoring..."
                    )
                    should_ignore = True

            if not should_ignore:
                self._send_bytes(ack_frame)

            if parsed_cmd.command_type in (
                UdpCommandType.PING,
                UdpCommandType.TIME_SYNC,
            ):
                return

            if parsed_cmd.command_type is None:
                _LOGGER.warning("Received command with no command_type defined.")
                return

            _LOGGER.debug(f"Parsed State: {parsed_cmd}")
            self._notify_callbacks(parsed_cmd)

    async def _session_loop(self):
        while True:
            try:
                await asyncio.sleep(0.5)
                now = time.monotonic()

                match self.state:
                    case ConnectionState.CONNECTING:
                        if (
                            self._handshake_started is not None
                            and now - self._handshake_started >= HANDSHAKE_TIMEOUT
                        ):
                            _LOGGER.warning(
                                "Handshake timed out after %.1fs for %s; scheduling reconnect",
                                HANDSHAKE_TIMEOUT,
                                self.device.inet_address[0],
                            )
                            self._unacked_seq.clear()
                            self._handshake_started = None
                            # Entity state callbacks schedule retries with capped backoff.
                            self._set_state(ConnectionState.DISCONNECTED)
                            continue

                    case ConnectionState.DISCONNECTED:
                        _LOGGER.info(
                            f"Connection to {self.device.inet_address[0]} permanently stopped."
                        )
                        break

                    case ConnectionState.NOT_CONNECTED:
                        if now - self._last_reconnect_attempt >= RECONNECT_INTERVAL:
                            if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                                _LOGGER.error(
                                    f"Max reconnect attempts reached for {self.device.inet_address[0]}. Giving up."
                                )
                                self._set_state(ConnectionState.DISCONNECTED)
                                break
                            else:
                                _LOGGER.info(
                                    f"Device offline. Attempting auto-reconnect to {self.device.inet_address[0]}."
                                )
                                self._reconnect_attempts += 1
                                self._last_reconnect_attempt = now
                                asyncio.create_task(self.connect())

                    case ConnectionState.CONNECTED:
                        if now - self._last_activity >= PING_INTERVAL:
                            _LOGGER.debug(
                                f"Idle for {PING_INTERVAL}s. Sending Keep-Alive PING to {self.device.inet_address[0]}"
                            )
                            await self.send_command(CmdPing())

                unacked_keys = list(self._unacked_seq.keys())

                for seq in unacked_keys:
                    msg = self._unacked_seq.get(seq)
                    if not msg:
                        continue

                    if now - msg.last_sent >= RETRY_TIMEOUT:
                        if msg.attempts >= MAX_SEND_RETRIES:
                            _LOGGER.info(
                                f"Dropping packet seq={seq} after {MAX_SEND_RETRIES} failed attempts."
                            )

                            self._set_state(ConnectionState.DISCONNECTED)

                            del self._unacked_seq[seq]
                        else:
                            msg.attempts += 1
                            msg.last_sent = now
                            _LOGGER.debug(
                                f"Retrying packet seq={seq} (Attempt {msg.attempts}/{MAX_SEND_RETRIES})"
                            )
                            self._send_bytes(msg.frame)

            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                _LOGGER.error(
                    f"Error in session loop for device {self.device.inet_address[0]}: {e}"
                )
                if self.state != ConnectionState.DISCONNECTED:
                    self._set_state(ConnectionState.NOT_CONNECTED)


class TransportManager(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None
        self.devices: dict[tuple[str, int], SyncleoUdpDevice] = {}
        self.connections: dict[tuple[str, int], SyncleoConnection] = {}

    def connection_made(self, transport):
        self.transport = transport
        _LOGGER.info("Syncleo Transport Bound.")

    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        if addr in self.connections:
            self.connections[addr].feed_datagram(data)

    def register_device(self, device: SyncleoUdpDevice) -> SyncleoConnection | None:
        if self.transport is None:
            _LOGGER.error(
                f"Cannot register {device.mac_address}: UDP socket is not bound yet!"
            )
            return None
        self.devices[device.inet_address] = device
        conn = SyncleoConnection(device, self.transport)
        self.connections[device.inet_address] = conn
        return conn

    def unregister_device(self, device: SyncleoUdpDevice):
        if device.inet_address in self.connections:
            self.connections[device.inet_address].disconnect()
            del self.connections[device.inet_address]
            del self.devices[device.inet_address]
