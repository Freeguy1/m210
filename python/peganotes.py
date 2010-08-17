"""
Python API to Pegasus Notetaker devices.

Currently only Pegasus Mobile Notetaker M210 is supported.

"""

from __future__ import absolute_import

import os
import select
import struct

import linux.hidraw

class CommunicationError(Exception):
    """
    Raised when an unexpected message is received from a M210 device.
    """
    pass

class ModeButtonInterrupt(Exception):
    pass

class TimeoutError(Exception):
    """
    Raised when communication to a M210 device timeouts.
    """
    pass

class M210(object):
    """
    M210 exposes two interfaces via USB-connection. By default, udev
    creates two hidraw devices to represent these interfaces when the
    device is plugged in. Paths to these devices must be passed to
    initialize a M210-connection. Interface 1 is used for reading and
    writing, interface 2 only for reading.

    Usage example::

      >>> import peganotes
      >>> m210 = peganotes.M210(["/dev/hidraw1", "/dev/hidraw2"])
      >>> m210.get_info()
      {'firmware_version': 337, 'analog_version': 265, 'pad_version': 32028, 'mode': 'tablet'}
    
    """

    def __init__(self, hidraw_filepaths):
        self._fds = []
        for filepath, mode in zip(hidraw_filepaths, (os.O_RDWR, os.O_RDONLY)):
            fd = os.open(filepath, mode)
            devinfo = linux.hidraw.get_devinfo(fd)
            if devinfo != {'product': 257, 'vendor': 3616, 'bustype': 3}:
                raise ValueError('%s is not a M210 hidraw device.' % filepath)
            self._fds.append(fd)

    def _read(self, iface_n):
        fd = self._fds[iface_n]

        rlist, _, _ = select.select([fd], [], [], 1.0)
        if not fd in rlist:
            raise TimeoutError("Reading timeouted.")

        response_size = (64, 9)[iface_n]
        response = os.read(fd, response_size)

        if iface_n == 0:
            if response[:2] == '\x80\xb5':
                raise ModeButtonInterrupt()

        return response

    def _write(self, request):
        request_header = struct.pack('BBB', 0x00, 0x02, len(request))
        os.write(self._fds[0], request_header + request)

    def _wait_ready(self):
        while True:
            self._write('\x95')
            try:
                response = self._read(0)
            except TimeoutError:
                continue
            except ModeButtonInterrupt:
                continue
            break

        if (response[:3] != '\x80\xa9\x28'
            or response[9] != '\x0e'):
            raise CommunicationError('Unexpected response to info request: %s'
                                     % response)

        firmware_ver, analog_ver, pad_ver = struct.unpack('>HHH', response[3:9])

        mode = {'\x01': 'mouse', '\x02': 'tablet'}[response[10]]

        return {'firmware_version': firmware_ver,
                'analog_version': analog_ver,
                'pad_version': pad_ver,
                'mode': mode}

    def get_info(self):
        return self._wait_ready()
