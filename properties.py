import sys
import requests
import png
import os
import mathutils
import math
import logging
import itertools
import colorsys
import bpy
import bgl
from collections import namedtuple
from bpy.types import Panel, Operator, SpaceView3D, PropertyGroup
from bpy.props import PointerProperty, StringProperty, CollectionProperty, IntProperty, BoolProperty, IntVectorProperty, FloatVectorProperty, FloatProperty, EnumProperty, BoolVectorProperty
from bpy.app.translations import pgettext

logger = logging.getLogger("cpc_exporter")

# Properties
class CPCSceneProperties(PropertyGroup):
    height = IntProperty(name="Height", min=4, max=65536, default=1080)
    width = IntProperty(name="Width", min=4, max=65536, default=1920)
    scale = FloatProperty(name="Scale", min=0.00001, max=100000.0, step=1, default=100.0, precision=3)
    export_path = StringProperty(name="Export path", subtype='FILE_PATH', description="Export path", default="//sample.svg")
    draw_area = BoolProperty(default=False)
    slide = FloatProperty(name="Slide", step=10, default=0.1)
    use_background = BoolProperty(name="Use backGround", default=False)
    background_color = FloatVectorProperty(name="Background Color", subtype='COLOR', size=4, min=0, max=1, default=[0.8, 0.8, 0.8, 0.8])
    script_is_executed = BoolProperty(default=False)
    lock_init_project = BoolProperty(default=True)

