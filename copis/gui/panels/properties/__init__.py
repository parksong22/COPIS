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
# along with COPISClient. If not, see <https://www.gnu.org/licenses/>.

"""COPIS Application GUI properties panel."""

import wx
import wx.lib.scrolledpanel as scrolled

from pydispatch import dispatcher

from copis.globals import ActionType, Point5
from copis.helpers import get_action_args_values

from ._default_panel import DefaultPanel
from ._transform_panel import TransformPanel


class PropertiesPanel(scrolled.ScrolledPanel):
    """Properties panel. Shows settings and controls in the context of the
        current selection."""

    _CONFIG = {
        'Default': ['default'],
        'Pose': ['transform']
        # 'Device': ['device_info', 'device_config'],
        # 'Object': ['default']
    }


    def __init__(self, parent) -> None:
        """Initialize PropertiesPanel with constructors."""
        super().__init__(parent, style=wx.BORDER_DEFAULT)

        self.parent = parent
        self.core = self.parent.core

        self.Sizer = wx.BoxSizer(wx.VERTICAL)

        self._property_panels = {}

        self.build_panels()
        self.update_to_selected('Default')

        self.SetupScrolling(scroll_x=False)
        self.Layout()

        # Bind listeners.
        # dispatcher.connect(self.on_device_selected, signal='ntf_d_selected')
        dispatcher.connect(self.on_pose_selected, signal='ntf_a_selected')
        # dispatcher.connect(self.on_object_selected, signal='ntf_o_selected')
        # dispatcher.connect(self.on_deselected, signal='ntf_d_deselected')
        dispatcher.connect(self.on_deselected, signal='ntf_a_deselected')
        # dispatcher.connect(self.on_deselected, signal='ntf_o_deselected')

    def build_panels(self) -> None:
        """Initialize all property panels."""
        # self._property_panels['transform'] = _PropTransform(self)
        # self._property_panels['device_info'] = _PropDeviceInfo(self)
        # self._property_panels['device_config'] = _PropDeviceConfig(self)
        # self._property_panels['quick_actions'] = _PropQuickActions(self)
        self._property_panels['transform'] = TransformPanel(self)
        self._property_panels['default'] = DefaultPanel(self)

        for _, panel in self._property_panels.items():
            self.Sizer.Add(panel, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 0)

    def update_to_selected(self, selected: str) -> None:
        """Update panels to reflect the given selection."""
        if selected not in self._CONFIG:
            return

        # Show/hide appropriate panels.
        for name, panel in self._property_panels.items():
            panel.Show(name in self._CONFIG[selected])

        self.Layout()
        w, h = self.Sizer.GetMinSize()
        self.SetVirtualSize((w, h))

    def on_pose_selected(self, pose_index: int) -> None:
        """On ntf_a_selected, set to pose view."""

        pose = self.core.project.poses[pose_index].position
        if pose.atype == ActionType.G0 or pose.atype == ActionType.G1:
            args = get_action_args_values(pose.args)

            self._property_panels['transform'].set_pose(Point5(*args[:5]))
            self.update_to_selected('Pose')
            self.parent.update_properties_panel_title('pose properties')

    def on_deselected(self) -> None:
        """On ntf_*_deselected, reset to default view."""
        self.update_to_selected('Default')
        self.parent.update_properties_panel_title('properties')
