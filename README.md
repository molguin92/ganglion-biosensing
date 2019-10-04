[![PyPI version](https://badge.fury.io/py/ganglion-biosensing.svg)](https://badge.fury.io/py/ganglion-biosensing)
# ganglion-biosensing

Modern Python 3.7+ library for interfacing with the OpenBCI Ganglion biosensing board over BTLE.

The origins of this library come from my personal disagreement with some of the design and implementation choices made by the developers of the official [pyOpenBCI library](https://github.com/OpenBCI/pyOpenBCI). Some of the code in this repository has been obtained and/or adapted from the official pyOpenBCI code (following the MIT License).

It should be noted that this library does not aim to be a full replacement for the official library, as it is completely focused on the Ganglion board and not on the Cyton. It should rather be looked at as an alternative which aims to target a more modern and efficient implementation from the ground up.

## Installation
Simply do:
```bash
pip install ganglion-biosensing
```

Alternatively, install from the Github repository:
```bash
pip install git+https://github.com/molguin92/ganglion-biosensing.git
```

## Usage
Usage is pretty straightforward - simply declare a Ganglion within a with-block for automatic connection and cleanup:

```python
from ganglion_biosensing.board.ganglion import GanglionBoard

if __name__ == '__main__':
    with GanglionBoard(mac='FF:FF:FF:FF:FF:FF') as board:
        board.start_streaming()
        for i in range(500):
            print(board.samples.get(block=True))
```

The code is thread safe by design - samples are collected in an asynchronous manner and deposited in the `board.samples` queue.

For more details see the `examples/` directory and the code itself.


## License

Copyright 2019 - Manuel Olguín Muñoz.

Licensed under an MIT license, see [LICENSE](./LICENSE) for details.