# Operator
class InitProjectOperator(bpy.types.Operator):
    bl_idname = "cpc.init_project_operator"
    bl_label = "Init Project"
    bl_options = {'REGISTER', 'UNDO'}

    ImageSize = namedtuple("ImageSize", "px512 px1024 px2048 px4096 px8192")
    image_size = ImageSize(512, 1024, 2048, 4096, 8192)
    Colors = namedtuple("Colors", "red yellow green cyan blue magenta")
    colors = Colors(0.0, 0.167, 0.333, 0.5, 0.667, 0.833)

    use_gpu = True

    node_group_name = "paper"
    img_size = image_size.px2048
    img_name = "drawing_paper_{0}.png".format(img_size)

    def invoke(self, context, event):
        logger.info("start")

        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        self.screen_setting(context)
        self.scene_setting(context.scene)
        self.render_setting(context.scene.render)
        self.cycles_setting(context.scene.cycles)
        self.gpu_setting(context)
        self.area_setting(bpy.data.screens)
        self.camrea_setting(context)

        # from setting_kirikamie.py
        self.init_compositor(context.scene.node_tree)
        self.add_image()
        self.add_node_group()
        self.add_base(context)
        self.add_light(context)

        context.scene.cpc_scene_properties.script_is_executed = True

        logger.info("end")

        return {'FINISHED'}

    def screen_setting(self, context):
        screens = bpy.data.screens

        screen_names = ["3D View Full", "Animation", "Game Logic", "Motion Tracking", "Video Editing"]

        for screen_name in screen_names:
            if screen_name in screens:
                bpy.ops.screen.delete({'screen': screens[screen_name]})

        context.window.screen = screens['Default']

    def scene_setting(self, scene):
        scene.render.engine = 'CYCLES'
        scene.use_nodes = True

    def render_setting(self, render):
        render.engine = 'CYCLES'
        render.resolution_x = 1024
        render.resolution_y = 1024
        render.resolution_percentage = 100
        # render.layers["RenderLayer"].use_pass_normal = True

    def cycles_setting(self, cycles):
        cycles.sample_clamp_indirect = 1.0
        cycles.samples = 100
        cycles.preview_samples = 10
        cycles.transparent_max_bounces = 0
        cycles.transparent_min_bounces = 0
        cycles.max_bounces = 2
        cycles.min_bounces = 2
        cycles.diffuse_bounces = 2
        cycles.glossy_bounces = 0
        cycles.transmission_bounces = 0
        cycles.volume_bounces = 0
        cycles.caustics_reflective = False
        cycles.caustics_refractive = False
        cycles.blur_glossy = 1.0
        cycles.film_transparent = True

    def gpu_setting(self, context):
        if self.use_gpu:
            if context.user_preferences.addons["cycles"].preferences.compute_device_type != 'CPU':
                context.scene.cycles.device = 'GPU'
                context.scene.render.tile_x = 512
                context.scene.render.tile_y = 512

    def area_setting(self, screens):
        for screen in screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    override = bpy.context.copy()
                    override["window"] = bpy.context.window
                    override["screen"] = screen
                    override["area"] = area
                    bpy.ops.view3d.view_persportho(override)
                    bpy.ops.view3d.viewnumpad(override, type='TOP')

                    logger.debug("area_setting in:" + screen.name)

                    for space in area.spaces:
                        space.use_occlude_geometry = False
                        # space.lens = 50

    def camrea_setting(self, context):
        layers = self.get_layers([19])
        bpy.ops.object.camera_add(location=(0.0, 0.0, 20.0), rotation=(0.0, 0.0, 0.0), layers=layers)
        camera = context.object
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = 10.0

    def init_compositor(self, node_tree):
        for n in node_tree.nodes:
            node_tree.nodes.remove(n)

        node_rlayers = node_tree.nodes.new("CompositorNodeRLayers")
        node_rlayers.location = -300, 200

        node_color_balance = node_tree.nodes.new("CompositorNodeColorBalance")
        node_color_balance.location = -100, 200

        node_comp = node_tree.nodes.new("CompositorNodeComposite")
        node_comp.location = 400, 200

        node_view = node_tree.nodes.new("CompositorNodeViewer")
        node_view.location = 400, 0

        links = node_tree.links
        links.new(node_rlayers.outputs[0], node_color_balance.inputs[1])
        links.new(node_color_balance.outputs[0], node_comp.inputs[0])
        links.new(node_color_balance.outputs[0], node_view.inputs[0])

    def add_image(self):

        if self.img_name in bpy.data.images:
            return

        url = "https://kaerudokoro.netlify.com/uncategorized/setting_kirikamie/" + self.img_name
        request = requests.get(url, stream=True)
        reader = png.Reader(request.raw)
        x, y, pixel_raw, meta = reader.asFloat()

        pixel_array = list(pixel_raw)
        pixel_array.reverse()
        pixels = [flatten for inner in pixel_array for flatten in inner]

        image = bpy.data.images.new(self.img_name, width=x, height=y)
        image.pixels = pixels
        image.pack(as_png=True)

        # image.file_format = 'PNG'

    def add_node_group(self):
        if self.node_group_name in bpy.data.node_groups:
            return

        group = bpy.data.node_groups.new(self.node_group_name, "ShaderNodeTree")

        # create group inputs
        group_inputs = group.nodes.new("NodeGroupInput")
        group_inputs.location = -600, 0
        group.inputs.new("NodeSocketVector","Vector")
        input_fac = group.inputs.new("NodeSocketFloat","Fac")
        input_fac.min_value = 0.0
        input_fac.max_value = 1.0
        group.inputs.new("NodeSocketColor","Color")

        # create nodes in a group
        node_map = group.nodes.new("ShaderNodeMapping")
        node_map.location = -400, 300
        node_map.scale = 0.1, 0.1, 1.0

        node_img = group.nodes.new("ShaderNodeTexImage")
        node_img.location = 0, 200
        image = bpy.data.images.get(self.img_name)
        node_img.image = image

        node_mix = group.nodes.new("ShaderNodeMixRGB")
        node_mix.location = 200, 0
        node_mix.blend_type = 'MULTIPLY'

        node_bsdf = group.nodes.new("ShaderNodeBsdfDiffuse")
        node_bsdf.location = 400, 0

        # create group outputs
        group_outputs = group.nodes.new("NodeGroupOutput")
        group_outputs.location = 600, 0
        group.outputs.new("NodeSocketShader","BSDF")

        # link inputs
        group.links.new(group_inputs.outputs["Vector"], node_map.inputs[0])
        group.links.new(group_inputs.outputs["Fac"], node_mix.inputs[0])
        group.links.new(group_inputs.outputs["Color"], node_mix.inputs[2])

        # link nodes together
        group.links.new(node_map.outputs[0], node_img.inputs[0])
        group.links.new(node_img.outputs[0], node_mix.inputs[1])
        group.links.new(node_mix.outputs[0], node_bsdf.inputs[0])

        #link output
        group.links.new(node_bsdf.outputs[0], group_outputs.inputs["BSDF"])

    def add_base(self, context):
        name = "base"

        bpy.ops.mesh.primitive_plane_add(radius=5.0,calc_uvs=True,location=(0.0, 0.0, 0.0),layers=self.get_layers([10]))
        obj = context.object
        obj.name = name
        obj.data.name = name
        obj.draw_type = 'WIRE'
        obj.cycles_visibility.glossy = False
        obj.cycles_visibility.transmission = False
        obj.cycles_visibility.scatter = False

        mat = self.add_base_material(name, (1.0, 1.0, 1.0, 1.0))

        obj.active_material = mat

    def add_base_material(self, name, color):
        mat = self.add_material(name)

        nodes = mat.node_tree.nodes
        for node_del in nodes:
            nodes.remove(node_del)

        node_texc = nodes.new("ShaderNodeTexCoord")
        node_texc.location = -200, 200

        node_rgb = nodes.new("ShaderNodeRGB")
        node_rgb.location = -200, -100
        node_rgb.outputs[0].default_value = color

        group = nodes.new("ShaderNodeGroup")
        group.node_tree = bpy.data.node_groups.get(self.node_group_name)
        group.location = 0, 0
        group.inputs[1].default_value = 1.0

        node_output = nodes.new("ShaderNodeOutputMaterial")
        node_output.location = 200, 0

        links = mat.node_tree.links
        links.new(node_texc.outputs[4], group.inputs[0])
        links.new(node_rgb.outputs[0], group.inputs[2])
        links.new(group.outputs[0], node_output.inputs[0])

        return mat

    def add_material(self, name):
        mat = bpy.data.materials.new("Material")
        mat.name = name
        mat.use_nodes = True
        return mat

    def add_light(self, context):
        name = "light"

        bpy.ops.mesh.primitive_plane_add(radius=50.0,location=(0.0, 0.0, 50.0),layers=self.get_layers([10]))
        obj = context.object
        obj.name = name
        obj.data.name = name
        obj.draw_type = 'WIRE'

        mat = self.add_material(name)
        nodes = mat.node_tree.nodes
        nodes.remove(nodes.get("Diffuse BSDF"))

        node = nodes.new("ShaderNodeEmission")
        node.location = 0, 300
        node.inputs[1].default_value = 2.0

        node_output = nodes.get("Material Output")

        links = mat.node_tree.links
        links.new(node.outputs[0], node_output.inputs[0])

        obj.active_material = mat

    def get_layers(self, num_list):
        layers = [False] * 20
        for num in num_list:
            layers[num] = True
        return layers

