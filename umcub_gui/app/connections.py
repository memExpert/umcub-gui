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
    def __init__(self, tap=None):
        self.tap = tap          # the exchange log, on every connection opened here and by the jobs (tap_for)
        self.names = {}         # device string -> Connection.name its events carry (the log's device filter)
        self._ports = {}        # umcub.exclusive_key -> (Connection, lock): serial ports shared by their nodes
        self._devices = {}      # _key(target) -> (Device, lock, protocol, target)
        self._guard = threading.Lock()

    def tap_for(self, spec, node=None):
        """The tap of a connection to `spec` (opened for `node`: on CAN its IDs, its SMP packets do not say it): notes
        the connection's name, then the exchange log; None without one."""
        if self.tap is None:
            return None

        def tap(ev):
            self.names[spec] = ev.connection
            self.tap(ev, node)
        return tap

    def __bool__(self):
        return bool(self._devices)

    def open(self, t, protocol):
        """Connect to the target's device (keys, SECURE handshake) and keep it; returns the Device (the one already
        open for a second row of the same device)."""
        medium = umcub.exclusive_key(t.spec)
        with self._guard:
            if _key(t) in self._devices:
                return self._devices[_key(t)][0]
            port = self._ports.get(medium) if medium else None
            if medium and port is None:
                port = self._ports[medium] = (umcub.open_connection(t.spec, tap=self.tap_for(t.spec)),
                                              threading.Lock())
        try:
            dev = connect_target(t, port[0]) if port else connect_target(t, tap=self.tap_for(t.spec, t.node))
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
        """(Connection, lock) of the open serial port of `spec` (however it is spelled), or None."""
        medium = umcub.exclusive_key(spec)
        return self._ports.get(medium) if medium else None

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
        """Close every device, each once its ping or job is done (no longer than a few seconds)."""
        for key in list(self._devices):
            d = self._devices.get(key)
            if d:
                got = d[1].acquire(timeout=5)
                try:
                    self._close(key)
                finally:
                    if got:
                        d[1].release()

    def _close(self, key):
        with self._guard:
            d = self._devices.pop(key, None)    # a ping may have closed it meanwhile
        if d is None:
            return
        dev = d[0]
        try:
            dev.close()
        except (umcub.UmcubError, OSError):
            pass                            # a device that is gone cannot say goodbye
        self._drop_port(key[0])

    def _drop_port(self, spec):
        medium = umcub.exclusive_key(spec)
        with self._guard:
            in_use = any(umcub.exclusive_key(k[0]) == medium for k in self._devices)
            port = self._ports.pop(medium, None) if medium and not in_use else None
        if port:
            port[0].close()
