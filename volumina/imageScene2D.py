import numpy, math

from PyQt4.QtCore import QRect, QRectF, QPointF, Qt, QSizeF, QLineF, QObject, pyqtSignal, SIGNAL
from PyQt4.QtGui import QGraphicsScene, QTransform, QPen, QColor, QBrush, QPolygonF, QPainter, QGraphicsItem, \
                        QGraphicsItemGroup, QGraphicsLineItem, QGraphicsTextItem, QGraphicsPolygonItem, \
                        QGraphicsRectItem

from volumina.tiling import Tiling, TileProvider, TiledImageLayer
from volumina.layerstack import LayerStackModel
from volumina.pixelpipeline.imagepump import StackedImageSources

import datetime

#*******************************************************************************
# D i r t y I n d i c a t o r                                                  *
#*******************************************************************************
class DirtyIndicator(QGraphicsItem):
    """
    Indicates the computation progress of each tile. Each tile can be composed
    of multiple layers and is dirty as long as any of these layer tiles are
    not yet computed/up to date. The number of layer tiles still missing is
    indicated by a 'pie' chart.
    """
    def __init__(self, tiling):
        QGraphicsItem.__init__(self, parent=None)
        self._tiling = tiling
        self._indicate = numpy.zeros(len(tiling))
        self._zeroProgressTimestamp = [None] * len(tiling)

    def boundingRect(self):
        return self._tiling.boundingRectF()

    def paint(self, painter, option, widget):
        dirtyColor = QColor(255,0,0)
        painter.setOpacity(0.5)
        painter.save()
        painter.setBrush(QBrush(dirtyColor, Qt.SolidPattern))
        painter.setPen(dirtyColor)

        for i,p in enumerate(self._tiling.tileRectFs):
            if self._indicate[i] == 1.0:
                continue

            # Don't show unless 300 millisecs have passed since the tile progress was reset.
            startTime = self._zeroProgressTimestamp[i]
            if startTime is not None and datetime.datetime.now() - startTime < datetime.timedelta(milliseconds=300):
                continue

            w,h = p.width(), p.height()
            r = min(w,h)
            rectangle = QRectF(p.center()-QPointF(r/4,r/4), QSizeF(r/2, r/2));
            startAngle = 0 * 16
            spanAngle  = min(360*16, int((1.0-self._indicate[i])*360.0) * 16)
            painter.drawPie(rectangle, startAngle, spanAngle)

        painter.restore()

    def setTileProgress(self, tileId, progress):
        self._indicate[tileId] = progress
        if progress > 0.0:
            self._zeroProgressTimestamp[tileId] = None
        elif self._zeroProgressTimestamp[tileId] is None:
            self._zeroProgressTimestamp[tileId] = datetime.datetime.now()
        self.update()

#*******************************************************************************
# I m a g e S c e n e 2 D                                                      *
#*******************************************************************************

