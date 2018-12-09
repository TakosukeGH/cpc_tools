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
    image_size = EnumProperty(
        items = [
            ('0',"512 x 512",'','IMAGE_DATA',0),
            ('1',"1024 x 1024",'','IMAGE_DATA',1),
            ('2',"2048 x 2048",'','IMAGE_DATA',2),
            ('3',"4096 x 4096",'','IMAGE_DATA',3),
            ('4',"8192 x 8192",'','IMAGE_DATA',4)],
        name="Image Size", description="Image size", default="0")
    material_type = EnumProperty(
        items = [
            ('0',"Paper",'','MATERIAL',0),
            ('1',"Diffuse",'','MATERIAL',1)],
        name="Material Type", description="Material type", default="0")
    slide = FloatProperty(name="Slide", step=10, default=0.1)
    script_is_executed = BoolProperty(default=False)

# Operator
class InitProjectOperator(bpy.types.Operator):
    bl_idname = "cpc.init_project_operator"
    bl_label = "Init Project"
    bl_options = {'REGISTER', 'UNDO'}

    image_sizes = (512, 1024, 2048, 4096, 8192)
    img_name = "drawing_paper_{0}.png".format(512)

    use_gpu = True

    node_group_name = "paper"

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
        self.add_image(context)
        self.add_node_group()
        self.add_base(context)
        self.add_light(context)
        self.add_diffuse_material(context)

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
        scene.layers = self.get_layers([0, 10])

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

    def add_image(self, context):
        img_size = self.image_sizes[int(context.scene.cpc_scene_properties.image_size)]
        self.img_name = "drawing_paper_{0}.png".format(img_size)

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
        name = "cpc_base"

        bpy.ops.mesh.primitive_plane_add(radius=5.0,calc_uvs=True,location=(0.0, 0.0, 0.0),layers=self.get_layers([10]))
        obj = context.object
        obj.name = name
        obj.data.name = name
        obj.draw_type = 'WIRE'
        obj.cycles_visibility.glossy = False
        obj.cycles_visibility.transmission = False
        obj.cycles_visibility.scatter = False

        mat = self.add_base_material("cpc_base_material", (1.0, 1.0, 1.0, 1.0))

        obj.active_material = mat

    def add_base_material(self, name, color):
        mat = self.add_material(name)

        nodes = mat.node_tree.nodes
        for node_del in nodes:
            nodes.remove(node_del)

        node_texc = nodes.new("ShaderNodeTexCoord")
        node_texc.location = -200, 200

        node_rgb = nodes.new("ShaderNodeRGB")
        node_rgb.name = "cpc_color_node"
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
        name = "cpc_light"

        bpy.ops.mesh.primitive_plane_add(radius=50.0,location=(0.0, 0.0, 50.0),layers=self.get_layers([10]))
        obj = context.object
        obj.name = name
        obj.data.name = name
        obj.draw_type = 'WIRE'
        obj.cycles_visibility.camera = False

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

    def add_diffuse_material(self, context):
        mat = self.add_material("cpc_diffuse_material")

        mat.use_fake_user = True

        nodes = mat.node_tree.nodes
        for node_del in nodes:
            nodes.remove(node_del)

        node_rgb = nodes.new("ShaderNodeRGB")
        node_rgb.name = "cpc_color_node"
        node_rgb.location = -200, 0
        node_rgb.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)

        node_bsdf = nodes.new("ShaderNodeBsdfDiffuse")
        node_bsdf.location = 0, 0

        node_output = nodes.new("ShaderNodeOutputMaterial")
        node_output.location = 200, 0

        links = mat.node_tree.links
        links.new(node_rgb.outputs[0], node_bsdf.inputs[0])
        links.new(node_bsdf.outputs[0], node_output.inputs[0])

        return mat

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

        if not cpc_scene_properties.script_is_executed:
            layout = self.layout
            layout.label("Image Size")
            layout.prop(cpc_scene_properties, "image_size", text="")
            layout.row().separator()
            row = layout.row()
            row.scale_y = 2.0
            row.operator(InitProjectOperator.bl_idname, text=pgettext(InitProjectOperator.bl_label), icon='LOAD_FACTORY')
            return

        layout = self.layout

        col = layout.column(align=True)
        col.prop(cpc_scene_properties, "material_type", text="")

        col = layout.column(align=True)
        col.operator(AddCurveTool.bl_idname, icon='CURVE_BEZCIRCLE')
        col.operator(AddMeshTool.bl_idname, icon='MESH_GRID')

        layout.row().separator()

        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator(UpObject.bl_idname, icon='TRIA_UP')
        row.operator(DownObject.bl_idname, icon='TRIA_DOWN')
        col.prop(cpc_scene_properties, "slide")
        col.operator(ResetObject.bl_idname, icon='X')

        col = layout.column(align=True)

        col.label(text="Group:")
        col.operator("group.create", text="New Group")
        col.operator("group.objects_add_active", text="Add to Active")
        col.operator("group.objects_remove", text="Remove from Group")
        props = col.operator("object.select_grouped", text="Grouped")
        props.type = 'GROUP'

        layout.row().separator()

        if context.object is not None:
            obj = context.object
            if obj.type == 'CURVE':
                layout.prop(obj.data, "resolution_u")

            elif obj.type =='MESH':
                if "cpc_subsurf" in obj.modifiers:
                    mod = obj.modifiers["cpc_subsurf"]
                    layout.label(text="Subdivisions:")
                    layout.prop(mod, "levels")

            if obj.type =='MESH' or obj.type == 'CURVE':
                mat = obj.active_material
                if "cpc_color_node" in mat.node_tree.nodes:
                    node = mat.node_tree.nodes["cpc_color_node"]
                    out = node.outputs[0]
                    layout.label(text="Color:")
                    layout.prop(out, "default_value", text="")

