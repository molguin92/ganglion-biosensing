from bluepy.btle import Scanner


def find_mac() -> str:
    """
    Scans for nearby Ganglion boards, and returns the MAC address of the
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
        raise OSError('No nearby Ganglion boards discovered.')
    else:
        return gang_macs[0]
