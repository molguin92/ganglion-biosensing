import json
import logging
import queue
import socket
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

from ganglion_biosensing.board.board import BaseBiosensingBoard, BoardType, \
    OpenBCISample
from ganglion_biosensing.util.constants.ganglion import GanglionCommand, \
    GanglionConstants

# data needs to be converted from raw measurements to microvolts!
#     private final float MCP3912_Vref = 1.2f;  // reference voltage for ADC
#     in MCP3912 set in hardware

#     private final float MCP3912_gain = 1.0;  //assumed gain setting for
#     MCP3912.  NEEDS TO BE ADJUSTABLE JM

#     private float scale_fac_uVolts_per_count = (MCP3912_Vref * 1000000.f) /
#     (8388607.0 * MCP3912_gain * 1.5 * 51.0); //MCP3912 datasheet page 34.
#     Gain of InAmp = 80

_MCP3912_Vref = 1.2
_MCP3912_gain = 1.0


def _convert_count_to_uVolts(counts: int) -> float:
    return counts * ((_MCP3912_Vref * 1000000) /
                     (8388607.0 * _MCP3912_gain * 1.5 * 51.0))


_ganglion_connect_seq = [
    {
        'type'   : 'command',
        'command': GanglionCommand.CHANNEL_1_ON.decode('utf-8')
    },
    {
        'type'   : 'command',
        'command': GanglionCommand.CHANNEL_2_ON.decode('utf-8')
    },
    {
        'type'   : 'command',
        'command': GanglionCommand.CHANNEL_3_ON.decode('utf-8')
    },
    {
        'type'   : 'command',
        'command': GanglionCommand.CHANNEL_4_ON.decode('utf-8')
    },
    {
        'action': 'stop',
        'type'  : 'accelerometer'
    }
]


