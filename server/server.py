import json
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from json import JSONDecodeError
from threading import Thread
from typing import List, Optional, Dict, Generic, TypeVar, Any

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicNumbers

from message import create_error, create_message
from network import Connection, NetworkInterface


class State(Enum):
    Authenticate = 1
    Idle = 2
    Error = 99


@dataclass
class AuthenticationData:
    private_key: int
    public_key: int
    secret: int


T = TypeVar("T")


@dataclass
class Result(Generic[T]):
    success: bool
    error: Optional[str]
    value: Optional[T]


class ConnectionProcessor:
    def __init__(self, network: NetworkInterface, connection: Connection) -> None:
        self.network = network
        self.connection = connection

        self.running = False
        self.state = State.Authenticate
        self.process_thread = Thread(target=self._process)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.process_thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.process_thread.join()

    def _get_message(self, expected_type: str) -> Optional[Dict[str, Any]]:
        msg = self.network.get_message(self.connection)
        if msg is None:
            return None

        try:
            data = json.loads(msg)
        except JSONDecodeError:
            self.network.push_message(self.connection, create_error("Invalid JSON"))
            return None

        if not isinstance(data, dict):
            self.network.push_message(self.connection, create_error("Invalid JSON"))
            return None

        if "type" not in data:
            self.network.push_message(
                self.connection, create_error("Missing 'type' field")
            )
            return None

        if data["type"] != expected_type:
            self.network.push_message(self.connection, create_error("Invalid type"))
            return None

        return data

    def _process(self) -> None:
        while self.running:
            time.sleep(0.1)

            if self.state == State.Authenticate:
                print(
                    f"Generating authentication keys for {self.connection.ip}:{self.connection.port}"
                )
                self.network.encryption.generate_keys()
                public_numbers = self.network.encryption.public_key.public_numbers()

                self.network.push_message(
                    self.connection,
                    create_message(
                        "auth",
                        {
                            "authenticated": False,
                            "x": public_numbers.x,
                            "y": public_numbers.y,
                        },
                    ),
                )

                # Wait for client authentication data
                data = self._get_message("auth")
                if data is None:
                    continue

                # Exchange keys and retrieve shared key
                client_public_numbers = EllipticCurvePublicNumbers(
                    data["x"], data["y"], ec.SECP384R1()
                )
                self.network.encryption.exchange_keys(
                    client_public_numbers.public_key()
                )
                print(
                    f"Successfully authenticated {self.connection.ip}:{self.connection.port}"
                )

                # Send a message back to the client indicating that authentication is complete
                self.network.push_message(
                    self.connection, create_message("auth", {"authenticated": True})
                )
                self.network.encryption.set_enabled(True)

                self.state = State.Idle
            elif self.state == State.Idle:
                message = self._get_message("error")
                print("Received:", message)

        self.network.stop()


class FileServer:
    SYS_RAND = secrets.SystemRandom()

    def __init__(self, host: str = "127.0.0.1", port: int = 50000) -> None:
        self.host = host
        self.port = port

        self.network = NetworkInterface()
        self.processors: List[ConnectionProcessor] = []
        self.running = True

    def handle_connection(self, connection: Connection) -> None:
        processor = ConnectionProcessor(self.network, connection)
        processor.start()
        self.processors.append(processor)

    def process(self) -> None:
        try:
            self.network.start_server(self.host, self.port, self.handle_connection)
            print(f"Started server on {self.host}:{self.port}")
        except Exception as err:
            self.stop()
            print(
                f"An error occurred when starting the server on {self.host}:{self.port}"
            )
            print(err)
            return

        # while self.running:
        #     print("\nClients:")
        #     print(self.network.get_clients())
        #
        #     message = input("Enter message: ")
        #     ip = input("Enter client IP: ")
        #     port = input("Enter client port: ")
        #     self.network.push_message(ip, int(port), message)

    def stop(self) -> None:
        self.running = False
        self.network.stop()

        for processor in self.processors:
            processor.stop()

