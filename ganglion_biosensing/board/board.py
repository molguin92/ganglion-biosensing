from __future__ import annotations

import queue
from abc import abstractmethod
from contextlib import AbstractContextManager
from enum import Enum
from typing import NamedTuple
import numpy as np


class OpenBCISample(NamedTuple):
    seq: int
    pkt_id: int
    channel_data: np.ndarray


class BoardType(Enum):
    GANGLION = 0
    CYTON = 1


class BaseBiosensingBoard(AbstractContextManager):

    def __init__(self):
        self._sample_q: 'queue.Queue[OpenBCISample]' = queue.Queue()

    def __enter__(self) -> BaseBiosensingBoard:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_streaming()
        self.disconnect()

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def start_streaming(self) -> None:
        pass

    @abstractmethod
    def stop_streaming(self) -> None:
        pass

    @property
    @abstractmethod
    def is_streaming(self) -> bool:
        pass

    @property
    @abstractmethod
    def board_type(self) -> BoardType:
        pass

    @property
    def samples(self) -> 'queue.Queue[OpenBCISample]':
        """
        Queue object containing the samples collected by the board during
        streaming.
        """
        return self._sample_q
