"""Offline regressions: fake UDP transport, synthetic keys, no device traffic."""

import asyncio
import copy
import importlib.util
import pathlib
import struct
import time
import unittest

from pysyncleo.enums import ConnectionState, FrameType
from pysyncleo.models import SyncleoUdpDevice, UnackedMessage

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "syncleo_local_transport", ROOT / "custom_components/syncleo/transport.py"
)
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


class FakeTransport:
    def __init__(self):
        self.frames = []

    def sendto(self, data, addr):
        self.frames.append((data, addr))


def finish_handshake(connection):
    peer = copy.copy(connection.encoder)
    peer.encinkey, peer.encoutkey = peer.encoutkey, peer.encinkey
    payload = b"\0" + struct.pack("<HBBB", 3, 1, 12, 0) + bytes(16)
    connection.feed_datagram(peer.encode(1, FrameType.CMD, payload))


class HandshakeRegression(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        transport.HANDSHAKE_TIMEOUT = 0.05
        transport.RETRY_TIMEOUT = 10
        self.connections = []

    async def asyncTearDown(self):
        for connection in self.connections:
            connection.disconnect()
        await asyncio.sleep(0)

    def connection(self, port=41122):
        connection = transport.SyncleoConnection(
            SyncleoUdpDevice(
                "00:00:00:00:00:01",
                ("192.0.2.1", port),
                protocol=3,
                device_pubkey=bytes(range(1, 33)),
            ),
            FakeTransport(),
        )
        self.connections.append(connection)
        return connection

    async def test_ack_without_full_reply_expires(self):
        connection = self.connection()
        await connection.connect()
        connection.feed_datagram(struct.pack("<BBH", 0, FrameType.ACK, 0))
        self.assertEqual(connection._unacked_seq, {})
        await asyncio.sleep(0.6)
        self.assertEqual(connection.state, ConnectionState.DISCONNECTED)
        self.assertEqual(len(connection.transport.frames), 1)

    async def test_successful_handshake_is_not_expired(self):
        connection = self.connection()
        await connection.connect()
        finish_handshake(connection)
        await asyncio.sleep(0.6)
        self.assertEqual(connection.state, ConnectionState.CONNECTED)

    async def test_retry_discards_old_packets_and_crypto(self):
        connection = self.connection()
        await connection.connect()
        old_encoder = connection.encoder
        connection._unacked_seq[77] = UnackedMessage(
            b"old", 100, time.monotonic() - 100
        )
        connection._set_state(ConnectionState.DISCONNECTED)
        await connection.connect()
        self.assertEqual(set(connection._unacked_seq), {0})
        self.assertIsNot(connection.encoder, old_encoder)
        finish_handshake(connection)
        self.assertEqual(connection.state, ConnectionState.CONNECTED)

    async def test_concurrent_connect_does_not_duplicate_handshake(self):
        connection = self.connection()
        await asyncio.gather(connection.connect(), connection.connect())
        self.assertEqual(len(connection.transport.frames), 1)

    async def test_offline_then_return_recovers_through_state_callback(self):
        connection = self.connection()
        retry_tasks = []

        async def retry():
            await asyncio.sleep(0.05)
            await connection.connect()
            finish_handshake(connection)

        def state_changed(state):
            if state == ConnectionState.DISCONNECTED:
                retry_tasks.append(asyncio.create_task(retry()))

        connection.register_state_callback(state_changed)
        await connection.connect()
        await asyncio.sleep(0.7)
        self.assertEqual(connection.state, ConnectionState.CONNECTED)
        self.assertEqual(len(retry_tasks), 1)
        connection.unregister_state_callback(state_changed)
        await asyncio.gather(*retry_tasks)

    async def test_device_timeouts_are_isolated(self):
        failed, healthy = self.connection(), self.connection(41123)
        await failed.connect()
        await healthy.connect()
        finish_handshake(healthy)
        await asyncio.sleep(0.6)
        self.assertEqual(failed.state, ConnectionState.DISCONNECTED)
        self.assertEqual(healthy.state, ConnectionState.CONNECTED)

    async def test_explicit_disconnect_cancels_session(self):
        connection = self.connection()
        await connection.connect()
        connection.disconnect()
        await asyncio.sleep(0.6)
        self.assertEqual(connection.state, ConnectionState.DISCONNECTED)
        self.assertIsNone(connection._loop_task)
        self.assertEqual(connection._unacked_seq, {})
        self.assertEqual(len(connection.transport.frames), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
