from __future__ import annotations

import logging
from abc import abstractmethod
from contextlib import AbstractContextManager
from enum import Enum
from typing import Any, Callable, NamedTuple

import numpy as np


class OpenBCISample(NamedTuple):
    timestamp: float
    seq: int
    pkt_id: int
    channel_data: np.ndarray


class BoardType(Enum):
    GANGLION = 0
    CYTON = 1


class BaseBiosensingBoard(AbstractContextManager):

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._sample_callback = self._default_callback

    def set_callback(self, callback: Callable[[OpenBCISample], Any]) -> None:
        self._sample_callback = callback

    def _default_callback(self, sample):
        self._logger.debug(f'Default callback: {sample}')

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
