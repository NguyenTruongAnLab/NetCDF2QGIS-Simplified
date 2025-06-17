"""Contains specific installation features to help fetch potentially missing libraries.
"""

import re
import os
import sys
import subprocess
import importlib

class ImportInstall:
    """Attempts to install libraries that cannot be found in the user env.
    """
    
    def __init__(self, lib):
        
        self.lib, self.version = self.sanitize_input(lib)
        try:
            importlib.import_module(self.lib)
        except:
            # Change dir to prevent subprocess errors in older Python versions
            original_dir = os.getcwd()
            os.chdir(os.path.dirname(os.path.realpath(__file__)))
            
            self.get_python_exe()
            # Ensure latest pip is being used
            self.install_library('pip')
            # Install the library
            if self.version:
                self.install_library(self.lib+self.version)
            else:
                self.install_library(self.lib)
            # Add library to path
            self.get_lib_location()
            if self.loc not in sys.path:
                sys.path.append(self.loc)
            
            os.chdir(original_dir)


    def sanitize_input(self, lib):
        """Splits library names and operator+version.
        """
        r = re.compile(r"(\w*)(.*)")
        m = r.search(lib)
        if m:
            return m.group(1), m.group(2)
        else:
            return lib, None


    def get_python_exe(self):
        """Fetches the python executable being used.
        """
        if os.name=='nt':
            # sys.executable cannot be used here since it returns the QGIS executable.
            res = subprocess.run("WHERE python", shell=True, capture_output=True)
            self.exe = res.stdout.decode('utf-8').strip()
        else:
            self.exe = sys.executable


    def install_library(self, lib):
        """Installs a given library using pip.
        """
        res = subprocess.run(
            f"\"{self.exe}\" -m pip install {lib} --upgrade --user", shell=True, capture_output=True
        )


    def get_lib_location(self):
        """Fetches a given library's location.
        """
        res = subprocess.run(f"\"{self.exe}\" -m pip show {self.lib}", shell=True, capture_output=True)
        out = res.stdout.decode('utf-8')
        self.loc = out[out.find("Location: ")+10:out.find("Requires: ")].strip()
