# -*- coding: utf-8 -*-
import os
import shutil
from os import makedirs                       
from os.path import expanduser
import traceback, sys
from time import sleep
import numpy as np
import subprocess
import glob
#from datetime import datetime 
from osgeo import osr, gdal, ogr
import xml.etree.cElementTree as etree

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

from qgis.utils import iface
from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtGui import QColor, QBrush
#from qgis.core import Qgis
#from qgis.core import QgsDataSourceUri 
from qgis.core import QgsProject, QgsRasterLayer, QgsLayerTreeLayer, QgsColorRampShader, QgsSingleBandPseudoColorRenderer, QgsRasterShader, QgsVectorLayer, QgsGradientColorRamp # , QgsRectangle
#from qgis.core import QgsPointXY, QgsWkbTypes, QgsGeometry, QgsPoint
from qgis.core import QgsGraduatedSymbolRenderer, QgsCategorizedSymbolRenderer, QgsMarkerSymbol, QgsRendererCategory, QgsRendererRange, QgsClassificationRange  #, QgsFillSymbol, QgsMessageLog
from qgis.core import QgsCoordinateReferenceSystem, QgsApplication # , QgsTask
from qgis.analysis import QgsAlignRaster
from PyQt5.QtCore import QThreadPool, QRunnable, QObject, pyqtSlot, QThread, QTimer

from PyQt5 import QtCore #, QtWidgets
from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QMenu, QHeaderView, QColorDialog, QTreeWidgetItem # , QAction, QTableView
from PyQt5.QtGui import QPixmap, QFont # , QIcon, QMenu

from .import_tools import ImportInstall

if (sys.version_info.major, sys.version_info.minor) <= (3,7):
    ImportInstall('netCDF4==1.5.5.1')
else:
    ImportInstall('netCDF4')
from netCDF4 import Dataset, num2date #, date2num
    
# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _  = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'import_netcdf_dialog_base.ui'))


