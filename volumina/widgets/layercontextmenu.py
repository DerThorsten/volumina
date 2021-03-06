from functools import partial
from PyQt4.QtCore import QPoint, pyqtSignal, Qt
from PyQt4.QtGui import QMenu, QAction, QDialog, QHBoxLayout, QTableWidget, QSizePolicy, QTableWidgetItem, QColor
from volumina.layer import ColortableLayer, GrayscaleLayer, RGBALayer, ClickableColortableLayer
from layerDialog import GrayscaleLayerDialog, RGBALayerDialog
from volumina.events import Event
from exportDlg import ExportDialog

###
### lazyflow input
###
_has_lazyflow = True
try:
    from lazyflow.graph import Graph
    from lazyflow.operators.operators import OpArrayPiper
    from lazyflow.roi import roiToSlice
except ImportError as e:
    exceptStr = str(e)
    _has_lazyflow = False


def _add_actions_grayscalelayer( layer, menu ):
    def adjust_thresholds_callback():
        dlg = GrayscaleLayerDialog(menu.parent())
        dlg.setLayername(layer.name)
        def dbgPrint(a, b):
            layer.set_normalize(0, (a,b))
            print "normalization changed to [%d, %d]" % (a,b)
        dlg.grayChannelThresholdingWidget.setRange(layer.range[0][0], layer.range[0][1])
        dlg.grayChannelThresholdingWidget.setValue(layer.normalize[0][0], layer.normalize[0][1])
        dlg.grayChannelThresholdingWidget.valueChanged.connect(dbgPrint)
        dlg.show()

    adjThresholdAction = QAction("Adjust thresholds", menu)
    adjThresholdAction.triggered.connect(adjust_thresholds_callback)
    menu.addAction(adjThresholdAction)

def _add_actions_rgbalayer( layer, menu ): 
    def adjust_thresholds_callback():
        dlg = RGBALayerDialog(menu.parent())
        dlg.setLayername(layer.name)
        if layer.datasources[0] == None:
            dlg.showRedThresholds(False)
        if layer.datasources[1] == None:
            dlg.showGreenThresholds(False)
        if layer.datasources[2] == None:
            dlg.showBlueThresholds(False)
        if layer.datasources[3] == None:
            dlg.showAlphaThresholds(False)

        def dbgPrint(layerIdx, a, b):
            layer.set_normalize(layerIdx, (a, b))
            print "normalization changed for channel=%d to [%d, %d]" % (layerIdx, a,b)
        dlg.redChannelThresholdingWidget.setRange(layer.range[0][0], layer.range[0][1])
        dlg.greenChannelThresholdingWidget.setRange(layer.range[1][0], layer.range[1][1])
        dlg.blueChannelThresholdingWidget.setRange(layer.range[2][0], layer.range[2][1])
        dlg.alphaChannelThresholdingWidget.setRange(layer.range[3][0], layer.range[3][1])

        dlg.redChannelThresholdingWidget.setValue(layer.normalize[0][0], layer.normalize[0][1])
        dlg.greenChannelThresholdingWidget.setValue(layer.normalize[1][0], layer.normalize[1][1])
        dlg.blueChannelThresholdingWidget.setValue(layer.normalize[2][0], layer.normalize[2][1])
        dlg.alphaChannelThresholdingWidget.setValue(layer.normalize[3][0], layer.normalize[3][1])

        dlg.redChannelThresholdingWidget.valueChanged.connect(  partial(dbgPrint, 0))
        dlg.greenChannelThresholdingWidget.valueChanged.connect(partial(dbgPrint, 1))
        dlg.blueChannelThresholdingWidget.valueChanged.connect( partial(dbgPrint, 2))
        dlg.alphaChannelThresholdingWidget.valueChanged.connect(partial(dbgPrint, 3))

        dlg.resize(dlg.minimumSize())
        dlg.show()

    adjThresholdAction = QAction("Adjust thresholds", menu)
    adjThresholdAction.triggered.connect(adjust_thresholds_callback)
    menu.addAction(adjThresholdAction)
 
class LayerColortableDialog(QDialog):
    def __init__(self, layer, parent=None):
        super(LayerColortableDialog, self).__init__(parent=parent)
        
        h = QHBoxLayout(self)
        t = QTableWidget(self)
        t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)       
        t.setRowCount(len(layer._colorTable))
        t.setColumnCount(1)
        t.setVerticalHeaderLabels(["%d" %i for i in range(len(layer._colorTable))])
        
        for i in range(len(layer._colorTable)): 
            item = QTableWidgetItem(" ")
            t.setItem(i,0, item);
            item.setBackgroundColor(QColor.fromRgba(layer._colorTable[i]))
            item.setFlags(Qt.ItemIsSelectable)
        
        h.addWidget(t)
    
def _add_actions_colortablelayer( layer, menu ): 
    def adjust_colortable_callback():
        dlg = LayerColortableDialog(layer, menu.parent())
        dlg.exec_()
        
    adjColortableAction = QAction("Change colortable", menu)
    adjColortableAction.triggered.connect(adjust_colortable_callback)
    menu.addAction(adjColortableAction)
    if layer.colortableIsRandom:
        randomizeColors = QAction("Randomize colors", menu)
        randomizeColors.triggered.connect(layer.randomizeColors)
        menu.addAction(randomizeColors)

def _add_actions( layer, menu ):
    if isinstance(layer, GrayscaleLayer):
        _add_actions_grayscalelayer( layer, menu )
    elif isinstance( layer, RGBALayer ):
        _add_actions_rgbalayer( layer, menu )
    elif isinstance( layer, ColortableLayer ) or isinstance( layer, ClickableColortableLayer ):
        _add_actions_colortablelayer( layer, menu )

def layercontextmenu( layer, pos, parent=None, volumeEditor = None ):
    '''Show a context menu to manipulate properties of layer.

    layer -- a volumina layer instance
    pos -- QPoint 

    '''
    def onExport():
        if _has_lazyflow:
            inputArray = layer.datasources[0].request((slice(None),)).wait()
            expDlg = ExportDialog(parent = menu)
            g = Graph()
            piper = OpArrayPiper(graph=g)
            piper.inputs["Input"].setValue(inputArray)
            expDlg.setInput(piper.outputs["Output"],g)
        expDlg.show()
        
    menu = QMenu("Menu", parent)
    title = QAction("%s" % layer.name, menu)
    title.setEnabled(False)
    
    export = QAction("Export...",menu)
    export.setStatusTip("Export Layer...")
    export.triggered.connect(onExport)
    
    menu.addAction(title)
    menu.addAction(export)
    menu.addSeparator()
    _add_actions( layer, menu )

    menu.addSeparator()
    for name, callback in layer.contexts:
        action = QAction(name, menu)
        action.triggered.connect(callback)
        menu.addAction(action)

    menu.exec_(pos)    
