from __future__ import annotations

from boards.board import BaseBiosensingBoard, BoardType


class GanglionBoard(BaseBiosensingBoard):
    def __init__(self, mac: str):
        pass

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def start_streaming(self) -> 'queue.Queue[OpenBCISample]':
        pass

    def stop_streaming(self) -> None:
        pass

    @property
    def is_streaming(self) -> bool:
        pass

    @property
    def board_type(self) -> BoardType:
        pass
