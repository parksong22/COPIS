#!/usr/bin/env python3
"""Canvas3D class and associated classes."""

import math
import random
import numpy as np
import platform as pf

from threading import Lock

import wx
from wx import glcanvas
from OpenGL.GL import *
from OpenGL.GLU import *

from gl.glhelper import arcball, axis_angle_to_quat, quat_to_transformation_matrix, quat_product, draw_circle, draw_helix
from gl.path3d import Path3D
from gl.camera3d import Camera3D
from gl.bed3d import Bed3D
from gl.proxy3d import Proxy3D

from enums import ViewCubePos, ViewCubeSize
from utils import timing


class _Size():
    def __init__(self, width, height, scale_factor):
        self._width = width
        self._height = height
        self._scale_factor = scale_factor

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, width):
        self._width = width

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, height):
        self._height = height

    @property
    def scale_factor(self):
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, scale_factor):
        self._scale_factor = scale_factor


class Canvas3D(glcanvas.GLCanvas):
    """Canvas3D class."""
    # True: use arcball controls, False: use orbit controls
    orbit_controls = True
    color_background = (0.941, 0.941, 0.941, 1)
    zoom_min = 0.1
    zoom_max = 7.0

    def __init__(self, parent, build_dimensions=None, axes=True, bounding_box=True, every=100, subdivisions=10):
        self.parent = parent
        display_attrs = glcanvas.GLAttributes()
        display_attrs.MinRGBA(8, 8, 8, 8).DoubleBuffer().Depth(24).EndList()
        super().__init__(self.parent, display_attrs, id=wx.ID_ANY, pos=wx.DefaultPosition,
                         size=wx.DefaultSize, style=0, name='GLCanvas', palette=wx.NullPalette)
        self._canvas = self
        self._context = glcanvas.GLContext(self._canvas)

        self._gl_initialized = False
        self._dirty = False # dirty flag to track when we need to re-render the canvas
        self._scale_factor = None
        self._mouse_pos = None
        self._width = None
        self._height = None
        if build_dimensions:
            self._build_dimensions = build_dimensions
        else:
            self._build_dimensions = [400, 400, 400, 200, 200, 200]
        self._dist = 0.5 * (self._build_dimensions[1] + max(self._build_dimensions[0], self._build_dimensions[2]))

        self._bed3d = Bed3D(self._build_dimensions, axes, bounding_box, every, subdivisions)
        self._proxy3d = Proxy3D('Sphere', [1], (0, 53, 107))
        self._path3d = Path3D()
        self._camera3d_list = []
        self._path3d_list = []
        self._camera3d_scale = 10

        self._zoom = 1
        self._rot_quat = [0.0, 0.0, 0.0, 1.0]
        self._rot_lock = Lock()
        self._angle_z = 0
        self._angle_x = 0
        self._inside = False

        self._viewcube_pos = ViewCubePos.TOP_RIGHT
        self._viewcube_size = ViewCubeSize.MEDIUM

        # bind events
        self._canvas.Bind(wx.EVT_SIZE, self.on_size)
        self._canvas.Bind(wx.EVT_IDLE, self.on_idle)
        self._canvas.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self._canvas.Bind(wx.EVT_KEY_UP, self.on_key)
        self._canvas.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_wheel)
        self._canvas.Bind(wx.EVT_MOUSE_EVENTS, self.on_mouse)
        self._canvas.Bind(wx.EVT_LEFT_DCLICK, self.on_left_dclick)
        self._canvas.Bind(wx.EVT_ENTER_WINDOW, self.on_enter_window)
        self._canvas.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave_window)
        self._canvas.Bind(wx.EVT_ERASE_BACKGROUND, self.on_erase_background)
        self._canvas.Bind(wx.EVT_PAINT, self.on_paint)
        self._canvas.Bind(wx.EVT_SET_FOCUS, self.on_set_focus)

    def init_opengl(self):
        """Initialize OpenGL."""
        if self._gl_initialized:
            return True

        if self._context is None:
            return False

        glClearColor(*self.color_background)
        glClearDepth(1.0)

        glDepthFunc(GL_LESS)

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # set antialiasing
        glEnable(GL_LINE_SMOOTH)

        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_MULTISAMPLE)

        if not self._bed3d.init():
            return False

        self._gl_initialized = True
        return True

    # @timing
    def render(self):
        """Render frame."""
        # ensure that canvas is current and initialized
        if not self._is_shown_on_screen() or not self._set_current():
            return

        # ensure that opengl is initialized
        if not self.init_opengl():
            return

        canvas_size = self.get_canvas_size()
        glViewport(0, 0, canvas_size.width, canvas_size.height)
        self._width = max(10, canvas_size.width)
        self._height = max(10, canvas_size.height)

        self.apply_view_matrix()
        self.apply_projection()

        self._picking_pass()

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._render_background()
        self._render_objects()
        self._render_viewcube()

        self._canvas.SwapBuffers()

    # ---------------------
    # Canvas event handlers
    # ---------------------

    def on_size(self, event):
        """Handle EVT_SIZE."""
        self._dirty = True

    def on_idle(self, event):
        """Handle EVT_IDLE."""
        if not self._gl_initialized or self._canvas.IsFrozen():
            return

        self._dirty = self._dirty or any((i.dirty for i in self._camera3d_list))

        self._refresh_if_shown_on_screen()

        for camera in self._camera3d_list:
            camera.dirty = False
        self._dirty = False

    def on_key(self, event):
        """Handle EVT_KEY_DOWN and EVT_KEY_UP."""
        pass

    def on_mouse_wheel(self, event):
        """Handle mouse wheel event and adjust zoom."""
        if not self._gl_initialized or event.MiddleIsDown():
            return

        scale = self.get_scale_factor()
        event.SetX(int(event.GetX() * scale))
        event.SetY(int(event.GetY() * scale))

        self._update_camera_zoom(event.GetWheelRotation() / event.GetWheelDelta())

    def on_mouse(self, event):
        """Handle mouse events.
            LMB drag:   move viewport
            RMB drag:   unused
            LMB/RMB up: reset position
        """
        if not self._gl_initialized or not self._set_current():
            return

        scale = self.get_scale_factor()
        event.SetX(int(event.GetX() * scale))
        event.SetY(int(event.GetY() * scale))

        if event.Dragging():
            if event.LeftIsDown():
                self.rotate_camera(event, orbit=self.orbit_controls)
            elif event.RightIsDown() or event.MiddleIsDown():
                self.translate_camera(event)
        elif event.LeftUp() or event.MiddleUp() or event.RightUp() or event.Leaving():
            if self._mouse_pos is not None:
                self._mouse_pos = None
        elif event.Moving():
            pass
        else:
            event.Skip()
        self._dirty = True

    def on_left_dclick(self, event):
        """Handle EVT_LEFT_DCLICK."""
        # Detect click location
        scale = self.get_scale_factor()
        event.SetX(int(event.GetX() * scale))
        event.SetY(int(event.GetY() * scale))
        glFlush()

        # Read pixel color
        pixel = glReadPixels(event.GetX(), self._height - event.GetY(), 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
        camid = 125 - pixel[0]

        # If user double clicks something other than camera
        if camid > len(self._camera3d_list) or camid < 0:
            return 0

        wx.GetApp().mainframe.set_selected_camera(camid)

    def on_enter_window(self, event):
        self._inside = True

    def on_leave_window(self, event):
        self._inside = False

    def on_erase_background(self, event):
        """Handle the erase background event."""
        pass  # Do nothing, to avoid flashing on MSW.

    def on_paint(self, event):
        """Handle EVT_PAINT."""
        if self._gl_initialized:
            self._dirty = True
        else:
            self.render()

    def on_set_focus(self, event):
        """Handle EVT_SET_FOCUS."""
        self._refresh_if_shown_on_screen()

    def get_canvas_size(self):
        """Get canvas size based on scaling factor."""
        w, h = self._canvas.GetSize()
        factor = self.get_scale_factor()
        w = int(w * factor)
        h = int(h * factor)
        return _Size(w, h, factor)

    # ---------------------
    # Canvas util functions
    # ---------------------

    def destroy(self):
        """Clean up the OpenGL context."""
        self._context.destroy()
        glcanvas.GLCanvas.Destroy()

    @property
    def dirty(self):
        return self._dirty

    @dirty.setter
    def dirty(self, value):
        self._dirty = value

    def _is_shown_on_screen(self):
        return self._canvas.IsShownOnScreen()

    def _set_current(self):
        return False if self._context is None else self._canvas.SetCurrent(self._context)

    def _update_camera_zoom(self, delta_zoom):
        zoom = self._zoom / (1.0 - max(min(delta_zoom, 4.0), -4.0) * 0.1)
        self._zoom = max(min(zoom, self.zoom_max), self.zoom_min)
        self._dirty = True
        self._update_parent_zoom_slider()

    def _refresh_if_shown_on_screen(self):
        if self._is_shown_on_screen():
            self._set_current()
            self.render()

    def _picking_pass(self):
        glDisable(GL_MULTISAMPLE)

        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        self._render_volumes_for_picking()
        # self._render_xxxx_for_picking()

        glEnable(GL_MULTISAMPLE)

        cnv_size = self.get_canvas_size()
        print(self._mouse_pos)
        # if self._inside:
        #     color = glReadPixels(self._mouse_pos, cnv_size.height - event.GetY() - 1, 1, 1, GL_RGB, GL_UNSIGNED_BYTE)
        return

    def _render_background(self):
        glClearColor(*self.color_background)

    def _render_objects(self):
        if self._bed3d is not None:
            self._bed3d.render()

        if self._proxy3d is not None:
            self._proxy3d.render()

        if not self._camera3d_list:
            return
        for cam in self._camera3d_list:
            cam.render()

        if not self._path3d_list:
            return

    def _render_viewcube(self):
        if self._viewcube_pos is None or self._viewcube_size is None:
            return

        # restrict viewport to left/right corner
        glViewport(*self._get_viewcube_viewport())

        vertices = np.array([
            1.0, 1.0, 1.0,
            1.0, -1.0, 1.0,
            1.0, -1.0, -1.0,
            1.0, 1.0, -1.0,
            -1.0, 1.0, -1.0,
            -1.0, 1.0, 1.0,
            -1.0, -1.0, 1.0,
            -1.0, -1.0, -1.0])
        indices = np.array([
            0, 1, 2, 2, 3, 0,
            0, 3, 4, 4, 5, 0,
            0, 5, 6, 6, 1, 0,
            1, 6, 7, 7, 2, 1,
            7, 4, 3, 3, 2, 7,
            4, 7, 6, 6, 5, 4])

        # store current projection matrix, load orthographic projection
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(-2.0, 2.0, -2.0, 2.0, -2.0, 2.0)

        # store current modelview and load identity transform
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glMultMatrixd(quat_to_transformation_matrix(self._rot_quat))

        # disable depth testing so the quad is always on top
        glDisable(GL_DEPTH_TEST)

        # draw cube
        glColor4f(0.7, 0.7, 0.7, 0.9)
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, vertices)
        glDrawElements(GL_TRIANGLES, 36, GL_UNSIGNED_BYTE, indices)
        glDisableClientState(GL_VERTEX_ARRAY)

        # re-enable depth testing
        glEnable(GL_DEPTH_TEST)

        # restore modelview and projection to previous state
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def _render_volumes_for_picking(self):
        glDisable(GL_CULL_FACE)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)

        view_matrix = self.get_modelview_matrix()

        # render everything where color is related to id

        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        glEnable(GL_CULL_FACE)

    def _get_viewcube_viewport(self):
        width, height = self._width, self._height
        size = self._viewcube_size
        if self._viewcube_pos == ViewCubePos.TOP_LEFT:
            corner = (0, height - size)
        elif self._viewcube_pos == ViewCubePos.TOP_RIGHT:
            corner = (width - size, height - size)
        elif self._viewcube_pos == ViewCubePos.BOTTOM_LEFT:
            corner = (0, 0)
        elif self._viewcube_pos == ViewCubePos.BOTTOM_LEFT:
            corner = (width - size, 0)
        return (*corner, size, size)

    # ------------------
    # Accessor functions
    # ------------------

    def _update_parent_zoom_slider(self):
        self.parent.set_zoom_slider(self._zoom)

    @property
    def viewcube_pos(self):
        return self._viewcube_pos

    @viewcube_pos.setter
    def viewcube_pos(self, value):
        if value not in ViewCubePos:
            return
        self._viewcube_pos = value

    @property
    def viewcube_size(self):
        return self._viewcube_size

    @viewcube_pos.setter
    def viewcube_size(self, value):
        if value not in ViewCubeSize:
            return
        self._viewcube_size = value

    @property
    def bed3d(self):
        return self._bed3d

    @property
    def proxy3d(self):
        return self._proxy3d

    @property
    def zoom(self):
        return self._zoom

    @zoom.setter
    def zoom(self, value):
        self._zoom = value
        self._dirty = True

    @property
    def build_dimensions(self):
        return self._build_dimensions

    @build_dimensions.setter
    def build_dimensions(self, value):
        self._build_dimensions = value
        self._bed3d.build_dimensions = value
        self._dirty = True

    @property
    def camera3d_scale(self):
        return self._camera3d_scale

    @camera3d_scale.setter
    def camera3d_scale(self, value):
        for camera in self._camera3d_list:
            camera.scale = value
            camera.dirty = True

    @property
    def camera3d_list(self):
        return self._camera3d_list

    @camera3d_list.setter
    def camera3d_list(self, value):
        self._camera3d_list = value
        self._dirty = True

    # -----------------------
    # Canvas camera functions
    # -----------------------

    def apply_view_matrix(self):
        """Apply modelview matrix according to rotation quat."""
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(
            0.0, 0.0, self._dist * 1.5, # eyeX, eyeY, eyeZ
            0.0, 0.0, 0.0,              # centerX, centerY, centerZ
            0.0, 1.0, 0.0)              # upX, upY, upZ
        glMultMatrixd(quat_to_transformation_matrix(self._rot_quat))

    def apply_projection(self):
        """Set camera projection. Also updates zoom."""
        # TODO: add toggle between perspective and orthographic view modes
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(
            np.arctan(np.tan(np.deg2rad(45.0)) / self._zoom) * 180 / math.pi,
            float(self._width) / self._height,
            0.1,
            2000.0)
        glMatrixMode(GL_MODELVIEW)

    def get_modelview_matrix(self):
        """Return GL_MODELVIEW_MATRIX."""
        mat = (GLdouble * 16)()
        glGetDoublev(GL_MODELVIEW_MATRIX, mat)
        return mat

    def get_projection_matrix(self):
        """Return GL_PROJECTION_MATRIX."""
        mat = (GLdouble * 16)()
        glGetDoublev(GL_PROJECTION_MATRIX, mat)
        return mat

    def get_viewport(self):
        """Return GL_VIEWPORT."""
        vec = (GLint * 4)()
        glGetIntegerv(GL_VIEWPORT, vec)
        return vec

    def rotate_camera(self, event, orbit=True):
        """Update _rot_quat based on mouse position.
            orbit = True:   Use orbit method to rotate.
            orbit = False:  Use arcball method to rotate.
        """
        if self._mouse_pos is None:
            self._mouse_pos = event.GetPosition()
            return
        last = self._mouse_pos
        cur = event.GetPosition()

        p1x = last.x * 2.0 / self._width - 1.0
        p1y = 1 - last.y * 2.0 / self._height
        p2x = cur.x * 2.0 / self._width - 1.0
        p2y = 1 - cur.y * 2.0 / self._height

        if p1x == p2x and p1y == p2y:
            self._rot_quat = [0.0, 0.0, 0.0, 1.0]

        with self._rot_lock:
            if orbit:
                delta_x = p2y - p1y
                self._angle_x += delta_x
                rot_x = axis_angle_to_quat([1.0, 0.0, 0.0], self._angle_x)

                delta_z = p2x - p1x
                self._angle_z -= delta_z
                rot_z = axis_angle_to_quat([0.0, 1.0, 0.0], self._angle_z)

                self._rot_quat = quat_product(rot_z, rot_x)
            else:
                quat = arcball(p1x, p1y, p2x, p2y, self._dist / 250.0)
                self._rot_quat = quat_product(self._rot_quat, quat)
        self._mouse_pos = cur

    def translate_camera(self, event):
        if self._mouse_pos is None:
            self._mouse_pos = event.GetPosition()
            return
        last = self._mouse_pos
        cur = event.GetPosition()
        # Do stuff
        self._mouse_pos = cur

    # -------------------
    # Misc util functions
    # -------------------

    def get_scale_factor(self):
        if self._scale_factor is None:
            if pf.system() == 'Darwin': # MacOS
                self._scale_factor = 2.0
            else:
                self._scale_factor = 1.0
        return self._scale_factor
