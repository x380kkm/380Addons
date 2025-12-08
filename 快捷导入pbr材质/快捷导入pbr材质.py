bl_info = {
    "name": "PBR快捷导入",
    "author": "380kkm (Modified)",
    "version": (1, 4),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > PBR快导",
    "description": "快捷导入PBR材质 原作者b站快绘,使用Gemini修改",
    "category": "导入工具"
}

import bpy
import os
from mathutils import Vector
import math

# === 1. 修正后的贴图映射表 ===
texture_type_mapping = {
    # === 图片对应规范 ===
    "_c": "BaseColor",      # 基础色
    "_n": "Normal",         # 法线
    "_e": "Emission",       # 自发光 (新增)
    "_ao": "AmbientOcclusion", # AO
    "_r": "Roughness",      # 粗糙度
    "_m": "Metallic",       # 金属度
    "_arm": "ARM",          # 混合贴图 (AO=R, Rough=G, Metal=B)
    
    # === 其他常见简写 ===
    "_d": "Displacement",
    "_h": "Displacement",
    "_o": "Alpha",
    
    # === 标准全称容错 ===
    "base": "BaseColor",
    "color": "BaseColor",
    "diffuse": "BaseColor",
    "albedo": "BaseColor",
    "col": "BaseColor",
    "emissive": "Emission",
    "emission": "Emission",
    "metallic": "Metallic",
    "metalness": "Metallic",
    "roughness": "Roughness",
    "normal": "Normal",
    "nrm": "Normal",
    "bump": "Bump",
    "height": "Displacement",
    "displacement": "Displacement",
    "disp": "Displacement",
    "opacity": "Alpha",
    "alpha": "Alpha",
    "ao": "AmbientOcclusion",
}

def load_texture_node(material, texture_path, label, location, is_color=True):
    """创建并返回纹理节点"""
    nodes = material.node_tree.nodes
    node = nodes.new(type='ShaderNodeTexImage')
    try:
        node.image = bpy.data.images.load(texture_path)
    except:
        print(f"无法加载图片: {texture_path}")
        return node
        
    node.label = label
    node.location = location
    # 对于非颜色数据（法线、粗糙度、金属度、ARM等），设置为非SRGB
    if not is_color:
        if hasattr(node.image, 'colorspace_settings'):
            node.image.colorspace_settings.is_data = True
            # Blender 2.8+ 常用 'Non-Color'
            try:
                node.image.colorspace_settings.name = 'Non-Color'
            except:
                pass 
    return node

def create_pbr_material(material, texture_files):
    """为材质添加PBR贴图并排布节点"""
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    # 清空现有节点
    for node in nodes:
        nodes.remove(node)

    # 创建核心节点
    principled_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled_node.location = Vector((200, -200))

    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = Vector((600, -200))
    links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])

    # 整理文件列表
    ordered_texture_files = {key: None for key in set(texture_type_mapping.values())}

    for file_path in texture_files:
        base_name = os.path.splitext(os.path.basename(file_path))[0].lower()
        if "sheenopacity" in base_name: continue
        
        texture_type = None
        # 1. 后缀优先匹配 (比如 _c, _arm)
        for key, type_name in texture_type_mapping.items():
            if base_name.endswith(key):
                texture_type = type_name
                break
        # 2. 包含匹配
        if not texture_type:
             texture_type = next((v for k, v in texture_type_mapping.items() if k in base_name), None)

        if texture_type:
            if ordered_texture_files[texture_type] is None:
                ordered_texture_files[texture_type] = file_path

    # === 2. 更新处理顺序，加入 ARM 和 Emission ===
    offset_y = 0
    texture_nodes = {}
    normal_map_node = None 
    process_order = ["BaseColor", "ARM", "Metallic", "Roughness", "Emission", "Normal", "Bump", "Alpha", "Displacement", "AmbientOcclusion"]

    for texture_type in process_order:
        file_path = ordered_texture_files.get(texture_type)
        if file_path:
            # 只有 BaseColor 和 Emission 是颜色数据，其他(包括ARM)都是非颜色数据
            is_color_data = texture_type in ["BaseColor", "Emission"]
            
            texture_node = load_texture_node(material, file_path, texture_type, Vector((-400, offset_y)), is_color_data)
            texture_nodes[texture_type] = texture_node

            # === 连接逻辑 ===
            if texture_type == "BaseColor":
                links.new(texture_node.outputs['Color'], principled_node.inputs['Base Color'])
            
            # === 新增：ARM 混合贴图逻辑 ===
            elif texture_type == "ARM":
                # 添加分离RGB节点 (Blender 3.3+ 改名为 Separate Color，为了兼容2.80使用 Separate RGB)
                sep_node = nodes.new(type='ShaderNodeSeparateRGB')
                sep_node.location = Vector((-150, offset_y - 50))
                links.new(texture_node.outputs['Color'], sep_node.inputs['Image'])
                
                # 业界标准: R=AO, G=Roughness, B=Metallic
                # 连接粗糙度 (Green)
                links.new(sep_node.outputs['G'], principled_node.inputs['Roughness'])
                # 连接金属度 (Blue)
                links.new(sep_node.outputs['B'], principled_node.inputs['Metallic'])
                # AO (Red) 通常需要通过 MixRGB 混合到 BaseColor，这里暂不做复杂处理，仅留作节点
            
            elif texture_type == "Metallic":
                # 如果没有ARM贴图，才连接单独的金属度
                if "ARM" not in ordered_texture_files:
                    links.new(texture_node.outputs['Color'], principled_node.inputs['Metallic'])
            
            elif texture_type == "Roughness":
                # 如果没有ARM贴图，才连接单独的粗糙度
                if "ARM" not in ordered_texture_files:
                    links.new(texture_node.outputs['Color'], principled_node.inputs['Roughness'])
            
            # === 新增：自发光逻辑 ===
            elif texture_type == "Emission":
                # 兼容不同Blender版本的输入名称
                target_input = 'Emission' 
                if 'Emission Color' in principled_node.inputs:
                    target_input = 'Emission Color' # Blender 4.0+
                
                links.new(texture_node.outputs['Color'], principled_node.inputs[target_input])
                # 默认把自发光强度设为1 (如果存在 Strength 输入)
                if 'Emission Strength' in principled_node.inputs:
                    principled_node.inputs['Emission Strength'].default_value = 1.0

            elif texture_type == "Normal":
                normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                normal_map_node.location = Vector((-150, -600)) 
                links.new(texture_node.outputs['Color'], normal_map_node.inputs['Color'])
                links.new(normal_map_node.outputs['Normal'], principled_node.inputs['Normal'])
            
            elif texture_type == "Bump":
                bump_map_node = nodes.new(type='ShaderNodeBump')
                bump_map_node.location = Vector((-150, -800))
                links.new(texture_node.outputs['Color'], bump_map_node.inputs['Height'])
                if normal_map_node:
                    links.new(normal_map_node.outputs['Normal'], bump_map_node.inputs['Normal'])
                links.new(bump_map_node.outputs['Normal'], principled_node.inputs['Normal'])
            
            elif texture_type == "Displacement":
                displacement_node = nodes.new(type='ShaderNodeDisplacement')
                displacement_node.location = Vector((-50, -1000))
                links.new(texture_node.outputs['Color'], displacement_node.inputs['Height'])
                links.new(displacement_node.outputs['Displacement'], output_node.inputs['Displacement'])
            
            elif texture_type == "Alpha":
                links.new(texture_node.outputs['Color'], principled_node.inputs['Alpha'])
            
            offset_y -= 300 

    # 重新排列左侧纹理节点位置
    offset_y = 0
    for texture_type in process_order:
        if texture_type in texture_nodes:
            texture_nodes[texture_type].location.y = -offset_y
            offset_y += 300

    # 统一添加坐标映射
    tex_coord_node = nodes.new(type='ShaderNodeTexCoord')
    tex_coord_node.location = Vector((-900, 0))
    mapping_node = nodes.new(type='ShaderNodeMapping')
    mapping_node.location = Vector((-700, 0))
    links.new(tex_coord_node.outputs['UV'], mapping_node.inputs['Vector'])

    for texture_type in process_order:
        if texture_type in texture_nodes:
            links.new(mapping_node.outputs['Vector'], texture_nodes[texture_type].inputs['Vector'])

