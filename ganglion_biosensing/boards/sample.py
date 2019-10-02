from typing import NamedTuple

import numpy as np

from ganglion_biosensing.boards.board import BoardType


class OpenBCISample(NamedTuple):
    seq: int
    timestamp: float
    channel_data: np.ndarray
    board: BoardType
