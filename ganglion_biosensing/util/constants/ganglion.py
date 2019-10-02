# sampling rate
from enum import Enum
from typing import NamedTuple


class _GanglionConstants(NamedTuple):
    SAMPLING_RATE: int
    DELTA_T: float
    BLE_SERVICE: str
    BLE_CHAR_RECEIVE: str
    BLE_CHAR_SEND: str
    BLE_CHAR_DISCONNECT: str
    NOTIF_UUID: int


GanglionConstants = _GanglionConstants(
    SAMPLING_RATE=200,  # Hz
    DELTA_T=1.0 / 200,
    BLE_SERVICE='fe84',
    # characteristics of interest
    BLE_CHAR_RECEIVE='2d30c082f39f4ce6923f3484ea480596',
    BLE_CHAR_SEND='2d30c083f39f4ce6923f3484ea480596',
    BLE_CHAR_DISCONNECT='2d30c084f39f4ce6923f3484ea480596',
    NOTIF_UUID=0x2902
)


class GanglionCommand(bytes, Enum):
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
