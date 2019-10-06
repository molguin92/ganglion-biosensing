import time

from ganglion_biosensing.board.ganglion import GanglionBoard

if __name__ == '__main__':
    with GanglionBoard(mac='D2:EA:16:D2:EB:3F') as board:
        board.set_callback(lambda x: print(x))
        board.start_streaming()

        time.sleep(5.0)
