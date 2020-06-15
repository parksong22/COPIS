#!/usr/bin/env python3
"""TODO: Fill in docstring"""

import numpy as np

import wx
from wx import glcanvas

from OpenGL.GL import *
from OpenGL.GLU import *
# from .trackball import trackball, mulquat, axis_to_quat


class CanvasBase(glcanvas.GLCanvas):
    MIN_ZOOM = 0.5
    MAX_ZOOM = 5.0
    NEAR_CLIP = 3.0
    FAR_CLIP = 7.0
    ASPECT_CONSTRAINT = 1.9
    orbit_control = True
    color_background = (0.941, 0.941, 0.941, 1)

    def __init__(self, parent, *args, **kwargs):
        super(CanvasBase, self).__init__(parent, -1)
        self.GLinitialized = False
        self.context = glcanvas.GLContext(self)

        self.width = None
        self.height = None

        # initial mouse position
        self.lastx = self.x = 30
        self.lastz = self.z = 30
        
        self.viewpoint = (0.0, 0.0, 0.0)
        self.basequat = [0, 0, 0, 1]
        self.angle_z = 0
        self.angle_x = 0
        self.zoom = 1

        self.gl_broken = False

        # bind events
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.processEraseBackgroundEvent)
        self.Bind(wx.EVT_SIZE, self.processSizeEvent)
        self.Bind(wx.EVT_PAINT, self.processPaintEvent)

    def processEraseBackgroundEvent(self, event):
        pass  # Do nothing, to avoid flashing on MSW.

    def processSizeEvent(self, event):
        if self.IsFrozen():
            event.Skip()
            return
        if self.IsShownOnScreen():
            self.SetCurrent(self.context)
            self.OnReshape()
            self.Refresh(False)
            timer = wx.CallLater(100, self.Refresh)
            timer.Start()
        event.Skip()

    def processPaintEvent(self, event):
        self.SetCurrent(self.context)

        if not self.gl_broken:
            try:
                self.OnInitGL()
                self.OnDraw()
            except Exception as e: # TODO: add specific glcanvas exception
                self.gl_broken = True
                print('OpenGL Failed:')
                print(e)
                # TODO: display this error in the console window
        event.Skip()

    def Destroy(self):
        self.context.destroy()
        glcanvas.GLCanvas.Destroy()

    def OnInitGL(self):
        if self.GLinitialized:
            return
        self.GLinitialized = True
        self.SetCurrent(self.context)
        glClearColor(*self.color_background)
        glClearDepth(1.0)

    def OnReshape(self):
        size = self.GetClientSize()
        width, height = size.width, size.height

        self.width = max(float(width), 1.0)
        self.height = max(float(height), 1.0)

        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(np.arctan(np.tan(50.0 * 3.14159 / 360.0) / self.zoom) * 360.0 / 3.14159, float(width) / height, self.NEAR_CLIP, self.FAR_CLIP)
        glMatrixMode(GL_MODELVIEW)

    def OnDraw(self):
        self.SetCurrent(self.context)
        glClearColor(*self.color_background)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.draw_objects()
        self.SwapBuffers()

    # To be implemented by a sub-class

    def create_objects(self):
        '''create opengl objects when opengl is initialized'''
        pass

    def draw_objects(self):
        '''called in the middle of ondraw after the buffer has been cleared'''
        pass

    # old zoom event handler, still in use, phasing out soon
    def onMouseWheel(self, event):
        wheelRotation = event.GetWheelRotation()

        if wheelRotation != 0:
            if wheelRotation > 0:
                self.zoom += 0.1
            elif wheelRotation < 0:
                self.zoom -= 0.1

            if self.zoom < self.MIN_ZOOM:
                self.zoom = self.MIN_ZOOM
            elif self.zoom > self.MAX_ZOOM:
                self.zoom = self.MAX_ZOOM

        self.OnReshape()
        self.Refresh()

    # implementation in progress

    def get_modelview_mat(self, local_transform):
        mvmat = (GLdouble * 16)()
        glGetDoublev(GL_MODELVIEW_MATRIX, mvmat)
        return mvmat

    def mouse_to_3d(self, x, y, z=1.0, local_transform=False):
        x = float(x)
        y = self.height - float(y)
        pmat = (GLdouble * 16)()
        mvmat = self.get_modelview_mat(local_transform)
        viewport = (GLint * 4)()
        px = (GLdouble)()
        py = (GLdouble)()
        pz = (GLdouble)()
        glGetIntegerv(GL_VIEWPORT, viewport)
        glGetDoublev(GL_PROJECTION_MATRIX, pmat)
        glGetDoublev(GL_MODELVIEW_MATRIX, mvmat)
        gluUnProject(x, y, z, mvmat, pmat, viewport, px, py, pz)
        return (px.value, py.value, pz.value)

    def mouse_to_ray(self, x, y, local_transform=False):
        x = float(x)
        y = self.height - float(y)
        pmat = (GLdouble * 16)()
        mvmat = (GLdouble * 16)()
        viewport = (GLint * 4)()
        px = (GLdouble)()
        py = (GLdouble)()
        pz = (GLdouble)()
        glGetIntegerv(GL_VIEWPORT, viewport)
        glGetDoublev(GL_PROJECTION_MATRIX, pmat)
        mvmat = self.get_modelview_mat(local_transform)
        gluUnProject(x, y, 1, mvmat, pmat, viewport, px, py, pz)
        ray_far = (px.value, py.value, pz.value)
        gluUnProject(x, y, 0., mvmat, pmat, viewport, px, py, pz)
        ray_near = (px.value, py.value, pz.value)
        return ray_near, ray_far

    def mouse_to_plane(self, x, y, plane_normal, plane_offset, local_transform = False):
        # Ray/plane intersection
        ray_near, ray_far = self.mouse_to_ray(x, y, local_transform)
        ray_near = numpy.array(ray_near)
        ray_far = numpy.array(ray_far)
        ray_dir = ray_far - ray_near
        ray_dir = ray_dir / numpy.linalg.norm(ray_dir)
        plane_normal = numpy.array(plane_normal)
        q = ray_dir.dot(plane_normal)
        if q == 0:
            return None
        t = - (ray_near.dot(plane_normal) + plane_offset) / q
        if t < 0:
            return None
        return ray_near + t * ray_dir

    def orbit(self, p1x, p1y, p2x, p2y):
        pass

    def handle_rotation(self, event):
        if self.initpos is None:
            self.initpos = event.GetPosition()
        else:
            p1 = self.initpos
            p2 = event.GetPosition()

            width, height = self.width, self.height
            x_scale = 180.0 / max(width, 1.0)
            z_scale = 180.0 / max(height, 1.0)
            glRotatef((p2.x - p1.x) * x_scale, 0.0, 0.0, 1.0)
            glRotatef((p2.y - p1.y) * z_scale, 1.0, 0.0, 0.0)
            self.initpos = p2

    def handle_translation(self, event):
        if self.initpos is None:
            self.initpos = event.GetPosition()
        else:
            p1 = self.initpos
            p2 = event.GetPosition()
            # Do stuff
            self.initpos = p2