class NetCDF2GISDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(NetCDF2GISDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setWindowFlags(QtCore.Qt.WindowCloseButtonHint | QtCore.Qt.WindowMinimizeButtonHint)
        self.setupUi(self)
        # 
        logo = QPixmap(os.path.join(os.path.dirname(__file__), 'Noveltis.jpg')) 
        logo = logo.scaled(140, 50, Qt.KeepAspectRatio, Qt.FastTransformation)
        self.label_logo.setPixmap(logo)
        logo2 = QPixmap(os.path.join(os.path.dirname(__file__), 'Mercator_499-499-max.jpg')) # Mercator_302-302-max.png # Mercator_499-499-max.jpg
        logo2 = logo2.scaled(100, 100, Qt.KeepAspectRatio, Qt.FastTransformation)
        self.label_logo_Mercator.setPixmap(logo2)
        bg = QPixmap(os.path.join(os.path.dirname(__file__), 'ocean.jpg')) 
#        bg = bg.scaled(970, 670, Qt.KeepAspectRatio, Qt.FastTransformation)
        self.label_bg.setPixmap(bg)
        self.textEdit_about.setDisabled(True)
        
        self.Button_clear_bottom_line.clicked.connect(self.clear_bottom_line)
        self.Button_quit.clicked.connect(self.close)
        self.Button_add_file.clicked.connect(self.new_file_selection)
        self.Button_supress_file.clicked.connect(self.remove_file)
        # Init Option tab
        self.Button_clean_temp.clicked.connect(self.clean_temp_dir)
        self.Button_temp_dir.clicked.connect(self.select_temp_dir)
        self.Button_in_dir.clicked.connect(self.select_in_dir)
        self.Button_out_dir.clicked.connect(self.select_out_dir)

        self.tableWidget_files.itemClicked.connect(self.check_file_selection)
        self.tableWidget_files.setAcceptDrops(True)
        self.tabWidget_files.setCurrentIndex(0)
        self.dict_var_selected_date_list = {}
        
        self.tableWidget_files.viewport().installEventFilter(self)
        types = ['text/uri-list']
        types.extend(self.tableWidget_files.mimeTypes())
        self.tableWidget_files.mimeTypes = lambda: types
        
        self.proj = 4326
        self.Selected_file = None
        self.files = []
        self.lineEdit_temp_dir.setText(os.path.join(os.path.dirname(__file__), 'tmp'))
        self.Selected_layers = []
        self.layers = {}
#        self.qgis_project = QgsApplication([], True)
#        self.qgis_project.layerTreeRoot()
#        iface.layerTreeView()
        self.Selected_variables = []
        self.synchronized_variables = {}
        self.variable_windows = []
        self.other_windows = []
        self.tabWidget_variables.setCurrentIndex(0)
#        self.tableWidget_variables.itemClicked.connect(self.select_variable)
#        self.tableWidget_variables.itemActivated.connect(self.check_variable_selection)
        self.tableWidget_variables.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tableWidget_variables.customContextMenuRequested.connect(self.Variable_Menu)
        self.tableWidget_variables.viewport().installEventFilter(self)
        self.comboBox_projection.activated.connect(self.set_projection)
        # Read preference file
        self.preference_dict = {}
        self.read_preferences()
        # Update projection Combo box
        self.update_projection_list()
        # Setup QGIS project
        self.qgis_project = QgsProject.instance()
        self.qgis_project.layerTreeRoot()
        self.set_projection()
        
        # Display welcome message
        self.message_bottom_display.setText("Welcome! Select NetCDF files using the '+' button (multiple selection supported). CRS is set to WGS84 (EPSG:4326) by default and will remain unchanged. Manually select different CRS if needed.")
        # Setup Context menu
        self.tableWidget_layers.itemClicked.connect(self.check_layer_selection)
        self.tableWidget_layers.itemActivated.connect(self.check_layer_selection)
#        self.layer_dict = {}
        self.tableWidget_layers.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tableWidget_layers.customContextMenuRequested.connect(self.Layer_Menu)
        self.tableWidget_layers.viewport().installEventFilter(self)
        
#    def dropEvent(self, event):
#        if event.mimeData().hasUrls:
#            event.setDropAction(QtCore.Qt.CopyAction)
#            event.accept()
#            files = [u.toLocalFile() for u in event.mimeData().urls()]
#            for f in files:
#                print(f)


    def eventFilter(self, source, event):
        '''and
            source is self.tableWidget_files.viewport()
        '''
        if (event.type() == QtCore.QEvent.Drop and
            event.mimeData().hasUrls() ):
            for url in event.mimeData().urls():
                self.files.append(url.toLocalFile())
                self.update_file_table()
            return True
    
        if(event.type() == QtCore.QEvent.MouseButtonPress and
           event.buttons() == QtCore.Qt.RightButton and
           source is self.tableWidget_layers.viewport()):
            item = self.tableWidget_layers.itemAt(event.pos())
#            print('Global Pos:', event.globalPos())
            if item is not None:
#                print('Table Item:', item.row(), item.column())
                self.menu = QMenu(self)
                self.action_check = self.menu.addAction('Check in QGIS')
                self.action_uncheck = self.menu.addAction('Uncheck in QGIS')
                self.menu.addAction('------------')
                self.action_remove = self.menu.addAction('Remove from list')
                self.action_group = self.menu.addAction('Remove Group')
                self.menu.addAction('------------')
                self.action_save = self.menu.addAction('Save as TIFF')
                self.action_align = self.menu.addAction('Align Rasters')
                self.action_vect = self.menu.addAction('Vectorize')

        if(event.type() == QtCore.QEvent.MouseButtonPress and
           event.buttons() == QtCore.Qt.RightButton and
           source is self.tableWidget_variables.viewport()):
            item = self.tableWidget_variables.itemAt(event.pos())
#            print('Global Pos:', event.globalPos())
            if item is not None:
#                print('Table Item:', item.row(), item.column())
                self.menu = QMenu(self)
                self.action_display = self.menu.addAction('Add Layer')
                
        return super(NetCDF2GISDialog, self).eventFilter(source, event)


    def Layer_Menu(self, pos):
        ''' Generate the rightclick menu on the Layer table widget
        '''
#        print("pos======",pos)
        action = self.menu.exec_(self.tableWidget_layers.mapToGlobal(pos))
        
        # Actions for Layers
        if action is not None and action == self.action_check:
#            print("***MENU*** Remove")
            self.check_layer()
        if action is not None and action == self.action_uncheck:
#            print("***MENU*** Remove")
            self.uncheck_layer()
        if action is not None and action == self.action_remove:
#            print("***MENU*** Remove")
            self.delete_layer()
        elif action is not None and action == self.action_save:
#            print("***MENU*** Save")
            self.save_dialog()
        elif action is not None and action == self.action_group:
#            print("***MENU*** Align")
            self.delete_layer_group()
        elif action is not None and action == self.action_align:
#            print("***MENU*** Align")
            self.align_dialog()
        elif action is not None and action == self.action_vect:
#            print("***MENU*** Vectorize")
            self.vector_dialog()

        
    def Variable_Menu(self, pos):
        ''' Generate the rightclick menu on the Variable table widget
        '''
        print("DEBUG: Variable_Menu called")
        
        # Create menu here to ensure it's always initialized
        self.menu = QMenu(self)
        self.action_display = self.menu.addAction('Add Layer')
        
        action = self.menu.exec_(self.tableWidget_variables.mapToGlobal(pos))
        
        # Actions for Variables
        if action is not None and action == self.action_display:
            print("DEBUG: Add Layer action selected")
            self.display_variable(None, True)
        else:
            print("DEBUG: No action or different action selected")
    
    def set_projection(self):
        '''
        Sets the projection for NetCDF data processing, but does NOT change the QGIS project CRS.
        This allows users to manually specify the CRS for their NetCDF files.
        '''
        if not self.comboBox_projection.currentData():
            # If no projection is selected, default to WGS84
            self.proj = 4326
            self.message_bottom_display.setText("NetCDF data CRS set to WGS84 (EPSG:4326) - Project CRS unchanged")
        else:
            self.proj = int(self.comboBox_projection.currentData())
            self.message_bottom_display.setText(f"NetCDF data CRS set to {self.comboBox_projection.currentText()} (EPSG:{self.proj}) - Project CRS unchanged")
            
        # Store the current projection selection for later use
        self.current_projection = self.comboBox_projection.currentText()
        self.current_epsg = self.proj
        
        # DO NOT automatically change the QGIS project CRS
        # The project CRS should remain as set by the user
        # Only store the CRS for NetCDF data processing
        try:
            if isinstance(self.proj, int):
                # Create CRS object for validation and later use
                self.netcdf_crs = QgsCoordinateReferenceSystem(f"EPSG:{self.proj}")
            else:
                self.netcdf_crs = QgsCoordinateReferenceSystem()
                self.netcdf_crs.createFromUserInput(str(self.proj))
            
            if not self.netcdf_crs.isValid():
                print(f"Warning: Invalid CRS for projection {self.proj}, using default EPSG:4326")
                self.netcdf_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                self.proj = 4326
                
            print(f"NetCDF data will be processed using CRS: {self.netcdf_crs.authid()} - {self.netcdf_crs.description()}")
            
        except Exception as e:
            print(f"Error validating projection {self.proj}: {e}, using default EPSG:4326")
            self.netcdf_crs = QgsCoordinateReferenceSystem("EPSG:4326")
            self.proj = 4326
        
          
    def update_variables(self, file=None):
        '''
        Function to update variables display and extract coordinate information from NetCDF file
        '''
        # Initialize coordinate variables to handle cases where the NetCDF file doesn't have the expected dimensions
        self.x_min = None
        self.x_max = None
        self.y_min = None
        self.y_max = None
        self.x_res = None
        self.y_res = None
        self.lons = None
        self.lats = None
        self.dates = None
        self.depths = None
        self.temp_dir = os.path.join(os.path.dirname(__file__), 'tmp') if not hasattr(self, 'temp_dir') else self.temp_dir
        
        if file is None:
            n_file = self.Selected_file
        else:
            n_file = file
        try:
            self.ds = Dataset(n_file, 'r')
        except Exception as e:
            QMessageBox.warning(self, u'Warning', u"Please select a valid NetCDF file. Error: " + str(e))
            return
          
        # Dimensions
        self.tableWidget_variables.setSortingEnabled(False)
        self.tableWidget_variables.setRowCount(len(self.ds.variables))
        
        # Set up table columns for enhanced information
        headers = ['Variable', 'Dimensions', 'Units', 'Description', 'Min/Max', 'Shape', 'Type']
        self.tableWidget_variables.setColumnCount(len(headers))
        self.tableWidget_variables.setHorizontalHeaderLabels(headers)
        
        i=0
        
        font1 = QFont()
        font1.setItalic(True)
        font2 = QFont()
        font2.setBold(True)
        
        # List of possible dimension names for coordinates
        lon_names = ['lon', 'lons', 'longitude', 'longitudes', 'x', 'nav_lon', 'nav_longitude', 'xc', 'x_c']
        lat_names = ['lat', 'lats', 'latitude', 'latitudes', 'y', 'nav_lat', 'nav_latitude', 'yc', 'y_c']
        time_names = ['time', 'date', 'times', 'dates', 't', 'time_counter']
        depth_names = ['depth', 'depths', 'z', 'level', 'levels', 'deptht', 'depthw']
        
        # Also check for x/y dimensions in the dataset
        x_dim_found = any(dim.lower() == 'x' for dim in self.ds.dimensions)
        y_dim_found = any(dim.lower() == 'y' for dim in self.ds.dimensions)
        
        if x_dim_found and 'x' not in self.ds.variables:
            self.message_bottom_display.setText("Found 'x' dimension but no corresponding variable. Will try to use longitude.")
        
        if y_dim_found and 'y' not in self.ds.variables:
            self.message_bottom_display.setText("Found 'y' dimension but no corresponding variable. Will try to use latitude.")
        
        for var in self.ds.variables:
            lon_dim  = False
            lat_dim  = False
            time_dim = False
            z_dim    = False
            
            # Check dimensions
            for dim in self.ds.variables[var].dimensions:
                if dim.lower() in lon_names:
                   lon_dim = True
                elif dim.lower() in lat_names:
                   lat_dim = True
                elif dim.lower() in time_names:
                   time_dim = True
                elif dim.lower() in depth_names:
                   z_dim = True
                   
            # If the variable itself is a coordinate, mark it appropriately
            if var.lower() in lon_names:
                lon_dim = True
            elif var.lower() in lat_names:
                lat_dim = True

            # Check for common coordinate variable naming patterns
            if any(x in var.lower() for x in ['east', 'lon', 'long', 'longitude', 'x']):
                lon_dim = True
            elif any(x in var.lower() for x in ['north', 'lat', 'latitude', 'y']):
                lat_dim = True

            # Create and set up dimension cell display
            dim_cell = QtWidgets.QTextBrowser()
            dim_cell.setFrameShape(QtWidgets.QFrame.NoFrame)
            dim_cell.setFrameShadow(QtWidgets.QFrame.Plain)
            dim_text = str(self.ds.variables[var].dimensions).replace("(", "").replace(")", "").replace("'", "").replace(" ", "").replace(",", "\n")
            dim_cell.setText(dim_text)
            dim_cell.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            dim_cell.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            dim_cell.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
            dim_cell.setStyleSheet("background-color: rgba(220, 220, 220, 0);")
            if lon_dim and lat_dim:
                dim_cell.setFont(font2)
            else:
                dim_cell.setFont(font1)
                
            # Set up variable display in table
            self.tableWidget_variables.setItem(i, 0, QTableWidgetItem(var))
            if lon_dim and lat_dim:
                self.tableWidget_variables.item(i,0).setFont(font2)
            else:
                self.tableWidget_variables.item(i,0).setFont(font1)
                
            self.tableWidget_variables.setCellWidget(i, 1, dim_cell)
            
            # Try to get and display units
            try:
                self.tableWidget_variables.setItem(i, 2, QTableWidgetItem(self.ds.variables[var].units))
                if lon_dim and lat_dim:
                    self.tableWidget_variables.item(i,2).setFont(font2)
                else:
                    self.tableWidget_variables.item(i,2).setFont(font1)
            except:
                pass
                
            # Try to get and display standard_name or long_name
            description = ""
            try:
                description = self.ds.variables[var].standard_name
            except:
                try:
                    description = self.ds.variables[var].long_name
                except:
                    description = "No description"
                    
            self.tableWidget_variables.setItem(i, 3, QTableWidgetItem(description))
            if lon_dim and lat_dim:
                self.tableWidget_variables.item(i,3).setFont(font2)
            else:
                self.tableWidget_variables.item(i,3).setFont(font1)
            
            # Calculate and display min/max values for data variables
            min_max_text = ""
            try:
                # Only calculate statistics for non-coordinate variables with data
                if (lon_dim and lat_dim and 
                    var.lower() not in lon_names + lat_names + time_names + depth_names):
                    
                    # Get a sample of data to calculate statistics efficiently
                    var_data = self.ds.variables[var]
                    data_shape = var_data.shape
                    
                    # For large datasets, sample a subset for statistics
                    if len(data_shape) > 2 and data_shape[0] > 1:
                        # Take first time/depth slice
                        sample_data = var_data[0]
                    else:
                        sample_data = var_data[:]
                    
                    # Calculate statistics
                    flat_data = sample_data.flatten()
                    valid_data = flat_data[~np.isnan(flat_data)]
                    
                    if len(valid_data) > 0:
                        min_val = np.min(valid_data)
                        max_val = np.max(valid_data)
                        min_max_text = f"{min_val:.3f} / {max_val:.3f}"
                    else:
                        min_max_text = "No valid data"
                        
            except Exception as e:
                min_max_text = "Error calculating"
                
            self.tableWidget_variables.setItem(i, 4, QTableWidgetItem(min_max_text))
            if lon_dim and lat_dim:
                self.tableWidget_variables.item(i,4).setFont(font2)
            else:
                self.tableWidget_variables.item(i,4).setFont(font1)
            
            # Display variable shape
            shape_text = str(self.ds.variables[var].shape)
            self.tableWidget_variables.setItem(i, 5, QTableWidgetItem(shape_text))
            if lon_dim and lat_dim:
                self.tableWidget_variables.item(i,5).setFont(font2)
            else:
                self.tableWidget_variables.item(i,5).setFont(font1)
            
            # Display variable data type
            dtype_text = str(self.ds.variables[var].dtype)
            self.tableWidget_variables.setItem(i, 6, QTableWidgetItem(dtype_text))
            if lon_dim and lat_dim:
                self.tableWidget_variables.item(i,6).setFont(font2)
            else:
                self.tableWidget_variables.item(i,6).setFont(font1)
            
            # Set row height based on dimensions
            self.tableWidget_variables.setRowHeight(i, len(self.ds.variables[var].dimensions)*15)

            i += 1        

            # Set auto_mask to False to avoid masked arrays
            try:
                self.ds.variables[var].set_auto_mask(False)
            except:
                pass
                
            # Process coordinate variables
            var_lower = var.lower()
            
            # Process time dimension
            if var_lower in time_names:
                try:
                    self.dates = self.get_dates(var)
                except Exception as e:
                    print(f"Error getting dates from {var}: {str(e)}")
                    
            # Process depth dimension
            elif var_lower in depth_names:
                try:
                    self.depths = self.ds.variables[var][:]
                except Exception as e:
                    print(f"Error getting depths from {var}: {str(e)}")
                    
            # Process longitude dimension
            elif var_lower in lon_names:
                try:
                    if self.lons is None:
                        self.lons = self.ds.variables[var][:]
                    else:
                        if len(self.lons.shape) == 2:
                            self.lons = self.ds.variables[var][:]
                
                    # Calculate min, max and resolution
                    if self.lons is not None:
                        self.x_min = np.nanmin(self.lons)
                        self.x_max = np.nanmax(self.lons)
                        
                        if len(self.lons.shape) == 1 and len(self.lons) > 1:
                            self.x_res = np.abs(self.lons[1] - self.lons[0])
                        else:
                            # For 2D arrays or arrays with only one element
                            self.x_res = 0.1  # Default resolution
                except Exception as e:
                    print(f"Error processing longitude from {var}: {str(e)}")

            # Process latitude dimension
            elif var_lower in lat_names:
                try:
                    if self.lats is None:
                        self.lats = self.ds.variables[var][:]
                    else:
                        if len(self.lats.shape) == 2:
                            self.lats = self.ds.variables[var][:]
                
                    # Calculate min, max and resolution
                    if self.lats is not None:
                        self.y_min = np.nanmin(self.lats)
                        self.y_max = np.nanmax(self.lats)
                        
                        if len(self.lats.shape) == 1 and len(self.lats) > 1:
                            self.y_res = np.abs(self.lats[1] - self.lats[0])
                        else:
                            # For 2D arrays or arrays with only one element
                            self.y_res = 0.1  # Default resolution
                except Exception as e:
                    print(f"Error processing latitude from {var}: {str(e)}")
                    
        # If we still don't have lat/lon information, check if the NetCDF file uses x/y as dimensions directly
        # This is common in some NetCDF formats where x/y are dimensions but not variables
        if (self.lons is None or self.lats is None) and 'x' in self.ds.dimensions and 'y' in self.ds.dimensions:
            try:
                # If x is a dimension but not a variable, create synthetic coordinates
                if self.lons is None:
                    x_size = len(self.ds.dimensions['x'])
                    self.lons = np.arange(x_size)
                    self.x_min = 0
                    self.x_max = x_size - 1
                    self.x_res = 1
                    print("Created synthetic x coordinates from dimension")
                
                # If y is a dimension but not a variable, create synthetic coordinates
                if self.lats is None:
                    y_size = len(self.ds.dimensions['y'])
                    self.lats = np.arange(y_size)
                    self.y_min = 0
                    self.y_max = y_size - 1
                    self.y_res = 1
                    print("Created synthetic y coordinates from dimension")
                
                # Make sure UI shows this info
                self.message_bottom_display.setText("Using x/y dimensions for coordinates. GeoTIFF won't have proper geocoding.")
            except Exception as e:
                print(f"Error creating synthetic coordinates from x/y dimensions: {str(e)}")
                
        # Keep the default CRS selection (WGS84) - no auto-detection
        # The user can manually change the CRS if needed using the dropdown
        print("DEBUG: Keeping default CRS selection (WGS84 EPSG:4326) - auto-detection disabled")

#        self.tableWidget_variables.resizeColumnsToContents() #.verticalHeader().resizeSections(QHeaderView.ResizeToContents)
#        self.tableWidget_variables.verticalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
#        self.tableWidget_variables.resizeRowsToContents()
        self.tableWidget_variables.setSortingEnabled(True)
        
        # Resize columns to fit content
        self.tableWidget_variables.resizeColumnsToContents()

        # Stereographic projection auto-detection removed - causes incorrect CRS selection
        # Users should manually select the appropriate CRS from the dropdown
        self.ds_proj = None
        
        # Update Metadata tab with detailed information about dimensions and coordinates
        txt = "Dimensions:\n----------\n"
        for dim in self.ds.dimensions:
            if dim in self.ds.variables:
                txt += "\t%s :\t%s\n" % (dim, len(self.ds.variables[dim]))
            else:
                txt += "\t%s :\t%s\n" % (dim, len(self.ds.dimensions[dim]))
        
        # Add coordinate information if available
        txt += "\nCoordinates:\n--------------\n"
        
        # Check if longitude coordinates were found
        if hasattr(self, 'x_min') and self.x_min is not None:
            txt += "\t%s :\t%s\n" % ("X min", self.x_min)
            txt += "\t%s :\t%s\n" % ("X max", self.x_max)
            if hasattr(self, 'x_res') and self.x_res is not None:
                txt += "\t%s :\t%s\n" % ("X resolution", self.x_res)
        else:
            txt += "\tLongitude coordinates not identified\n"
            
        # Check if latitude coordinates were found
        if hasattr(self, 'y_min') and self.y_min is not None:
            txt += "\t%s :\t%s\n" % ("Y min", self.y_min)
            txt += "\t%s :\t%s\n" % ("Y max", self.y_max)
            if hasattr(self, 'y_res') and self.y_res is not None:
                txt += "\t%s :\t%s\n" % ("Y resolution", self.y_res)
        else:
            txt += "\tLatitude coordinates not identified\n"
            
        # Additional information about time and depth dimensions
        if hasattr(self, 'dates') and self.dates is not None:
            txt += "\nTime Information:\n---------------\n"
            txt += "\tTime points: %d\n" % len(self.dates)
            if len(self.dates) > 0:
                txt += "\tFirst date: %s\n" % self.dates[0]
                txt += "\tLast date: %s\n" % self.dates[-1]
                
        if hasattr(self, 'depths') and self.depths is not None:
            txt += "\nDepth Information:\n---------------\n"
            txt += "\tDepth levels: %d\n" % len(self.depths)
            if len(self.depths) > 0:
                txt += "\tMin depth: %.2f\n" % min(self.depths)
                txt += "\tMax depth: %.2f\n" % max(self.depths)
        if hasattr(self, 'x_res') and self.x_res is not None and hasattr(self, 'y_res') and self.y_res is not None:
            txt += "\t%s :\t%s x %s\n" % ( "Resolution", self.x_res, self.y_res)
        if self.ds_proj is not None:
            txt += "\nProjection:\n--------------\n"
            txt += "\t%s\n" % (self.ds_proj) 
        txt += "\nGlobal Attributes:\n--------------\n"
        for key, att in self.ds.__dict__.items():
            txt += "%s :\n\t%s\n" % (key, att)
        self.textBrowser_metadata.setText(txt)
        
#        print(self.x_min, self.x_max, self.x_res, self.y_min, self.y_max, self.y_res)
        
        
    def get_dates(self, var):
        '''
        '''
        dates = num2date(self.ds.variables[var][:], self.ds.variables[var].units)
        # localise to UTC
#        dates = np.array([pytz.utc.localize(d) for d in dates])  
#        print(dates)
        return dates         


           
       
    def close(self):
        ''' Close the connection before deleting the instance of the object
        '''        
        buttonReply = QMessageBox.question(self, u'Import NetCDF : question', 
                                       "Are you sure you want to quit?", 
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)

        if buttonReply == QMessageBox.Yes:
            # Clean Layer Table
            self.tableWidget_layers.setRowCount(0)
            # Clean Temp dir
            self.clean_temp_dir()
            
            # Close TIFF window if open
            try:
                for variable_window in self.variable_windows:
                    variable_window.tiff_window.close()
            except:
                pass

            # Close Variable window if open
            try:
                for variable_window in self.variable_windows:
                    variable_window.close()
            except:
                pass

            super().close()


    def clean_temp_dir(self):
        ''' Delete temp files in the temp directory
        '''
        temp = glob.glob("%s/*.*" % self.lineEdit_temp_dir.text())
        for ff in temp:
            try:
                os.remove(ff)
            except:
                pass
        
        self.message_bottom_display.setText("temp file(s) deleted")
        
        
    def select_temp_dir(self):
        '''
        '''
        temp_directory = QFileDialog.getExistingDirectory(
            self,
            u"Select temporary file directory",
            expanduser('~'), # ~
            QFileDialog.ShowDirsOnly)
        
        self.lineEdit_temp_dir.setText(temp_directory)


    def select_in_dir(self):
        '''
        '''
        in_directory = QFileDialog.getExistingDirectory(
            self,
            u"Select default input directory",
            expanduser('~'), # ~
            QFileDialog.ShowDirsOnly)
        
        self.lineEdit_in_dir.setText(in_directory)


    def select_out_dir(self):
        '''
        '''
        out_directory = QFileDialog.getExistingDirectory(
            self,
            u"Select default output directory",
            expanduser('~'), # ~
            QFileDialog.ShowDirsOnly)
        
        self.lineEdit_out_dir.setText(out_directory)        
        
        
    def new_file_selection(self):
        ''' prompt a window to enable the user to select multiple files
        '''
        if self.lineEdit_in_dir.text() == "":
            tt = "~"
        else:
            tt = self.lineEdit_in_dir.text()
            
        # Use getOpenFileNames (plural) to allow multiple file selection
        nc_files, _ = QFileDialog.getOpenFileNames(self,
                            u"Select NetCDF files (multiple selection allowed)",
                            expanduser(tt), "(*.nc)")

        if nc_files:  # List is not empty
            # Update the input directory based on the first selected file
            self.lineEdit_in_dir.setText(os.path.dirname(nc_files[0]))
            
            # Add all selected files to the list
            for nc_file in nc_files:
                if nc_file not in self.files:  # Avoid duplicates
                    self.files.append(nc_file)
            
            # Set the last selected file as the current file
            self.Selected_file = nc_files[-1]
            self.update_file_table()    
            self.update_variables()
            
            # Display message about multiple files
            if len(nc_files) > 1:
                self.message_bottom_display.setText(f"Added {len(nc_files)} NetCDF files. Currently viewing: {os.path.basename(self.Selected_file)}")
            else:
                self.message_bottom_display.setText(f"Added NetCDF file: {os.path.basename(self.Selected_file)}")
        
        

    def update_file_table(self):
        ''' Update the table containing the list of input directories
        '''
        self.tabWidget_files.setCurrentIndex(0)
        self.tabWidget_variables.setCurrentIndex(0)

        self.tableWidget_files.setSortingEnabled(False)
        self.tableWidget_files.setRowCount(len(self.files))
        
        for i, dd in enumerate(self.files):
            self.tableWidget_files.setItem(i, 0, QTableWidgetItem(str(i)))
            self.tableWidget_files.setItem(i, 1, QTableWidgetItem(os.path.basename(dd)))
            self.tableWidget_files.setItem(i, 2, QTableWidgetItem(os.path.dirname(dd)))

        self.tableWidget_files.setColumnWidth(0, 15)

        try:
            self.Selected_file = dd
        except:
            pass
        
        self.nc_id = len(self.files)
        self.update_variables()


    def check_file_selection(self):
        ''' Detect the selection of path in the table
        '''
        for c in self.tableWidget_files.selectedItems():
            if c.column() == 1:
                name = c.text()
            if c.column() == 2:
                path = c.text()
            self.nc_id = c.row()

        self.Selected_file = os.path.join(path, name)
        self.message_bottom_display.setText("Selected file : %s" % self.Selected_file)
        self.update_variables()


    def remove_file(self):
        ''' 
        '''
#        print(self.Selected_file)
#        print(self.files)
        try:
            self.files.remove(self.Selected_file)
        except:
            try:
                self.files.remove(self.Selected_file.replace('\\', '/'))
            except:
                pass
        
        self.update_file_table()


    def check_layer_selection(self):
        ''' Detect the selection of path in the table
        '''
        self.Selected_layers = []
        for c in self.tableWidget_layers.selectedItems():
            if c.column() == 0:
                self.Selected_layers.append(c.text())
                
        for key, data in self.layers.items():
            if key in self.Selected_layers:
                self.layers[key]['selected'] = True
            else:
                self.layers[key]['selected'] = False
                
        self.message_bottom_display.setText("Selected file(s) : %s" % self.Selected_layers)


    def delete_layer(self):
        ''' 
        '''
        inst = QgsProject.instance()
        buttonReply = QMessageBox.question(self, u'Import NetCDF : question', 
                                       "Are you sure you want to delete the following layers?\n%s" %  self.Selected_layers, 
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)

        if buttonReply == QMessageBox.Yes:
            for layr in self.Selected_layers:
                for lid, data in self.layers.items():
                    if data['name'] == layr:
                        rlid = lid
#                lname = ff.split("/")[-1]
#                layr = inst.mapLayersByName(lname)
#                for l in layr:
#                    inst.removeMapLayer(layr.id())
                inst.removeMapLayer(rlid)
                try:
                    os.remove(self.layers[rlid]['file'])
                except:
                    self.message_bottom_display.setText("File non deleted : %s" % rlid)
                self.layers.pop(rlid)
#                print("DELETE layer", rlid)
        
        self.Selected_layers = []
        self.update_layer_table()


    def delete_layer_group(self):
        ''' 
        '''
        groups_to_delete = []
        for layr in self.Selected_layers:
            for lid, data in self.layers.items():
                if data['name'] == layr:
                    groups_to_delete.append(data['group'])

        # remove duplicates in list
        groups_to_delete = list(dict.fromkeys(groups_to_delete))
                
        buttonReply = QMessageBox.question(self, u'Import NetCDF : question', 
                                       "Are you sure you want to delete the groups: %s?" % groups_to_delete, 
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)

        if buttonReply == QMessageBox.Yes:
            layers_to_delete = []        
            for group in groups_to_delete:
                for lid, data in self.layers.items():
                    if data['group'] == group:
#                        print("[delete_layer_group]", lid)
                        layers_to_delete.append(lid)
                # Remove group
                self.rem_group(group)
                            
            # Remove layers
            for rlid in layers_to_delete:
                self.layers.pop(rlid)
                    
            # Refresh table
            self.Selected_layers = []
            self.update_layer_table()
        

    def update_layer_table(self):
        ''' Update the table containing the list of layers
        layers = { layer_id : {"file"  : file,
                               "group" : group,
                               "name"  : name,
                               "nc"    : id of netcdf file,
                               "checked" : True | False}}
        '''
        self.tabWidget_files.setCurrentIndex(1)
        self.tableWidget_layers.setRowCount(0) #.clear()
        self.tableWidget_layers.setSortingEnabled(False)
        self.tableWidget_layers.setRowCount(len(self.layers))
        
        font = QFont()
#        font.setItalic(True)
        bgrd = QBrush(QColor(220, 220, 220, 150), Qt.SolidPattern) # light gray
        i = 0
#        print("[update_layer_table]", self.layers)
        for lid, dd in self.layers.items():
            self.tableWidget_layers.setItem(i, 0, QTableWidgetItem(dd['name']))
            self.tableWidget_layers.setItem(i, 1, QTableWidgetItem(dd['group']))
            self.tableWidget_layers.setItem(i, 2, QTableWidgetItem(str(dd['nc'])))
            self.tableWidget_layers.setItem(i, 3, QTableWidgetItem(dd['file']))
            if dd["checked"]:
                self.tableWidget_layers.item(i, 0).setFont(font)
                self.tableWidget_layers.item(i, 0).setBackground(bgrd)
                self.tableWidget_layers.item(i, 1).setFont(font)
                self.tableWidget_layers.item(i, 1).setBackground(bgrd)
                self.tableWidget_layers.item(i, 2).setFont(font)
                self.tableWidget_layers.item(i, 2).setBackground(bgrd)
                self.tableWidget_layers.item(i, 3).setFont(font)
                self.tableWidget_layers.item(i, 3).setBackground(bgrd)

            if dd['selected']:
                self.tableWidget_layers.item(i, 0).setSelected(True)
                self.tableWidget_layers.item(i, 1).setSelected(True)
                self.tableWidget_layers.item(i, 2).setSelected(True)
            else:
                self.tableWidget_layers.item(i, 0).setSelected(False)
                self.tableWidget_layers.item(i, 1).setSelected(False)
                self.tableWidget_layers.item(i, 2).setSelected(False)
 
            i += 1

        self.tableWidget_variables.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tableWidget_layers.setColumnWidth(0, 150)
        self.tableWidget_layers.setColumnWidth(1, 50)
        self.tableWidget_layers.setColumnWidth(2, 50)
        self.tableWidget_layers.setColumnWidth(3, 500)
        self.tableWidget_layers.setSortingEnabled(True)


    def add_layer(self, layer_dict):
        '''
        '''
        # if layer already in dict, remove it
        if layer_dict['name'] in self.layers.keys():
            # check if same group
            if layer_dict['group'] == self.layers[layer_dict['name']]['group']:
                self.layers.pop(layer_dict['name'])
        #add to dict
        self.layers[layer_dict['layer_id']] = {
                            'file'     : layer_dict['file'],
                            'group'    : layer_dict['group'],
                            'name'     : layer_dict['name'],
                            'nc'       : layer_dict['nc'],
                            'selected' : True,
                            'checked'  : True}
        
        self.update_layer_table()

   
    def update_layers(self, layers):
        '''
        '''
        self.layers.update(layers)
        self.update_layer_table()
        
    def update_dict_var_selected_date_list(self, var, llist):
        
        self.dict_var_selected_date_list[var] = llist
        
    def update_layer_selection_dates(self, selected):
        '''Propagates a given selection to all variable windows.
        '''
        # Disable table signals temporarily
        for variable_window in self.variable_windows:
            variable_window.tableWidget_dates.setUpdatesEnabled(False)
            variable_window.tableWidget_dates.blockSignals(True)
        
        # Propagate the selection
        for variable_window in self.variable_windows:
            if variable_window.variable not in self.synchronized_variables:
                continue
            variable_window.time = True
            table = variable_window.tableWidget_dates
            row_count = table.rowCount()
            column_count = table.columnCount()
            for row in range(row_count):
                date = table.item(row,1).text()[:-3]
                if date in selected:
                    for col in range(column_count):
                        item = table.item(row, col)
                        if item:
                            item.setSelected(True)
                            if row not in variable_window.selected_date_list:
                                if row not in variable_window.selected_date_list:
                                    variable_window.selected_date_list.append(row)
                                if not variable_window.variable in self.dict_var_selected_date_list:
                                    self.dict_var_selected_date_list[variable_window.variable] = []
                                if row not in self.dict_var_selected_date_list[variable_window.variable]:
                                    self.dict_var_selected_date_list[variable_window.variable].append(row)
                else:
                    for col in range(column_count):
                        item = table.item(row, col)
                        if item:
                            item.setSelected(False)
             
        # Reactivate signals
        for variable_window in self.variable_windows:
            variable_window.tableWidget_dates.setUpdatesEnabled(True)
            variable_window.tableWidget_dates.blockSignals(False)
                
           
    def update_layer_selection_depths(self, selected):
        '''Propagates a given selection to all variable windows.
        '''
        # Disable table signals temporarily
        for variable_window in self.variable_windows:
            variable_window.tableWidget_depths.setUpdatesEnabled(False)
            variable_window.tableWidget_depths.blockSignals(True)
        
        # Propagate the selection
        for variable_window in self.variable_windows:
            table = variable_window.tableWidget_depths
            row_count = table.rowCount()
            column_count = table.columnCount()
            for row in range(row_count):
                date = table.item(row,1).text()
                if date in selected:
                    for col in range(column_count):
                        item = table.item(row, col)
                        if item:
                            item.setSelected(True)
                else:
                    for col in range(column_count):
                        item = table.item(row, col)
                        if item:
                            item.setSelected(False)
                            
        # Reactivate signals
        for variable_window in self.variable_windows:
            variable_window.tableWidget_depths.setUpdatesEnabled(True)
            variable_window.tableWidget_depths.blockSignals(False)

   
    def save_tiff(self):
        '''
        '''
#        print("[ADD TIFF]", self.tiff_window.tiff_dict)

        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup("TIFF")
    
        if group is None:
            if self.tiff_window.checkBox_display.isChecked():
                # Create the group
                tiff_group = root.addGroup("TIFF")
                tiff_group.setExpanded(True)
                # Move to top 
                self.tiff_group = tiff_group.clone()
                root.insertChildNode(0, self.tiff_group)
                root.removeChildNode(tiff_group)
        else:
            self.tiff_group = group

        tiff_dir = self.tiff_window.lineEdit_directory.text()
        self.lineEdit_out_dir.setText(tiff_dir)
        # Copy Tiff file
        for layer_name in self.Selected_layers:
            for lid, data in self.layers.items():
                if data['name'] == layer_name:
                    rlid = lid
            layer_file = self.layers[rlid]['file']
            tiff_file = "%s/%s.tif" % (tiff_dir, layer_name)
#            print(layer_name, tiff_file)
            #Copy file
            shutil.copy(layer_file, tiff_file)

            if self.tiff_window.checkBox_display.isChecked():
                # Open resulting TIFF file
                ds = gdal.Open(tiff_file)
                
                if ds is not None and self.tiff_window.checkBox_display.isChecked():
                    band = ds.GetRasterBand(1)
                    data = band.ReadAsArray()
                    rlayer = QgsRasterLayer(tiff_file, layer_name, "gdal")
                    if self.tiff_group is not None:
                        QgsProject.instance().addMapLayer(rlayer, False)
                        self.tiff_group.insertChildNode(-1, QgsLayerTreeLayer(rlayer))
                    else:
                        QgsProject.instance().addMapLayer(rlayer, True)
                    
                    iface.setActiveLayer(rlayer)
                    # Make layer visible with inverted spectral styling
                    try:
                        print(f"DEBUG: Starting styling for layer: {layer_name}")
                        print(f"DEBUG: Data range: {np.nanmin(data):.4f} to {np.nanmax(data):.4f}")
                        
                        # Create a single band pseudocolor renderer
                        provider = rlayer.dataProvider()
                        renderer = QgsSingleBandPseudoColorRenderer(provider, 1)
                        
                        # Set classification range to data range
                        data_min = np.nanmin(data)
                        data_max = np.nanmax(data)
                        renderer.setClassificationMin(data_min)
                        renderer.setClassificationMax(data_max)
                        
                        print(f"DEBUG: Created pseudocolor renderer with range: {data_min:.4f} to {data_max:.4f}")
                        
                        # Apply inverted spectral color ramp with quantile classification
                        self.apply_inverted_spectral_styling(rlayer, renderer, data, data_min, data_max)
                        
                        # Force layer refresh
                        rlayer.triggerRepaint()
                        iface.layerTreeView().refreshLayerSymbology(rlayer.id())
                        iface.mapCanvas().refresh()
                        
                        print(f"DEBUG: Applied inverted spectral styling to saved TIFF layer")
                        print(f"DEBUG: Renderer type: {type(rlayer.renderer()).__name__}")
                        
                        # Check if renderer is working
                        current_renderer = rlayer.renderer()
                        if isinstance(current_renderer, QgsSingleBandPseudoColorRenderer):
                            print("DEBUG: Successfully applied pseudocolor renderer")
                        else:
                            print(f"DEBUG: Unexpected renderer type: {type(current_renderer).__name__}")
                        
                    except Exception as style_error:
                        print(f"DEBUG: TIFF styling failed: {style_error}")
                        import traceback
                        traceback.print_exc()
                        # Fall back to basic renderer
                        renderer = QgsSingleBandPseudoColorRenderer(rlayer.dataProvider(), 1)
                        rlayer.setRenderer(renderer)
                        rlayer.triggerRepaint()     
                    mlyr = QgsProject.instance().layerTreeRoot().findLayer(rlayer.id())
                    mlyr.setItemVisibilityCheckedParentRecursive(True)
                    mlyr.setExpanded(False)
                    rlayer.setAutoRefreshEnabled(True)
                    ds.FlushCache()
                    ds = None
#                    print("[save_tiff]", layer_name)
                    layer_id = rlayer.id()
                    grp = self.tiff_group.name()
                else:
                    print("[save_tiff]", "Layer not displayed", layer_name)
                    layer_id = ""
                    grp = ""
                    break
        
                # if layer already in dict, remove it
                if layer_id in self.layers.keys():
                    # check if same group
                    if grp == self.layers[layer_id]['group']:
                        self.layers.pop(layer_id)
                #add to dict
                self.layers[layer_id] = {
                                    'file'    : tiff_file,
                                    'group'   : grp,
                                    'name'    : layer_name,
                                    'nc'      : None,
                                    'selected': True,
                                    'checked' : True}
                # deselect self.Selected_layers
                self.layers[rlid]['selected'] = False
        
        self.message_bottom_display.setText("TIFF saved in : %s" % tiff_dir)
        self.tiff_window.close()
        self.update_layer_table()
    
    def check_file_name(self, file_name):
        for file_path in self.files:
            if file_name in file_path:
                return file_path
            
    def check_variable_selection(self, dictio=None):
        ''' Detect the selection of variable in the table
        '''
        print("DEBUG: check_variable_selection called")
        
        if dictio is not None:
            self.Selected_variables = dictio
            print(f"DEBUG: Using provided dictio: {dictio}")
        else:
            self.Selected_variables = []
            for c in self.tableWidget_variables.selectedItems():
                if c.column() == 0:
                    self.Selected_variables.append(c.text())
                    print(f"DEBUG: Selected variable from table: {c.text()}")
        
        print(f"DEBUG: Total selected variables: {len(self.Selected_variables)}")
        
        if len(self.Selected_variables) == 0:
            print("DEBUG: No variables selected")
            return []
            
        var_dicts = []
        for sv in self.Selected_variables:
            print(f"DEBUG: Processing variable: {sv}")
            
            try:
                # Allow auto masking and scaling
                if dictio is not None:
                    self.ds = Dataset(self.check_file_name(dictio[sv]), 'r')
                    self.update_variables(self.check_file_name(dictio[sv]))
                
                if not hasattr(self, 'ds') or self.ds is None:
                    print("DEBUG: No dataset available")
                    continue
                    
                if sv not in self.ds.variables:
                    print(f"DEBUG: Variable {sv} not found in dataset")
                    continue
                
                self.ds.variables[sv].set_auto_maskandscale(True)
                mdata = self.ds.variables[sv][:]
                
                mask = np.ma.getmaskarray(mdata)
                data = np.ma.getdata(mdata)
                data[mask] = np.NaN
                
                # Fix the reference to nc variable data
                nc_var = self.ds.variables[sv]

                var_dict = {'name' : sv, 
                                'dimension' : self.ds.variables[sv].dimensions,
                                'data'      : data,
                                'lons'      : self.lons,
                                'lats'      : self.lats,
                                'x_min'     : self.x_min,
                                'x_max'     : self.x_max,
                                'x_res'     : self.x_res,
                                'y_min'     : self.y_min,
                                'y_max'     : self.y_max,
                                'y_res'     : self.y_res,
                                'proj4'     : getattr(self, 'ds_proj', None),
                                'file'      : self.Selected_file,
                                'nc'        : nc_var}

                if len(var_dict['dimension']) < 2:
                    QMessageBox.warning(self, u'Warning', u"Please select a variable with lat, lon dimensions")
                    var_dict = None
                else:
                    # Check dimensions
                    var_dict['dates']  = None
                    var_dict['depths'] = None
                    for dim in self.ds.variables[sv].dimensions:
                        # Check dates
                        if dim.lower() in ['time', 'times', 'date', 'dates']:
                            var_dict['dates'] = getattr(self, 'dates', None)
                        # Check immersions
                        elif dim.lower() in ['depth', 'depths', 'z']:
                            var_dict['depths'] = getattr(self, 'depths', None)
                
                var_dicts.append(var_dict)
                print(f"DEBUG: Successfully processed variable: {sv}")
                
            except Exception as e:
                print(f"DEBUG: Error processing variable {sv}: {e}")
                import traceback
                traceback.print_exc()
                continue
            
        print(f"DEBUG: Returning {len(var_dicts)} variable dictionaries")
        return var_dicts
    

    def display_variable(self, dictio=None, single=False):
        ''' Display selected variable directly as raster layer with statistics and outlier clipping
        '''
        print("DEBUG: display_variable called")
        self.message_bottom_display.setText("Display variable called...")
        
        try:
            var_dicts = self.check_variable_selection(dictio)
            print(f"DEBUG: Found {len(var_dicts)} variables to display")
            
            for var_dict in var_dicts:
                if var_dict is not None:
                    print(f"DEBUG: Processing variable: {var_dict.get('name', 'Unknown')}")
                    
                    # Get the variable data
                    variable_name = var_dict['name']
                    
                    # Display simple message
                    self.message_bottom_display.setText(f"Loading variable: {variable_name}")
                    
                    # Get the NetCDF data
                    nc_file = var_dict['file']
                    var_data = var_dict['nc']
                    
                    print(f"DEBUG: Variable data shape: {var_data.shape}")
                    
                    # Create a temporary file for the raster with NetCDF filename included
                    temp_dir = self.lineEdit_temp_dir.text()
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir)
                        print(f"DEBUG: Created temp directory: {temp_dir}")
                    
                    nc_filename = os.path.splitext(os.path.basename(nc_file))[0]  # Get filename without extension
                    output_file = os.path.join(temp_dir, f"{nc_filename}_{variable_name}.tif")
                    print(f"DEBUG: Output file: {output_file}")
                    
                    # Get variable data and metadata
                    data = var_data[:]
                    print(f"DEBUG: Data shape after extraction: {data.shape}")
                    
                    # Handle dimensions - take first slice if multi-dimensional
                    original_shape = data.shape
                    while len(data.shape) > 2:
                        data = data[0]
                        print(f"DEBUG: Reduced data shape: {data.shape}")
                    
                    # Check if we have longitude and latitude data
                    if not hasattr(self, 'lons') or self.lons is None:
                        self.message_bottom_display.setText("Error: No longitude data available")
                        return
                    if not hasattr(self, 'lats') or self.lats is None:
                        self.message_bottom_display.setText("Error: No latitude data available")
                        return
                    
                    # Create georeferenced raster with proper coordinate handling
                    if not hasattr(self, 'lons') or self.lons is None:
                        self.message_bottom_display.setText("Error: No longitude data available")
                        return
                    if not hasattr(self, 'lats') or self.lats is None:
                        self.message_bottom_display.setText("Error: No latitude data available")
                        return
                    
                    # Handle coordinate arrays properly
                    # For 1D coordinate arrays (regular grids)
                    if len(self.lons.shape) == 1 and len(self.lats.shape) == 1:
                        # Regular grid with 1D coordinate arrays
                        lon_array = self.lons[:]
                        lat_array = self.lats[:]
                        
                        # Ensure coordinates are sorted (ascending for proper georeferencing)
                        if lon_array[0] > lon_array[-1]:
                            lon_array = np.flip(lon_array)
                            data = np.fliplr(data)  # Flip data horizontally
                            print("DEBUG: Flipped longitude coordinates and data horizontally")
                            
                        if lat_array[0] < lat_array[-1]:
                            lat_array = np.flip(lat_array)
                            data = np.flipud(data)  # Flip data vertically
                            print("DEBUG: Flipped latitude coordinates and data vertically")
                        
                        min_x = float(lon_array[0])
                        max_x = float(lon_array[-1])
                        min_y = float(lat_array[-1])  # min lat is now at bottom after sorting
                        max_y = float(lat_array[0])   # max lat is now at top after sorting
                        
                        # Calculate pixel sizes
                        pixel_width = (max_x - min_x) / (len(lon_array) - 1) if len(lon_array) > 1 else 1.0
                        pixel_height = (max_y - min_y) / (len(lat_array) - 1) if len(lat_array) > 1 else 1.0
                        
                    # For 2D coordinate arrays (irregular grids)
                    elif len(self.lons.shape) == 2 and len(self.lats.shape) == 2:
                        # 2D coordinate arrays - use bounds
                        min_x = float(np.min(self.lons))
                        max_x = float(np.max(self.lons))
                        min_y = float(np.min(self.lats))
                        max_y = float(np.max(self.lats))
                        
                        # Calculate pixel sizes based on data shape
                        rows, cols = data.shape
                        pixel_width = (max_x - min_x) / cols if cols > 1 else 1.0
                        pixel_height = (max_y - min_y) / rows if rows > 1 else 1.0
                        
                    else:
                        self.message_bottom_display.setText("Error: Incompatible coordinate array dimensions")
                        return
                    
                    print(f"DEBUG: Coordinate bounds - X: {min_x:.6f} to {max_x:.6f}, Y: {min_y:.6f} to {max_y:.6f}")
                    print(f"DEBUG: Pixel size - Width: {pixel_width:.6f}, Height: {pixel_height:.6f}")
                    print(f"DEBUG: Data shape: {data.shape}")
                    
                    # Get projection (using the one selected in the UI)
                    proj_idx = self.comboBox_projection.currentIndex()
                    proj_epsg = self.comboBox_projection.itemData(proj_idx)
                    if proj_epsg is None or proj_epsg == "":
                        proj_epsg = 4326  # Default to WGS84
                    
                    print(f"DEBUG: Using EPSG: {proj_epsg}")
                    
                    # Calculate basic statistics
                    flat_data = data.flatten()
                    valid_data = flat_data[~np.isnan(flat_data)]
                    
                    if len(valid_data) == 0:
                        self.message_bottom_display.setText(f"Error: No valid data found in variable {variable_name}")
                        continue
                    
                    # Calculate comprehensive statistics including percentiles
                    data_min = np.min(valid_data)
                    data_max = np.max(valid_data)
                    data_mean = np.mean(valid_data)
                    data_std = np.std(valid_data)
                    data_median = np.median(valid_data)
                    valid_pixels = len(valid_data)
                    total_pixels = len(flat_data)
                    
                    # Calculate percentiles for clipping options
                    percentiles = [1, 2, 5, 10, 25, 50, 75, 90, 95, 98, 99]
                    perc_values = np.percentile(valid_data, percentiles)
                    perc_dict = dict(zip(percentiles, perc_values))
                    
                    print(f"DEBUG: Statistics - Min: {data_min:.4f}, Max: {data_max:.4f}, Mean: {data_mean:.4f}")
                    print(f"DEBUG: Statistics - Std: {data_std:.4f}, Median: {data_median:.4f}")
                    print(f"DEBUG: Valid pixels: {valid_pixels}/{total_pixels} ({valid_pixels/total_pixels*100:.1f}%)")
                    print(f"DEBUG: Percentiles: 1%={perc_dict[1]:.3f}, 5%={perc_dict[5]:.3f}, 95%={perc_dict[95]:.3f}, 99%={perc_dict[99]:.3f}")
                    
                    # Show clipping options dialog
                    clipping_choice = self.show_clipping_dialog(variable_name, perc_dict, data_min, data_max, valid_pixels)
                    
                    # Handle clipping based on user choice
                    if clipping_choice['apply_clipping']:
                        min_value = clipping_choice['min_value']
                        max_value = clipping_choice['max_value']
                        clipping_applied = True
                        clip_method = clipping_choice['method']
                        
                        # Count how many pixels will be clipped
                        clipped_low = np.sum(valid_data < min_value)
                        clipped_high = np.sum(valid_data > max_value)
                        clipped_total = clipped_low + clipped_high
                        
                        print(f"DEBUG: User chose {clip_method} clipping: {min_value:.4f} to {max_value:.4f}")
                        print(f"DEBUG: Will clip {clipped_total} pixels ({clipped_total/valid_pixels*100:.1f}%)")
                        
                        # Apply clipping to the actual data array
                        # Values below min_value become nodata, values above max_value become nodata
                        data_clipped = data.copy()
                        data_clipped[data < min_value] = np.nan
                        data_clipped[data > max_value] = np.nan
                        data = data_clipped
                        
                        # Recalculate statistics after clipping for metadata
                        clipped_flat = data.flatten()
                        clipped_valid = clipped_flat[~np.isnan(clipped_flat)]
                        if len(clipped_valid) > 0:
                            clipped_min = np.min(clipped_valid)
                            clipped_max = np.max(clipped_valid) 
                            clipped_mean = np.mean(clipped_valid)
                            clipped_pixels = len(clipped_valid)
                            print(f"DEBUG: After clipping - Range: {clipped_min:.4f} to {clipped_max:.4f}, Mean: {clipped_mean:.4f}")
                            print(f"DEBUG: After clipping - Valid pixels: {clipped_pixels}/{total_pixels} ({clipped_pixels/total_pixels*100:.1f}%)")
                        else:
                            print("WARNING: No valid pixels remaining after clipping!")
                    else:
                        min_value = data_min
                        max_value = data_max
                        clipping_applied = False
                        print("DEBUG: User chose no clipping")
                    
                    # Export to GeoTIFF with corrected geotransform
                    driver = gdal.GetDriverByName('GTiff')
                    rows, cols = data.shape
                    out_raster = driver.Create(output_file, cols, rows, 1, gdal.GDT_Float32)
                    
                    # Calculate proper GDAL geotransform
                    # GDAL geotransform: [top_left_x, pixel_width, rotation, top_left_y, rotation, -pixel_height]
                    # The coordinates should represent the top-left corner of the top-left pixel
                    
                    # For pixel-centered coordinates, adjust to pixel corners
                    top_left_x = min_x - (pixel_width / 2.0)
                    top_left_y = max_y + (pixel_height / 2.0)  # Add because we'll use negative pixel_height
                    
                    geotransform = [
                        top_left_x,      # Top-left X coordinate (pixel corner)
                        pixel_width,     # Pixel width (positive for west-to-east)
                        0,               # Rotation (0 for north-up images)
                        top_left_y,      # Top-left Y coordinate (pixel corner)
                        0,               # Rotation (0 for north-up images)
                        -pixel_height    # Pixel height (negative for north-to-south)
                    ]
                    
                    print(f"DEBUG: GDAL Geotransform: {geotransform}")
                    out_raster.SetGeoTransform(geotransform)
                    
                    # Set projection
                    srs = osr.SpatialReference()
                    srs.ImportFromEPSG(int(proj_epsg))
                    out_raster.SetProjection(srs.ExportToWkt())
                    print(f"DEBUG: Set projection to EPSG:{proj_epsg}")
                    
                    # Ensure data is properly oriented for GDAL
                    # Data should be oriented with first row at the top (north)
                    # Since our geotransform assumes this orientation, no additional flipping needed here
                    
                    # Prepare data for writing - convert NaN to nodata value
                    no_data_value = -9999.0
                    data_for_writing = data.copy()
                    data_for_writing[np.isnan(data)] = no_data_value
                    
                    # Write data to raster
                    outband = out_raster.GetRasterBand(1)
                    outband.WriteArray(data_for_writing)
                    outband.SetNoDataValue(no_data_value)
                    
                    print(f"DEBUG: Data written to raster. Shape: {data_for_writing.shape}, NoData value: {no_data_value}")
                    print(f"DEBUG: Data range in raster: {np.nanmin(data):.4f} to {np.nanmax(data):.4f}")
                    
                    # Add metadata with both original and final statistics
                    metadata = {
                        'VARIABLE_NAME': variable_name,
                        'ORIGINAL_DATA_MIN': str(data_min),
                        'ORIGINAL_DATA_MAX': str(data_max),
                        'ORIGINAL_DATA_MEAN': str(data_mean),
                        'ORIGINAL_DATA_STD': str(data_std),
                        'ORIGINAL_DATA_MEDIAN': str(data_median),
                        'ORIGINAL_VALID_PIXELS': str(valid_pixels),
                        'TOTAL_PIXELS': str(total_pixels),
                        'ORIGINAL_SHAPE': str(original_shape),
                        'CLIPPING_APPLIED': str(clipping_applied),
                        'CRS_EPSG': str(proj_epsg)
                    }
                    
                    # Add current data statistics (after clipping if applied)
                    current_flat = data.flatten()
                    current_valid = current_flat[~np.isnan(current_flat)]
                    if len(current_valid) > 0:
                        metadata['FINAL_DATA_MIN'] = str(np.min(current_valid))
                        metadata['FINAL_DATA_MAX'] = str(np.max(current_valid))
                        metadata['FINAL_DATA_MEAN'] = str(np.mean(current_valid))
                        metadata['FINAL_VALID_PIXELS'] = str(len(current_valid))
                    
                    if clipping_applied:
                        metadata['CLIP_METHOD'] = clipping_choice['method']
                        metadata['CLIP_MIN_VALUE'] = str(min_value)
                        metadata['CLIP_MAX_VALUE'] = str(max_value)
                        metadata['PIXELS_CLIPPED'] = str(clipped_total)
                        metadata['PERCENT_CLIPPED'] = str(round(clipped_total/valid_pixels*100, 2))
                        if 'low_percentile' in clipping_choice:
                            metadata['CLIP_LOW_PERCENTILE'] = str(clipping_choice['low_percentile'])
                            metadata['CLIP_HIGH_PERCENTILE'] = str(clipping_choice['high_percentile'])
                    
                    outband.SetMetadata(metadata)
                    outband.FlushCache()
                    
                    # Close the raster to ensure it's written
                    out_raster = None
                    outband = None
                    
                    print(f"DEBUG: GeoTIFF created: {output_file}")
                    
                    # Add layer to QGIS with NetCDF filename included
                    nc_filename = os.path.splitext(os.path.basename(nc_file))[0]  # Get filename without extension
                    layer_name = f"{nc_filename}_{variable_name}"
                    rlayer = QgsRasterLayer(output_file, layer_name, "gdal")
                    
                    if rlayer.isValid():
                        print("DEBUG: Raster layer is valid")
                        
                        # Add to map first
                        QgsProject.instance().addMapLayer(rlayer)
                        
                        # Apply enhanced styling with inverted spectral color ramp
                        try:
                            # Create a single band pseudocolor renderer
                            provider = rlayer.dataProvider()
                            renderer = QgsSingleBandPseudoColorRenderer(provider, 1)
                            
                            # Set classification range to clipped values
                            renderer.setClassificationMin(min_value)
                            renderer.setClassificationMax(max_value)
                            
                            # Create inverted spectral color ramp with quantile classification
                            self.apply_inverted_spectral_styling(rlayer, renderer, data, min_value, max_value)
                            
                            print("DEBUG: Inverted spectral styling applied successfully")
                        except Exception as style_error:
                            print(f"DEBUG: Styling failed: {style_error}")
                            # Layer will still be added without custom styling
                        
                        # Create layer dictionary for tracking
                        layer_dict = {
                            'layer_id': rlayer.id(),
                            'file': output_file,
                            'group': 'NetCDF',
                            'name': layer_name,
                            'nc': var_data,
                            'selected': True,
                            'checked': True
                        }
                        
                        # Add to layer tracking
                        try:
                            self.add_layer(layer_dict)
                        except Exception as track_error:
                            print(f"DEBUG: Layer tracking failed: {track_error}")
                        
                        # Display comprehensive statistics message
                        stats_msg = (f"Variable {variable_name} loaded | "
                                   f"Range: {data_min:.3f} to {data_max:.3f} | "
                                   f"Mean: {data_mean:.3f} ± {data_std:.3f} | "
                                   f"Valid: {valid_pixels}/{total_pixels} pixels | "
                                   f"CRS: EPSG:{proj_epsg}")
                        
                        if clipping_applied:
                            stats_msg += f" | Clipped: {clipping_choice['method']}"
                        
                        self.message_bottom_display.setText(stats_msg)
                        print(f"DEBUG: {stats_msg}")
                    else:
                        error_msg = f"Error: Could not load raster layer for {variable_name}"
                        self.message_bottom_display.setText(error_msg)
                        print(f"DEBUG: {error_msg}")
                        print(f"DEBUG: Raster layer error: {rlayer.error().message()}")
        
        except Exception as e:
            error_msg = f"Error displaying variable: {str(e)}"
            self.message_bottom_display.setText(error_msg)
            print(f"DEBUG: Exception in display_variable: {e}")
            import traceback
            traceback.print_exc()
        
        # Clear the selected variables
        self.Selected_variables = []

    def show_clipping_dialog(self, variable_name, percentiles, data_min, data_max, valid_pixels):
        """Show a dialog for choosing clipping options with statistics"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QWidget
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Clipping Options for {variable_name}")
        dialog.setMinimumSize(700, 600)
        
        # Create scroll area for the content
        scroll = QScrollArea()
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        
        # Information section
        info_label = QLabel(f"<b>Variable:</b> {variable_name}<br>"
                           f"<b>Valid pixels:</b> {valid_pixels:,}<br>"
                           f"<b>Full range:</b> {data_min:.6f} to {data_max:.6f}<br>"
                           f"<b>Outlier clipping removes extreme values to improve visualization</b>")
        layout.addWidget(info_label)
        
        # Percentile statistics table
        layout.addWidget(QLabel("<b>Percentile Statistics:</b>"))
        
        stats_table = QTableWidget(10, 2)  # Show key percentiles
        stats_table.setHorizontalHeaderLabels(["Percentile", "Value"])
        stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        stats_table.setMaximumHeight(250)
        
        # Show key percentiles
        key_percentiles = [1, 2, 5, 10, 25, 50, 75, 90, 95, 98, 99]
        valid_percentiles = [(p, percentiles[p]) for p in key_percentiles if p in percentiles]
        
        for i, (perc, value) in enumerate(valid_percentiles[:10]):  # Limit to 10 rows
            stats_table.setItem(i, 0, QTableWidgetItem(f"{perc}%"))
            stats_table.setItem(i, 1, QTableWidgetItem(f"{value:.6f}"))
        
        layout.addWidget(stats_table)
        
        # Clipping options section
        layout.addWidget(QLabel("<b>Choose Clipping Method:</b>"))
        
        # Radio button options
        button_group = QButtonGroup()
        
        # No clipping option
        no_clip_radio = QRadioButton("No clipping - use full data range")
        no_clip_radio.setChecked(True)  # Default
        button_group.addButton(no_clip_radio, 0)
        layout.addWidget(no_clip_radio)
        
        # Common clipping options with detailed statistics
        clipping_options = [
            (1, 99, "Conservative"),
            (2, 98, "Moderate"),
            (5, 95, "Aggressive"), 
            (10, 90, "Very Aggressive")
        ]
        
        for i, (low_perc, high_perc, description) in enumerate(clipping_options, 1):
            if low_perc in percentiles and high_perc in percentiles:
                low_val = percentiles[low_perc]
                high_val = percentiles[high_perc]
                
                # Calculate percentage of data that would be clipped
                clip_percent = low_perc + (100 - high_perc)  # Total percentage clipped
                pixels_removed = int(valid_pixels * (clip_percent / 100))
                
                radio_text = (f"{description} ({low_perc}%-{high_perc}%): "
                             f"Range {low_val:.4f} to {high_val:.4f} "
                             f"[Removes {pixels_removed:,} pixels ({clip_percent:.0f}%)]")
                
                radio = QRadioButton(radio_text)
                button_group.addButton(radio, i)
                layout.addWidget(radio)
        
        # Buttons
        button_layout = QHBoxLayout()
        ok_button = QPushButton("Apply Selection")
        cancel_button = QPushButton("Cancel (No Clipping)")
        
        def accept_dialog():
            dialog.accept()
        
        def reject_dialog():
            dialog.reject()
        
        ok_button.clicked.connect(accept_dialog)
        cancel_button.clicked.connect(reject_dialog)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        # Set up scroll area
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        
        # Main dialog layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        dialog.setLayout(main_layout)
        
        # Show dialog and get result
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            selected_id = button_group.checkedId()
            
            if selected_id == 0:  # No clipping
                return {
                    'apply_clipping': False,
                    'method': 'none',
                    'min_value': data_min,
                    'max_value': data_max
                }
            else:  # Some clipping option
                low_perc, high_perc, description = clipping_options[selected_id - 1]
                return {
                    'apply_clipping': True,
                    'method': f'{low_perc}%-{high_perc}%',
                    'min_value': percentiles[low_perc],
                    'max_value': percentiles[high_perc],
                    'low_percentile': low_perc,
                    'high_percentile': high_perc
                }
        else:  # Cancelled
            return {
                'apply_clipping': False,
                'method': 'cancelled',
                'min_value': data_min,
                'max_value': data_max
            }

    def update_selected_variables(self, dictio):
        self.synchronized_variables = dictio

    def get_synchronized_variables(self):
        return self.synchronized_variables
        
    def close_all(self):
        
        for window in self.variable_windows:
            if window.variable in self.synchronized_variables:
                window.display_close()
                
    def same_time(self, list_files):
        
        list = []
        
        for file in self.files:
            found = False
            for file_name in list_files:
                if file_name in file:
                    found = True
            if not found:
                continue
            ds = Dataset(file, 'r')
            for var in ds.variables:
                if var.lower() in ['time', 'date', 'times', 'dates']:
                    for date in num2date(ds.variables[var][:], ds.variables[var].units):
                        if date.strftime("%d-%m-%Y %H:%M")[-2:] not in list:
                            list.append(date.strftime("%d-%m-%Y %H:%M")[-2:])
                        
        if len(list)==1:
            return False
        
        if len(list)>1:
            return True
        
        return False

    def add_layers_several_variables_function(self):
        ''' Display a message that multi-variable selection is not supported in the simplified version
        '''
        self.message_bottom_display.setText("Multiple variable selection has been simplified. Please select and display variables one by one.")
    
    def sequence_variable(self):
        ''' Display a message that sequencing is not supported in the simplified version
        '''
        self.message_bottom_display.setText("Animation/sequencing feature has been removed in the simplified plugin version.")
        # Clear the selected variables
        self.Selected_variables = []
        
    def read_preferences(self):
        ''' Read preference file
        
        preference_dict = { projection : {  "names" : [],
                                            "EPSG"  : [],
                                            "units" : [] }
                          }
        '''
        xml_file = "%s/preferences.xml" % os.path.dirname(__file__)
        print(f"[DEBUG] Reading preferences from: {xml_file}")

        root = etree.parse(xml_file).getroot()
        self.preference_dict["projection"] = {"names" : [], "EPSG" : [], "units" : []}
        
        # Read projection settings
        for entry in root[0]:
            self.preference_dict["projection"]["names"].append(entry.attrib["name"])
            self.preference_dict["projection"]["EPSG"].append(entry.attrib["EPSG"])
            self.preference_dict["projection"]["units"].append(entry.attrib["unit"])
        
        # Read data processing settings (percentile clipping) - set defaults first
        self.preference_dict["data_processing"] = {
            "percentile_clipping_enabled": True,
            "min_percentile": 2,
            "max_percentile": 98,
            "presets": [
                {"name": "Conservative (2-98%)", "min": 2, "max": 98, "description": "Default conservative clipping"},
                {"name": "Moderate (5-95%)", "min": 5, "max": 95, "description": "Moderate outlier removal"},
                {"name": "Minimal (1-99%)", "min": 1, "max": 99, "description": "Minimal clipping"},
                {"name": "Aggressive (10-90%)", "min": 10, "max": 90, "description": "Strong outlier removal"}
            ]
        }
        
        # Look for data_processing section
        for section in root:
            print(f"[DEBUG] Found XML section: {section.tag}")
            if section.tag == "data_processing":
                print(f"[DEBUG] Processing data_processing section")
                for setting in section:
                    print(f"[DEBUG] Found setting: {setting.tag} with attributes: {setting.attrib}")
                    if setting.tag == "percentile_clipping":
                        enabled = setting.attrib.get("enabled", "true").lower() == "true"
                        min_perc = float(setting.attrib.get("min_percentile", "2"))
                        max_perc = float(setting.attrib.get("max_percentile", "98"))
                        
                        self.preference_dict["data_processing"]["percentile_clipping_enabled"] = enabled
                        self.preference_dict["data_processing"]["min_percentile"] = min_perc
                        self.preference_dict["data_processing"]["max_percentile"] = max_perc
                        
                        print(f"[DEBUG] Set percentile clipping: enabled={enabled}, min={min_perc}, max={max_perc}")
                    
                    elif setting.tag == "percentile_presets":
                        # Read custom presets from XML if available
                        custom_presets = []
                        for preset in setting:
                            if preset.tag == "preset":
                                preset_info = {
                                    "name": preset.attrib.get("name", "Custom"),
                                    "min": int(preset.attrib.get("min", "2")),
                                    "max": int(preset.attrib.get("max", "98")),
                                    "description": preset.attrib.get("description", "")
                                }
                                custom_presets.append(preset_info)
                        
                        if custom_presets:
                            self.preference_dict["data_processing"]["presets"] = custom_presets
                            print(f"[DEBUG] Loaded {len(custom_presets)} custom presets from XML")
        
        print(f"[DEBUG] Final data_processing preferences: {self.preference_dict['data_processing']}")
#        print("[PREFERENCES]", self.preference_dict)


    def update_projection_list(self):
        ''' update the combo list giving the choice of projections
        '''
        self.comboBox_projection.clear()
        
        # Always prioritize WGS84 Geographic as default for satellite data
        wgs84_added = False
        
        # Add WGS84 first
        for i, proj in enumerate(self.preference_dict["projection"]["names"]):
            epsg = self.preference_dict["projection"]["EPSG"][i]
            if epsg == "4326" or "WGS 84 (Geographic)" in proj:
                self.comboBox_projection.addItem(proj, epsg)
                wgs84_added = True
                break
        
        # Add separator after WGS84
        if wgs84_added:
            self.comboBox_projection.insertSeparator(1)
        
        # Add all other projections
        for i, proj in enumerate(self.preference_dict["projection"]["names"]):
            epsg = self.preference_dict["projection"]["EPSG"][i]
            # Skip WGS84 as it's already added
            if epsg == "4326" or "WGS 84 (Geographic)" in proj:
                continue
            self.comboBox_projection.addItem(proj, epsg)
            
        # Set WGS84 as default selection
        self.comboBox_projection.setCurrentIndex(0)
        
        # Add user-friendly message about CRS selection
        self.message_bottom_display.setText("Default CRS: WGS84. If your data doesn't display correctly, select a different CRS from the dropdown. This plugin is designed for general NetCDF use.")


    @staticmethod
    def rem_group(target):
        '''Removes a group from the interface
        '''
        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup(target)
        if group is not None:
            for child in group.children():
                try:
#                    print("removing", child)
                    QgsProject.instance().removeMapLayer(child.layerId())
                except AttributeError:
                    pass
            root.removeChildNode(group)


    def clear_bottom_line(self):
        ''' Force the comment line to null
        '''
        self.message_bottom_display.setText("...")       


    def check_layer(self):
        '''Save layer as TIFF
        '''
        for layer in self.Selected_layers:
            #find layer id in self.layers dict
            for lid, data in self.layers.items():
                if data['name'] == layer:
                    rlid = lid
                    
            mlyr = QgsProject.instance().layerTreeRoot().findLayer(rlid)
            mlyr.setItemVisibilityChecked(True)
            self.layers[rlid]['checked'] = True
        # Update table
        self.update_layer_table()    


    def uncheck_layer(self):
        '''Save layer as TIFF
        '''
        for layer in self.Selected_layers:
            #find layer id in self.layers dict
            for lid, data in self.layers.items():
                if data['name'] == layer:
                    rlid = lid
                    
            mlyr = QgsProject.instance().layerTreeRoot().findLayer(rlid)
            mlyr.setItemVisibilityChecked(False)
            self.layers[rlid]['checked'] = False
        # Update table
        self.update_layer_table()    
            

    def save_dialog(self):
        '''Legacy dialog feature removed in simplified version'''
        QMessageBox.information(self, "Feature Removed", "Save dialog functionality has been removed in the simplified version.\nUse QGIS's standard Export > Save As to save raster layers.")


    def align_dialog(self):
        '''Legacy dialog feature removed in simplified version'''
        QMessageBox.information(self, "Feature Removed", "Align dialog functionality has been removed in the simplified version.\nUse QGIS's Raster > Align Rasters tool for alignment needs.")


    def vector_dialog(self):
        '''Legacy dialog feature removed in simplified version'''
        QMessageBox.information(self, "Feature Removed", "Vector dialog functionality has been removed in the simplified version.\nUse QGIS's Processing Toolbox for vector operations.")


    def vector_raster(self):
        '''Legacy functionality removed in simplified version'''
        QMessageBox.information(self, "Feature Removed", "Vector raster functionality has been removed in the simplified version.\nUse QGIS's Processing Toolbox for vector operations.")


    def align_raster_legacy_stub(self):
        '''Legacy functionality removed in simplified version'''
        QMessageBox.information(self, "Feature Removed", "Align raster functionality has been removed in the simplified version.\nUse QGIS's Raster > Align Rasters tool for alignment needs.")


    def align_raster(self):
        '''Legacy functionality removed in simplified version'''
        QMessageBox.information(self, "Feature Removed", "Align raster functionality has been removed in the simplified version.\nUse QGIS's Raster > Align Rasters tool for alignment needs.")
        if ds1 is not None:
            xsize1 = ds1.RasterXSize
            ysize1 = ds1.RasterYSize
            proj = ds1.GetProjection()
            geoT1  = ds1.GetGeoTransform()
            minx1 = geoT1[0]
            maxy1 = geoT1[3]
            maxx1 = minx1 + geoT1[1] * xsize1
            miny1 = maxy1 + geoT1[5] * ysize1
            band1 = ds1.GetRasterBand(1)
            data1 = np.flipud(band1.ReadAsArray())[::ratio,::ratio]
            data1=data1.flatten()
            SRS = osr.SpatialReference()
            SRS.ImportFromWkt(proj)
#        ds1 = None

        ds2 = gdal.Open(rraster2)
        if ds2 is not None:
            xsize2 = ds2.RasterXSize
            ysize2 = ds2.RasterYSize
#            proj = ds.GetProjection()
            geoT2  = ds2.GetGeoTransform()
            minx2 = geoT2[0]
            maxy2 = geoT2[3]
            maxx2 = minx2 + geoT2[1] * xsize2
            miny2 = maxy2 + geoT2[5] * ysize2
            band2 = ds2.GetRasterBand(1)
            data2 = np.flipud(band2.ReadAsArray())[::ratio,::ratio]
            data2 = data2.flatten()
#        ds2 = None
        
        if (xsize1 != xsize2) or (ysize1 != ysize2) or (minx1 != minx2) or (maxy1 != maxy2) or (maxx1 != maxx2) or (miny1 != miny2):
            QMessageBox.warning(self, u'Warning', u"Please, choose two layers with same geographic size")
            return
        
        xx = np.linspace(minx1, maxx1, num=xsize1, endpoint=True, retstep=False)
        yy = np.linspace(miny1, maxy1, num=ysize1, endpoint=True, retstep=False)
        lons, lats = np.meshgrid(xx, yy)
        lons = lons[::ratio,::ratio]
        lons = lons.flatten()
        lats = lats[::ratio,::ratio]
        lats = lats.flatten()
#        print(lons)
#        print(np.nanmin(data1), np.nanmax(data1), np.nanmean(data1))
#        print(np.nanmin(data2), np.nanmax(data2), np.nanmean(data2))
        
        if self.vector_window.mode == 'UV':
            self.length = np.sqrt(np.square(data1) + np.square(data2)).astype(np.float64)
            self.dir = np.degrees(np.arctan2(data1, data2)).astype(np.float64)
        else:
            self.length = data2.flatten().astype(np.float64)
            self.dir  = data1.flatten().astype(np.float64)
        if dirtype == "Current":
            # self.dir = np.mod(self.dir+180, 360)
            if self.dir.any()>180 : #coordinates from 0 to 360
                for i in range(len(self.dir)):
                    if self.dir[i]<=180:
                        self.dir[i] = self.dir[i]+180.
                    elif self.dir[i]>180 :
                        self.dir[i] = self.dir[i]-180.
                    else:
                        pass
            else: #coordinates from -180 to 180
                for i in range(len(self.dir)):
                    if self.dir[i]<=0:
                        print("av",self.dir[i])
                        self.dir[i] = self.dir[i]+180.
                        print("ap",self.dir[i])
                    elif self.dir[i]>0 : 
                        print("av",self.dir[i])
                        self.dir[i] = self.dir[i]-180.
                        print("ap",self.dir[i])
                    else:
                        pass
#        print(np.nanmin(self.length), np.nanmax(self.length), np.nanmean(self.length))
#        print(np.nanmin(self.dir), np.nanmax(self.dir), np.nanmean(self.dir))
#        print(lons.shape, lats.shape, self.dir.shape, self.length.shape)
        # Remove Nans
        mask = ~np.isnan(self.dir)
        self.dir    = self.dir[mask]
        self.length = self.length[mask]
        lons  = lons[mask]
        lats  = lats[mask]
        
        # Create vector File
        out_dir = self.vector_window.lineEdit_directory.text()
        self.lineEdit_out_dir.setText(out_dir)
        layer_name = self.vector_window.lineEdit_filename.text()
        point_file = os.path.join(out_dir, layer_name)
        shpDriver = ogr.GetDriverByName("GML")
        if os.path.exists(point_file):
            shpDriver.DeleteDataSource(point_file)
#                    os.remove(point_file)
        outDataSource = shpDriver.CreateDataSource(point_file)
        if outDataSource is not None:
            # create the layer
            layer = outDataSource.CreateLayer(point_file, SRS, geom_type=ogr.wkbPoint)
            # Add the fields
            layer.CreateField(ogr.FieldDefn("latitude",      ogr.OFTReal))
            layer.CreateField(ogr.FieldDefn("longitude",     ogr.OFTReal))
            layer.CreateField(ogr.FieldDefn("direction", ogr.OFTReal))
            layer.CreateField(ogr.FieldDefn("length",    ogr.OFTReal))
            # Add the attributes and features to the shapefile
            for i, pp in enumerate(self.length):
                # create the feature
                feature = ogr.Feature(layer.GetLayerDefn())
                # Set the attributes using the values from the delimited text file
                feature.SetField("latitude",      lats[i])
                feature.SetField("longitude",     lons[i])
                feature.SetField("length", self.length[i])
                feature.SetField("direction", self.dir[i])
                # create the WKT for the feature using Python string formatting
                p_wkt = "POINT(%f %f)" %  (lons[i] , lats[i])
                # Create the point from the Well Known Txt
                point = ogr.CreateGeometryFromWkt(p_wkt)
                feature.SetGeometry(point)
                layer.CreateFeature(feature)
                feature = None
            # Save and close the data source
            outDataSource = None
            # Open resulting GML file
            ds = ogr.Open(point_file)
            if ds is not None:
                root = QgsProject.instance().layerTreeRoot()
                group = root.findGroup("VECTOR")
                if group is None:
                    # Create the group
                    v_group = root.addGroup("VECTOR")
                    v_group.setExpanded(True)
                    # Move to top 
                    self.v_group = v_group.clone()
                    root.insertChildNode(0, self.v_group)
                    root.removeChildNode(v_group)
                else:
                    self.v_group = group

                v_layer = QgsVectorLayer(point_file, layer_name, "ogr")
#                sstyle = {'name': 'arrow',
#                           'color': color.name(),
#                           'outline_style': 'no',
#                           'size': '2'}
#                symbol = QgsMarkerSymbol.createSimple(sstyle)
#                
##                v_layer.renderer().setSymbol(symbol)
#
##                c_renderer = QgsCategorizedSymbolRenderer()
##                cat1 = QgsRendererCategory('1', QgsMarkerSymbol(), 'category 1')
##                c_renderer.addCategory(cat1)
#                g_renderer = QgsGraduatedSymbolRenderer()
#                qrange = QgsRendererRange(np.nanmin(self.dir), np.nanmax(self.dir), symbol, 'angle')
#                g_renderer.addClassRange(qrange) #(QgsRendererRange(QgsClassificationRange('class angle', -180, 180), symbol))
#                c_method = QgsApplication.classificationMethodRegistry().method('EqualInterval')
#                g_renderer.setClassificationMethod(c_method)
#                g_renderer.setClassAttribute("direction")
#                
#                v_layer.setRenderer(g_renderer)
                length_range = np.linspace(np.nanmin(self.length), np.nanmax(self.length), 11, endpoint=True)
                length_range = ["%.3f" % d for d in length_range]
                '''<ranges>
                  <range upper="%%01%%" symbol="0" label="%%00%% - %%01%%" lower="%%00%%" render="true"/>
                  <range upper="%%02%%" symbol="1" label="%%01%% - %%02%%" lower="%%01%%" render="true"/>
                  <range upper="%%03%%" symbol="2" label="%%02%% - %%03%%" lower="%%02%%" render="true"/>
                  <range upper="%%04%%" symbol="3" label="%%03%% - %%04%%" lower="%%03%%" render="true"/>
                  <range upper="%%05%%" symbol="4" label="%%04%% - %%05%%" lower="%%04%%" render="true"/>
                  <range upper="%%06%%" symbol="5" label="%%05%% - %%06%%" lower="%%05%%" render="true"/>
                  <range upper="%%07%%" symbol="6" label="%%06%% - %%07%%" lower="%%06%%" render="true"/>
                  <range upper="%%08%%" symbol="7" label="%%07%% - %%08%%" lower="%%07%%" render="true"/>
                  <range upper="%%09%%" symbol="8" label="%%08%% - %%09%%" lower="%%08%%" render="true"/>
                  <range upper="%%10%%" symbol="9" label="%%09%% - %%10%%" lower="%%09%%" render="true"/>
                </ranges>'''
                
                with open(os.path.join(os.path.dirname(__file__), 'arrow10.qml'), 'r') as f:
                    #read file
                    lines = f.readlines()
                    out_text = ""
                    for line in lines:
                        line = line.replace('%%00%%', length_range[0])
                        line = line.replace('%%01%%', length_range[1])
                        line = line.replace('%%02%%', length_range[2])
                        line = line.replace('%%03%%', length_range[3])
                        line = line.replace('%%04%%', length_range[4])
                        line = line.replace('%%05%%', length_range[5])
                        line = line.replace('%%06%%', length_range[6])
                        line = line.replace('%%07%%', length_range[7])
                        line = line.replace('%%08%%', length_range[8])
                        line = line.replace('%%09%%', length_range[9])
                        line = line.replace('%%10%%', length_range[10])
                        out_text = out_text + line #+ "\n"
                    
                with open(os.path.join(os.path.dirname(__file__), 'arrow.qml'), 'w') as ff:
                    #save output
                    ff.write(out_text)
                    
                v_layer.loadNamedStyle(os.path.join(os.path.dirname(__file__), 'arrow.qml'))
                v_layer.triggerRepaint()
                if self.v_group is not None:
                    inst.addMapLayer(v_layer, False)
                    self.v_group.insertChildNode(-1, QgsLayerTreeLayer(v_layer))
                else:
                    inst.addMapLayer(v_layer, True)
                
#                    iface.setActiveLayer(v_layer)
        
        self.message_bottom_display.setText("Vectorization completed")


    def align_raster(self):
        '''
        https://qgis.org/pyqgis/3.14/analysis/QgsAlignRaster.html?highlight=alignraster#qgis.analysis.QgsAlignRaster.setDestinationCrs
        '''
        raster_list = []
        align_list = []
        tiff_dir = self.align_window.lineEdit_directory.text()
        self.lineEdit_out_dir.setText(tiff_dir)
        # Open ref TIFF file
        for lid, data in self.layers.items():
            if data['name'] == self.align_window.comboBox_reference.currentText():
                rlid = lid
                rraster = data['file']
                rname = data['name']
            elif data['name'] in self.Selected_layers:
                output = "%s/%s_aligned.tiff" % (tiff_dir, data['name'])
                align_list.append(QgsAlignRaster.Item(data['file'], output))
                raster_list.append(output)

        alignClass = QgsAlignRaster()
        align_list.insert(0, QgsAlignRaster.Item(rraster, "%s/%s_aligned.tiff" % (tiff_dir, rname)))
        
        ds = gdal.Open(self.layers[rlid]['file'])
        if ds is not None:
            xsize = ds.RasterXSize
            ysize = ds.RasterYSize
            proj = ds.GetProjection()
            geoT  = ds.GetGeoTransform()
            minx = geoT[0]
            maxy = geoT[3]
            maxx = minx + geoT[1] * xsize
            miny = maxy + geoT[5] * ysize
#            RasterSRS = osr.SpatialReference()
#                            outRasterSRS.ImportFromWkt(data["projection"])
#                            outRaster.SetProjection(outRasterSRS.ExportToWkt())
        else:
            print("[align_raster]", "BAD Reference FILE")
            return
        
        print("[align_raster]", xsize, ysize, minx, maxy, maxx, miny)
#        rLyr = QgsRasterLayer(rraster)
#        extent = rLyr.extent()
#        alignClass.setClipExtent(extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
#        print("[align_raster]", extent)
        s = alignClass.setParametersFromRaster(rraster)
        print("[align_raster]", s)
        alignClass.setRasters(align_list)
#        alignClass.setDestinationCrs(proj)
#        alignClass.setCellSize(xsize, ysize)
#        alignClass.setGridOffset(0)
        alignClass.setClipExtent(minx, miny, maxx, maxy)

#        alignClass.checkInputParameters()
        c = alignClass.checkInputParameters()
        print("[align_raster] Check:", c, alignClass.errorMessage())
        print("[align_raster] Extent:", alignClass.alignedRasterExtent())
        print("[align_raster] Size:", alignClass.alignedRasterSize())
        print("[align_raster] Suggested ref:", alignClass.suggestedReferenceLayer())
        
#        print("[align_raster]", alignClass.rasters())
        # Start Align
        for raster_item in align_list:
            e= alignClass.createAndWarp(raster_item)
        print("[align_raster] Error:", e, alignClass.errorMessage())

        # Display in QGIS
        if self.align_window.checkBox_display.isChecked():
            root = QgsProject.instance().layerTreeRoot()
            group = root.findGroup("ALIGN")
        
            if group is None:
                # Create the group
                tiff_group = root.addGroup("ALIGN")
                tiff_group.setExpanded(True)
                # Move to top 
                self.tiff_group = tiff_group.clone()
                root.insertChildNode(0, self.tiff_group)
                root.removeChildNode(tiff_group)
            else:
                self.tiff_group = group
                
            for tiff_file in raster_list:
                # Open resulting TIFF file
                ds = gdal.Open(tiff_file)
                layer_name = os.path.basename(tiff_file)
                
                if ds is not None and self.align_window.checkBox_display.isChecked():
                    band = ds.GetRasterBand(1)
                    data = band.ReadAsArray()
                    rlayer = QgsRasterLayer(tiff_file, layer_name, "gdal")
                    if self.tiff_group is not None:
                        QgsProject.instance().addMapLayer(rlayer, False)
                        self.tiff_group.insertChildNode(-1, QgsLayerTreeLayer(rlayer))
                    else:
                        QgsProject.instance().addMapLayer(rlayer, True)
                    
                    iface.setActiveLayer(rlayer)
                    # Make layer visible with inverted spectral styling
                    try:
                        # Create a single band pseudocolor renderer
                        provider = rlayer.dataProvider()
                        renderer = QgsSingleBandPseudoColorRenderer(provider, 1)
                        
                        # Set classification range to data range
                        data_min = np.nanmin(data)
                        data_max = np.nanmax(data)
                        renderer.setClassificationMin(data_min)
                        renderer.setClassificationMax(data_max)
                        
                        # Apply inverted spectral color ramp with quantile classification
                        self.apply_inverted_spectral_styling(rlayer, renderer, data, data_min, data_max)
                        
                        print(f"DEBUG: Applied inverted spectral styling to aligned TIFF layer")
                    except Exception as style_error:
                        print(f"DEBUG: Aligned TIFF styling failed: {style_error}")
                        # Fall back to basic renderer
                        renderer = QgsSingleBandPseudoColorRenderer(rlayer.dataProvider(), 1)
                        rlayer.setRenderer(renderer)
                        rlayer.triggerRepaint()     
                    mlyr = QgsProject.instance().layerTreeRoot().findLayer(rlayer.id())
                    mlyr.setItemVisibilityCheckedParentRecursive(True)
                    mlyr.setExpanded(False)
                    rlayer.setAutoRefreshEnabled(True)
                    ds.FlushCache()
                    ds = None
#                    print("[save_tiff]", layer_name)
                    layer_id = rlayer.id()
                    grp = self.tiff_group.name()
                else:
                    print("[align_tiff]", "Layer not displayed", layer_name)
                    self.message_bottom_display.setText("Rasters not aligned")
                    layer_id = ""
                    grp = ""
                    break
        
                # if layer already in dict, remove it
                if layer_id in self.layers.keys():
                    # check if same group
                    if grp == self.layers[layer_id]['group']:
                        self.layers.pop(layer_id)
                #add to dict
                self.layers[layer_id] = {
                                    'file'    : tiff_file,
                                    'group'   : grp,
                                    'name'    : layer_name,
                                    'nc'      : None,
                                    'selected': True,
                                    'checked' : True}
                # deselect self.Selected_layers
                self.layers[rlid]['selected'] = False
        
        self.message_bottom_display.setText("Rasters aligned and saved in : %s" % tiff_dir)
        self.align_window.close()
        self.update_layer_table()
        self.message_bottom_display.setText("Raster Alignment completed")

    def suggest_projection(self):
        """
        Auto-projection suggestion disabled - caused incorrect CRS selection.
        Users should manually select the appropriate CRS from the dropdown.
        Default CRS is WGS84 (EPSG:4326).
        """
        self.message_bottom_display.setText("Auto-detect CRS is disabled. Please manually select the appropriate CRS from the dropdown if needed. Default is WGS84 (EPSG:4326).")
        return False
            
    def add_suggestion_button(self):
        """
        Auto-detect CRS button disabled - caused incorrect CRS selection.
        The button is still added but now shows a message that auto-detection is disabled.
        """
        if not hasattr(self, 'suggestion_button'):
            self.suggestion_button = QtWidgets.QPushButton("Manual CRS Selection", self.tab_options)
            self.suggestion_button.setGeometry(QtCore.QRect(240, 40, 140, 22))
            self.suggestion_button.setToolTip("Auto-detect CRS is disabled. Use the CRS dropdown to manually select the appropriate projection. Default is WGS84 (EPSG:4326).")
            self.suggestion_button.clicked.connect(self.suggest_projection)
            self.suggestion_button.show()

    def apply_inverted_spectral_styling(self, rlayer, renderer, data, min_value, max_value):
        """
        Apply inverted spectral color ramp with quantile classification (around 50 classes)
        """
        from qgis.PyQt.QtGui import QColor
        
        # Create a color ramp shader
        shader = QgsColorRampShader()
        shader.setColorRampType(QgsColorRampShader.Interpolated)
        
        # Calculate quantiles for classification
        flat_data = data.flatten()
        valid_data = flat_data[~np.isnan(flat_data)]
        
        # Filter data to clipped range
        clipped_data = valid_data[(valid_data >= min_value) & (valid_data <= max_value)]
        
        if len(clipped_data) == 0:
            print("WARNING: No valid data in clipped range for styling")
            return
        
        # Number of classes (around 50)
        n_classes = 50
        
        # Calculate quantiles
        quantiles = []
        for i in range(n_classes + 1):
            if i == 0:
                quantiles.append(min_value)
            elif i == n_classes:
                quantiles.append(max_value)
            else:
                # Calculate quantile
                percentile = (i / n_classes) * 100
                quantile_value = np.percentile(clipped_data, percentile)
                quantiles.append(quantile_value)
        
        # Remove duplicates and sort
        quantiles = sorted(list(set(quantiles)))
        actual_classes = len(quantiles) - 1
        
        print(f"DEBUG: Using {actual_classes} quantile classes for styling")
        
        # Create inverted spectral color ramp items
        items = []
        for i, value in enumerate(quantiles):
            # Calculate position in the color ramp (0 to 1)
            if len(quantiles) > 1:
                position = i / (len(quantiles) - 1)
            else:
                position = 0
            
            # Inverted spectral colors (red to blue instead of blue to red)
            color = self.get_inverted_spectral_color(position)
            
            # Create label with appropriate precision
            if abs(value) < 0.001:
                label = f"{value:.6f}"
            elif abs(value) < 1:
                label = f"{value:.4f}"
            elif abs(value) < 100:
                label = f"{value:.2f}"
            else:
                label = f"{value:.1f}"
            
            items.append(QgsColorRampShader.ColorRampItem(value, color, label))
        
        # Set the shader properties
        shader.setColorRampItemList(items)
        
        # Create a raster shader and attach our color ramp shader
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(shader)
        
        # Set the renderer with the raster shader
        renderer.setShader(raster_shader)
        
        # Set the renderer on the layer
        rlayer.setRenderer(renderer)
        
        # Refresh the layer
        rlayer.triggerRepaint()
        
        print(f"DEBUG: Applied inverted spectral styling with {len(items)} color classes")

    def get_inverted_spectral_color(self, position):
        """
        Get color from inverted spectral color ramp (red to violet to blue)
        Position should be between 0 and 1
        """
        from qgis.PyQt.QtGui import QColor
        
        # Ensure position is between 0 and 1
        position = max(0, min(1, position))
        
        # Inverted spectral color ramp (red -> orange -> yellow -> green -> cyan -> blue -> violet)
        if position <= 0.166:  # Red to Orange
            progress = position / 0.166
            r = 213
            g = int(62 + (183 - 62) * progress)  # 62 to 183
            b = int(79 + (77 - 79) * progress)   # 79 to 77
        elif position <= 0.333:  # Orange to Yellow
            progress = (position - 0.166) / 0.167
            r = int(213 + (254 - 213) * progress)  # 213 to 254
            g = int(183 + (217 - 183) * progress)  # 183 to 217
            b = int(77 + (118 - 77) * progress)    # 77 to 118
        elif position <= 0.5:  # Yellow to Green
            progress = (position - 0.333) / 0.167
            r = int(254 + (144 - 254) * progress)  # 254 to 144
            g = int(217 + (255 - 217) * progress)  # 217 to 255
            b = int(118 + (144 - 118) * progress)  # 118 to 144
        elif position <= 0.666:  # Green to Cyan
            progress = (position - 0.5) / 0.166
            r = int(144 + (67 - 144) * progress)   # 144 to 67
            g = int(255 + (196 - 255) * progress)  # 255 to 196
            b = int(144 + (212 - 144) * progress)  # 144 to 212
        elif position <= 0.833:  # Cyan to Blue
            progress = (position - 0.666) / 0.167
            r = int(67 + (33 - 67) * progress)     # 67 to 33
            g = int(196 + (102 - 196) * progress)  # 196 to 102
            b = int(212 + (172 - 212) * progress)  # 212 to 172
        else:  # Blue to Violet
            progress = (position - 0.833) / 0.167
            r = int(33 + (103 - 33) * progress)    # 33 to 103
            g = int(102 + (0 - 102) * progress)    # 102 to 0
            b = int(172 + (31 - 172) * progress)   # 172 to 31
        
        return QColor(r, g, b)