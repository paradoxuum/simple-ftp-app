from enum import Enum

from connection import Connection
from state import State


class Action(Enum):
    Upload = 1


class Idle(State[Action]):
    def run(self, connection: Connection) -> None:
        pass

    def next(self, value: Action) -> State:
        pass


class Upload(State[Action]):
    def run(self, connection: Connection) -> None:
        pass

    def next(self, value: Action) -> State:
        pass
