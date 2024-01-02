import dataclasses
import logging
import selectors
import socket
import threading
import time
from queue import Queue
from typing import Dict, List, Optional, cast


@dataclasses.dataclass
class Connection:
    ip: str
    port: int
    sock: socket.socket
    input_buffer: Queue[Optional[bytes]] = Queue()
    output_buffer: Queue[bytes] = Queue()
    packet_header_length: int = 10
    network_buffer: bytes = b""
    message_buffer: bytes = b""
    message_in_progress: bool = False
    message_bytes_remaining: int = 0


logger = logging.getLogger()


def log_connection(connection: Connection, text: str) -> None:
    logger.info(f"[{connection.ip}:{connection.port}] {text}")


class ConnectionHandler:
    def __init__(self) -> None:
        self.selector = selectors.DefaultSelector()
        self.running = True

        self.connections: List[Connection] = []
        self.connection_map: Dict[str, Dict[str, Connection]] = {}

        self.connection_thread = threading.Thread(target=self.process)
        self.connection_thread.start()

    def get_message(self, ip: str, port: int) -> Optional[bytes]:
        connection = self.get_connection(ip, port)
        if connection is None:
            raise Exception(f"No connection is established to {ip}:{port}")
        return connection.input_buffer.get()

    def push_message(self, ip: str, port: int, message: bytes) -> None:
        connection = self.get_connection(ip, port)
        if connection is None:
            raise Exception(f"No connection is established to {ip}:{port}")

        connection.output_buffer.put(message)

    def get_connections(self) -> List[Connection]:
        return self.connections

    def get_connection(self, ip: str, port: int) -> Optional[Connection]:
        if not self.is_connected(ip, port):
            return None
        return self.connection_map[ip][str(port)]

    def is_connected(self, ip: str, port: int) -> bool:
        return ip in self.connection_map and str(port) in self.connection_map[ip]

    @staticmethod
    def read(connection: Connection) -> bool:
        data = connection.sock.recv(4096)
        if not data:
            return False

        connection.network_buffer += data

        buffer_empty = False
        while not buffer_empty:
            if connection.message_in_progress:
                if len(connection.network_buffer) >= connection.message_bytes_remaining:
                    # Get all remaining data from the packet from the network buffer
                    connection.message_buffer += connection.network_buffer[
                        : connection.message_bytes_remaining
                    ]

                    # Remove the data from the network buffer
                    connection.network_buffer = connection.network_buffer[
                        connection.message_bytes_remaining :
                    ]

                    # Enqueue the message:
                    connection.input_buffer.put(connection.message_buffer)

                    # Reset control variables
                    connection.message_in_progress = False
                    connection.message_bytes_remaining = 0
                    connection.message_buffer = b""
                else:
                    connection.message_buffer += connection.network_buffer
                    connection.message_bytes_remaining = (
                        connection.message_bytes_remaining
                        - len(connection.network_buffer)
                    )
                    connection.network_buffer = b""
                    buffer_empty = True
            else:
                if len(connection.network_buffer) >= connection.packet_header_length:
                    # Get the length of the next packet
                    connection.message_bytes_remaining = int(
                        connection.network_buffer[: connection.packet_header_length]
                    )

                    # Remove the header from the network buffer
                    connection.network_buffer = connection.network_buffer[
                        connection.packet_header_length :
                    ]
                    connection.message_in_progress = True
                else:
                    # We do not have a full packet header, wait for another incoming packet
                    buffer_empty = True

        return True

    @staticmethod
    def write(connection: Connection) -> None:
        if connection.output_buffer.empty():
            return

        message = connection.output_buffer.get()
        message_header = (
            str(len(message)).zfill(connection.packet_header_length).encode("utf-8")
        )
        connection.sock.sendall(message_header + message)

    def stop(self) -> None:
        self.running = False
        self.connection_thread.join()

    def add_connection(self, sock: socket.socket) -> Connection:
        ip, port = sock.getpeername()

        connection = Connection(ip, port, sock)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.selector.register(sock, events, data=connection)

        self.connections.append(connection)
        self.connection_map[str(ip)] = {str(port): connection}

        log_connection(connection, "Connection established")
        return connection

    def service_connection(self, key: selectors.SelectorKey, mask: int) -> None:
        sock = cast(socket.socket, key.fileobj)
        connection = cast(Connection, key.data)

        if mask & selectors.EVENT_READ:
            try:
                result = self.read(connection)
            except socket.error:
                result = False

            if not result:
                # TODO Log closed connection
                self.selector.unregister(sock)
                self.connections.remove(connection)
                sock.close()

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