# UI
class CPCToolPanel(Panel):
    bl_idname = "OBJECT_PT_cpc"
    bl_label = "Cut Paper Collage Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = 'CPC'

    def draw(self, context):
        cpc_scene_properties = context.scene.cpc_scene_properties

        layout = self.layout

        split = layout.split(percentage=0.85)
        col = split.column()
        col.operator(InitProjectOperator.bl_idname, text=pgettext(InitProjectOperator.bl_label))

        if cpc_scene_properties.lock_init_project:
            col.enabled = False

        col = split.column()
        if cpc_scene_properties.lock_init_project:
            icon = 'LOCKED'
        else:
            icon = 'UNLOCKED'
        col.prop(cpc_scene_properties, "lock_init_project", text="", icon=icon)

        if cpc_scene_properties.script_is_executed:
            split.enabled = False

        layout.row().separator()

        row = layout.row()
        row.operator(AddCurveTool.bl_idname, icon='CURVE_BEZCIRCLE')

        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator(UpObject.bl_idname, icon='TRIA_UP')
        row.operator(DownObject.bl_idname, icon='TRIA_DOWN')
        col.prop(cpc_scene_properties, "slide")
        col.operator(ResetObject.bl_idname, icon='X')

        layout.row().separator()

        if context.object is not None:
            obj = context.object
            if obj.type == 'CURVE':
                row = layout.row()
                row.prop(obj.data, "resolution_u")
                if len(obj.data.materials) > 0:
                    mat = obj.data.materials[0]
                    col = layout.column(align=True)
                    col.label("Viewport Color:")
                    col.prop(mat, "diffuse_color", text="")
                    col.prop(mat, "alpha")

# op
class AddCurveTool(Operator):
    bl_idname = "cpc.addcurve"
    bl_label = "Add curve"

    def invoke(self, context, event):
        loc=(0.0, 0.0, 0.0)
        if len(context.selected_objects) > 0:
            loc = (context.object.location[0], context.object.location[1], context.object.location[2] + 0.1)

        bpy.ops.curve.primitive_bezier_circle_add(location=loc)
        obj = context.object

        obj.lock_location[2] = True

        curve = obj.data

        curve.dimensions = '2D'
        curve.resolution_u = 5

        mat = bpy.data.materials.new(name="svg_material")
        mat.diffuse_color = (1.0, 1.0, 1.0)
        curve.materials.append(mat)

        return {'FINISHED'}

class UpObject(Operator):
    bl_idname = "cpc.upobject"
    bl_label = "Up"

    def invoke(self, context, event):
        slide = context.scene.cpc_scene_properties.slide
        for obj in context.selected_objects:
            obj.location[2] += slide

        return {'FINISHED'}

class DownObject(Operator):
    bl_idname = "cpc.downobject"
    bl_label = "Down"

    def invoke(self, context, event):
        slide = context.scene.cpc_scene_properties.slide
        for obj in context.selected_objects:
            obj.location[2] -= slide

        return {'FINISHED'}

class ResetObject(Operator):
    bl_idname = "cpc.resetobject"
    bl_label = "Reset"

    def invoke(self, context, event):
        for obj in context.selected_objects:
            obj.location[2] = 0.0

        return {'FINISHED'}

translations = {
    "ja_JP": {
        ("*", "Base Settings"): "基本設定",
        ("*", "Export SVG"): "Export SVG",
        ("*", "Use background"): "背景色を使用",
    }
}

def register():
    bpy.types.Scene.cpc_scene_properties = PointerProperty(type=CPCSceneProperties)

    bpy.app.translations.register(__name__, translations)

def unregister():
    bpy.app.translations.unregister(__name__)
    del bpy.types.Scene.cpc_scene_properties

