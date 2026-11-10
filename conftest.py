#
# Licensed under Apache License, Version 2.0.
#
"""The plugin imports PartCAD's toolkit, plugin_models, the way a sandbox has it.

PartCAD runs a plugin with its wrappers on the path; the tests here run it in
the interpreter PartCAD is installed in, and put the same directory there.
"""

import os
import sys

import partcad

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(partcad.__file__)), "wrappers"))
