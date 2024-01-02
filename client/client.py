import json
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from threading import Thread
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ec
from message import create_message
from network import ClientInterface, Connection


class State(Enum):
    Authenticate = 1
    Idle = 2
    Error = 99


@dataclass
class AuthenticationData:
    private_key: int
    public_key: int
    secret: int


class FileClient:
    SYS_RAND = secrets.SystemRandom()

    def __init__(self, host: str = "127.0.0.1", port: int = 50000) -> None:
        self.host = host
        self.port = port

        self.network = ClientInterface(host, port)
        self.connection: Optional[Connection] = None
        self.running = True
        self._state = State.Authenticate

        self.process_thread = Thread(target=self.process)

    def set_state(self, state: State) -> None:
        self._state = state

    def start(self) -> None:
        self.process_thread.start()

    def process(self) -> None:
        try:
            self.connection = self.network.start()
        except Exception as err:
            self.running = False
            # TODO Stop threads, maybe implement monitor thread using "errored" field
            print(
                f"An error occurred when establishing a connection to {self.host}:{self.port}"
            )
            print(err)
            return

        while self.running:
            time.sleep(0.1)
            if self.connection is None:
                continue

            if self._state == State.Authenticate:
                message = self.network.get_message(self.connection)
                if message is None:
                    return
                data = json.loads(message)

                print("Generating authentication keys...")
                server_public_numbers = ec.EllipticCurvePublicNumbers(
                    data["x"], data["y"], ec.SECP384R1()
                )

                public_key = self.network.encryption.generate_keys()
                self.network.encryption.exchange_keys(
                    server_public_numbers.public_key()
                )

                client_public_numbers = public_key.public_numbers()
                self.network.push_message(
                    self.connection,
                    create_message(
                        "auth",
                        {
                            "authenticated": True,
                            "x": client_public_numbers.x,
                            "y": client_public_numbers.y,
                        },
                    ),
                )

                confirm_msg = self.network.get_message(self.connection)
                if confirm_msg is None:
                    return
                confirm_data = json.loads(confirm_msg)

                if "authenticated" in confirm_data and confirm_data["authenticated"]:
                    self.network.encryption.set_enabled(True)
                    self.set_state(State.Idle)
                    print("Successfully authenticated")
                    return

                # TODO Throw error?
                print("Failed to authenticate")

    def stop(self) -> None:
        self.running = False
        if self.connection is not None:
            self.connection.input_buffer.put(None)
        self.process_thread.join()
        self.network.stop()

