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

"""MainWindow class."""

import wx
import wx.lib.agw.aui as aui

from pydispatch import dispatcher
from glm import vec3

import copis.store as store

from copis.globals import WindowState
from copis.classes import AABBObject3D, CylinderObject3D, Action, Pose
from .about import AboutDialog
from .panels.console import ConsolePanel
from .panels.controller import ControllerPanel
from .panels.evf import EvfPanel
from .panels.machine_toolbar import MachineToolbar
from .panels.pathgen_toolbar import PathgenToolbar
from .panels.properties import PropertiesPanel
from .panels.timeline import TimelinePanel
from .panels.viewport import ViewportPanel
from .pref_frame import PreferenceFrame
from .proxy_dialogs import ProxygenCylinder, ProxygenAABB
from .wxutils import create_scaled_bitmap
from .custom_tab_art import CustomAuiTabArt


class MainWindow(wx.Frame):
    """Main window.

    Manages menubar, statusbar, and aui manager.

    Attributes:
        console_panel: A pointer to the console panel.
        controller_panel: A pointer to the controller panel.
        evf_panel: A pointer to the electronic viewfinder panel.
        properties_panel: A pointer to the properties panel.
        timeline_panel: A pointer to the timeline management panel.
        viewport_panel: A pointer to the viewport panel.
        machine_toolbar: A pointer to the machine toolbar.
        pathgen_toolbar: A pointer to the pathgen toolbar.
    """

    _FILE_DIALOG_WILDCARD = 'COPIS Files (*.copis)|*.copis|All Files (*.*)|*.*'
    _COPIS_WEBSITE = 'http://www.copis3d.org/'

    def __init__(self, chamber_dimensions, *args, **kwargs) -> None:
        """Initializes MainWindow with constructors."""
        super().__init__(*args, **kwargs)
        self.core = wx.GetApp().core
        # set minimum size to show whole interface properly
        # pylint: disable=invalid-name
        min_size = self.core.config.application_settings.window_min_size
        self.MinSize = wx.Size(min_size.width, min_size.height)

        self.chamber_dimensions = chamber_dimensions

        # project saving
        self.project_dirty = False

        self.file_menu = None
        self._menubar = None
        self._mgr = None

        # dictionary of panels and menu items
        self.panels = {}
        self.menuitems = {}

        # initialize gui
        self.init_mgr()
        self.init_statusbar()
        self.init_menubar()

        # TODO: re-enable liveview
        # self.add_evf_pane()

        self._mgr.Bind(aui.EVT_AUI_PANE_CLOSE, self.on_pane_close)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.numpoints = None

        # Bind listeners.
        dispatcher.connect(self._handle_project_dirty_changed,
            signal='ntf_project_dirty_changed')

    # --------------------------------------------------------------------------
    # Accessor methods
    # --------------------------------------------------------------------------

    @property
    def console_panel(self) -> ConsolePanel:
        """Returns the console panel."""
        return self.panels['console']

    @property
    def controller_panel(self) -> ControllerPanel:
        """Returns the controller panel."""
        return self.panels['controller']

    @property
    def evf_panel(self) -> EvfPanel:
        """Returns the EVF panel."""
        return self.panels['evf']

    @property
    def properties_panel(self) -> PropertiesPanel:
        """Returns the properties panel."""
        return self.panels['properties']

    @property
    def timeline_panel(self) -> TimelinePanel:
        """Returns the timeline panel."""
        return self.panels['timeline']

    @property
    def viewport_panel(self) -> ViewportPanel:
        """Returns the viewport panel."""
        return self.panels['viewport']

    @property
    def machine_toolbar(self) -> MachineToolbar:
        """Returns the machine toolbar."""
        return self.panels['machine_toolbar']

    @property
    def pathgen_toolbar(self) -> PathgenToolbar:
        """Returns the path generation toolbar."""
        return self.panels['pathgen_toolbar']

    def _handle_project_dirty_changed(self, is_project_dirty: bool) -> None:
        self.file_menu.Enable(wx.ID_NEW, is_project_dirty)

    def init_statusbar(self) -> None:
        """Initialize statusbar."""
        if self.StatusBar is not None:
            return

        self.CreateStatusBar(1)
        self.SetStatusText('Ready')

    # --------------------------------------------------------------------------
    # Menubar related methods
    # --------------------------------------------------------------------------

    def init_menubar(self) -> None:
        """Initialize menubar.

        Menu tree:
            - &File
                - &New Project              Ctrl+N
                - &Open Project...          Ctrl+O
                - &Recent Projects           >
                - &Save Project             Ctrl+S
                - Save Project &As...       Ctrl+Shift+S
                ---
                - E&xit                     Alt+F4
            - &Edit
                - &Keyboard Shortcuts...
                ---
                - &Preferences
            - &View
                - [x] &Status Bar
            - &Camera
                - (*) &Perspective Projection
                - ( ) &Orthographic Projection
            - &Tools
                - Add &Cylinder Proxy Object
                - Add &Box Proxy Object
            - &Window
                - [ ] Camera EVF
                - [x] Console
                - [x] Controller
                - [x] Properties
                - [x] Timeline
                - [x] Viewport
                ---
                - Window &Preferences...
            - Help
                - COPIS &Help...            F1
                ---
                - &Visit COPIS website      Ctrl+F1
                - &About COPIS...
        """
        if self._menubar is not None:
            return

        self._menubar = wx.MenuBar(0)

        # File menu.
        self.file_menu = wx.Menu()

        recent_menu = wx.Menu()

        _item = wx.MenuItem(None, wx.ID_NEW, '&New Project\tCtrl+N', 'Create new project')
        _item.Bitmap = create_scaled_bitmap('add_project', 16)
        self.Bind(wx.EVT_MENU, self.on_new_project, self.file_menu.Append(_item))

        _item = wx.MenuItem(None, wx.ID_OPEN, '&Open Project...\tCtrl+O', 'Open existing project')
        _item.Bitmap = create_scaled_bitmap('open_project', 16)
        self.Bind(wx.EVT_MENU, self.on_open_project, self.file_menu.Append(_item))

        _item = wx.MenuItem(None, wx.ID_JUMP_TO, '&Recent Projects', 'Open one of recent projects',
            subMenu=recent_menu)
        self.file_menu.Append(_item)

        _item = wx.MenuItem(None, wx.ID_SAVE, '&Save Project\tCtrl+S', 'Save project')
        _item.Bitmap = create_scaled_bitmap('save', 16)
        self.Bind(wx.EVT_MENU, self.on_save, self.file_menu.Append(_item))

        _item = wx.MenuItem(None, wx.ID_SAVEAS, 'Save Project &As...\tCtrl+Shift+S',
            'Save project as')
        _item.Bitmap = create_scaled_bitmap('save', 16)
        self.Bind(wx.EVT_MENU, self.on_save_as, self.file_menu.Append(_item))

        self.file_menu.Enable(wx.ID_NEW, False)
        self.file_menu.Enable(wx.ID_JUMP_TO, False)
        self.file_menu.Enable(wx.ID_SAVE, False)

        self.file_menu.AppendSeparator()

        _item = wx.MenuItem(None, wx.ID_ANY, 'E&xit\tAlt+F4', 'Close the program')
        _item.Bitmap = create_scaled_bitmap('exit_to_app', 16)
        self.Bind(wx.EVT_MENU, self.on_exit, self.file_menu.Append(_item))

        # Edit menu.
        edit_menu = wx.Menu()
        _item = wx.MenuItem(None, wx.ID_ANY, '&Keyboard Shortcuts...', 'Open keyboard shortcuts')
        self.Bind(wx.EVT_MENU, None, edit_menu.Append(_item))
        edit_menu.AppendSeparator()

        _item = wx.MenuItem(None, wx.ID_ANY, '&Preferences', 'Open preferences')
        _item.Bitmap = create_scaled_bitmap('tune', 16)
        self.Bind(wx.EVT_MENU, self.open_preferences_frame, edit_menu.Append(_item))

        # View menu.
        view_menu = wx.Menu()
        self.statusbar_menuitem = view_menu.Append(wx.ID_ANY, '&Status &Bar',
            'Toggle status bar visibility', wx.ITEM_CHECK)
        view_menu.Check(self.statusbar_menuitem.Id, True)
        self.Bind(wx.EVT_MENU, self.update_statusbar, self.statusbar_menuitem)

        # Camera menu.
        camera_menu = wx.Menu()
        _item = wx.MenuItem(None, wx.ID_ANY, '&Perspective Projection',
            'Set viewport projection to perspective', wx.ITEM_RADIO)
        self.Bind(wx.EVT_MENU, self.panels['viewport'].set_perspective_projection,
            camera_menu.Append(_item))
        _item = wx.MenuItem(None, wx.ID_ANY, '&Orthographic Projection',
            'Set viewport projection to orthographic', wx.ITEM_RADIO)
        self.Bind(wx.EVT_MENU, self.panels['viewport'].set_orthographic_projection,
            camera_menu.Append(_item))

        # Tools menu.
        tools_menu = wx.Menu()
        _item = wx.MenuItem(None, wx.ID_ANY, 'Add &Cylinder Proxy Object',
            'Add a cylinder proxy object to the chamber')
        self.Bind(wx.EVT_MENU, self.add_proxy_cylinder, tools_menu.Append(_item))
        _item = wx.MenuItem(None, wx.ID_ANY, 'Add &Box Proxy Object',
            'Add a box proxy object to the chamber')
        self.Bind(wx.EVT_MENU, self.add_proxy_aabb, tools_menu.Append(_item))

        # Window menu.
        window_menu = wx.Menu()
        self.menuitems['evf'] = window_menu.Append(wx.ID_ANY, 'Camera EVF',
            'Show/hide camera EVF window', wx.ITEM_CHECK)
        self.menuitems['evf'].Enable(False)
        self.Bind(wx.EVT_MENU, self.update_evf_panel, self.menuitems['evf'])
        self.menuitems['console'] = window_menu.Append(wx.ID_ANY, 'Console',
            'Show/hide console window', wx.ITEM_CHECK)
        self.menuitems['console'].Check(True)
        self.Bind(wx.EVT_MENU, self.update_console_panel, self.menuitems['console'])
        self.menuitems['controller'] = window_menu.Append(wx.ID_ANY, 'Controller',
            'Show/hide controller window', wx.ITEM_CHECK)
        self.menuitems['controller'].Check(True)
        self.Bind(wx.EVT_MENU, self.update_controller_panel, self.menuitems['controller'])
        self.menuitems['properties'] = window_menu.Append(wx.ID_ANY, 'Properties',
            'Show/hide camera properties window', wx.ITEM_CHECK)
        self.menuitems['properties'].Check(True)
        self.Bind(wx.EVT_MENU, self.update_properties_panel, self.menuitems['properties'])
        self.menuitems['timeline'] = window_menu.Append(wx.ID_ANY, 'Timeline',
            'Show/hide timeline window', wx.ITEM_CHECK)
        self.menuitems['timeline'].Check(True)
        self.Bind(wx.EVT_MENU, self.update_timeline_panel, self.menuitems['timeline'])
        self.menuitems['viewport'] = window_menu.Append(wx.ID_ANY,'Viewport',
            'Show/hide viewport window', wx.ITEM_CHECK)
        self.menuitems['viewport'].Check(True)
        self.Bind(wx.EVT_MENU, self.update_viewport_panel, self.menuitems['viewport'])
        window_menu.AppendSeparator()

        _item = wx.MenuItem(None, wx.ID_ANY, 'Window &Preferences...', 'Open window preferences')
        _item.Bitmap = create_scaled_bitmap('tune', 16)
        self.Bind(wx.EVT_MENU, None, window_menu.Append(_item))

        # Help menu.
        help_menu = wx.Menu()
        _item = wx.MenuItem(None, wx.ID_ANY, 'COPIS &Help...\tF1', 'Open COPIS help menu')
        _item.Bitmap = create_scaled_bitmap('help_outline', 16)
        self.Bind(wx.EVT_MENU, None, help_menu.Append(_item))
        help_menu.AppendSeparator()

        _item = wx.MenuItem(None, wx.ID_ANY, '&Visit COPIS website\tCtrl+F1',
            f'Open {self._COPIS_WEBSITE}')
        _item.Bitmap = create_scaled_bitmap('open_in_new', 16)
        self.Bind(wx.EVT_MENU, self.open_copis_website, help_menu.Append(_item))
        _item = wx.MenuItem(None, wx.ID_ANY, '&About COPIS...', 'Show about dialog')
        _item.Bitmap = create_scaled_bitmap('info', 16)
        self.Bind(wx.EVT_MENU, self.open_about_dialog, help_menu.Append(_item))

        self._menubar.Append(self.file_menu, '&File')
        self._menubar.Append(edit_menu, '&Edit')
        self._menubar.Append(view_menu, '&View')
        self._menubar.Append(camera_menu, '&Camera')
        self._menubar.Append(tools_menu, '&Tools')
        self._menubar.Append(window_menu, '&Window')
        self._menubar.Append(help_menu, '&Help')
        self.SetMenuBar(self._menubar)

    def on_new_project(self, _) -> None:
        """TODO: Implement project file/directory creation """
        pass

    def on_open_project(self, _) -> None:
        """Opens 'open' dialog.

        TODO: Implement reading file/directory
        """
        if self.project_dirty:
            if wx.MessageBox('Current project has not been saved. Proceed?', 'Please confirm',
                             wx.ICON_QUESTION | wx.YES_NO, self) == wx.NO:
                return

        with wx.FileDialog(self, 'Open Project File', wildcard=self._FILE_DIALOG_WILDCARD,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as file_dialog:

            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return     # the user changed their mind

            # Proceed loading the file chosen by the user
            path = file_dialog.Path
            try:
                self.do_load_project(path)
            except Exception as err:
                wx.LogError(str(err))

    def on_save(self, _) -> None:
        """Opens 'save' dialog.

        TODO: Implement saving with projects
        """

    def on_save_as(self, _) -> None:
        """Opens 'save as' dialog.

         TODO: Implement saving as with projects
        """
        with wx.FileDialog(
            self, 'Save Project As', wildcard = self._FILE_DIALOG_WILDCARD,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as file_dialog:

            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return

            # save the current contents in the file
            path = file_dialog.Path
            try:
                with open(path, 'x'):
                    self.do_save_project(path)
            except IOError:
                wx.LogError(f'Could not save in file "{path}".')

    def on_export(self, _) -> None:
        """Exports action list as series of G-code commands."""
        self.core.export_poses("./test.copis")

    def do_save_project(self, path) -> None:
        """Saves project to file Path."""
        self.project_dirty = False
        store.save(path, self.core.project.poses)

    def do_load_project(self, path: str) -> None:
        """Loads project from file Path."""
        poses = store.load(path, [])

        # Adjust actions from list of actions to a list of poses.
        if isinstance(poses[0], Action):
            real_poses = []
            for i in range(0, len(poses), 2):
                chunk = poses[i:i + 2]
                real_poses.append(Pose(chunk[0], [chunk[1]]))

            poses = real_poses

        self.core.project.poses.clear(False)
        self.core.project.poses.extend(poses)

    def update_statusbar(self, event: wx.CommandEvent) -> None:
        """Updates status bar visibility based on menu item."""
        self.StatusBar.Show(event.IsChecked())
        self._mgr.Update()

    def add_proxy_cylinder(self, _) -> None:
        """Opens dialog to generate cylinder proxy object."""
        with ProxygenCylinder(self) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                start = vec3(dlg.start_x_ctrl.num_value,
                             dlg.start_y_ctrl.num_value,
                             dlg.start_z_ctrl.num_value)
                end = vec3(dlg.end_x_ctrl.num_value,
                           dlg.end_y_ctrl.num_value,
                           dlg.end_z_ctrl.num_value)
                radius = dlg.radius_ctrl.num_value
                self.core.project.proxies.append(CylinderObject3D(start, end, radius))

    def add_proxy_aabb(self, _) -> None:
        """Opens dialog to generate box proxy object."""
        with ProxygenAABB(self) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                lower = vec3(dlg.lower_x_ctrl.num_value,
                             dlg.lower_y_ctrl.num_value,
                             dlg.lower_z_ctrl.num_value)
                upper = vec3(dlg.upper_x_ctrl.num_value,
                             dlg.upper_y_ctrl.num_value,
                             dlg.upper_z_ctrl.num_value)
                self.core.project.proxies.append(AABBObject3D(lower, upper))

    def open_preferences_frame(self, _) -> None:
        """Opens the preferences frame."""
        preferences_dialog = PreferenceFrame(self)
        preferences_dialog.Show()

    def open_copis_website(self, _) -> None:
        """Launches the COPIS project's website."""
        wx.LaunchDefaultBrowser(self._COPIS_WEBSITE)

    def open_about_dialog(self, _) -> None:
        """Opens the 'about' dialog."""
        about = AboutDialog(self)
        about.Show()

    def on_exit(self, _) -> None:
        """On menu close, exit application."""
        self.Close()

    # --------------------------------------------------------------------------
    # AUI related methods
    # --------------------------------------------------------------------------

    def init_mgr(self) -> None:
        """Initialize AuiManager and attach panes.

        NOTE: We are NOT USING wx.aui, but wx.lib.agw.aui, a pure Python
        implementation of wx.aui. As such, the correct documentation on
        wxpython.org should begin with
        https://wxpython.org/Phoenix/docs/html/wx.lib.agw.aui rather than
        https://wxpython.org/Phoenix/docs/html/wx.aui.
        """
        if self._mgr is not None:
            return

        # Create AUI manager and set flags.
        self._mgr = aui.AuiManager(self, agwFlags=
            aui.AUI_MGR_ALLOW_FLOATING |
            aui.AUI_MGR_TRANSPARENT_DRAG |
            aui.AUI_MGR_TRANSPARENT_HINT |
            aui.AUI_MGR_HINT_FADE |
            aui.AUI_MGR_LIVE_RESIZE |
            aui.AUI_MGR_AUTONB_NO_CAPTION)

        # Set auto notebook style.
        self._mgr.SetAutoNotebookStyle(
            aui.AUI_NB_TOP |
            aui.AUI_NB_TAB_SPLIT |
            aui.AUI_NB_TAB_MOVE |
            aui.AUI_NB_SCROLL_BUTTONS |
            aui.AUI_NB_WINDOWLIST_BUTTON |
            aui.AUI_NB_MIDDLE_CLICK_CLOSE |
            aui.AUI_NB_CLOSE_ON_ACTIVE_TAB |
            aui.AUI_NB_TAB_FLOAT)

        # Set AUI colors and style.
        # See https://wxpython.org/Phoenix/docs/html/wx.lib.agw.aui.dockart.AuiDefaultDockArt.html
        dockart = aui.AuiDefaultDockArt()
        dockart.SetMetric(aui.AUI_DOCKART_SASH_SIZE, 3)
        dockart.SetMetric(aui.AUI_DOCKART_CAPTION_SIZE, 18)
        dockart.SetMetric(aui.AUI_DOCKART_PANE_BUTTON_SIZE, 16)
        dockart.SetColor(aui.AUI_DOCKART_BACKGROUND_COLOUR,
            wx.SystemSettings().GetColour(wx.SYS_COLOUR_MENU))
        dockart.SetColor(aui.AUI_DOCKART_BACKGROUND_GRADIENT_COLOUR,
            wx.SystemSettings().GetColour(wx.SYS_COLOUR_MENU))
        dockart.SetColor(aui.AUI_DOCKART_SASH_COLOUR,
            wx.SystemSettings().GetColour(wx.SYS_COLOUR_MENU))
        dockart.SetColor(aui.AUI_DOCKART_ACTIVE_CAPTION_COLOUR, '#FFFFFF')
        dockart.SetColor(aui.AUI_DOCKART_INACTIVE_CAPTION_COLOUR, '#FFFFFF')
        dockart.SetMetric(aui.AUI_DOCKART_GRADIENT_TYPE, aui.AUI_GRADIENT_NONE)
        self._mgr.SetArtProvider(dockart)

        tabart = CustomAuiTabArt()
        self._mgr.SetAutoNotebookTabArt(tabart)

        # Initialize relevant panels.
        self.panels['viewport'] = ViewportPanel(self)
        self.panels['console'] = ConsolePanel(self)
        self.panels['timeline'] = TimelinePanel(self)
        self.panels['controller'] = ControllerPanel(self)
        self.panels['properties'] = PropertiesPanel(self)
        self.panels['machine_toolbar'] = MachineToolbar(self)
        self.panels['pathgen_toolbar'] = PathgenToolbar(self)

        # Add viewport panel.
        self._mgr.AddPane(
            self.panels['viewport'],
            aui.AuiPaneInfo().Name('viewport').Caption('Viewport').
            Dock().Center().MaximizeButton().MinimizeButton().DefaultPane().MinSize(350, 250))

        # Add console, timeline panel.
        self._mgr.AddPane(
            self.panels['console'],
            aui.AuiPaneInfo().Name('console').Caption('Console').
            Dock().Bottom().Position(0).Layer(0).MinSize(280, 180).Show(True))
        self._mgr.AddPane(
            self.panels['timeline'],
            aui.AuiPaneInfo().Name('timeline').Caption('Timeline').
            Dock().Bottom().Position(1).Layer(0).MinSize(280, 180).Show(True),
            target=self._mgr.GetPane('console'))

        # Add properties and controller panel.
        self._mgr.AddPane(
            self.panels['properties'],
            aui.AuiPaneInfo().Name('properties').Caption('Properties').
            Dock().Right().Position(0).Layer(1).MinSize(280, 200).Show(True))
        self._mgr.AddPane(
            self.panels['controller'],
            aui.AuiPaneInfo().Name('controller').Caption('Controller').
            Dock().Right().Position(1).Layer(1).MinSize(280, 200).Show(True))

        # Set first tab of all auto notebooks as the one selected.
        for notebook in self._mgr.GetNotebooks():
            notebook.SetSelection(0)

        # Add toolbar panels.
        self.panels['machine_toolbar'].Realize()
        self._mgr.AddPane(
            self.panels['machine_toolbar'],
            aui.AuiPaneInfo().Name('machine_toolbar').Caption('Machine Toolbar').
            ToolbarPane().BottomDockable(False).Top().Layer(10))
        self.panels['pathgen_toolbar'].Realize()
        self._mgr.AddPane(
            self.panels['pathgen_toolbar'],
            aui.AuiPaneInfo().Name('pathgen_toolbar').Caption('Pathgen Toolbar').
            ToolbarPane().BottomDockable(False).Top().Layer(10))

        self._mgr.Update()

    def add_evf_pane(self) -> None:
        """Initialize camera liveview panel.

        TODO!
        """
        if self.core.edsdk.camera_count == 0:
            return

        self.panels['evf'] = EvfPanel(self)
        self._mgr.AddPane(
            self.panels['evf'],
            aui.AuiPaneInfo().Name('Evf').Caption('Live View').
            Float().Right().Position(1).Layer(0).MinSize(600, 420).
            MinimizeButton(True).DestroyOnClose(True).MaximizeButton(True))
        self.Update()

    def update_console_panel(self, event: wx.CommandEvent) -> None:
        """Show or hide console panel."""
        self._mgr.ShowPane(self.console_panel, event.IsChecked())

    def update_controller_panel(self, event: wx.CommandEvent) -> None:
        """Show or hide controller panel."""
        self._mgr.ShowPane(self.controller_panel, event.IsChecked())

    def update_evf_panel(self, event: wx.CommandEvent) -> None:
        """Show or hide evf panel."""
        self._mgr.ShowPane(self.evf_panel, event.IsChecked())

    def update_properties_panel(self, event: wx.CommandEvent) -> None:
        """Show or hide properties panel."""
        self._mgr.ShowPane(self.properties_panel, event.IsChecked())

    def update_timeline_panel(self, event: wx.CommandEvent) -> None:
        """Show or hide timeline panel."""
        self._mgr.ShowPane(self.timeline_panel, event.IsChecked())

    def update_viewport_panel(self, event: wx.CommandEvent) -> None:
        """Show or hide viewport panel."""
        self._mgr.ShowPane(self.viewport_panel, event.IsChecked())

    def on_pane_close(self, event: aui.framemanager.AuiManagerEvent) -> None:
        """Update menu items in the Window menu when a pane has been closed."""
        pane = event.GetPane()

        # if closed pane is a notebook, process and hide all pages in the notebook.
        if pane.IsNotebookControl():
            notebook = pane.window
            for i in range(notebook.GetPageCount()):
                nb_pane = self._mgr.GetPane(notebook.GetPage(i))
                self._mgr.ShowPane(self.panels[nb_pane.name], False)
                self.menuitems[nb_pane.name].Check(False)
        else:
            self._mgr.ShowPane(self.panels[pane.name], False)
            self.menuitems[pane.name].Check(False)

        # if pane.name == 'Evf':
        #     pane.window.timer.Stop()
        #     pane.window.on_destroy()
        #     self.DetachPane(pane.window)
        #     pane.window.Destroy()

        print('hidden', pane.name)

    def on_close(self, event: wx.CloseEvent) -> None:
        """On EVT_CLOSE, exit application."""
        event.StopPropagation()

        pos = self.GetPosition()
        size = self.GetSize()
        self.core.config.update_window_state(
            WindowState(pos.x, pos.y, size.x, size.y, self.IsMaximized()))

        if self.project_dirty:
            if wx.MessageBox('Current project has not been saved. Proceed?', 'Please confirm',
                             wx.ICON_QUESTION | wx.YES_NO, self) == wx.NO:
                return

        self._mgr.UnInit()
        self.Destroy()

    def __del__(self) -> None:
        pass
