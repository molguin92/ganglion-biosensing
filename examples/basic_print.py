from ganglion_biosensing.board.ganglion import GanglionBoard

if __name__ == '__main__':
    with GanglionBoard(mac='D2:EA:16:D2:EB:3F') as board:
        board.start_streaming()
        for i in range(500):
            print(board.samples.get(block=True))
