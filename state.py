from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from connection import Connection
from network import NetworkInterface

T = TypeVar("T")


class State(ABC, Generic[T]):
    def __init__(self, network: NetworkInterface) -> None:
        self.network = network

    @abstractmethod
    def run(self, connection: Connection) -> None:
        pass

    @abstractmethod
    def next(self, value: T) -> State:
        pass


class StateMachine:
    def __init__(self, initial_state: State) -> None:
        self.initial_state = initial_state
