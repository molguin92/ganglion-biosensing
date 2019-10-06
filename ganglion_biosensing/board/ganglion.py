from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Iterator, List, Optional, Tuple

import numpy as np
from bitstring import BitArray
from bluepy.btle import DefaultDelegate, Peripheral

from ganglion_biosensing.board.board import BaseBiosensingBoard, BoardType, \
    OpenBCISample
from ganglion_biosensing.util.bluetooth import decompress_signed, find_mac
from ganglion_biosensing.util.constants.ganglion import GanglionCommand, \
    GanglionConstants


# TODO: implement accelerometer reading


class GanglionBoard(BaseBiosensingBoard):
    """
    Represents an OpenBCI Ganglion board, providing methods to access the
    streaming data in an asynchronous manner using queues.

    The easiest way to use this class is as a context manager, see the
    included examples for reference.
    """

    def __init__(self,
                 mac: Optional[str] = None,
                 callback: Optional[Callable[[OpenBCISample], Any]] = None):
        """
        Initialize this board, indicating the MAC address of the target board.

        If the MAC address is not provided, automatic discovery will be
        attempted, which might require root privileges.

        Note that this doesn't actually connect to the board until connect()
        is manually called (or invoked through a context manager).

        :param mac: MAC address of the board.
        """
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._mac_address = find_mac() if not mac else mac
        self._ganglion = None

        if callback:
            self._sample_callback = callback

        self._shutdown_event = threading.Event()
        self._shutdown_event.set()

        self._streaming_thread = threading.Thread(
            target=GanglionBoard._streaming,
            args=(self,))

    def _streaming(self):
        self._ganglion.send_command(GanglionCommand.STREAM_START)
        while not self._shutdown_event.is_set():
            try:
                self._ganglion.waitForNotifications(GanglionConstants.DELTA_T)
            except Exception as e:
                self._logger.error('Something went wrong: ', e)
                return

    def connect(self) -> None:
        """
        Connect to the board.

        Automatically called when this object is used as a context manager.
        """
        if self._ganglion:
            self._logger.warning('Already connected!')
            return

        self._logger.debug(f'Connecting to Ganglion with MAC address '
                           f'{self._mac_address}')
        # TODO: fix
        self._ganglion = _GanglionPeripheral(self._mac_address)

    def disconnect(self) -> None:
        """
        Disconnects from the board.

        Automatically called when this object is used as a context manager,
        at the end of the with-block
        """
        if self._ganglion:
            if not self._shutdown_event.is_set():
                self.stop_streaming()

            self._ganglion.disconnect()
            self._ganglion = None

    def start_streaming(self) -> None:
        """
        Initiates streaming of data from the board. Samples are
        asynchronously stored in self.samples queue of this object.
        """
        if not self._shutdown_event.is_set():
            self._logger.warning('Already streaming!')
        else:
            self._ganglion.setDelegate(_GanglionDelegate(self._sample_callback))
            self._shutdown_event.clear()
            self._streaming_thread.start()

    def stop_streaming(self) -> None:
        """
        Stop streaming from the board.
        """
        self._logger.debug('Stopping stream.')
        self._shutdown_event.set()
        self._streaming_thread.join()

        # reset the thread
        self._streaming_thread = threading.Thread(
            target=GanglionBoard._streaming,
            args=(self,))

    @property
    def is_streaming(self) -> bool:
        return not self._shutdown_event.is_set()

    @property
    def board_type(self) -> BoardType:
        return BoardType.GANGLION

    def set_callback(self, callback: Callable[[OpenBCISample], Any]) -> None:
        if not self._shutdown_event.is_set():
            self._logger.warning('Unable to set callback while streaming.')
        else:
            super().set_callback(callback)


