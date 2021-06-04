# This file is part of COPISClient.
#
# COPISClient is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# COPISClient is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with COPISClient.  If not, see <https://www.gnu.org/licenses/>.

"""COPIS Application Core functions."""

__version__ = ""

# pylint: disable=using-constant-test

import sys

if sys.version_info.major < 3:
    print("You need to run this on Python 3")
    sys.exit(-1)

# pylint: disable=wrong-import-position
import logging
import threading
import time
import warnings

from collections import namedtuple
from importlib import import_module
from functools import wraps
from queue import Queue, Empty as QueueEmpty
from typing import List
from glm import vec3

from pydispatch import dispatcher

import copis.coms.serial_controller as serial_controller
import copis.command_processor as command_processor

from .globals import ActionType, DebugEnv
from .classes import (
    Action, Device, MonitoredList, Object3D, OBJObject3D,
    ReadThread)


def locked(func):
    """Provide thread locking mechanism."""
    @wraps(func)
    def inner(*args, **kw):
        with inner.lock:
            return func(*args, **kw)
    inner.lock = threading.Lock()
    return inner


class COPISCore:
    """COPISCore. Connects and interacts with devices in system.

    Attributes:
        points: A list of points representing a path.
        devices: A list of devices (cameras).
        objects: A list of proxy objects.
        selected_device: Current selected device. -1 if not selected.
        selected_points: A list of integers representing the index of selected
            points.

    Emits:
        core_a_list_changed: When the action list has changed.
        core_a_selected: When a new point (action) has been selected.
        core_a_deselected: When a point (action) has been deselected.
        core_d_list_changed: When the device list has changed.
        core_d_selected: When a device has been selected.
        core_d_deselected: When the current device has been deselected.
        core_o_selected: When a proxy object has been selected.
        core_o_deselected: When the current proxy object has been deselected.
        core_error: Any copiscore access errors.
    """

    _YIELD_TIMEOUT = .001
    _G_COMMANDS = [ActionType.G0, ActionType.G1, ActionType.G2, ActionType.G3,
            ActionType.G4, ActionType.G17, ActionType.G18, ActionType.G19,
            ActionType.G90, ActionType.G91, ActionType.G92]
    _C_COMMANDS = [ActionType.C0, ActionType.C1]

    def __init__(self, parent) -> None:
        """Initialize a CopisCore instance."""
        self.config = parent.config

        self._is_edsdk_enabled = False
        self._edsdk = None
        self.evf_thread = None

        self._is_serial_enabled = False
        self._serial = None

        self.init_edsdk()
        self.init_serial()

        self._check_configs()

        # clear to send, enabled after responses
        self._clear_to_send = False
        # True if sending actions, false if paused
        self.is_imaging = False
        self.is_paused = False

        # logging
        self.sentlines = {}
        self.sent = []

        self.read_threads = []
        self.send_thread = None
        self.stop_send_thread = False
        self.imaging_thread = None

        self._mainqueue = None
        self._sidequeue = Queue(0)

        # TODO: this might not exist after testing machine.
        # self.offset_devices(*self.config.machine_settings.devices)

        # list of actions (paths)
        self._actions: List[Action] = MonitoredList('core_a_list_changed')

        # list of devices (cameras)
        self._devices: List[Device] = MonitoredList('core_d_list_changed',
            iterable=self.config.machine_settings.devices)

        # list of objects (proxy objects)
        self._objects: List[Object3D] = MonitoredList('core_o_list_changed',
            iterable=[
                # start with handsome dan :)
                OBJObject3D('model/handsome_dan.obj', scale=vec3(20, 20, 20)),
            ])

        self._selected_points: List[int] = []
        self._selected_device: int = -1

    def _check_configs(self) -> None:
        warn = self.config.settings.debug_env == DebugEnv.DEV.value
        msg = None
        machine_config = self.config.machine_settings

        if machine_config.machine is None:
            # If the machine is not configured, throw no matter what.
            warn = False
            msg = 'The machine is not configured.'

        # TODO:
        # - Check 3 cameras per chamber max.
        # - Check cameras within chamber bounds.

        if msg is not None:
            warning = UserWarning(msg)
            if warn:
                warnings.warn(warning)
            else:
                raise warning

    @locked
    def disconnect(self):
        """disconnects to the active serial port."""
        if self.is_serial_port_connected:
            port_name = self._get_active_serial_port_name()
            read_thread = next(filter(lambda t: t.port == port_name, self.read_threads))

            if read_thread:
                read_thread.stop = True
                if threading.current_thread() != read_thread.thread:
                    read_thread.thread.join()

                self.read_threads.remove(read_thread)
                if len(self.read_threads) == 0:
                    self._stop_sender()

            if self.imaging_thread:
                self.is_imaging = False
                self.imaging_thread.join()
                self.imaging_thread = None

            self._serial.close_port()

        self.is_imaging = False

        dispatcher.send('core_message', message=f'Disconnected from device {port_name}')

    @locked
    def connect(self, baud: int = serial_controller.BAUDS[-1]) -> bool:
        """Connects to the active serial port."""
        if not self._is_serial_enabled:
            dispatcher.send('core_message', message='Serial is not enabled')
        else:
            connected = self._serial.open_port(baud)

            if connected:
                port_name = next(
                        filter(lambda p: p.is_connected and p.is_active, self.serial_port_list)
                    ).name

                read_thread = threading.Thread(
                    target=self._listen,
                    name=f'read thread {port_name}')

                self.read_threads.append(ReadThread(thread=read_thread, port=port_name))
                read_thread.start()

                self._start_sender()

                dispatcher.send('core_message', message=f'Connected to device {port_name}')
            else:
                dispatcher.send('core_message', message='Unable to connect to device')

        return connected

    def reset(self) -> None:
        """Reset the machine."""
        return

    def _listen(self) -> None:
        read_thread = \
            next(filter(lambda t: t.thread == threading.current_thread(), self.read_threads))
        continue_listening = lambda t = read_thread: not t.stop

        while continue_listening():
            time.sleep(self._YIELD_TIMEOUT)
            if not self._edsdk.is_waiting_for_image:
                self._clear_to_send = True
                resp = self._serial.read(read_thread.port)
                if resp:
                    dispatcher.send('core_message', message=resp)

        print(f'exiting read thread {read_thread.port}')

    def _start_sender(self) -> None:
        self.stop_send_thread = False
        self.send_thread = threading.Thread(
            target=self._sender,
            name='send thread')
        self.send_thread.start()

    def _stop_sender(self) -> None:
        if self.send_thread:
            self.stop_send_thread = True
            self.send_thread.join()
            self.send_thread = None
            print('Send thread stopped')
        else:
            print('No send thread to stop')

    def _sender(self) -> None:
        while not self.stop_send_thread:
            try:
                command = self._sidequeue.get(True, 0.1)
            except QueueEmpty:
                continue

            while self.is_serial_port_connected and self.is_imaging and not self._clear_to_send:
                time.sleep(self._YIELD_TIMEOUT)

            self._send(command)

            while self.is_serial_port_connected and self.is_imaging and not self._clear_to_send:
                time.sleep(self._YIELD_TIMEOUT)

    def start_imaging(self, startindex=0) -> bool:
        """TODO"""

        if self.is_imaging or not self.is_serial_port_connected:
            return False

        # TODO: setup machine before starting

        self._mainqueue = self._actions.copy()
        self.is_imaging = True

        self._clear_to_send = False
        self.imaging_thread = threading.Thread(
            target=self._do_imaging,
            name='imaging thread',
            kwargs={"resuming": True}
        )
        self.imaging_thread.start()
        dispatcher.send('core_message', message='Imaging started')
        return True

    def cancel_imaging(self) -> None:
        """TODO"""

        self.pause()
        self.is_paused = False
        self._mainqueue = None
        self._clear_to_send = True
        dispatcher.send('core_message', message='Imaging stopped')

    def pause(self) -> bool:
        """Pause the current run, saving the current position."""

        if not self.is_imaging:
            return False

        self.is_paused = True
        self.is_imaging = False

        # try joining the print thread: enclose it in try/except because we
        # might be calling it from the thread itself
        try:
            self.imaging_thread.join()
        except RuntimeError as e:
            pass

        self.imaging_thread = None
        return True

    def resume(self) -> bool:
        """Resume the current run."""

        if not self.is_paused:
            return False

        # send commands to resume printing

        self.is_paused = False
        self.is_imaging = True
        self.imaging_thread = threading.Thread(
            target=self._do_imaging,
            name='imaging thread',
            kwargs={"resuming": True}
        )
        self.imaging_thread.start()
        dispatcher.send('core_message', message='Imaging resumed')
        return True

    def send_now(self, command):
        """Send a command to machine ahead of the command queue."""
        # Don't send now if imaging and G or C commands are sent.
        # No jogging or homing while imaging is in process.
        if self.is_imaging and command.atype in self._G_COMMANDS + self._C_COMMANDS:
            dispatcher.send('core_error', message='Action commands not allowed while imaging.')
            return

        if self.is_serial_port_connected:
            self._sidequeue.put_nowait(command)
        else:
            logging.error("Not connected to device.")

    def _do_imaging(self, resuming=False) -> None:
        """TODO"""
        self._stop_sender()

        try:
            while self.is_imaging and self.is_serial_port_connected:
                self._send_next()

            self.sentlines = {}
            self.sent = []

        except:
            logging.error("Imaging thread died")

        finally:
            self.imaging_thread = None
            self._start_sender()

    def _send_next(self):
        if not self.is_serial_port_connected:
            return

        # wait until we get the ok from listener
        while self.is_serial_port_connected and self.is_imaging and not self._clear_to_send:
            time.sleep(self._YIELD_TIMEOUT)

        if not self._sidequeue.empty():
            self._send(self._sidequeue.get_nowait())
            self._sidequeue.task_done()
            return

        if self.is_imaging and self._mainqueue:
            curr = self._mainqueue.pop(0)
            self._send(curr)
            self._clear_to_send = False

        else:
            self.is_imaging = False
            self._clear_to_send = True

    def _send(self, command):
        """Send command to machine."""

        if not self.is_serial_port_connected:
            return

        # log sent command
        self.sent.append(command)

        # debug command
        logging.debug(command)

        if command.atype in self._G_COMMANDS:

            # try writing to printer
            # ser.write(command.encode())
            pass

        elif command.atype == ActionType.C0:
            if self._edsdk.connect(command.device):
                self._edsdk.take_picture()

        elif command.atype == ActionType.C1:
            pass

        elif command.atype == ActionType.M24:
            pass

        elif command.atype == ActionType.M17:
            pass

        elif command.atype == ActionType.M18:
            pass

    # --------------------------------------------------------------------------
    # Action and device data methods
    # --------------------------------------------------------------------------

    def add_action(self, atype: ActionType, device: int, *args) -> bool:
        """TODO: validate args given atype"""
        new = Action(atype, device, len(args), list(args))

        self._actions.append(new)

        # if certain type, broadcast that positions are modified
        if atype in (ActionType.G0, ActionType.G1, ActionType.G2, ActionType.G3):
            dispatcher.send('core_a_list_changed')

        return True

    def remove_action(self, index: int) -> Action:
        """Remove an action given action list index."""
        action = self._actions.pop(index)
        dispatcher.send('core_a_list_changed')
        return action

    def clear_action(self) -> None:
        self._actions.clear()
        dispatcher.send('core_a_list_changed')

    @property
    def actions(self) -> List[Action]:
        return self._actions

    @property
    def devices(self) -> List[Device]:
        return self._devices

    @property
    def objects(self) -> List[Object3D]:
        return self._objects

    @property
    def selected_device(self) -> int:
        return self._selected_device

    @property
    def selected_points(self) -> List[int]:
        return self._selected_points

    def select_device(self, index: int) -> None:
        """Select device given index in devices list."""
        if index < 0:
            self._selected_device = -1
            dispatcher.send('core_d_deselected')

        elif index < len(self._devices):
            self._selected_device = index
            self.select_point(-1)
            dispatcher.send('core_o_deselected')
            dispatcher.send('core_d_selected', device=self._devices[index])

        else:
            dispatcher.send('core_error', message=f'invalid device index {index}')

    def select_point(self, index: int, clear: bool = True) -> None:
        """Add point to points list given index in actions list.

        Args:
            index: An integer representing index of action to be selected.
            clear: A boolean representing whether to clear the list before
                selecting the new point or not.
        """
        if index == -1:
            self._selected_points.clear()
            dispatcher.send('core_a_deselected')
            return

        if index >= len(self._actions):
            return

        if clear:
            self._selected_points.clear()

        if index not in self._selected_points:
            self._selected_points.append(index)
            self.select_device(-1)
            dispatcher.send('core_o_deselected')
            dispatcher.send('core_a_selected', points=self._selected_points)

    def deselect_point(self, index: int) -> None:
        """Remove point from selected points given index in actions list."""
        try:
            self._selected_points.remove(index)
            dispatcher.send('core_a_deselected')
        except ValueError:
            return

    def update_selected_points(self, args) -> None:
        """Update position of points in selected points list."""
        for id_ in self.selected_points:
            for i in range(min(len(self.actions[id_].args), len(args))):
                self.actions[id_].args[i] = args[i]

        dispatcher.send('core_a_list_changed')

    def export_actions(self, filename: str = None) -> list:
        """Serialize action list and write to file.

        TODO: Expand to include not just G0 and C0 actions
        """

        lines = []

        for action in self._actions:
            line = command_processor.serialize_command(action)
            lines.append(line)

        if filename is not None:
            with open(filename, 'w') as file:
                file.write('\n'.join(lines))

        dispatcher.send('core_a_exported', filename=filename)
        return lines

    # --------------------------------------------------------------------------
    # Canon EDSDK methods
    # --------------------------------------------------------------------------

    def init_edsdk(self) -> None:
        """Initializes the Canon EDSDK controller."""
        if self._is_edsdk_enabled:
            return

        self._edsdk = import_module('copis.coms.edsdk_controller')
        self._edsdk.initialize(ConsoleOutput())

        self._is_edsdk_enabled = self._edsdk.is_enabled

    def terminate_edsdk(self):
        """Disconnects all EDSDK connections; and terminates the Canon EDSDK."""
        if self._is_edsdk_enabled:
            self._edsdk.terminate()

    # --------------------------------------------------------------------------
    # Serial methods
    # --------------------------------------------------------------------------

    def init_serial(self) -> None:
        """Initializes the serial controller."""
        if self._is_serial_enabled:
            return

        is_dev_env = self.config.settings.debug_env == DebugEnv.DEV.value
        self._serial = serial_controller
        self._serial.initialize(ConsoleOutput(), is_dev_env)
        self._is_serial_enabled = True

    def terminate_serial(self):
        """Disconnects all serial connections; and terminates all serial threading activity."""
        if self._is_serial_enabled:
            for read_thread in self.read_threads:
                read_thread.stop = True
                if threading.current_thread() != read_thread.thread:
                    read_thread.thread.join()

            self.read_threads.clear()

            if self.imaging_thread:
                self.is_imaging = False
                self.imaging_thread.join()
                self.imaging_thread = None

            self._stop_sender()
            self._serial.terminate()

    @locked
    def select_serial_port(self, name: str) -> bool:
        """Sets the active serial port to the provided one."""
        selected = self._serial.select_port(name)
        if not selected:
            dispatcher.send('core_message', message='Unable to select serial port')

        return selected

    def update_serial_ports(self) -> None:
        """Updates the serial ports list."""
        self._serial.update_port_list()

    def _get_active_serial_port_name(self):
        port = next(
                filter(lambda p: p.is_active, self.serial_port_list), None
            )
        return port.name if port else None


    @property
    def serial_bauds(self):
        """Returns available serial com bauds."""
        return self._serial.BAUDS

    @property
    def serial_port_list(self) -> List:
        """Returns a safe (without the actual connections) representation
        of the serial ports list."""
        safe_list = []
        device = namedtuple('SerialDevice', 'name is_connected is_active')

        # pylint: disable=not-an-iterable
        for port in self._serial.port_list:
            safe_port = device(
                name=port.name,
                is_connected=port.connection is not None and port.connection.is_open,
                is_active=port.is_active
            )

            safe_list.append(safe_port)

        return safe_list

    @property
    def is_serial_port_connected(self):
        """Return a flag indicating whether the active serial port is connected."""
        return self._serial.is_port_open


class ConsoleOutput:
    """Implement console output operations."""

    def __init__(self):
        return

    def print(self, msg: str) -> None:
        """Dispatch a message to the console."""
        dispatcher.send('core_message', message=msg)
