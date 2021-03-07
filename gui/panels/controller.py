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

"""ControllerPanel class.

TODO: Currently nonfunctional - needs to be connected to copiscore when
serial connections are implemented.
"""

import utils
import wx
import wx.lib.scrolledpanel as scrolled
from gui.wxutils import (EVT_FANCY_TEXT_UPDATED_EVENT, FancyTextCtrl,
                         create_scaled_bitmap, simple_statictext)
from pydispatch import dispatcher
from utils import Point3, Point5


class ControllerPanel(scrolled.ScrolledPanel):
    """Controller panel. When camera selected, jogs movement.

    Args:
        parent: Pointer to a parent wx.Frame.
    """

    def __init__(self, parent, *args, **kwargs) -> None:
        """Inits ControllerPanel with constructors."""
        super().__init__(parent, style=wx.BORDER_DEFAULT)
        self.p = parent

        self.Sizer = wx.BoxSizer(wx.VERTICAL)

        self._add_state_controls()
        self._add_jog_controls()

        self.SetupScrolling(scroll_x=False)

        # start disabled, as no devices will be selected
        self.Disable()
        self.Layout()

        # bind copiscore listeners
        dispatcher.connect(self.on_device_selected, signal='core_d_selected')
        dispatcher.connect(self.on_device_deselected, signal='core_d_deselected')

    def on_device_selected(self, device) -> None:
        """On core_d_selected, update and enable controls."""
        self.update_machine_pos(device.position)
        self.Enable()

    def on_device_deselected(self) -> None:
        """On core_d_deselected, clear and disable controls."""
        self.update_machine_pos(Point5())
        self.Disable()

    def _add_state_controls(self) -> None:
        """Initialize controller state sizer and setup child elements."""
        info_sizer = wx.StaticBoxSizer(wx.StaticBox(self, label='State'), wx.VERTICAL)

        info_grid = wx.FlexGridSizer(6, 4, 0, 0)
        info_grid.AddGrowableCol(2)

        x_text = wx.StaticText(info_sizer.StaticBox, label='X')
        y_text = wx.StaticText(info_sizer.StaticBox, label='Y')
        z_text = wx.StaticText(info_sizer.StaticBox, label='Z')
        p_text = wx.StaticText(info_sizer.StaticBox, label='P')
        t_text = wx.StaticText(info_sizer.StaticBox, label='T')
        for text in (x_text, y_text, z_text, p_text, t_text):
            text.Font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        mpos_text = wx.StaticText(info_sizer.StaticBox, label='Machine')
        mzero_text = wx.StaticText(info_sizer.StaticBox, label='Zero')

        self.x_m_text = wx.TextCtrl(info_sizer.StaticBox, value='0.000', size=(50, 24), style=wx.TE_READONLY)
        self.y_m_text = wx.TextCtrl(info_sizer.StaticBox, value='0.000', size=(50, 24), style=wx.TE_READONLY)
        self.z_m_text = wx.TextCtrl(info_sizer.StaticBox, value='0.000', size=(50, 24), style=wx.TE_READONLY)
        self.p_m_text = wx.TextCtrl(info_sizer.StaticBox, value='0.000', size=(50, 24), style=wx.TE_READONLY)
        self.t_m_text = wx.TextCtrl(info_sizer.StaticBox, value='0.000', size=(50, 24), style=wx.TE_READONLY)
        for text in (self.x_m_text, self.y_m_text, self.z_m_text, self.p_m_text, self.t_m_text):
            text.Font = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        x0_m_btn = wx.Button(info_sizer.StaticBox, label='X0', size=(30, -1))
        y0_m_btn = wx.Button(info_sizer.StaticBox, label='Y0', size=(30, -1))
        z0_m_btn = wx.Button(info_sizer.StaticBox, label='Z0', size=(30, -1))
        p0_m_btn = wx.Button(info_sizer.StaticBox, label='P0', size=(30, -1))
        t0_m_btn = wx.Button(info_sizer.StaticBox, label='T0', size=(30, -1))
        for btn in (x0_m_btn, y0_m_btn, z0_m_btn, p0_m_btn, t0_m_btn):
            btn.Font = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        info_grid.AddMany([
            (0, 0),
            (8, 0),
            (mpos_text, 0, 0, 0),
            (mzero_text, 0, 0, 0),

            (x_text, 0, 0, 0),
            (0, 0),
            (self.x_m_text, 0, wx.ALL|wx.EXPAND, 1),
            (x0_m_btn, 0, wx.EXPAND, 0),

            (y_text, 0, 0, 0),
            (0, 0),
            (self.y_m_text, 0, wx.ALL|wx.EXPAND, 1),
            (y0_m_btn, 0, wx.EXPAND, 0),

            (z_text, 0, 0, 0),
            (0, 0),
            (self.z_m_text, 0, wx.ALL|wx.EXPAND, 1),
            (z0_m_btn, 0, wx.EXPAND, 0),

            (p_text, 0, 0, 0),
            (0, 0),
            (self.p_m_text, 0, wx.ALL|wx.EXPAND, 1),
            (p0_m_btn, 0, wx.EXPAND, 0),

            (t_text, 0, 0, 0),
            (0, 0),
            (self.t_m_text, 0, wx.ALL|wx.EXPAND, 1),
            (t0_m_btn, 0, wx.EXPAND, 0),
        ])

        info_sizer.Add(info_grid, 1, wx.ALL|wx.EXPAND, 4)
        self.Sizer.Add(info_sizer, 0, wx.ALL|wx.EXPAND, 7)

    def _add_jog_controls(self) -> None:
        """Initialize jog controller sizer and setup child elements."""
        jog_sizer = wx.StaticBoxSizer(wx.StaticBox(self, label='Jog Controller'), wx.VERTICAL)

        xyzpt_grid = wx.FlexGridSizer(6, 4, 0, 0)
        for col in (0, 1, 2, 3):
            xyzpt_grid.AddGrowableCol(col)

        arrow_nw_btn = wx.BitmapButton(jog_sizer.StaticBox, bitmap=create_scaled_bitmap('arrow_nw', 20), size=(24, 24))
        arrow_ne_btn = wx.BitmapButton(jog_sizer.StaticBox, bitmap=create_scaled_bitmap('arrow_ne', 20), size=(24, 24))
        arrow_sw_btn = wx.BitmapButton(jog_sizer.StaticBox, bitmap=create_scaled_bitmap('arrow_sw', 20), size=(24, 24))
        arrow_se_btn = wx.BitmapButton(jog_sizer.StaticBox, bitmap=create_scaled_bitmap('arrow_se', 20), size=(24, 24))

        x_pos_btn = wx.Button(jog_sizer.StaticBox, label='X+', size=(24, 24))
        x_neg_btn = wx.Button(jog_sizer.StaticBox, label='X-', size=(24, 24))
        y_pos_btn = wx.Button(jog_sizer.StaticBox, label='Y+', size=(24, 24))
        y_neg_btn = wx.Button(jog_sizer.StaticBox, label='Y-', size=(24, 24))
        xy_btn = wx.BitmapButton(jog_sizer.StaticBox, bitmap=create_scaled_bitmap('keyboard', 24), size=(24, 24))
        z_pos_btn = wx.Button(jog_sizer.StaticBox, label='Z+', size=(24, 24))
        z_neg_btn = wx.Button(jog_sizer.StaticBox, label='Z-', size=(24, 24))

        tilt_up_btn = wx.Button(jog_sizer.StaticBox, label='T+', size=(24, 24))
        tilt_down_btn = wx.Button(jog_sizer.StaticBox, label='T-', size=(24, 24))
        pan_right_btn = wx.Button(jog_sizer.StaticBox, label='P+', size=(24, 24))
        pan_left_btn = wx.Button(jog_sizer.StaticBox, label='P-', size=(24, 24))

        for btn in (x_pos_btn, x_neg_btn, y_pos_btn, y_neg_btn, z_pos_btn, z_neg_btn,
                    tilt_up_btn, pan_left_btn, tilt_down_btn, pan_right_btn):
            btn.Font = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        xyzpt_grid.AddMany([
            (arrow_nw_btn, 0, wx.EXPAND, 0),
            (y_pos_btn, 0, wx.EXPAND, 0),
            (arrow_ne_btn, 0, wx.EXPAND, 0),
            (z_pos_btn, 0, wx.EXPAND, 0),

            (x_neg_btn, 0, wx.EXPAND, 0),
            (xy_btn, 0, wx.EXPAND, 0),
            (x_pos_btn, 0, wx.EXPAND, 0),
            (0, 0),

            (arrow_sw_btn, 0, wx.EXPAND, 0),
            (y_neg_btn, 0, wx.EXPAND, 0),
            (arrow_se_btn, 0, wx.EXPAND, 0),
            (z_neg_btn, 0, wx.EXPAND, 0),

            (0, 5), (0, 0), (0, 0), (0, 0),

            (0, 0),
            (tilt_up_btn, 0, wx.EXPAND, 0),
            (0, 0),
            (0, 0),

            (pan_left_btn, 0, wx.EXPAND, 0),
            (tilt_down_btn, 0, wx.EXPAND, 0),
            (pan_right_btn, 0, wx.EXPAND, 0),
            (0, 0),
        ])

        jog_sizer.Add(xyzpt_grid, 0, wx.ALL|wx.EXPAND, 4)
        jog_sizer.AddSpacer(8)

        # ---

        step_feedrate_grid = wx.FlexGridSizer(3, 2, 4, 8)
        step_feedrate_grid.AddGrowableCol(0, 2)
        step_feedrate_grid.AddGrowableCol(1, 1)

        self.xyz_step_ctrl = FancyTextCtrl(
            jog_sizer.StaticBox, size=(48, -1), style=wx.TE_PROCESS_ENTER, name='xyz_step',
            max_precision=0, default_unit='mm', unit_conversions=utils.xyz_units)
        self.pt_step_ctrl = FancyTextCtrl(
            jog_sizer.StaticBox, size=(48, -1), style=wx.TE_PROCESS_ENTER, name='pt_step',
            max_precision=0, default_unit='dd', unit_conversions=utils.pt_units)
        self.feed_rate_ctrl = wx.TextCtrl(jog_sizer.StaticBox, value="1", size=(48, -1), style=wx.TE_PROCESS_ENTER, name='feed_rate')

        step_feedrate_grid.AddMany([
            (simple_statictext(jog_sizer.StaticBox, 'XYZ distance:', 72), 0, wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, 0),
            (self.xyz_step_ctrl, 0, wx.EXPAND, 0),

            (simple_statictext(jog_sizer.StaticBox, 'PT distance:', 72), 0, wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, 0),
            (self.pt_step_ctrl, 0, wx.EXPAND, 0),

            (simple_statictext(jog_sizer.StaticBox, 'Feed rate:', 72), 0, wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, 0),
            (self.feed_rate_ctrl, 0, wx.EXPAND, 0),
        ])

        jog_sizer.Add(step_feedrate_grid, 0, wx.ALL|wx.EXPAND, 4)

        self.Sizer.Add(jog_sizer, 0, wx.ALL|wx.EXPAND, 7)

    def update_machine_pos(self, pos: Point5) -> None:
        """Update machine position values given point."""
        self.x_m_text.ChangeValue(f'{pos.x:.3f}')
        self.y_m_text.ChangeValue(f'{pos.y:.3f}')
        self.z_m_text.ChangeValue(f'{pos.z:.3f}')
        self.p_m_text.ChangeValue(f'{pos.p:.3f}')
        self.t_m_text.ChangeValue(f'{pos.t:.3f}')
