# NetCDF2QGIS - Simplified Edition

## Overview
This plugin is a streamlined version of the NetCDF2QGIS plugin that was originally created by Copernicus Marine. The original plugin development was discontinued in 2024, but this simplified version maintains the core functionality needed for loading and processing NetCDF files in QGIS.

This version focuses exclusively on:
1. Loading NetCDF files
2. Selecting the correct CRS (Coordinate Reference System)
3. Clipping outlier values
4. Displaying NetCDF variables as raster layers

All animation, sequencing, and other advanced features have been removed to create a more stable and focused plugin.

## Acknowledgments
This plugin is a simplified version of the original NetCDF2QGIS plugin from Copernicus Marine. The original can be found at: https://help.marine.copernicus.eu/en/articles/7979674-how-to-download-and-use-the-netcdf2qgis-plugin-on-qgis

We acknowledge the original development team for their excellent work. This fork was created to maintain a working version with simplified functionality after the original plugin's maintenance was discontinued.

## Features

### Maintained from original:
- Loading NetCDF files into QGIS
- Variable selection and display
- CRS selection with auto-detection capabilities
- Outlier clipping for improved visualization
- Metadata viewing

### Removed for simplicity:
- Animation and sequence features
- Multiple variable synchronized viewing
- Advanced dialogs for layer manipulation
- Various legacy features that were causing stability issues

## Requirements
- QGIS 3.10 or later
- Windows 10 or later
- Python with netCDF4 and numpy packages (automatically installed by the plugin)

## Installation
1. Download this plugin
2. In QGIS, go to Plugins → Manage and Install Plugins → Install from ZIP
3. Select the downloaded ZIP file
4. Activate the plugin

## How to Use

### Basic Usage:
1. Open the plugin from the QGIS menu or toolbar
2. Click the '+' button to add a NetCDF file
3. The plugin will display available variables from your NetCDF file
4. Right-click on a variable and select "Add Layer" to display it on the map
5. The variable will be automatically displayed with appropriate styling

### Advanced Options:
- **CRS Selection**: Choose the appropriate projection for your data in the Options tab. The default is WGS84 (EPSG:4326), which works for most global datasets.
- **CRS Selection Note**: If the default CRS does not work for your data, please select a different CRS from the dropdown list. This plugin is designed for general NetCDF use, not specific to any particular region.
- **Outlier Clipping**: Configure in the preferences.xml file to automatically clip extreme values
- **Temporary Directory**: Set a location for temporary files in the Options tab

## Troubleshooting
If you encounter issues with Python dependencies, the plugin will attempt to automatically install required packages. If this fails, you may need to manually install:
```
pip install netCDF4==1.5.5.1 numpy
```

## Contributing
Feel free to submit issues and pull requests to improve this plugin.

## License
MIT License - see [LICENSE](LICENSE) file for details.

This simplified version is based on the original NetCDF2QGIS plugin from Copernicus Marine.

## Changelog
See [CHANGELOG.md](CHANGELOG.md) for version history and updates.

## Support
- Report issues: [GitHub Issues](https://github.com/NguyenTruongAnLab/NetCDF2QGIS-Simplified/issues)
- Documentation: This README file
- Original plugin reference: [Copernicus Marine NetCDF2QGIS](https://help.marine.copernicus.eu/en/articles/7979674-how-to-download-and-use-the-netcdf2qgis-plugin-on-qgis)