# op
class AddCurveTool(Operator):
    bl_idname = "cpc.addcurve"
    bl_label = "Add curve"

    def invoke(self, context, event):
        loc=(0.0, 0.0, 0.1)
        if len(context.selected_objects) > 0:
            loc = (context.object.location[0], context.object.location[1], context.object.location[2] + 0.1)

        bpy.ops.curve.primitive_bezier_circle_add(location=loc)
        obj = context.object

        obj.lock_location[2] = True
        obj.lock_scale[2] = True

        curve = obj.data

        curve.dimensions = '2D'
        curve.resolution_u = 5

        material_type = context.scene.cpc_scene_properties.material_type
        if material_type == "0" and "cpc_base_material" in bpy.data.materials:
            mat = bpy.data.materials["cpc_base_material"]
        elif material_type == "1" and "cpc_diffuse_material" in bpy.data.materials:
            mat = bpy.data.materials["cpc_diffuse_material"]
        else:
            mat = bpy.data.materials.new(name="cpc_material")

        mat.diffuse_color = (1.0, 1.0, 1.0)
        curve.materials.append(mat)

        return {'FINISHED'}

class AddMeshTool(Operator):
    bl_idname = "cpc.addgrid"
    bl_label = "Add grid"

    def invoke(self, context, event):
        loc=(0.0, 0.0, 0.1)
        if len(context.selected_objects) > 0:
            loc = (context.object.location[0], context.object.location[1], context.object.location[2] + 0.1)

        bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3, location=loc)
        obj = context.object

        obj.lock_location[2] = True

        mod = obj.modifiers.new(name="cpc_subsurf", type='SUBSURF')
        mod.levels = 3
        mod.render_levels = 3

        mash = obj.data

        material_type = context.scene.cpc_scene_properties.material_type
        if material_type == "0" and "cpc_base_material" in bpy.data.materials:
            mat = bpy.data.materials["cpc_base_material"]
        elif material_type == "1" and "cpc_diffuse_material" in bpy.data.materials:
            mat = bpy.data.materials["cpc_diffuse_material"]
        else:
            mat = bpy.data.materials.new(name="cpc_material")

        mat.diffuse_color = (1.0, 1.0, 1.0)
        mash.materials.append(mat)

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

