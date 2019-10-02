from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Optional

from bluepy.btle import Peripheral

from ganglion_biosensing.boards.board import BaseBiosensingBoard, BoardType
from ganglion_biosensing.util.bluetooth import find_mac


class _GanglionCommand(bytes, Enum):
    CHANNEL_1_ON = '!'.encode('ascii')
    CHANNEL_2_ON = '@'.encode('ascii')
    CHANNEL_3_ON = '#'.encode('ascii')
    CHANNEL_4_ON = '$'.encode('ascii')
    CHANNEL_1_OFF = '1'.encode('ascii')
    CHANNEL_2_OFF = '2'.encode('ascii')
    CHANNEL_3_OFF = '3'.encode('ascii')
    CHANNEL_4_OFF = '4'.encode('ascii')
    SYNTH_SQR_ON = '['.encode('ascii')
    SYNTH_SQR_OFF = ']'.encode('ascii')
    IMP_TEST_START = 'z'.encode('ascii')
    IMP_TEST_STOP = 'Z'.encode('ascii')
    ACCEL_ON = 'n'.encode('ascii')
    ACCEL_OFF = 'N'.encode('ascii')
    SD_LOGGING_5MIN = 'A'.encode('ascii')
    SD_LOGGING_15MIN = 'S'.encode('ascii')
    SD_LOGGING_30MIN = 'F'.encode('ascii')
    SD_LOGGING_1HR = 'G'.encode('ascii')
    SD_LOGGING_2HR = 'H'.encode('ascii')
    SD_LOGGING_4HR = 'J'.encode('ascii')
    SD_LOGGING_12HR = 'K'.encode('ascii')
    SD_LOGGING_24HR = 'L'.encode('ascii')
    SD_LOGGING_TEST = 'a'.encode('ascii')
    SD_LOGGING_STOP = 'j'.encode('ascii')
    STREAM_START = 'b'.encode('ascii')
    STREAM_STOP = 's'.encode('ascii')
    QUERY_REGS = '?'.encode('ascii')
    RESET = 'v'.encode('ascii')
    # TODO: change sampling rate and WiFi shield commands


class _GanglionPeripheral(Peripheral):
    # service for communication, as per docs
    _BLE_SERVICE = "fe84"
    # characteristics of interest
    _BLE_CHAR_RECEIVE = "2d30c082f39f4ce6923f3484ea480596"
    _BLE_CHAR_SEND = "2d30c083f39f4ce6923f3484ea480596"
    _BLE_CHAR_DISCONNECT = "2d30c084f39f4ce6923f3484ea480596"
    _NOTIF_UUID = 0x2902

    def __init__(self, mac: str):
        super().__init__(mac, 'random')
        self._logger = logging.getLogger(self.__class__.__name__)

        self._service = self.getServiceByUUID(self._BLE_SERVICE)
        self._char_read = self.getCharacteristics(self._BLE_CHAR_RECEIVE)[0]
        self._char_write = self.getCharacteristics(self._BLE_CHAR_SEND)[0]
        self._char_discon = \
            self._service.getCharacteristics(self._BLE_CHAR_DISCONNECT)[0]

        # enable notifications:
        try:
            desc_notify = \
                self._char_read.getDescriptors(forUUID=self._NOTIF_UUID)[0]
            desc_notify.write(b'\x01')
        except Exception as e:
            self._logger.error(
                "Something went wrong while trying to enable notifications:", e)
            raise

        self._logger.debug("Connection established.")

    def send_command(self, cmd: _GanglionCommand) -> None:
        self._char_write.write(cmd.value)

    def disconnect(self):
        try:
            self._char_discon.write(b' ')
        except Exception as e:
            # exceptions here don't really matter as we're disconnecting anyway
            # although, it would be good to check WHY self.char_discon.write()
            # ALWAYS throws an exception...
            self._logger.debug(e)
            pass

        try:
            super().disconnect()
        except Exception as e:
            self._logger.debug(e)
            pass


class GanglionBoard(BaseBiosensingBoard):
    def __init__(self, mac: Optional[str] = None):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._mac_address = find_mac() if not mac else mac
        self._ganglion = None

        self._shutdown_event = threading.Event()
        self._shutdown_event.set()

        self._streaming_thread = threading.Thread(
            target=GanglionBoard._streaming,
            args=(self,))

    def _streaming(self):
        self._ganglion.send_command(_GanglionCommand.STREAM_START)
        while not self._shutdown_event.is_set():
            # todo
            pass

    def connect(self) -> None:
        if self._ganglion:
            raise OSError('Already connected!')
        self._logger.debug(f'Connecting to Ganglion with MAC address '
                           f'{self._mac_address}')
        self._ganglion = _GanglionPeripheral(self._mac_address)

    def disconnect(self) -> None:
        if self._ganglion:
            if not self._shutdown_event.is_set():
                self.stop_streaming()

            self._ganglion.disconnect()
            self._ganglion = None

    def start_streaming(self) -> None:
        if not self._shutdown_event.is_set():
            self._logger.warning('Already streaming!')
        else:
            self._shutdown_event.clear()
            self._streaming_thread.start()

    def stop_streaming(self) -> None:
        self._logger.debug('Stopping stream.')
        self._shutdown_event.set()
        self._streaming_thread.join()

    @property
    def is_streaming(self) -> bool:
        return not self._shutdown_event.is_set()

    @property
    def board_type(self) -> BoardType:
        return BoardType.GANGLION
