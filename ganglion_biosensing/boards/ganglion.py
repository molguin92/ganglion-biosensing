from __future__ import annotations

import logging
import queue
import threading
from enum import Enum
from typing import Iterable, Optional, Tuple

import numpy as np
from bitstring import BitArray
from bluepy.btle import DefaultDelegate, Peripheral

from ganglion_biosensing.boards.board import BaseBiosensingBoard, BoardType, \
    OpenBCISample
from ganglion_biosensing.util.bluetooth import find_mac

# sampling rate
_DEFAULT_SAMPLING_RATE = 200  # Hz
_DEFAULT_DELTA_T = 1.0 / _DEFAULT_SAMPLING_RATE  # ms


def _decompress_signed(pkt_id: int, bit_array: BitArray) \
        -> 'Tuple[np.ndarray, np.ndarray]':
    channel_samples = bit_array.cut(18) if pkt_id <= 100 else bit_array.cut(19)

    def _process_channels(sample: Iterable[BitArray]) -> np.ndarray:
        sample_deltas = []
        for channel_data in sample:
            channel_delta = channel_data.uint
            if channel_data.endswith('0b1'):
                # ends with a 1 means that it's a negative number
                channel_delta -= 1
                channel_delta *= -1
            sample_deltas.append(channel_delta)

        return np.array(sample_deltas, dtype=np.int32)

    sample_1 = _process_channels(channel_samples[:4])
    sample_2 = _process_channels(channel_samples[4:])
    return sample_1, sample_2


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
        super().__init__()
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
            try:
                self._ganglion.waitForNotifications(_DEFAULT_DELTA_T)
            except Exception as e:
                self._logger.error("Something went wrong: ", e)
                return

    def connect(self) -> None:
        if self._ganglion:
            raise OSError('Already connected!')

        self._logger.debug(f'Connecting to Ganglion with MAC address '
                           f'{self._mac_address}')
        self._ganglion = _GanglionPeripheral(self._mac_address)
        self._ganglion.setDelegate(_GanglionDelegate(self._sample_q))

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


class _GanglionDelegate(DefaultDelegate):
    def __init__(self, result_q: 'queue.Queue[OpenBCISample]'):
        super().__init__()
        self._last_values = np.array([0, 0, 0, 0], dtype=np.int32)
        self._last_id = -1
        self._result_q = result_q
        self._sample_cnt = 0
        self._logger = logging.getLogger(self.__class__.__name__)
        self._wait_for_full_pkt = True

    def handleNotification(self, cHandle, data):
        """Called when data is received. It parses the raw data from the
        Ganglion and returns an OpenBCISample object"""

        if len(data) < 1:
            self._logger.warning('A packet should at least hold one byte...')
            return

        bit_array = BitArray()
        start_byte = data[0]

        dropped, dummy_samples = self._upd_sample_count(start_byte)

        if self._wait_for_full_pkt:
            if start_byte != 0:
                self._logger.warning('Need to wait for next full packet...')
                for dummy in dummy_samples:
                    self._result_q.put(dummy)
                return
            else:
                self._logger.warning('Got full packet, resuming.')
                self._wait_for_full_pkt = False

        if dropped > 0:
            self._logger.error(f'Dropped {dropped} packets! '
                               'Need to wait for next full packet...')

            for dummy in dummy_samples:
                self._result_q.put(dummy)
            self._wait_for_full_pkt = True
            return

        if start_byte == 0:
            # uncompressed sample
            for byte in data[1:13]:
                bit_array.append(f'0b{byte:08b}')

            results = []
            # and split it into 24-bit chunks here
            for sub_array in bit_array.cut(24):
                # calling ".int" interprets the value as signed 2's complement
                results.append(sub_array.int)

            self._last_values = np.array(results, dtype=np.int32)

            # store the sample
            self._result_q.put(OpenBCISample(self._sample_cnt,
                                             self._last_values))
            self._sample_cnt += 1

        elif 1 <= start_byte <= 200:
            for byte in data[1:]:
                bit_array.append(f'0b{byte:08b}')

            delta_1, delta_2 = _decompress_signed(start_byte, bit_array)

            tmp_value = self._last_values - delta_1
            self._last_values = tmp_value - delta_2

            self._result_q.put(
                OpenBCISample(self._sample_cnt, tmp_value))
            self._result_q.put(
                OpenBCISample(self._sample_cnt + 1, self._last_values))
            self._sample_cnt += 2

    def _upd_sample_count(self, num):
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
                    OpenBCISample(self._sample_cnt, np.array([np.NaN] * 4)),
                    OpenBCISample(self._sample_cnt + 1, np.array([np.NaN] * 4))
                ])
                self._sample_cnt += 2
        self._last_id = num
        return dropped, dummy_samples