class _GanglionDelegate(DefaultDelegate):
    def __init__(self, callback: Callable[[OpenBCISample], Any]):
        super().__init__()
        self._last_values = np.array([0, 0, 0, 0], dtype=np.int32)
        self._last_id = -1
        self._result_callback = callback
        self._sample_cnt = 0
        self._timestamps = None
        self._logger = logging.getLogger(self.__class__.__name__)
        self._wait_for_full_pkt = True

    @staticmethod
    def _timestamp_generator() -> Iterator[float]:
        timestamp = time.time()
        while True:
            yield timestamp
            timestamp = timestamp + GanglionConstants.DELTA_T

    def handleNotification(self, cHandle, data):
        """Called when data is received. It parses the raw data from the
        Ganglion and returns an OpenBCISample object"""

        if len(data) < 1:
            self._logger.warning('A packet should at least hold one byte...')
            return

        bit_array = BitArray()
        start_byte = data[0]

        dropped, dummy_samples = self._upd_sample_count(start_byte)

        if start_byte == 0:
            # uncompressed sample
            if not self._timestamps:
                self._timestamps = _GanglionDelegate._timestamp_generator()

            self._wait_for_full_pkt = False

            for byte in data[1:13]:
                bit_array.append(f'0b{byte:08b}')

            results = []
            # and split it into 24-bit chunks here
            for sub_array in bit_array.cut(24):
                # calling '.int' interprets the value as signed 2's complement
                results.append(sub_array.int)

            self._last_values = np.array(results, dtype=np.int32)

            # store the sample
            self._result_callback(
                OpenBCISample(next(self._timestamps),
                              self._sample_cnt - 1,
                              start_byte,
                              self._last_values))

        elif 1 <= start_byte <= 200:
            if self._wait_for_full_pkt:
                self._logger.warning('Need to wait for next full packet...')
                for dummy in dummy_samples:
                    self._result_callback(dummy)
                return
            elif dropped > 0:
                self._logger.error(f'Dropped {dropped} packets! '
                                   'Need to wait for next full packet...')

                for dummy in dummy_samples:
                    self._result_callback(dummy)
                self._wait_for_full_pkt = True
                return
            else:
                for byte in data[1:]:
                    bit_array.append(f'0b{byte:08b}')

                delta_1, delta_2 = decompress_signed(start_byte, bit_array)

                tmp_value = self._last_values - delta_1
                self._last_values = tmp_value - delta_2

                self._result_callback(
                    OpenBCISample(next(self._timestamps),
                                  self._sample_cnt - 2,
                                  start_byte, tmp_value))
                self._result_callback(
                    OpenBCISample(next(self._timestamps),
                                  self._sample_cnt - 1,
                                  start_byte,
                                  self._last_values))

    def _upd_sample_count(self, num) -> Tuple[int, List[OpenBCISample]]:
        """Checks dropped packets"""
        dropped = 0
        dummy_samples = []
        if num not in [0, 206, 207]:
            if self._last_id == 0:
                if num >= 101:
                    dropped = num - 101
                else:
                    dropped = num - 1
            else:
                dropped = (num - self._last_id) - 1

            # generate dummy samples
            # generate NaN samples for the callback
            dummy_samples = []
            for i in range(dropped, -1, -1):
                dummy_samples.extend([
                    OpenBCISample(next(self._timestamps),
                                  self._sample_cnt,
                                  num - i,
                                  np.array([np.NaN] * 4)),
                    OpenBCISample(next(self._timestamps),
                                  self._sample_cnt + 1,
                                  num - i,
                                  np.array([np.NaN] * 4))
                ])
                self._sample_cnt += 2
        else:
            self._sample_cnt += 1
        self._last_id = num
        return dropped, dummy_samples


class _GanglionPeripheral(Peripheral):
    def __init__(self, mac: str):
        super().__init__(mac, 'random')
        self._logger = logging.getLogger(self.__class__.__name__)

        self._service = \
            self.getServiceByUUID(GanglionConstants.BLE_SERVICE)
        self._char_read = self._service.getCharacteristics(
            GanglionConstants.BLE_CHAR_RECEIVE)[0]
        self._char_write = \
            self._service.getCharacteristics(
                GanglionConstants.BLE_CHAR_SEND)[0]
        self._char_discon = \
            self._service.getCharacteristics(
                GanglionConstants.BLE_CHAR_DISCONNECT)[0]

        # enable notifications:
        try:
            desc_notify = \
                self._char_read.getDescriptors(
                    forUUID=GanglionConstants.NOTIF_UUID)[0]
            desc_notify.write(b'\x01')
        except Exception as e:
            self._logger.error(
                'Something went wrong while trying to enable notifications:', e)
            raise

        self._logger.debug('Connection established.')

    def send_command(self, cmd: GanglionCommand) -> None:
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