# PBR导入核心类
class ImportPBRTexturesOperator(bpy.types.Operator):
    bl_idname = "spio.import_pbr_textures"
    bl_label = "导入PBR材质(球+板)"

    def execute(self, context):
        folder_path = bpy.path.abspath(context.scene.pbr_folder_path)

        if not os.path.exists(folder_path):
            self.report({'ERROR'}, "文件夹路径无效")
            return {'CANCELLED'}
        
        valid_subfolders = []
        for subfolder_name in os.listdir(folder_path):
            subfolder_path = os.path.join(folder_path, subfolder_name)
            if os.path.isdir(subfolder_path):
                texture_files = [
                    os.path.join(subfolder_path, f) for f in os.listdir(subfolder_path)
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tga'))
                ]
                if texture_files:
                    valid_subfolders.append((subfolder_name, texture_files))

        if not valid_subfolders:
            self.report({'WARNING'}, "未找到包含贴图的子文件夹")
            return {'CANCELLED'}

        spacing_x = 3.0
        spacing_y = 3.0
        grid_cols = math.ceil(math.sqrt(len(valid_subfolders)))

        for idx, (name, files) in enumerate(valid_subfolders):
            row = idx // grid_cols
            col = idx % grid_cols
            loc_x = col * spacing_x
            loc_y = -row * spacing_y
            
            # 材质
            material = bpy.data.materials.new(name=name)
            material.use_nodes = True
            create_pbr_material(material, files)

            # 平面
            bpy.ops.mesh.primitive_plane_add(size=2.0, location=(loc_x, loc_y, 0))
            plane = bpy.context.active_object
            plane.name = f"{name}_Plane"
            plane.data.materials.append(material)

            # 材质球
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, location=(loc_x, loc_y, 0.6))
            sphere = bpy.context.active_object
            sphere.name = f"{name}_Sphere"
            bpy.ops.object.shade_smooth()
            sphere.data.materials.append(material)

        self.report({'INFO'}, f"成功导入 {len(valid_subfolders)} 组材质")
        return {'FINISHED'}

# 面板
class PBRMaterialPanel(bpy.types.Panel):
    bl_label = "PBR材质导入 (修正版)"
    bl_idname = "PBR_MATERIAL_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "导入工具"

    def draw(self, context):
        layout = self.layout
        layout.label(text="PBR 批量导入工具")
        layout.prop(context.scene, "pbr_folder_path")
        layout.operator("spio.import_pbr_textures", text="一键导入")

def register():
    bpy.utils.register_class(ImportPBRTexturesOperator)
    bpy.utils.register_class(PBRMaterialPanel)
    bpy.types.Scene.pbr_folder_path = bpy.props.StringProperty(
        name="贴图路径",
        description="选择包含PBR贴图子文件夹的根目录",
        subtype='DIR_PATH'
    )

def unregister():
    bpy.utils.unregister_class(ImportPBRTexturesOperator)
    bpy.utils.unregister_class(PBRMaterialPanel)
    del bpy.types.Scene.pbr_folder_path

if __name__ == "__main__":
    register()