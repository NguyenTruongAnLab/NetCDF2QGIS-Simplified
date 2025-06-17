# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load NetCDF2GIS class from file NetCDF2GIS.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .import_netcdf import NetCDF2GIS
    return NetCDF2GIS(iface)
