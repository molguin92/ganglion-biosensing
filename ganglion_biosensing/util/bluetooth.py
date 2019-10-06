from typing import Iterable, Tuple

import numpy as np
from bitstring import BitArray
from bluepy.btle import Scanner


def find_mac() -> str:
    """
    Scans for nearby Ganglion board, and returns the MAC address of the
    first one detected.

    Requires root!

    :return: MAC address of the first Ganglion device discovered.
    """
    scanner = Scanner()
    devices = scanner.scan()
    gang_macs = []
    for dev in devices:
        for adtype, desc, value in dev.getScanData():
            if desc == 'Complete Local Name' and value.startswith(
                    'Ganglion'):
                gang_macs.append(dev.addr)

    if len(gang_macs) < 1:
        raise OSError('No nearby Ganglion board discovered.')
    else:
        return gang_macs[0]


def decompress_signed(pkt_id: int, bit_array: BitArray) \
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

    channel_samples = list(channel_samples)
    sample_1 = _process_channels(channel_samples[:4])
    sample_2 = _process_channels(channel_samples[4:])
    return sample_1, sample_2
