bl_info= {
    "name": "CPC Exporter",
    "author": "Takosuke",
    "version": (0, 0, 1),
    "blender": (2, 79, 0),
    "location": "View3D > Tools Panel",
    "description": "Cut Paper Collage Tools.",
    "support": "COMMUNITY",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": '3D View'}

if "bpy" in locals():
    import imp
    imp.reload(properties)
else:
    from . import properties

import bpy
import logging

logger = logging.getLogger("cpc_exporter")

if not logger.handlers:
    hdlr = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)-7s %(asctime)s %(message)s (%(module)s %(funcName)s)", datefmt="%H:%M:%S")
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG) # DEBUG, INFO, WARNING, ERROR, CRITICAL

logger.debug("init logger") # debug, info, warning, error, critical

def register():
    bpy.utils.register_module(__name__)
    properties.register()

def unregister():
    properties.unregister()
    bpy.utils.unregister_module(__name__)

if __name__ == "__main__":
    register()
