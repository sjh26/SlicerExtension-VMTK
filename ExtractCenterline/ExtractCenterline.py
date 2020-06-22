import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# ExtractCenterline
#

class ExtractCenterline(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Extract Centerline"
        self.parent.categories = ["Vascular Modeling Toolkit"]
        self.parent.dependencies = []
        self.parent.contributors = ["Andras Lasso (PerkLab)",
                                    "Daniel Haehn (Boston Children's Hospital)",
                                    "Luca Antiga (Orobix)",
                                    "Steve Pieper (Isomics)"]
        self.parent.helpText = """
    Compute and quantify centerline network of vasculature or airways from a surface model.
    Surface model can be created from image volume using Segment Editor module.
    This module replaces the old "Centerline Computation" module. Documentation is available
    <a href="https://github.com/vmtk/SlicerExtension-VMTK">here</a>.
    """
        self.parent.acknowledgementText = """
    """  # TODO: replace with organization, grant and thanks.

#
# ExtractCenterlineWidget
#

class ExtractCenterlineWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self.updatingGUIFromParameterNode = False

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer)
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/ExtractCenterline.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        self.nodeSelectors = [
            (self.ui.inputSurfaceSelector, "InputSurface"),
            (self.ui.endPointsMarkupsSelector, "EndPoints"),
            (self.ui.outputNetworkModelSelector, "Network"),
            (self.ui.outputCenterlineModelSelector, "CenterlineModel"),
            (self.ui.outputCenterlineCurveSelector, "CenterlineCurve"),
            (self.ui.outputQuantificationResultsTableSelector, "QuantificationResults"),
            (self.ui.outputPreprocessedSurfaceModelSelector, "PreprocessedSurface"),
            (self.ui.outputMeshErrorsMarkupsSelector, "MeshErrors"),
            (self.ui.outputVoronoiDiagramModelSelector, "VoronoiDiagram")
            ]

        # Set scene in MRML widgets. Make sure that in Qt designer
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create a new parameterNode
        # This parameterNode stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.
        self.logic = ExtractCenterlineLogic()
        self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)
        self.setParameterNode(self.logic.getParameterNode())

        # Connections
        self.ui.parameterNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.setParameterNode)
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.ui.autoDetectEndPointsPushButton.connect('clicked(bool)', self.onAutoDetectEndPoints)
        self.ui.preprocessInputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.subdivideInputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.targetKPointCountWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
        self.ui.decimationAggressivenessWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
        self.ui.inputSegmentSelectorWidget.connect('currentSegmentChanged(QString)', self.updateParameterNodeFromGUI)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        for nodeSelector, roleName in self.nodeSelectors:
            nodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def setParameterNode(self, inputParameterNode):
        """
        Adds observers to the selected parameter node. Observation is needed because when the
        parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Set parameter node in the parameter node selector widget
        wasBlocked = self.ui.parameterNodeSelector.blockSignals(True)
        self.ui.parameterNodeSelector.setCurrentNode(inputParameterNode)
        self.ui.parameterNodeSelector.blockSignals(wasBlocked)

        if inputParameterNode == self._parameterNode:
            # No change
            return

        # Unobserve previusly selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        if inputParameterNode is not None:
            self.addObserver(inputParameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        # Disable all sections if no parameter node is selected
        parameterNode = self._parameterNode
        if not slicer.mrmlScene.IsNodePresent(parameterNode):
            parameterNode = None
        self.ui.inputsCollapsibleButton.enabled = parameterNode is not None
        self.ui.outputsCollapsibleButton.enabled = parameterNode is not None
        self.ui.advancedCollapsibleButton.enabled = parameterNode is not None
        if parameterNode is None:
            return

        if self.updatingGUIFromParameterNode:
            return
        self.updatingGUIFromParameterNode = True

        # Update each widget from parameter node
        # Need to temporarily block signals to prevent infinite recursion (MRML node update triggers
        # GUI update, which triggers MRML node update, which triggers GUI update, ...)
        for nodeSelector, roleName in self.nodeSelectors:
            nodeSelector.setCurrentNode(self._parameterNode.GetNodeReference(roleName))

        inputSurfaceNode = self._parameterNode.GetNodeReference("InputSurface")
        if inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
            self.ui.inputSegmentSelectorWidget.setCurrentSegmentID(self._parameterNode.GetParameter("InputSegmentID"))
            self.ui.inputSegmentSelectorWidget.setVisible(True)
        else:
            self.ui.inputSegmentSelectorWidget.setVisible(False)

        self.ui.targetKPointCountWidget.value = float(self._parameterNode.GetParameter("TargetNumberOfPoints"))/1000.0

        self.ui.decimationAggressivenessWidget.value = float(self._parameterNode.GetParameter("DecimationAggressiveness"))

        # do not block signals so that related widgets are enabled/disabled according to its state
        self.ui.preprocessInputSurfaceModelCheckBox.checked = (self._parameterNode.GetParameter("PreprocessInputSurface") == "true")

        self.ui.subdivideInputSurfaceModelCheckBox.checked = (self._parameterNode.GetParameter("SubdivideInputSurface") == "true")

        self.updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None:
            return

        for nodeSelector, roleName in self.nodeSelectors:
            self._parameterNode.SetNodeReferenceID(roleName, nodeSelector.currentNodeID)

        inputSurfaceNode = self._parameterNode.GetNodeReference("InputSurface")
        if inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
            self._parameterNode.SetParameter("InputSegmentID", self.ui.inputSegmentSelectorWidget.currentSegmentID())

        self.ui.inputSegmentSelectorWidget.setCurrentSegmentID(self._parameterNode.GetParameter("InputSegmentID"))
        self.ui.inputSegmentSelectorWidget.setVisible(inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"))

        wasModify = self._parameterNode.StartModify()
        self._parameterNode.SetParameter("TargetNumberOfPoints", str(self.ui.targetKPointCountWidget.value*1000.0))
        self._parameterNode.SetParameter("DecimationAggressiveness", str(self.ui.decimationAggressivenessWidget.value))
        self._parameterNode.SetParameter("PreprocessInputSurface", "true" if self.ui.preprocessInputSurfaceModelCheckBox.checked else "false")
        self._parameterNode.SetParameter("SubdivideInputSurface", "true" if self.ui.subdivideInputSurfaceModelCheckBox.checked else "false")
        self._parameterNode.EndModify(wasModify)

    def getPreprocessedPolyData(self):
        inputSurfacePolyData = self.logic.polyDataFromNode(self._parameterNode.GetNodeReference("InputSurface"),
                                                           self._parameterNode.GetParameter("InputSegmentID"))
        if not inputSurfacePolyData or inputSurfacePolyData.GetNumberOfPoints() == 0:
            raise ValueError("Valid input surface is required")

        preprocessEnabled = (self._parameterNode.GetParameter("PreprocessInputSurface") == "true")
        if not preprocessEnabled:
            return inputSurfacePolyData
        targetNumberOfPoints = float(self._parameterNode.GetParameter("TargetNumberOfPoints"))
        decimationAggressiveness = float(self._parameterNode.GetParameter("DecimationAggressiveness"))
        subdivideInputSurface = (self._parameterNode.GetParameter("SubdivideInputSurface") == "true")
        preprocessedPolyData = self.logic.preprocess(inputSurfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface)
        return preprocessedPolyData

    def onApplyButton(self):
        """
        Run processing when user clicks "Apply" button.
        """
        qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            # Preprocessing
            slicer.util.showStatusMessage("Preprocessing...")
            slicer.app.processEvents()  # force update
            preprocessedPolyData = self.getPreprocessedPolyData()
            # Save preprocessing result to model node
            preprocessedSurfaceModelNode = self._parameterNode.GetNodeReference("PreprocessedSurface")
            if preprocessedSurfaceModelNode:
                preprocessedSurfaceModelNode.SetAndObserveMesh(preprocessedPolyData)
                if not preprocessedSurfaceModelNode.GetDisplayNode():
                    preprocessedSurfaceModelNode.CreateDefaultDisplayNodes()
                    preprocessedSurfaceModelNode.GetDisplayNode().SetColor(1.0, 1.0, 0.0)
                    preprocessedSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)
                    preprocessedSurfaceModelNode.GetDisplayNode().SetLineWidth(2)

            # Get non-manifold edges
            meshErrorsMarkupsNode = self._parameterNode.GetNodeReference("MeshErrors")
            if meshErrorsMarkupsNode:
                slicer.util.showStatusMessage("Get manifold edges...")
                slicer.app.processEvents()  # force update
                meshErrorsMarkupsNode.RemoveAllControlPoints()
                nonManifoldEdgePositions = self.logic.extractNonManifoldEdges(preprocessedPolyData)
                for pointIndex, position in enumerate(nonManifoldEdgePositions):
                    meshErrorsMarkupsNode.AddControlPoint(vtk.vtkVector3d(position), "NME {0}".format(pointIndex))
                numberOfNonManifoldEdges = len(nonManifoldEdgePositions)
                if numberOfNonManifoldEdges > 0:
                    logging.warning("Found {0} non-manifold edges.".format(numberOfNonManifoldEdges)
                                    + " Centerline computation may fail. Try to increase target point count or reduce decimation aggressiveness")
                    # TODO: we could remove non-manifold edges by using vtkFeatureEdges

            endPointsMarkupsNode = self._parameterNode.GetNodeReference("EndPoints")
            inputSurfaceModelNode = self._parameterNode.GetNodeReference("InputSurface")

            # Extract network
            networkModelNode = self._parameterNode.GetNodeReference("Network")
            if networkModelNode:
                slicer.util.showStatusMessage("Extract network...")
                slicer.app.processEvents()  # force update
                networkPolyData = self.logic.extractNetwork(preprocessedPolyData, endPointsMarkupsNode)
                networkModelNode.SetAndObserveMesh(networkPolyData)
                if not networkModelNode.GetDisplayNode():
                    networkModelNode.CreateDefaultDisplayNodes()
                    networkModelNode.GetDisplayNode().SetColor(0.0, 0.0, 1.0)
                    inputSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)

            # Extract centerline
            centerlineModelNode = self._parameterNode.GetNodeReference("CenterlineModel")
            centerlineCurveNode = self._parameterNode.GetNodeReference("CenterlineCurve")
            quantificationResultsTableNode = self._parameterNode.GetNodeReference("QuantificationResults")
            voronoiDiagramModelNode = self._parameterNode.GetNodeReference("VoronoiDiagram")
            if centerlineModelNode or centerlineCurveNode or quantificationResultsTableNode or voronoiDiagramModelNode:
                slicer.util.showStatusMessage("Extract centerline...")
                slicer.app.processEvents()  # force update
                centerlinePolyData, voronoiDiagramPolyData = self.logic.extractCenterline(preprocessedPolyData, endPointsMarkupsNode)
            if centerlineModelNode:
                centerlineModelNode.SetAndObserveMesh(centerlinePolyData)
                if not centerlineModelNode.GetDisplayNode():
                    centerlineModelNode.CreateDefaultDisplayNodes()
                    centerlineModelNode.GetDisplayNode().SetColor(0.0, 1.0, 0.0)
                    centerlineModelNode.GetDisplayNode().SetLineWidth(3)
                    inputSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)

            if voronoiDiagramModelNode:
                voronoiDiagramModelNode.SetAndObserveMesh(voronoiDiagramPolyData)
                if not voronoiDiagramModelNode.GetDisplayNode():
                    voronoiDiagramModelNode.CreateDefaultDisplayNodes()
                    voronoiDiagramModelNode.GetDisplayNode().SetColor(0.0, 1.0, 0.0)
                    voronoiDiagramModelNode.GetDisplayNode().SetOpacity(0.2)

            if centerlineCurveNode or quantificationResultsTableNode:
                slicer.util.showStatusMessage("Generate curves and quantification results table...")
                slicer.app.processEvents()  # force update
                self.logic.createCurveTreeFromCenterline(centerlinePolyData, centerlineCurveNode, quantificationResultsTableNode)

        except Exception as e:
            slicer.util.errorDisplay("Failed to compute results: "+str(e))
            import traceback
            traceback.print_exc()
        qt.QApplication.restoreOverrideCursor()
        slicer.util.showStatusMessage("Centerline analysis complete.", 3000)

    def onAutoDetectEndPoints(self):
        """
        Automatically detect mesh endpoints
        """
        qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            slicer.util.showStatusMessage("Preprocessing...")
            slicer.app.processEvents()  # force update
            preprocessedPolyData = self.getPreprocessedPolyData()
            endPointsMarkupsNode = self._parameterNode.GetNodeReference("EndPoints")
            if not endPointsMarkupsNode:
                endPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode",
                    slicer.mrmlScene.GetUniqueNameByString("Centerline endpoints"))
                endPointsMarkupsNode.CreateDefaultDisplayNodes()
                self._parameterNode.SetNodeReferenceID("EndPoints", endPointsMarkupsNode.GetID())
                # Make input surface semi-transparent to make all detected endpoints visible
                inputSurfaceModelNode = self._parameterNode.GetNodeReference("InputSurface")
                inputSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)
            
            slicer.util.showStatusMessage("Extract network...")
            slicer.app.processEvents()  # force update
            networkPolyData = self.logic.extractNetwork(preprocessedPolyData, endPointsMarkupsNode)

            # Retrieve start point position (if there any endpoints are specified)
            startPointPosition = None
            startPositionIndex = self.logic.startPointIndexFromEndPointsMarkupsNode(endPointsMarkupsNode)
            if startPositionIndex >= 0:
                startPointPosition = [0.0, 0.0, 0.0]
                endPointsMarkupsNode.GetNthControlPointPosition(startPositionIndex, startPointPosition)

            endpointPositions = self.logic.getEndPoints(networkPolyData, startPointPosition=startPointPosition)

            endPointsMarkupsNode.GetDisplayNode().PointLabelsVisibilityOff()
            endPointsMarkupsNode.RemoveAllMarkups()
            for position in endpointPositions:
                endPointsMarkupsNode.AddControlPoint(vtk.vtkVector3d(position))

            # Mark the first node as unselected, which means that it is the start point
            # (by default points are selected and there are more endpoints and only one start point,
            # therefore indicating start point by non-selected stat requires less clicking)
            if endPointsMarkupsNode.GetNumberOfControlPoints() > 0:
                endPointsMarkupsNode.SetNthControlPointSelected(0, False)

        except Exception as e:
          slicer.util.errorDisplay("Failed to detect end points: "+str(e))
          import traceback
          traceback.print_exc()
        qt.QApplication.restoreOverrideCursor()

        slicer.util.showStatusMessage("Automatic endpoint computation complete.", 3000)

#
# ExtractCenterlineLogic
#

class ExtractCenterlineLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        self.blankingArrayName = 'Blanking'
        self.radiusArrayName = 'Radius'  # maximum inscribed sphere radius
        self.groupIdsArrayName = 'GroupIds'
        self.centerlineIdsArrayName = 'CenterlineIds'
        self.tractIdsArrayName = 'TractIds'
        self.topologyArrayName = 'Topology'
        self.marksArrayName = 'Marks'
        self.lengthArrayName = 'Length'
        self.curvatureArrayName = 'Curvature'
        self.torsionArrayName = 'Torsion'
        self.tortuosityArrayName = 'Tortuosity'

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        # We choose a small target point number value, so that we can get fast speed
        # for smooth meshes. Actual mesh size will mainly determined by DecimationAggressiveness value.
        if not parameterNode.GetParameter("TargetNumberOfPoints"):
            parameterNode.SetParameter("TargetNumberOfPoints", "5000")
        if not parameterNode.GetParameter("DecimationAggressiveness"):
            parameterNode.SetParameter("DecimationAggressiveness", "4.0")
        if not parameterNode.GetParameter("PreprocessInputSurface"):
            parameterNode.SetParameter("PreprocessInputSurface", "true")
        if not parameterNode.GetParameter("SubdivideInputSurface"):
            parameterNode.SetParameter("SubdivideInputSurface", "false")

    def polyDataFromNode(self, surfaceNode, segmentId):
        if not surfaceNode:
            logging.error("Invalid input surface node")
            return None
        if surfaceNode.IsA("vtkMRMLModelNode"):
            return surfaceNode.GetPolyData()
        elif surfaceNode.IsA("vtkMRMLSegmentationNode"):
            # Segmentation node
            polyData = vtk.vtkPolyData()
            surfaceNode.CreateClosedSurfaceRepresentation()
            surfaceNode.GetClosedSurfaceRepresentation(segmentId, polyData)
            return polyData
        else:
            logging.error("Surface can only be loaded from model or segmentation node")
            return None

    def preprocess(self, surfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivide):
        # import the vmtk libraries
        try:
            import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
            import vtkvmtkMiscPython as vtkvmtkMisc
        except ImportError:
            raise ImportError("VMTK library is not found")

        numberOfInputPoints = surfacePolyData.GetNumberOfPoints()
        if numberOfInputPoints == 0:
            raise("Input surface model is empty")
        reductionFactor = (numberOfInputPoints-targetNumberOfPoints) / numberOfInputPoints
        if reductionFactor > 0.0:
            parameters = {}
            inputSurfaceModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "tempInputSurfaceModel")
            inputSurfaceModelNode.SetAndObserveMesh(surfacePolyData)
            parameters["inputModel"] = inputSurfaceModelNode
            outputSurfaceModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "tempDecimatedSurfaceModel")
            parameters["outputModel"] = outputSurfaceModelNode
            parameters["reductionFactor"] = reductionFactor
            parameters["method"] = "FastQuadric"
            parameters["aggressiveness"] = decimationAggressiveness
            decimation = slicer.modules.decimation
            cliNode = slicer.cli.runSync(decimation, None, parameters)
            surfacePolyData = outputSurfaceModelNode.GetPolyData()
            slicer.mrmlScene.RemoveNode(inputSurfaceModelNode)
            slicer.mrmlScene.RemoveNode(outputSurfaceModelNode)
            slicer.mrmlScene.RemoveNode(cliNode)

        surfaceCleaner = vtk.vtkCleanPolyData()
        surfaceCleaner.SetInputData(surfacePolyData)
        surfaceCleaner.Update()

        surfaceTriangulator = vtk.vtkTriangleFilter()
        surfaceTriangulator.SetInputData(surfaceCleaner.GetOutput())
        surfaceTriangulator.PassLinesOff()
        surfaceTriangulator.PassVertsOff()
        surfaceTriangulator.Update()

        # new steps for preparation to avoid problems because of slim models (f.e. at stenosis)
        if subdivide:
            subdiv = vtk.vtkLinearSubdivisionFilter()
            subdiv.SetInputData(surfaceTriangulator.GetOutput())
            subdiv.SetNumberOfSubdivisions(1)
            subdiv.Update()
            if subdiv.GetOutput().GetNumberOfPoints() == 0:
                logging.warning("Mesh subdivision failed. Skip subdivision step.")
                subdivide = False

        normals = vtk.vtkPolyDataNormals()
        if subdivide:
            normals.SetInputData(subdiv.GetOutput())
        else:
            normals.SetInputData(surfaceTriangulator.GetOutput())
        normals.SetAutoOrientNormals(1)
        normals.SetFlipNormals(0)
        normals.SetConsistency(1)
        normals.SplittingOff()
        normals.Update()

        return normals.GetOutput()

    def extractNonManifoldEdges(self, polyData, nonManifoldEdgesPolyData=None):
        '''
        Returns non-manifold edge center positions.
        nonManifoldEdgesPolyData: optional vtk.vtkPolyData() input, if specified then a polydata is returned that contains the edges
        '''
        import vtkvmtkDifferentialGeometryPython as vtkvmtkDifferentialGeometry
        neighborhoods = vtkvmtkDifferentialGeometry.vtkvmtkNeighborhoods()
        neighborhoods.SetNeighborhoodTypeToPolyDataManifoldNeighborhood()
        neighborhoods.SetDataSet(polyData)
        neighborhoods.Build()

        polyData.BuildCells()
        polyData.BuildLinks(0)

        edgeCenterPositions = []

        neighborCellIds = vtk.vtkIdList()
        nonManifoldEdgeLines = vtk.vtkCellArray()
        points = polyData.GetPoints()
        for i in range(neighborhoods.GetNumberOfNeighborhoods()):
            neighborhood = neighborhoods.GetNeighborhood(i)
            for j in range(neighborhood.GetNumberOfPoints()):
                neighborId = neighborhood.GetPointId(j)
                if i < neighborId:
                    neighborCellIds.Initialize()
                    polyData.GetCellEdgeNeighbors(-1, i, neighborId, neighborCellIds)
                    if neighborCellIds.GetNumberOfIds() > 2:
                        nonManifoldEdgeLines.InsertNextCell(2)
                        nonManifoldEdgeLines.InsertCellPoint(i)
                        nonManifoldEdgeLines.InsertCellPoint(neighborId)
                        p1 = points.GetPoint(i)
                        p2 = points.GetPoint(neighborId)
                        edgeCenterPositions.append([(p1[0]+p2[0])/2.0, (p1[1]+p2[1])/2.0, (p1[2]+p2[2])/2.0])

        if nonManifoldEdgesPolyData:
            pointsCopy = vtk.vtkPoints()
            pointsCopy.DeepCopy(polyData.GetPoints())
            nonManifoldEdgesPolyData.SetPoints(pointsCopy)
            nonManifoldEdgesPolyData.SetLines(nonManifoldEdgeLines)

        return edgeCenterPositions

    def startPointIndexFromEndPointsMarkupsNode(self, endPointsMarkupsNode):
        """Return start point index from endpoint markups node.
        Endpoint is the first unselected control point. If none of them is unselected then
        the first control point.
        """
        numberOfControlPoints = endPointsMarkupsNode.GetNumberOfControlPoints()
        if numberOfControlPoints == 0:
            return -1
        for controlPointIndex in range(numberOfControlPoints):
            if not endPointsMarkupsNode.GetNthControlPointSelected(controlPointIndex):
                # Found a non-selected node, this is the starting point
                return controlPointIndex
        # All points are selected, use the first one as start point
        return 0

    def extractNetwork(self, surfacePolyData, endPointsMarkupsNode):
        """
        Extract centerline network from surfacePolyData
        :param surfacePolyData: input surface
        :param endPointsMarkupsNode: markup node containing preferred branch starting point
        :return: polydata containing vessel centerlines
        """
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        import vtkvmtkMiscPython as vtkvmtkMisc

        # Decimate
        # It seems that decimation at this stage is not necessary (decimation in preprocessing is enough).
        # By not decimating here, we can keep th network and centerline extraction results more similar.
        # If network extraction is too slow then one can experiment with this flag.
        decimate = False
        if decimate:
            decimationFilter = vtk.vtkDecimatePro()
            decimationFilter.SetInputData(surfacePolyData)
            decimationFilter.SetTargetReduction(0.99)
            decimationFilter.SetBoundaryVertexDeletion(0)
            decimationFilter.PreserveTopologyOn()
            decimationFilter.Update()

        # Clean and triangulate
        cleaner = vtk.vtkCleanPolyData()
        if decimate:
            cleaner.SetInputData(decimationFilter.GetOutput())
        else:
            cleaner.SetInputData(surfacePolyData)
        triangleFilter = vtk.vtkTriangleFilter()
        triangleFilter.SetInputConnection(cleaner.GetOutputPort())
        triangleFilter.Update()
        simplifiedPolyData = triangleFilter.GetOutput()

        # Cut hole at start position
        if endPointsMarkupsNode and endPointsMarkupsNode.GetNumberOfControlPoints() > 0:
            startPosition = [0, 0, 0]
            endPointsMarkupsNode.GetNthControlPointPosition(
                self.startPointIndexFromEndPointsMarkupsNode(endPointsMarkupsNode), startPosition)
        else:
            # If no endpoints are specific then use the closest point to a corner
            bounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            simplifiedPolyData.GetBounds(bounds)
            startPosition = [bounds[0], bounds[2], bounds[4]]
        self.openSurfaceAtPoint(simplifiedPolyData, startPosition)

        # Extract network
        networkExtraction = vtkvmtkMisc.vtkvmtkPolyDataNetworkExtraction()
        networkExtraction.SetInputData(simplifiedPolyData)
        networkExtraction.SetAdvancementRatio(1.05)
        networkExtraction.SetRadiusArrayName(self.radiusArrayName)
        networkExtraction.SetTopologyArrayName(self.topologyArrayName)
        networkExtraction.SetMarksArrayName(self.marksArrayName)
        networkExtraction.Update()

        return networkExtraction.GetOutput()

    def extractCenterline(self, surfacePolyData, endPointsMarkupsNode):
        """Compute centerline.
        This is more robust and accurate but takes longer than the network extraction.
        :param surfacePolyData:
        :param endPointsMarkupsNode:
        :return:
        """

        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        import vtkvmtkMiscPython as vtkvmtkMisc

        # Cap all the holes that are in the mesh that are not marked as endpoints
        # Maybe this is not needed.
        capDisplacement = 0.0
        surfaceCapper = vtkvmtkComputationalGeometry.vtkvmtkCapPolyData()
        surfaceCapper.SetInputData(surfacePolyData)
        surfaceCapper.SetDisplacement(capDisplacement)
        surfaceCapper.SetInPlaneDisplacement(capDisplacement)
        surfaceCapper.Update()

        if not endPointsMarkupsNode or endPointsMarkupsNode.GetNumberOfControlPoints() < 2:
            raise ValueError("At least two endpoints are needed for centerline extraction")

        tubePolyData = surfaceCapper.GetOutput()
        pos = [0.0, 0.0, 0.0]
        # It seems that vtkvmtkComputationalGeometry does not need holes (unlike network extraction, which does need one hole)
        # # Punch holes at surface endpoints to have tubular structure
        # tubePolyData = surfaceCapper.GetOutput()
        # numberOfEndpoints = endPointsMarkupsNode.GetNumberOfControlPoints()
        # for pointIndex in range(numberOfEndpoints):
        #     endPointsMarkupsNode.GetNthControlPointPosition(pointIndex, pos)
        #     self.openSurfaceAtPoint(tubePolyData, pos)

        numberOfControlPoints = endPointsMarkupsNode.GetNumberOfControlPoints()
        foundStartPoint = False
        for controlPointIndex in range(numberOfControlPoints):
            if not endPointsMarkupsNode.GetNthControlPointSelected(controlPointIndex):
                foundStartPoint = True
                break

        sourceIdList = vtk.vtkIdList()
        targetIdList = vtk.vtkIdList()

        pointLocator = vtk.vtkPointLocator()
        pointLocator.SetDataSet(tubePolyData)
        pointLocator.BuildLocator()

        for controlPointIndex in range(numberOfControlPoints):
            isTarget = endPointsMarkupsNode.GetNthControlPointSelected(controlPointIndex)
            if not foundStartPoint and controlPointIndex == 0:
                # If no start point found then use the first point as source
                isTarget = False
            endPointsMarkupsNode.GetNthControlPointPosition(controlPointIndex, pos)
            # locate the point on the surface
            pointId = pointLocator.FindClosestPoint(pos)
            if isTarget:
                targetIdList.InsertNextId(pointId)
            else:
                sourceIdList.InsertNextId(pointId)

        slicer.tubePolyData = tubePolyData

        centerlineFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataCenterlines()
        centerlineFilter.SetInputData(tubePolyData)
        centerlineFilter.SetSourceSeedIds(sourceIdList)
        centerlineFilter.SetTargetSeedIds(targetIdList)
        centerlineFilter.SetRadiusArrayName(self.radiusArrayName)
        centerlineFilter.SetCostFunction('1/R')  # this makes path search prefer go through points with large radius
        centerlineFilter.SetFlipNormals(False)
        centerlineFilter.SetAppendEndPointsToCenterlines(0)
        centerlineFilter.SetSimplifyVoronoi(1)  # this slightly improves connectivity
        centerlineFilter.SetCenterlineResampling(0)
        centerlineFilter.SetResamplingStepLength(1.0)
        centerlineFilter.Update()

        centerlinePolyData = vtk.vtkPolyData()
        centerlinePolyData.DeepCopy(centerlineFilter.GetOutput())

        voronoiDiagramPolyData = vtk.vtkPolyData()
        voronoiDiagramPolyData.DeepCopy(centerlineFilter.GetVoronoiDiagram())

        logging.debug("End of Centerline Computation..")
        return centerlinePolyData, voronoiDiagramPolyData

    def openSurfaceAtPoint(self, polyData, holePosition=None, holePointIndex=None):
        '''
        Modifies the polyData by cutting a hole at the given position.
        '''

        if holePointIndex is None:
            pointLocator = vtk.vtkPointLocator()
            pointLocator.SetDataSet(polyData)
            pointLocator.BuildLocator()
            # find the closest point to the desired hole position
            holePointIndex = pointLocator.FindClosestPoint(holePosition)

        if holePointIndex < 0:
            # Calling GetPoint(-1) would crash the application
            raise ValueError("openSurfaceAtPoint failed: empty input polydata")

        # Tell the polydata to build 'upward' links from points to cells
        polyData.BuildLinks()
        # Mark cells as deleted
        cellIds = vtk.vtkIdList()
        polyData.GetPointCells(holePointIndex, cellIds)
        removeFirstCell = True
        if removeFirstCell:
            # remove first cell only (smaller hole)
            if cellIds.GetNumberOfIds() > 0:
                polyData.DeleteCell(cellIds.GetId(0))
                polyData.RemoveDeletedCells()
        else:
            # remove all cells
            for cellIdIndex in range(cellIds.GetNumberOfIds()):
                polyData.DeleteCell(cellIds.GetId(cellIdIndex))
            polyData.RemoveDeletedCells()

    def getEndPoints(self, inputNetworkPolyData, startPointPosition):
        '''
        Clips the surfacePolyData on the endpoints identified using the networkPolyData.
        If startPointPosition is specified then start point will be the closest point to that position.
        Returns list of endpoint positions. Largest radius point is be the first in the list.
        '''
        try:
            import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
            import vtkvmtkMiscPython as vtkvmtkMisc
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInputData(inputNetworkPolyData)
        cleaner.Update()
        network = cleaner.GetOutput()
        network.BuildCells()
        network.BuildLinks(0)

        networkPoints = network.GetPoints()
        radiusArray = network.GetPointData().GetArray(self.radiusArrayName)

        startPointId = -1
        maxRadius = 0
        minDistance2 = 0

        endpointIds = vtk.vtkIdList()
        for i in range(network.GetNumberOfCells()):
            numberOfCellPoints = network.GetCell(i).GetNumberOfPoints()
            if numberOfCellPoints < 2:
                continue

            for pointIndex in [0, numberOfCellPoints - 1]:
                pointId = network.GetCell(i).GetPointId(pointIndex)
                pointCells = vtk.vtkIdList()
                network.GetPointCells(pointId, pointCells)
                if pointCells.GetNumberOfIds() == 1:
                    endpointIds.InsertUniqueId(pointId)
                    if startPointPosition is not None:
                        # find start point based on position
                        position = networkPoints.GetPoint(pointId)
                        distance2 = vtk.vtkMath.Distance2BetweenPoints(position, startPointPosition)
                        if startPointId < 0 or distance2 < minDistance2:
                            minDistance2 = distance2
                            startPointId = pointId
                    else:
                        # find start point based on radius
                        radius = radiusArray.GetValue(pointId)
                        if startPointId < 0 or radius > maxRadius:
                            maxRadius = radius
                            startPointId = pointId

        endpointPositions = []
        numberOfEndpointIds = endpointIds.GetNumberOfIds()
        if numberOfEndpointIds == 0:
            return endpointPositions
        # add the largest radius point first
        endpointPositions.append(networkPoints.GetPoint(startPointId))
        # add all the other points
        for pointIdIndex in range(numberOfEndpointIds):
            pointId = endpointIds.GetId(pointIdIndex)
            if pointId == startPointId:
                # already added
                continue
            endpointPositions.append(networkPoints.GetPoint(pointId))

        return endpointPositions

    def createCurveTreeFromCenterline(self, centerlinePolyData, centerlineCurveNode=None, quantificationResultsTableNode=None):

        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

        branchExtractor = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchExtractor()
        branchExtractor.SetInputData(centerlinePolyData)
        branchExtractor.SetBlankingArrayName(self.blankingArrayName)
        branchExtractor.SetRadiusArrayName(self.radiusArrayName)
        branchExtractor.SetGroupIdsArrayName(self.groupIdsArrayName)
        branchExtractor.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
        branchExtractor.SetTractIdsArrayName(self.tractIdsArrayName)
        branchExtractor.Update()
        centerlines = branchExtractor.GetOutput()

        mergeCenterlines = vtkvmtkComputationalGeometry.vtkvmtkMergeCenterlines()
        mergeCenterlines.SetInputData(centerlines)
        mergeCenterlines.SetRadiusArrayName(self.radiusArrayName)
        mergeCenterlines.SetGroupIdsArrayName(self.groupIdsArrayName)
        mergeCenterlines.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
        mergeCenterlines.SetTractIdsArrayName(self.tractIdsArrayName)
        mergeCenterlines.SetBlankingArrayName(self.blankingArrayName)
        mergeCenterlines.SetResamplingStepLength(1.0)
        mergeCenterlines.SetMergeBlanked(True)
        mergeCenterlines.Update()
        mergedCenterlines = mergeCenterlines.GetOutput()

        if quantificationResultsTableNode:
            quantificationResultsTableNode.RemoveAllColumns()

            # Cell index column
            numberOfCells = mergedCenterlines.GetNumberOfCells()
            cellIndexArray = vtk.vtkIntArray()
            cellIndexArray.SetName("CellId")
            cellIndexArray.SetNumberOfValues(numberOfCells)
            for cellIndex in range(numberOfCells):
                cellIndexArray.SetValue(cellIndex, cellIndex)
            quantificationResultsTableNode.GetTable().AddColumn(cellIndexArray)

            # Get average radius
            pointDataToCellData = vtk.vtkPointDataToCellData()
            pointDataToCellData.SetInputData(mergedCenterlines)
            pointDataToCellData.ProcessAllArraysOff()
            pointDataToCellData.AddPointDataArray(self.radiusArrayName)
            pointDataToCellData.Update()
            averageRadiusArray = pointDataToCellData.GetOutput().GetCellData().GetArray(self.radiusArrayName)
            quantificationResultsTableNode.GetTable().AddColumn(averageRadiusArray)

            # Get length, curvature, torsion, tortuosity
            centerlineBranchGeometry = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchGeometry()
            centerlineBranchGeometry.SetInputData(mergedCenterlines)
            centerlineBranchGeometry.SetRadiusArrayName(self.radiusArrayName)
            centerlineBranchGeometry.SetGroupIdsArrayName(self.groupIdsArrayName)
            centerlineBranchGeometry.SetBlankingArrayName(self.blankingArrayName)
            centerlineBranchGeometry.SetLengthArrayName(self.lengthArrayName)
            centerlineBranchGeometry.SetCurvatureArrayName(self.curvatureArrayName)
            centerlineBranchGeometry.SetTorsionArrayName(self.torsionArrayName)
            centerlineBranchGeometry.SetTortuosityArrayName(self.tortuosityArrayName)
            centerlineBranchGeometry.SetLineSmoothing(False)
            #centerlineBranchGeometry.SetNumberOfSmoothingIterations(100)
            #centerlineBranchGeometry.SetSmoothingFactor(0.1)
            centerlineBranchGeometry.Update()
            centerlineProperties = centerlineBranchGeometry.GetOutput()
            for columnName in [self.lengthArrayName, self.curvatureArrayName, self.torsionArrayName, self.tortuosityArrayName]:
                quantificationResultsTableNode.GetTable().AddColumn(centerlineProperties.GetPointData().GetArray(columnName))

            # Get branch start and end positions
            startPointPositions = vtk.vtkDoubleArray()
            startPointPositions.SetName("StartPointPosition")
            endPointPositions = vtk.vtkDoubleArray()
            endPointPositions.SetName("EndPointPosition")
            for positions in [startPointPositions, endPointPositions]:
                positions.SetNumberOfComponents(3)
                positions.SetComponentName(0, "R")
                positions.SetComponentName(1, "A")
                positions.SetComponentName(2, "S")
                positions.SetNumberOfTuples(numberOfCells)
            for cellIndex in range(numberOfCells):
                pointIds = mergedCenterlines.GetCell(cellIndex).GetPointIds()
                startPointPosition = [0, 0, 0]
                if pointIds.GetNumberOfIds() > 0:
                    mergedCenterlines.GetPoint(pointIds.GetId(0), startPointPosition)
                if pointIds.GetNumberOfIds() > 1:
                    endPointPosition = [0, 0, 0]
                    mergedCenterlines.GetPoint(pointIds.GetId(pointIds.GetNumberOfIds()-1), endPointPosition)
                else:
                    endPointPosition = startPointPosition
                startPointPositions.SetTuple3(cellIndex, *startPointPosition)
                endPointPositions.SetTuple3(cellIndex, *endPointPosition)
            quantificationResultsTableNode.GetTable().AddColumn(startPointPositions)
            quantificationResultsTableNode.GetTable().AddColumn(endPointPositions)

            quantificationResultsTableNode.GetTable().Modified()

        if centerlineCurveNode:
            # Delete existing children of the output markups curve
            shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
            curveItem = shNode.GetItemByDataNode(centerlineCurveNode)
            shNode.RemoveItemChildren(curveItem)
            # Add centerline widgets
            self.processedCellIds = []
            self._addCenterline(mergedCenterlines, replaceCurve=centerlineCurveNode)

    def _addCenterline(self, mergedCenterlines, baseName=None, cellId=0, parentItem=None, replaceCurve=None):
        # Add current cell as a curve node
        assignAttribute = vtk.vtkAssignAttribute()
        assignAttribute.SetInputData(mergedCenterlines)
        assignAttribute.Assign(self.groupIdsArrayName, vtk.vtkDataSetAttributes.SCALARS,
                               vtk.vtkAssignAttribute.CELL_DATA)
        thresholder = vtk.vtkThreshold()
        thresholder.SetInputConnection(assignAttribute.GetOutputPort())
        groupId = mergedCenterlines.GetCellData().GetArray(self.groupIdsArrayName).GetValue(cellId)
        thresholder.ThresholdBetween(groupId - 0.5, groupId + 0.5)
        thresholder.Update()

        if replaceCurve:
            # update existing curve widget
            curveNode = replaceCurve
            if baseName is None:
                baseName = curveNode.GetName()
                # Parse name, if it ends with a number in a parenthesis ("branch (1)") then assume it contains
                # the cell index and remove it to get the base name
                import re
                matched = re.match("(.+) \([0-9]+\)", baseName)
                if matched:
                    baseName = matched[1]
            curveNode.SetName("{0} ({1})".format(baseName, cellId))
        else:
            if baseName is None:
                baseName = "branch"
            curveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", "{0} ({1})".format(baseName, cellId))

        curveNode.SetAttribute("CellId", str(cellId))
        curveNode.SetAttribute("GroupId", str(groupId))
        curveNode.SetControlPointPositionsWorld(thresholder.GetOutput().GetPoints())
        slicer.modules.markups.logic().SetAllMarkupsVisibility(curveNode, False)
        slicer.app.processEvents()
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        curveItem = shNode.GetItemByDataNode(curveNode)
        if parentItem is not None:
            shNode.SetItemParent(curveItem, parentItem)
        # Add connecting cells
        self.processedCellIds.append(cellId)
        cellPoints = mergedCenterlines.GetCell(cellId).GetPointIds()
        endPointIndex = cellPoints.GetId(cellPoints.GetNumberOfIds() - 1)
        numberOfCells = mergedCenterlines.GetNumberOfCells()
        branchIndex = 0
        for neighborCellIndex in range(numberOfCells):
            if neighborCellIndex in self.processedCellIds:
                continue
            if endPointIndex != mergedCenterlines.GetCell(neighborCellIndex).GetPointIds().GetId(0):
                continue
            branchIndex += 1
            self._addCenterline(mergedCenterlines, baseName, neighborCellIndex, curveItem)

#
# ExtractCenterlineTest
#

class ExtractCenterlineTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_ExtractCenterline1()

    def test_ExtractCenterline1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData
        inputVolume = SampleData.downloadFromURL(
          nodeNames='MRHead',
          fileNames='MR-Head.nrrd',
          uris='https://github.com/Slicer/SlicerTestingData/releases/download/MD5/39b01631b7b38232a220007230624c8e',
          checksums='MD5:39b01631b7b38232a220007230624c8e')[0]
        self.delayDisplay('Finished with download and loading')

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 279)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 50

        # Test the module logic

        logic = ExtractCenterlineLogic()

        # Test algorithm with non-inverted threshold
        logic.run(inputVolume, outputVolume, threshold, True)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.run(inputVolume, outputVolume, threshold, False)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay('Test passed')
