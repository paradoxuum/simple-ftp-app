import logging
import selectors
import socket
import threading
import time
from dataclasses import dataclass
from enum import Enum
from queue import Queue
from typing import Dict, List, Optional, cast, Callable

from encryption import NetworkEncryption


class Role(Enum):
    Client = 1
    Server = 2


@dataclass(frozen=True)
class PacketHeader:
    message_length: int
    timestamp: float


@dataclass
class Connection:
    ip: str
    port: int
    sock: socket.socket
    input_buffer: Queue[Optional[bytes]] = Queue()
    output_buffer: Queue[bytes] = Queue()
    packet_header_length: int = 32
    network_buffer: bytes = b""
    message_buffer: bytes = b""
    message_header: Optional[PacketHeader] = None
    message_bytes_remaining: int = 0


@dataclass
class ConnectionData:
    last_heartbeat: int
    connection: Connection
    encryption: NetworkEncryption


logger = logging.getLogger()


def log_connection(connection: Connection, text: str) -> None:
    logger.info(f"[{connection.ip}:{connection.port}] {text}")


class ConnectionHandler:
    def __init__(self, role: Role) -> None:
        self.selector = selectors.DefaultSelector()
        self.running = True
        self.role = role

        self.connections: List[ConnectionData] = []
        self.connection_map: Dict[str, Dict[str, ConnectionData]] = {}
        self.disconnect_callback: Optional[Callable[[ConnectionData], None]] = None

        self.connection_thread = threading.Thread(target=self.process)
        self.connection_thread.start()

    def on_disconnect(self, callback: Optional[Callable[[ConnectionData], None]] = None) -> None:
        self.disconnect_callback = callback

    def get_message_raw(
            self, ip: str, port: int, timeout: Optional[float] = None
    ) -> Optional[bytes]:
        conn = self.get_connection(ip, port)
        if conn is None:
            raise Exception(f"No connection is established to {ip}:{port}")

        msg = conn.connection.input_buffer.get(timeout=timeout)
        if msg is None:
            return None
        return conn.encryption.decrypt(msg)

    def get_message(
            self, ip: str, port: int, timeout: Optional[float] = None
    ) -> Optional[str]:
        msg = self.get_message_raw(ip, port, timeout)
        if msg is None:
            return None
        return msg.decode("utf-8")

    def push_message_raw(self, ip: str, port: int, message: bytes) -> None:
        data = self.get_connection(ip, port)
        if data is None:
            raise Exception(f"No connection is established to {ip}:{port}")

        encrypted_msg = data.encryption.encrypt(message)
        data.connection.output_buffer.put(encrypted_msg)

    def push_message(self, ip: str, port: int, message: str) -> None:
        self.push_message_raw(ip, port, message.encode("utf-8"))

    def get_connections(self) -> List[ConnectionData]:
        return self.connections

    def get_connection(self, ip: str, port: int) -> Optional[ConnectionData]:
        if not self.is_connected(ip, port):
            return None
        return self.connection_map[ip][str(port)]

    def is_connected(self, ip: str, port: int) -> bool:
        return ip in self.connection_map and str(port) in self.connection_map[ip]

    def remove_connection(self, ip: str, port: int) -> None:
        data = self.get_connection(ip, port)
        if data is None:
            return

        self.selector.unregister(data.connection.sock)
        data.connection.sock.close()

        del self.connection_map[ip][str(port)]
        if len(self.connection_map[ip]) == 0:
            del self.connection_map[ip]

        try:
            self.connections.remove(data)
        except ValueError:
            pass

        if self.disconnect_callback is not None:
            self.disconnect_callback(data)

    @staticmethod
    def _reset_read(connection: Connection) -> None:
        connection.message_header = None
        connection.message_bytes_remaining = 0
        connection.message_buffer = b""

    def _read_header(self, connection: Connection) -> bool:
        if len(connection.network_buffer) < connection.packet_header_length:
            # We do not have a full packet header, wait for another incoming packet
            return True

        # Get the length of the next packet using the header
        header = connection.network_buffer[:connection.packet_header_length]
        header_parts = header.split(b" ")

        connection.message_bytes_remaining = int(header_parts[0])
        connection.message_header = PacketHeader(message_length=connection.message_bytes_remaining,
                                                 timestamp=float(header_parts[1]))

        # Remove the header from the network buffer
        connection.network_buffer = connection.network_buffer[
                                    connection.packet_header_length:
                                    ]
        return False

    def _read_body(self, connection: Connection) -> bool:
        net_buffer_length = len(connection.network_buffer)
        if net_buffer_length < connection.message_bytes_remaining:
            # If the network buffer is smaller than the number of bytes remaining, the packet body is incomplete
            connection.message_buffer += connection.network_buffer
            connection.message_bytes_remaining -= net_buffer_length
            connection.network_buffer = b""
            return True

        if connection.message_header is None:
            # If the packet took over 500ms to receive, drop the packet
            ConnectionHandler._reset_read(connection)
            return True

        current_time = time.time() * 1000
        time_diff = (time.time() * 1000) - current_time
        if time_diff < 0 or time_diff > 500:
            ConnectionHandler._reset_read(connection)
            return True

        # Get all remaining data from the packet from the network buffer
        connection.message_buffer += connection.network_buffer[
                                     : connection.message_bytes_remaining
                                     ]

        # Remove the data from the network buffer
        connection.network_buffer = connection.network_buffer[
                                    connection.message_bytes_remaining:
                                    ]

        # Enqueue the message:
        connection.input_buffer.put(connection.message_buffer)

        # Reset control variables
        ConnectionHandler._reset_read(connection)

    def read(self, connection: Connection) -> bool:
        data = connection.sock.recv(4096)
        if not data:
            return False

        connection.network_buffer += data

        buffer_empty = False
        while not buffer_empty:
            if connection.message_header is not None:
                buffer_empty = self._read_body(connection)
            else:
                buffer_empty = self._read_header(connection)

        return True

    @staticmethod
    def write(connection: Connection) -> None:
        if connection.output_buffer.empty():
            return

        message = connection.output_buffer.get()

        message_header = f"{len(message)} {time.time() * 1000}".zfill(connection.packet_header_length)
        if len(message_header) > connection.packet_header_length:
            return
        connection.sock.sendall(message_header.encode("utf-8") + message)

    def stop(self) -> None:
        self.running = False

        # Remove connections
        for data in self.connections:
            self.remove_connection(data.connection.ip, data.connection.port)

        self.connection_thread.join()

    def add_connection(self, sock: socket.socket) -> ConnectionData:
        ip, port = sock.getpeername()

        connection = Connection(ip, port, sock)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.selector.register(sock, events, data=connection)

        encryption = NetworkEncryption()
        connection_data = ConnectionData(connection=connection, encryption=encryption, last_heartbeat=int(time.time()))

        self.connections.append(connection_data)
        self.connection_map[str(ip)] = {str(port): connection_data}
        return connection_data

    def service_connection(self, key: selectors.SelectorKey, mask: int) -> None:
        connection = cast(Connection, key.data)

        if mask & selectors.EVENT_READ:
            try:
                result = self.read(connection)
            except socket.error as e:
                result = False
                logger.error(
                    f"[{connection.ip}:{connection.port}] A read error occurred",
                    exc_info=e,
                )

            if not result:
                self.remove_connection(connection.ip, connection.port)

        if mask & selectors.EVENT_WRITE:
            self.write(connection)

    def process(self) -> None:
        with self.selector:
            while self.running:
                time.sleep(0.1)
                if len(self.connections) == 0:
                    continue

                events = self.selector.select(timeout=None)
                for key, mask in events:
                    if key.data is None:
                        self.add_connection(cast(socket.socket, key.fileobj))
                        continue
                    self.service_connection(key, mask)