class ImageScene2D(QGraphicsScene):
    """
    The 2D scene description of a tiled image generated by evaluating
    an overlay stack, together with a 2D cursor.
    """
    axesChanged = pyqtSignal(int, bool)

    @property
    def stackedImageSources(self):
        return self._stackedImageSources

    @stackedImageSources.setter
    def stackedImageSources(self, s):
        self._stackedImageSources = s
        s.sizeChanged.connect(self._onSizeChanged)

    @property
    def showTileOutlines(self):
        return self._showTileOutlines
    @showTileOutlines.setter
    def showTileOutlines(self, show):
        self._showTileOutlines = show
        self.invalidate()

    @property
    def showTileProgress(self):
        return self._showTileProgress
    @showTileOutlines.setter
    def showTileProgress(self, show):
        self._showTileProgress = show
        self._dirtyIndicator.setVisible(show)

    def resetAxes(self, finish=True):
        # rotation is in range(4) and indicates in which corner of the
        # view the origin lies. 0 = top left, 1 = top right, etc.
        self._rotation = 0
        self._swapped = self._swappedDefault # whether axes are swapped
        self._newAxes()
        self._setSceneRect()
        self.scene2data, isInvertible = self.data2scene.inverted()
        assert isInvertible
        if finish:
            self._finishViewMatrixChange()

    def _newAxes(self):
        """Given self._rotation and self._swapped, calculates and sets
        the appropriate data2scene transformation.

        """
        # TODO: this function works, but it is not elegant. There must
        # be a simpler way to calculate the appropriate tranformation.

        w, h = self.dataShape
        assert self._rotation in range(0, 4)

        # unlike self._rotation, the local variable 'rotation'
        # indicates how many times to rotate clockwise after swapping
        # axes.

        # t1 : do axis swap
        t1 = QTransform()
        if self._swapped:
            t1 = QTransform(0, 1, 0, 1, 0, 0, 0, 0, 1)
            h, w = w, h

        # t2 : do rotation
        t2 = QTransform()
        t2.rotate(self._rotation * 90)

        # t3: shift to re-center
        rot2trans = {0 : (0, 0),
                     1 : (h, 0),
                     2 : (w, h),
                     3 : (0, w)}

        trans = rot2trans[self._rotation]
        t3 = QTransform.fromTranslate(*trans)

        self.data2scene = t1 * t2 * t3
        if self._tileProvider:
            self._tileProvider.axesSwapped = self._swapped
        self.axesChanged.emit(self._rotation, self._swapped)

    def rot90(self, transform, rect, direction):
        """ direction: left ==> -1, right ==> +1"""
        assert direction in [-1, 1]
        self._rotation = (self._rotation + direction) % 4
        self._newAxes()

    def swapAxes(self, transform):
        self._swapped = not self._swapped
        self._newAxes()

    def _onRotateLeft(self):
        self.rot90(self.data2scene, self.sceneRect(), -1)
        self._finishViewMatrixChange()

    def _onRotateRight(self):
        self.rot90(self.data2scene, self.sceneRect(), 1)
        self._finishViewMatrixChange()

    def _onSwapAxes(self):
        self.swapAxes(self.data2scene)
        self._finishViewMatrixChange()

    def _finishViewMatrixChange(self):
        self.scene2data, isInvertible = self.data2scene.inverted()
        self._setSceneRect()
        self._tiling.data2scene = self.data2scene
        self._tileProvider._onSizeChanged()
        QGraphicsScene.invalidate(self, self.sceneRect())

    @property
    def sceneShape(self):
        return (self.sceneRect().width(), self.sceneRect().height())

    def _setSceneRect(self):
        w, h = self.dataShape
        rect = self.data2scene.mapRect(QRect(0, 0, w, h))
        sw, sh = rect.width(), rect.height()
        self.setSceneRect(0, 0, sw, sh)

    @property
    def dataShape(self):
        """
        The shape of the scene in QGraphicsView's coordinate system.
        """
        return self._dataShape

    @dataShape.setter
    def dataShape(self, value):
        """
        Set the size of the scene in QGraphicsView's coordinate system.
        dataShape -- (widthX, widthY),
        where the origin of the coordinate system is in the upper left corner
        of the screen and 'x' points right and 'y' points down
        """
        assert len(value) == 2
        self._dataShape = value
        self.reset()
        self._finishViewMatrixChange()

    def setCacheSize(self, cache_size):
        if cache_size != self._tileProvider._cache_size:
            self._tileProvider = TileProvider(self._tiling, self._stackedImageSources, cache_size=cache_size)
            self._tileProvider.sceneRectChanged.connect(self.invalidateViewports)

    def cacheSize(self):
        return self._tileProvider._cache_size

    def setPrefetchingEnabled(self, enable):
        self._prefetching_enabled = enable

    def setPreemptiveFetchNumber(self, n):
        if n > self.cacheSize() - 1:
            self._n_preemptive = self.cacheSize() - 1
        else:
            self._n_preemptive = n
    def preemptiveFetchNumber(self):
        return self._n_preemptive

    def invalidateViewports(self, sceneRectF):
        '''Call invalidate on the intersection of all observing viewport-rects and rectF.'''
        sceneRectF = sceneRectF if sceneRectF.isValid() else self.sceneRect()
        for view in self.views():
            QGraphicsScene.invalidate(self, sceneRectF.intersected(view.viewportRect()))

    def reset(self):
        """Reset rotations, tiling, etc. Called when first initialized
        and when the underlying data changes.

        """
        self.resetAxes(finish=False)

        self._tiling = Tiling(self._dataShape, self.data2scene, name=self.name)
        self._brushingLayer  = TiledImageLayer(self._tiling)

        if self._tileProvider:
            self._tileProvider.notifyThreadsToStop() # prevent ref cycle
        self._tileProvider = TileProvider(self._tiling, self._stackedImageSources)
        self._tileProvider.sceneRectChanged.connect(self.invalidateViewports)

        if self._dirtyIndicator:
            self.removeItem(self._dirtyIndicator)
        del self._dirtyIndicator
        self._dirtyIndicator = DirtyIndicator(self._tiling)
        self.addItem(self._dirtyIndicator)


    def __init__(self, posModel, along, preemptive_fetch_number=5,
                 parent=None, name="Unnamed Scene",
                 swapped_default=False):
        """
        * preemptive_fetch_number -- number of prefetched slices; 0 turns the feature off
        * swapped_default -- whether axes should be swapped by default.

        """
        QGraphicsScene.__init__(self, parent=parent)

        self._along = along
        self._posModel = posModel

        self._dataShape = (0, 0)
        self._offsetX = 0
        self._offsetY = 0
        self.name = name

        self._stackedImageSources = StackedImageSources(LayerStackModel())
        self._showTileOutlines = False
        self._showTileProgress = True

        self._tileProvider = None
        self._dirtyIndicator = None
        self._prefetching_enabled = False
        
        self._swappedDefault = swapped_default
        self.reset()

        # BowWave preemptive caching
        self.setPreemptiveFetchNumber(preemptive_fetch_number)
        self._course = (1,1) # (along, pos or neg direction)
        self._time = self._posModel.time
        self._channel = self._posModel.channel
        self._posModel.timeChanged.connect(self._onTimeChanged)
        self._posModel.channelChanged.connect(self._onChannelChanged)
        self._posModel.slicingPositionChanged.connect(self._onSlicingPositionChanged)

    def __del__(self):
        if self._tileProvider:
            self._tileProvider.notifyThreadsToStop()

    def _onSizeChanged(self):
        self._brushingLayer  = TiledImageLayer(self._tiling)

    def drawForeground(self, painter, rect):
        if self._tiling is None:
            return

        tile_nos = self._tiling.intersected(rect)

        for tileId in tile_nos:
            p = self._brushingLayer[tileId]
            if p.dataVer == p.imgVer:
                continue

            p.paint(painter) #access to the underlying image patch is serialized

            ## draw tile outlines
            if self._showTileOutlines:
                # Dashed black line
                pen = QPen()
                pen.setDashPattern([5,5])
                painter.setPen(pen)
                painter.drawRect(self._tiling.imageRects[tileId])

                # Dashed white line
                # (offset to occupy the spaces in the dashed black line)
                pen = QPen()
                pen.setDashPattern([5,5])
                pen.setDashOffset(5)
                pen.setColor(QColor(Qt.white))
                painter.setPen(pen)
                painter.drawRect(self._tiling.imageRects[tileId])

    def indicateSlicingPositionSettled(self, settled):
        if self._showTileProgress:
            self._dirtyIndicator.setVisible(settled)

    def drawBackground(self, painter, sceneRectF):
        painter.setBrush(QBrush(QColor(220, 220, 220)))
        painter.drawRect(QRect(0, 0, *self.sceneShape))

        if self._tileProvider is None:
            return

        tiles = self._tileProvider.getTiles(sceneRectF)
        for tile in tiles:
            # prevent flickering
            if not tile.progress < 1.0:
                painter.drawImage(tile.rectF, tile.qimg)
            if self._showTileProgress:
                self._dirtyIndicator.setTileProgress(tile.id, tile.progress)

        # preemptive fetching
        if self._prefetching_enabled:
            for through in self._bowWave(self._n_preemptive):
                self._tileProvider.prefetch(sceneRectF, through)

    def joinRendering(self):
        return self._tileProvider.join()

    def _bowWave(self, n):
        shape5d = self._posModel.shape5D
        sl5d = self._posModel.slicingPos5D
        through = [sl5d[self._along[i]] for i in xrange(3)]
        t_max = [shape5d[self._along[i]] for i in xrange(3)]

        BowWave = []

        a = self._course[0]
        for d in xrange(1,n+1):
            m = through[a] + d * self._course[1]
            if m < t_max[a] and m >= 0:
                t = list(through)
                t[a] = m
                BowWave.append(tuple(t))
        return BowWave

    def _onSlicingPositionChanged(self, new, old):
        if (new[self._along[1] - 1] - old[self._along[1] - 1]) < 0:
            self._course = (1, -1)
        else:
            self._course = (1, 1)

    def _onChannelChanged(self, new):
        if (new - self._channel) < 0:
            self._course = (2, -1)
        else:
            self._course = (2, 1)
        self._channel = new

    def _onTimeChanged(self, new):
        if (new - self._time) < 0:
            self._course = (0, -1)
        else:
            self._course = (0, 1)
        self._time = new