class GanglionHubConnection(BaseBiosensingBoard):
    def __init__(self,
                 board_id: str,
                 hub_ip: str = '127.0.0.1',
                 hub_port: int = 10996,
                 max_conn_attempts: int = 20):
        super().__init__()
        self._board_id = board_id
        self._logger = logging.getLogger(self.__class__.__name__)

        self._sample_q = queue.Queue()

        self._shutdown = threading.Event()
        self._shutdown.clear()
        self._connected_to_board = False
        self._streaming = False

        self._resp_cond = threading.Condition()
        self._exp_resp_types = []
        self._resp = []

        self._logger.info(f'Connecting to Hub {hub_ip}:{hub_port}...')

        # immediately try to connect
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        attempts = 0
        while True:
            try:
                self._logger.info(f'Connection attempt {attempts + 1}.')
                self._socket.connect((hub_ip, hub_port))
                self._logger.info('Connection success.')
                break
            except OSError:
                self._logger.info('Connection failed.')
                if attempts < max_conn_attempts:
                    self._logger.info('Reattempting connection...')
                    attempts += 1
                    time.sleep(0.01)
                    continue
                else:
                    self._logger.error('Too many connection attempts!')
                    self._socket.close()
                    raise

        self._recv_thread = threading.Thread(target=self._recv_loop)
        self._callback_thread = threading.Thread(target=self._callback_loop)

        self._recv_thread.start()
        self._callback_thread.start()

    def _send_cmds(self, cmds: List[Dict[str, Any]], wait_for_success=False):
        self._logger.debug(f'Sending commands: {cmds}')
        cmd_jsons = [json.dumps(cmd, indent=2, sort_keys=False)
                     for cmd in cmds]

        cmd_types = [cmd['type'] for cmd in cmds]

        if wait_for_success:
            with self._resp_cond:
                self._exp_resp_types = cmd_types
                self._resp = []

        for cmd_json in cmd_jsons:
            self._socket.sendall(f'{cmd_json}\r\n'.encode('utf-8'))

        if wait_for_success:
            self._logger.debug(
                f'Waiting for successful responses to \'{cmd_types}\'')
            with self._resp_cond:
                while len(self._exp_resp_types) > 0 and not \
                        self._shutdown.is_set():
                    self._resp_cond.wait(timeout=0.01)

                if self._shutdown.is_set():
                    return

                resps = self._resp
                self._exp_resp_type = []
                self._resp = []

            self._logger.debug('Got responses!')
            for resp in resps:
                try:
                    assert 200 <= resp['code'] < 300
                except AssertionError as e:
                    self._logger.error(
                        f'Got non-successful response: {resp}')
                    raise RuntimeError() from e

    def _callback_loop(self):
        """
        Called by the callback thread, executes the callbacks for each sample.
        """

        class _Timestamper:
            def __init__(self):
                self._ref_tstamp = None

            def timestamp(self, ref_timestamp: Optional[float] = None):
                if self._ref_tstamp is None:
                    if ref_timestamp:
                        self._ref_tstamp = ref_timestamp
                    else:
                        self._ref_tstamp = time.time()

                ret = self._ref_tstamp
                self._ref_tstamp += GanglionConstants.DELTA_T

                return ret

        logger = self._logger.getChild('CALLBACK')
        logger.debug('Starting callback thread...')
        timestamper = _Timestamper()

        def _handle_sample(sample: Dict):
            logger.debug(f'Handling sample: {sample}')
            # convert to OpenBCISample
            # timestamp comes in milliseconds, convert to seconds
            sample_time = sample.get('timestamp', -1) / 1000.0
            calc_time = timestamper.timestamp(sample_time)

            logger.debug(f'Adjusted time for sample: {calc_time}')

            channel_data = [_convert_count_to_uVolts(c) for c in
                            sample.get('channelDataCounts', [])]

            sample = OpenBCISample(
                timestamp=calc_time,
                seq=sample.get('sampleNumber', -1),
                pkt_id=-1,
                channel_data=np.array(channel_data, dtype=np.float64)
            )

            with self._callback_lock:
                self._sample_callback(sample)

        while not self._shutdown.is_set():
            try:
                _handle_sample(self._sample_q.get(block=True, timeout=0.01))
                self._sample_q.task_done()
            except queue.Empty:
                continue

        while not self._sample_q.empty():
            _handle_sample(self._sample_q.get())
            self._sample_q.task_done()

        logger.debug('Shut down callback thread.')

    def _recv_loop(self):
        """
        Socket read loop.
        """
        logger = self._logger.getChild('RECEIVE')
        logger.debug('Starting receiving thread...')

        data = b''
        while not self._shutdown.is_set():
            try:
                # small block size since messages are short
                data += self._socket.recv(64)

                # split up responses and process them
                while True:
                    raw_msg, lim, rest = \
                        data.partition(b'\r\n')
                    if len(lim) == len(rest) == 0:
                        # no remaining complete messages, read again from socket
                        break

                    data = rest  # save the remaining data for further
                    # processing

                    # parse the first extracted response
                    message = raw_msg.decode('utf-8')
                    # self._logger.debug(f'Raw incoming message: {message}')
                    parsed_msg = json.loads(message)

                    if parsed_msg['type'] == 'data':
                        # got a sample, put it in sample queue
                        logger.debug(f'Got a sample')
                        self._sample_q.put(parsed_msg)
                    else:
                        # asynchronous response to message
                        logger.debug(f'Message: {parsed_msg}')
                        with self._resp_cond:
                            if parsed_msg['type'] in self._exp_resp_types:
                                self._exp_resp_types.remove(parsed_msg['type'])
                                self._resp.append(parsed_msg)
                                self._resp_cond.notify()

            except socket.error as e:
                logger.debug('Socket error.')
                logger.debug(e)
                break

        logger.debug('Shut down receiving thread...')

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)
        self.shutdown()

    def connect(self) -> None:
        # connect to board
        # first, set protocol to BLED112
        self._logger.debug('Connecting...')
        protocol_cmd = {'protocol': 'bled112',
                        'action'  : 'start',
                        'type'    : 'protocol'}

        # wait for confirmation that it's started
        self._send_cmds([protocol_cmd], wait_for_success=True)
        self._logger.debug('BLE Protocol Started')

        # let it scan for a second
        time.sleep(1)
        # connect to Ganglion
        self._logger.debug(f'Connecting to board {self._board_id}...')
        connect_cmd = {'name': self._board_id, 'type': 'connect'}
        self._send_cmds([connect_cmd], wait_for_success=True)
        self._send_cmds(_ganglion_connect_seq, wait_for_success=True)

        # these hardcoded intervals are necessary, otherwise the board simply
        # does not have time to initialize...
        time.sleep(1)

        self._connected_to_board = True
        self._logger.debug(f'Connected to board {self._board_id}')

    def shutdown(self):
        if self._streaming:
            self.stop_streaming()

        if self._connected_to_board:
            self.disconnect()

        if not self._shutdown.is_set():
            self._logger.debug('Shutting down!')
            self._shutdown.set()

            self._socket.shutdown(socket.SHUT_RDWR)
            self._socket.close()

            self._sample_q.join()
            self._callback_thread.join()
            self._recv_thread.join()

    def disconnect(self) -> None:
        # disconnect from board
        if self._connected_to_board:
            disconnect_cmd = {'type': 'disconnect'}
            self._send_cmds([disconnect_cmd])
            self._connected_to_board = False

    def start_streaming(self) -> None:
        if not self._connected_to_board:
            raise RuntimeError('Not connected to board!')
        elif self._streaming:
            return

        start_stream_command = {
            'type'   : 'command',
            'command': GanglionCommand.STREAM_START.decode('utf-8')}
        self._send_cmds([start_stream_command])
        self._streaming = True

    def stop_streaming(self) -> None:
        if not self._connected_to_board:
            raise RuntimeError('Not connected to board!')
        elif not self._streaming:
            return

        stop_stream_command = {
            'type'   : 'command',
            'command': GanglionCommand.STREAM_STOP.decode('utf-8')}

        self._send_cmds([stop_stream_command])
        self._streaming = False

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def board_type(self) -> BoardType:
        return BoardType.GANGLION


if __name__ == '__main__':
    class CountingCallback:
        def __init__(self):
            self.i = 0

        def callback(self, sample):
            self.i += 1
            print(self.i, sample.timestamp, sample.channel_data)


    import sys

    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    with GanglionHubConnection('Ganglion-8819') as conn:
        conn.set_callback(CountingCallback().callback)
        conn.start_streaming()
        time.sleep(5)
