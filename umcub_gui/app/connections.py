"""Connections the window keeps open between jobs (Connect ... Disconnect).

A serial port is opened once and shared by its link nodes, which take turns under the port's lock; CAN and UDP
devices have a connection each (the library shares a CAN channel's bus). ping_all() keeps SECURE sessions alive and
finds the devices that no longer answer.
"""
import threading

import umcub

from .jobs import connect_target


def _key(t):
    return (t.spec, t.node, t.uid if t.node is None else "")


class Connections:
    def __init__(self):
        self._ports = {}        # spec -> (Connection, lock): serial ports shared by their nodes
        self._devices = {}      # _key(target) -> (Device, lock, protocol, target)
        self._guard = threading.Lock()

    def __bool__(self):
        return bool(self._devices)

    def open(self, t, protocol):
        """Connect to the target's device (keys, SECURE handshake) and keep it; returns the Device."""
        shared = umcub.exclusive_key(t.spec) is not None
        with self._guard:
            port = self._ports.get(t.spec) if shared else None
            if shared and port is None:
                port = self._ports[t.spec] = (umcub.open_connection(t.spec), threading.Lock())
        try:
            dev = connect_target(t, port[0] if port else None)
        except BaseException:
            self._drop_port(t.spec)
            raise
        with self._guard:
            self._devices[_key(t)] = (dev, port[1] if port else threading.Lock(), protocol, t)
        return dev

    def device(self, t):
        """(Device, lock) of an open target, or None."""
        d = self._devices.get(_key(t))
        return d[:2] if d else None

    def port(self, spec):
        """(Connection, lock) of an open serial port (to discover over), or None."""
        return self._ports.get(spec)

    def ping_all(self):
        """Ping every open device whose port is free; close the ones that do not answer and return their targets."""
        lost = []
        for key, (dev, lock, protocol, t) in list(self._devices.items()):
            if not lock.acquire(blocking=False):
                continue                    # a job is using the port: its traffic keeps the session alive
            try:
                dev.ping(protocol)
            except (umcub.UmcubError, OSError):     # OSError: the adapter was unplugged
                lost.append(t)
                self._close(key)
            finally:
                lock.release()
        return lost

    def close_all(self):
        for key in list(self._devices):
            self._close(key)

    def _close(self, key):
        with self._guard:
            dev = self._devices.pop(key)[0]
        try:
            dev.close()
        except (umcub.UmcubError, OSError):
            pass                            # a device that is gone cannot say goodbye
        self._drop_port(key[0])

    def _drop_port(self, spec):
        with self._guard:
            port = self._ports.pop(spec, None) if not any(k[0] == spec for k in self._devices) else None
        if port:
            port[0].close()
