#    Copyright (C) 2014 Jeremy S. Sanders
#    Email: Jeremy Sanders <jeremy@jeremysanders.net>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
###############################################################################

"""3D function plotting widget."""

from __future__ import division, print_function
import itertools
import numpy as N

from ..compat import czip, crange
from .. import qtall as qt4
from .. import setting
from .. import document
from ..helpers import threed

from . import plotters3d

def _(text, disambiguation=None, context='Function3D'):
    """Translate text."""
    return qt4.QCoreApplication.translate(context, text, disambiguation)

class Function3D(plotters3d.GenericPlotter3D):
    """Plotting functions in 3D."""

    typename='function3d'
    description=_('Plot a 3D function')

    # list of the supported modes
    _modes = [
        'x=fn(y,z)', 'y=fn(x,z)', 'z=fn(x,y)',
        'x,y,z=fns(t)',
        'x,y=fns(z)', 'y,z=fns(x)', 'x,z=fns(y)'
    ]

    # which axes are affected by which modes
    _affects = {
        'z=fn(x,y)': (('zAxis', 'both'),),
        'x=fn(y,z)': (('xAxis', 'both'),),
        'y=fn(x,z)': (('yAxis', 'both'),),
        'x,y,z=fns(t)': (('xAxis', 'sx'), ('yAxis', 'sy'), ('zAxis', 'sz')),
        'x,y=fns(z)': (('xAxis', 'both'), ('yAxis', 'both')),
        'y,z=fns(x)': (('yAxis', 'both'), ('zAxis', 'both')),
        'x,z=fns(y)': (('xAxis', 'both'), ('zAxis', 'both')),
    }

    # which modes require which axes as inputs
    _requires = {
        'z=fn(x,y)': (('both', 'xAxis'), ('both', 'yAxis')),
        'x=fn(y,z)': (('both', 'yAxis'), ('both', 'zAxis')),
        'y=fn(x,z)': (('both', 'xAxis'), ('both', 'zAxis')),
        'x,y,z=fns(t)': (),
        'x,y=fns(z)': (('both', 'zAxis'),),
        'y,z=fns(x)': (('both', 'xAxis'),),
        'x,z=fns(y)': (('both', 'yAxis'),),
    }

    # which modes require which variables
    _varmap = {
        'x,y=fns(z)': ('x', 'y', 'z'),
        'y,z=fns(x)': ('y', 'z', 'x'),
        'x,z=fns(y)': ('x', 'z', 'y'),
    }

    @classmethod
    def addSettings(klass, s):
        plotters3d.GenericPlotter3D.addSettings(s)

        s.add(setting.Int(
            'linesteps',
            50,
            minval = 3,
            descr = _('Number of steps to evaluate the function over for lines'),
            usertext=_('Line steps'),
            formatting=True ))
        s.add(setting.Int(
            'surfacesteps',
            20,
            minval = 3,
            descr = _('Number of steps to evaluate the function over for surfaces'
                      ' in each direction'),
            usertext=_('Surface steps'),
            formatting=True ))
        s.add(setting.Choice(
            'mode', klass._modes,
            'x,y,z=fns(t)',
            descr=_('Type of function to plot'),
            usertext=_('Mode') ), 0)

        s.add(setting.Str(
            'fnx', '',
            descr=_('Function for x coordinate'),
            usertext=_('X function') ), 1)
        s.add(setting.Str(
            'fny', '',
            descr=_('Function for y coordinate'),
            usertext=_('Y function') ), 2)
        s.add(setting.Str(
            'fnz', '',
            descr=_('Function for z coordinate'),
            usertext=_('Z function') ), 3)

        s.add(setting.Line3D(
            'Line',
            descr = _('Line settings'),
            usertext = _('Plot line')),
               pixmap = 'settings_plotline' )
        s.add(setting.Surface3D(
            'Surface',
            descr = _('Surface fill settings'),
            usertext=_('Surface')),
              pixmap='settings_bgfill' )

    def affectsAxisRange(self):
        """Which axes this widget affects."""
        s = self.settings
        affects = self._affects[s.mode]
        return [(getattr(s, v[0]), v[1]) for v in affects]

    def requiresAxisRange(self):
        """Which axes this widget depends on."""
        s = self.settings
        requires = self._requires[s.mode]
        return [(v[0], getattr(s, v[1])) for v in requires]

    def getLineVals(self):
        """Get vals for line plot."""
        s = self.settings
        mode = s.mode

        if mode == 'x,y,z=fns(t)':
            if not s.fnx or not s.fny or not s.fnz:
                return None

            xcomp = self.document.compileCheckedExpression(s.fnx)
            ycomp = self.document.compileCheckedExpression(s.fny)
            zcomp = self.document.compileCheckedExpression(s.fnz)
            if xcomp is None or ycomp is None or zcomp is None:
                return None

            # evaluate each expression
            env = self.document.eval_context.copy()
            env['t'] = N.linspace(0, 1, s.linesteps)
            zeros = N.zeros(s.linesteps, dtype=N.float64)
            try:
                valsx = eval(xcomp, env) + zeros
                valsy = eval(ycomp, env) + zeros
                valsz = eval(zcomp, env) + zeros
            except:
                # something wrong in the evaluation
                return None
            retn = (valsx, valsy, valsz)

        else:
            # lookup variables to go with function
            var = self._varmap[mode]
            fns = [getattr(s, 'fn'+var[0]), getattr(s, 'fn'+var[1])]
            if fns[0] is None or fns[1] is None:
                return None

            # get points to evaluate functions over
            axis = self.fetchAxis(var[2])
            if not axis:
                return
            arange = axis.getPlottedRange()
            if axis.settings.log:
                evalpts = N.logspace(
                    N.log10(arange[0]), N.log10(arange[1]), s.linesteps)
            else:
                evalpts = N.linspace(arange[0], arange[1], s.linesteps)

            # evaluate expressions
            env = self.document.eval_context.copy()
            env[var[2]] = evalpts
            zeros = N.zeros(s.linesteps, dtype=N.float64)
            try:
                vals1 = eval(fns[0], env) + zeros
                vals2 = eval(fns[1], env) + zeros
            except:
                # something wrong in the evaluation
                return None

            # assign correct output points
            retn = [None]*3
            idxs = ('x', 'y', 'z')
            retn[idxs.index(var[0])] = vals1
            retn[idxs.index(var[1])] = vals2
            retn[idxs.index(var[2])] = evalpts

        return retn

    def getGridVals(self):
        """Get values for 2D grid.

        Return steps1, steps2, height, axidx, depvariable
        axidx are the indices into the axes for height, step1, step2
        """

        s = self.settings
        mode = s.mode

        var, ovar1, ovar2, axidx = {
            'x=fn(y,z)': ('x', 'y', 'z', (0, 1, 2)),
            'y=fn(x,z)': ('y', 'z', 'x', (1, 2, 0)),
            'z=fn(x,y)': ('z', 'x', 'y', (2, 0, 1)),
        }[mode]
        axes = self.fetchAxes()

        # range of other axes
        ax1, ax2 = axes[axidx[1]], axes[axidx[2]]
        pr1 = ax1.getPlottedRange()
        pr2 = ax2.getPlottedRange()
        steps = s.surfacesteps
        logax1, logax2 = ax1.settings.log, ax2.settings.log

        # convert log ranges to linear temporarily
        if logax1:
            pr1 = N.log(pr1)
        if logax2:
            pr2 = N.log(pr2)

        # set variables in environment
        grid1, grid2 = N.indices((steps, steps))
        del1 = (pr1[1]-pr1[0])/(steps-1.)
        steps1 = N.arange(steps)*del1 + pr1[0]
        grid1 = grid1*del1 + pr1[0]
        del2 = (pr2[1]-pr2[0])/(steps-1.)
        steps2 = N.arange(steps)*del2 + pr2[0]
        grid2 = grid2*del2 + pr2[0]

        # convert back to log
        if logax1:
            grid1 = N.exp(grid1)
        if logax2:
            grid2 = N.exp(grid2)

        env = self.document.eval_context.copy()
        env[ovar1] = grid1
        env[ovar2] = grid2

        fn = getattr(s, 'fn%s' % var)  # get function from user
        comp = self.document.compileCheckedExpression(fn)
        if comp is None:
            return None

        try:
            height = eval(comp, env) + N.zeros(grid1.shape, dtype=N.float64)
        except:
            # something wrong in the evaluation
            return None

        return height, steps1, steps2, axidx, var

    def getRange(self, axis, depname, axrange):
        mode = self.settings.mode
        if mode == 'x,y,z=fns(t)':
            # get range of each variable
            retn = self.getLineVals()
            if not retn:
                return
            valsx, valsy, valsz = retn
            coord = {'sx': valsx, 'sy': valsy, 'sz': valsz}[depname]

        elif mode in ('x,y=fns(z)', 'y,z=fns(x)', 'x,z=fns(y)'):
            # is this axis one of the ones we affect?
            var = self._varmap[mode]
            if self.fetchAxis(var[0]) is axis:
                v = var[0]
            elif self.fetchAxis(var[1]) is axis:
                v = var[1]
            else:
                return

            retn = self.getLineVals()
            if not retn:
                return
            coord = retn[('x', 'y', 'z').index(v)]

        elif mode in ('z=fn(x,y)', 'x=fn(y,z)', 'y=fn(x,z)'):
            retn = self.getGridVals()
            if not retn:
                return
            height, steps1, steps2, axidx, var = retn
            if axis is not self.fetchAxis(var):
                return
            coord = height

        finite = coord[N.isfinite(coord)]
        if len(finite) > 0:
            axrange[0] = min(axrange[0], finite.min())
            axrange[1] = max(axrange[1], finite.max())

    def dataDrawSurface(self, axes, container):
        """Draw a surface plot."""
        retn = self.getGridVals()
        if not retn:
            return
        height, steps1, steps2, axidx, depvar = retn
        lheight = axes[axidx[0]].dataToLogicalCoords(height)
        lsteps1 = axes[axidx[1]].dataToLogicalCoords(steps1)
        lsteps2 = axes[axidx[2]].dataToLogicalCoords(steps2)

        # draw grid over each axis
        surfprop = lineprop = None
        s = self.settings
        if not s.Surface.hide:
            surfprop = s.Surface.makeSurfaceProp()
        if not s.Line.hide:
            lineprop = s.Line.makeLineProp()

        dirn = {'x': threed.Mesh.X_DIRN,
                'y': threed.Mesh.Y_DIRN,
                'z': threed.Mesh.Z_DIRN}[depvar]

        mesh = threed.Mesh(
            threed.ValVector(lsteps1), threed.ValVector(lsteps2),
            threed.ValVector(N.ravel(lheight)),
            dirn, lineprop, surfprop)
        container.addObject(mesh)

    def dataDrawToObject(self, axes):

        s = self.settings
        mode = s.mode

        axes = self.fetchAxes()
        if axes is None:
            return

        s = self.settings

        clipcontainer = self.makeClipContainer(axes)
        if mode in ('x,y,z=fns(t)', 'x,y=fns(z)', 'y,z=fns(x)', 'x,z=fns(y)'):
            retn = self.getLineVals()
            if not retn:
                return
            if s.Line.hide:
                return
            valsx, valsy, valsz = retn
            lx = axes[0].dataToLogicalCoords(valsx)
            ly = axes[1].dataToLogicalCoords(valsy)
            lz = axes[2].dataToLogicalCoords(valsz)
            lineprop = s.Line.makeLineProp()
            line = threed.PolyLine(lineprop)
            line.addPoints(
                threed.ValVector(lx), threed.ValVector(ly),
                threed.ValVector(lz))
            
            clipcontainer.addObject(line)

        elif mode in ('z=fn(x,y)', 'x=fn(y,z)', 'y=fn(x,z)'):
            self.dataDrawSurface(axes, clipcontainer)

        return clipcontainer

document.thefactory.register(Function3D)