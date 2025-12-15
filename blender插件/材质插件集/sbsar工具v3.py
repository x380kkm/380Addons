bl_info = {
    "name": "PBR & SBSAR工具箱",
    "author": "380kkm (Modified by Gemini)",
    "version": (2, 6), 
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > PBR工具",
    "description": "PBR导入、预览生成、UV处理及网格/材质清理工具",
    "category": "3D View"
}

import bpy
import os
import math
from mathutils import Vector

# =============================================================================
# 全局工具函数
# =============================================================================

def scan_files_with_depth(root_path, depth, extensions):
    """递归扫描指定目录深度的文件"""
    root_path = os.path.abspath(root_path)
    root_depth = root_path.rstrip(os.path.sep).count(os.path.sep)
    found_groups = []
    
    # 遍历目录树
    for root, dirs, files in os.walk(root_path):
        current_depth = root.rstrip(os.path.sep).count(os.path.sep) - root_depth
        
        # 达到指定深度停止递归
        if current_depth >= depth:
            del dirs[:]
            
        # 筛选符合后缀的文件
        valid_files = [os.path.join(root, f) for f in files if f.lower().endswith(extensions)]
        if valid_files:
            folder_name = os.path.basename(root) or os.path.basename(root_path)
            found_groups.append((folder_name, valid_files))
    return found_groups

def create_preview_geometry(name, location, material):
    """创建预览用的几何体 (平面 + 球体)"""
    # 1. 创建平面
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(location[0], location[1], 0))
    plane = bpy.context.active_object
    plane.name = f"{name}_Plane"
    if material: plane.data.materials.append(material)

    # 2. 创建球体
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, location=(location[0], location[1], 0.6))
    sphere = bpy.context.active_object
    sphere.name = f"{name}_Sphere"
    bpy.ops.object.shade_smooth()
    if material: sphere.data.materials.append(material)
    
    return plane, sphere

# =============================================================================
# 功能 1：PBR 导入
# =============================================================================

# 贴图后缀名关键字映射
texture_type_mapping = {
    "_c": "BaseColor", "_n": "Normal", "_e": "Emission", "_ao": "AmbientOcclusion",
    "_r": "Roughness", "_m": "Metallic", "_arm": "ARM", "_d": "Displacement",
    "_h": "Displacement", "_o": "Alpha", "base": "BaseColor", "color": "BaseColor",
    "diffuse": "BaseColor", "albedo": "BaseColor", "col": "BaseColor",
    "emissive": "Emission", "emission": "Emission", "metallic": "Metallic",
    "metalness": "Metallic", "roughness": "Roughness", "normal": "Normal",
    "nrm": "Normal", "bump": "Bump", "height": "Displacement",
    "displacement": "Displacement", "disp": "Displacement", "opacity": "Alpha",
    "alpha": "Alpha", "ao": "AmbientOcclusion",
}

def load_texture_node(material, texture_path, label, location, is_color=True):
    """加载图片节点并应用色彩空间设置"""
    nodes = material.node_tree.nodes
    node = nodes.new(type='ShaderNodeTexImage')
    try: node.image = bpy.data.images.load(texture_path)
    except: return node
    
    node.label = label
    node.location = location
    
    # 设置非彩色数据 (如法向、粗糙度)
    if not is_color and hasattr(node.image, 'colorspace_settings'):
        node.image.colorspace_settings.is_data = True
        try: node.image.colorspace_settings.name = 'Non-Color'
        except: pass 
    return node

def create_pbr_material(material, texture_files):
    """构建 PBR 材质节点树"""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in nodes: nodes.remove(node)

    # 1. 创建基础节点 (原理化BSDF + 输出)
    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled.location = Vector((200, -200))
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = Vector((600, -200))
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    # 2. 识别并整理文件列表
    ordered_files = {key: None for key in set(texture_type_mapping.values())}
    for f in texture_files:
        bn = os.path.splitext(os.path.basename(f))[0].lower()
        if "sheenopacity" in bn: continue
        
        # 匹配关键字
        t_type = None
        for k, v in texture_type_mapping.items():
            if bn.endswith(k):
                t_type = v
                break
        if not t_type: t_type = next((v for k, v in texture_type_mapping.items() if k in bn), None)
        if t_type and ordered_files[t_type] is None: ordered_files[t_type] = f

    # 3. 创建并链接贴图节点
    offset_y = 0
    tex_nodes = {}
    norm_node = None 
    order = ["BaseColor", "ARM", "Metallic", "Roughness", "Emission", "Normal", "Bump", "Alpha", "Displacement", "AmbientOcclusion"]

    for t_type in order:
        path = ordered_files.get(t_type)
        if path:
            is_col = t_type in ["BaseColor", "Emission"]
            node = load_texture_node(material, path, t_type, Vector((-400, offset_y)), is_col)
            tex_nodes[t_type] = node

            # 根据类型链接到原理化节点
            if t_type == "BaseColor":
                links.new(node.outputs['Color'], principled.inputs['Base Color'])
            elif t_type == "ARM": # 分离 ARM 贴图 (AO, Roughness, Metallic)
                sep = nodes.new(type='ShaderNodeSeparateRGB')
                sep.location = Vector((-150, offset_y - 50))
                links.new(node.outputs['Color'], sep.inputs['Image'])
                links.new(sep.outputs['G'], principled.inputs['Roughness'])
                links.new(sep.outputs['B'], principled.inputs['Metallic'])
            elif t_type == "Metallic" and "ARM" not in ordered_files:
                links.new(node.outputs['Color'], principled.inputs['Metallic'])
            elif t_type == "Roughness" and "ARM" not in ordered_files:
                links.new(node.outputs['Color'], principled.inputs['Roughness'])
            elif t_type == "Emission":
                tgt = 'Emission Color' if 'Emission Color' in principled.inputs else 'Emission'
                links.new(node.outputs['Color'], principled.inputs[tgt])
                if 'Emission Strength' in principled.inputs: principled.inputs['Emission Strength'].default_value = 1.0
            elif t_type == "Normal":
                norm_node = nodes.new(type='ShaderNodeNormalMap')
                norm_node.location = Vector((-150, -600)) 
                links.new(node.outputs['Color'], norm_node.inputs['Color'])
                links.new(norm_node.outputs['Normal'], principled.inputs['Normal'])
            elif t_type == "Bump":
                bump = nodes.new(type='ShaderNodeBump')
                bump.location = Vector((-150, -800))
                links.new(node.outputs['Color'], bump.inputs['Height'])
                if norm_node: links.new(norm_node.outputs['Normal'], bump.inputs['Normal'])
                links.new(bump.outputs['Normal'], principled.inputs['Normal'])
            elif t_type == "Displacement":
                disp = nodes.new(type='ShaderNodeDisplacement')
                disp.location = Vector((-50, -1000))
                links.new(node.outputs['Color'], disp.inputs['Height'])
                links.new(disp.outputs['Displacement'], output.inputs['Displacement'])
            elif t_type == "Alpha":
                links.new(node.outputs['Color'], principled.inputs['Alpha'])
            
            offset_y -= 300 

    # 4. 添加纹理坐标映射
    tex_coord = nodes.new(type='ShaderNodeTexCoord')
    tex_coord.location = Vector((-900, 0))
    mapping = nodes.new(type='ShaderNodeMapping')
    mapping.location = Vector((-700, 0))
    links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
    
    # 连接所有纹理的矢量输入
    for t_type in order:
        if t_type in tex_nodes:
            tex_nodes[t_type].location.y = -offset_y
            offset_y += 300
            links.new(mapping.outputs['Vector'], tex_nodes[t_type].inputs['Vector'])

class ImportPBRTexturesOperator(bpy.types.Operator):
    bl_idname = "spio.import_pbr_textures"
    bl_label = "导入PBR材质"
    bl_description = "扫描贴图文件夹并自动构建材质"

    def execute(self, context):
        # 1. 验证路径
        folder = bpy.path.abspath(context.scene.toolbox_folder_path)
        if not os.path.exists(folder):
            self.report({'ERROR'}, "路径无效")
            return {'CANCELLED'}
        
        # 2. 扫描文件
        groups = scan_files_with_depth(folder, context.scene.toolbox_recursion_depth, ('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tga'))
        if not groups:
            self.report({'WARNING'}, "未找到贴图")
            return {'CANCELLED'}

        # 3. 创建材质
        count = 0
        for name, files in groups:
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            create_pbr_material(mat, files)
            count += 1
        self.report({'INFO'}, f"导入 {count} 个材质")
        return {'FINISHED'}

# =============================================================================
# 功能 2：SBSAR 导入
# =============================================================================

class ImportSBSAROperator(bpy.types.Operator):
    bl_idname = "spio.import_sbsar_files"
    bl_label = "导入 SBSAR"
    bl_description = "批量导入 .sbsar 文件"

    def execute(self, context):
        # 1. 检查插件依赖
        if not hasattr(bpy.ops, "substance"):
            self.report({'ERROR'}, "需安装 Substance 插件")
            return {'CANCELLED'}

        # 2. 扫描文件
        folder = bpy.path.abspath(context.scene.toolbox_folder_path)
        groups = scan_files_with_depth(folder, context.scene.toolbox_recursion_depth, ('.sbsar'))
        
        total = sum(len(f) for _, f in groups)
        if total == 0:
            self.report({'WARNING'}, "未找到 SBSAR")
            return {'CANCELLED'}

        # 3. 调用插件导入
        for _, files in groups:
            if not files: continue
            try:
                bpy.ops.substance.ui_sbsar_load(
                    filepath=files[0], 
                    directory=os.path.dirname(files[0]) + os.sep,          
                    files=[{"name": os.path.basename(f)} for f in files]
                )
            except Exception as e: print(f"Error: {e}")
            
        self.report({'INFO'}, f"导入 {total} 个 SBSAR")
        return {'FINISHED'}

# =============================================================================
# 功能 3：预览生成
# =============================================================================

class GeneratePreviewsOperator(bpy.types.Operator):
    bl_idname = "spio.generate_previews"
    bl_label = "生成材质预览"
    
    target_mode: bpy.props.EnumProperty(
        items=[('ALL', "所有材质", ""), ('SELECTED', "选中物体材质", "")],
        default='ALL'
    )

    def execute(self, context):
        spacing = 3.0
        start_loc = context.scene.cursor.location.copy()
        mats = []
        
        # 1. 获取目标材质列表
        if self.target_mode == 'ALL':
            mats = [m for m in bpy.data.materials if m.use_nodes]
        elif self.target_mode == 'SELECTED':
            temp = set()
            for obj in context.selected_objects:
                if obj.type == 'MESH':
                    for s in obj.material_slots:
                        if s.material and s.material.use_nodes: temp.add(s.material)
            mats = list(temp)
        
        if not mats: return {'CANCELLED'}
        mats.sort(key=lambda m: m.name)
        
        # 2. 网格排列并生成
        grid = math.ceil(math.sqrt(len(mats)))
        for idx, mat in enumerate(mats):
            r, c = idx // grid, idx % grid
            create_preview_geometry(mat.name, (start_loc.x + c*spacing, start_loc.y - r*spacing, start_loc.z), mat)
            
        return {'FINISHED'}

# =============================================================================
# 功能 4：批量工具 (集合 & 选中)
# =============================================================================

class BatchApplyMaterialUVOperator(bpy.types.Operator):
    bl_idname = "spio.batch_apply_mat_uv"
    bl_label = "应用材质与UV (集合)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        col = context.scene.batch_target_collection
        mat = context.scene.batch_target_material
        size = context.scene.batch_cube_size
        if not col: return {'CANCELLED'}

        # 保存当前状态
        orig_act = context.view_layer.objects.active
        orig_sel = context.selected_objects[:]
        bpy.ops.object.select_all(action='DESELECT')

        count = 0
        for obj in col.objects:
            if obj.type == 'MESH':
                # 1. 替换材质
                if mat:
                    obj.data.materials.clear()
                    obj.data.materials.append(mat)
                
                # 2. 立方体投射 UV
                context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.cube_project(cube_size=size)
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.select_set(False)
                count += 1
        
        # 恢复状态
        if orig_act: context.view_layer.objects.active = orig_act
        for obj in orig_sel: obj.select_set(True)
        self.report({'INFO'}, f"处理了 {count} 个物体")
        return {'FINISHED'}

class BatchRotateUVOperator(bpy.types.Operator):
    bl_idname = "spio.batch_rotate_uv_90"
    bl_label = "UV旋转90° (集合)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        col = context.scene.batch_target_collection
        if not col: return {'CANCELLED'}
        if context.object and context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        
        count = 0
        for obj in col.objects:
            if obj.type == 'MESH' and obj.data.uv_layers.active:
                # 旋转所有 UV 坐标
                for loop in obj.data.uv_layers.active.data:
                    loop.uv = Vector((1.0 - loop.uv.y, loop.uv.x))
                count += 1
        self.report({'INFO'}, f"集合: {count} 个物体UV已旋转")
        return {'FINISHED'}

class RotateUVSelectedOperator(bpy.types.Operator):
    bl_idname = "spio.rotate_uv_selected_90"
    bl_label = "UV旋转90° (选中)"
    bl_description = "将所有选中物体的UV旋转90度"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sel_objs = context.selected_objects
        if not sel_objs:
            self.report({'WARNING'}, "未选中任何物体")
            return {'CANCELLED'}

        if context.object and context.object.mode != 'OBJECT': 
            bpy.ops.object.mode_set(mode='OBJECT')
            
        count = 0
        for obj in sel_objs:
            if obj.type == 'MESH' and obj.data.uv_layers.active:
                # 旋转所有 UV 坐标
                uv_layer = obj.data.uv_layers.active.data
                for loop in uv_layer:
                    loop.uv = Vector((1.0 - loop.uv.y, loop.uv.x))
                count += 1
                
        self.report({'INFO'}, f"选中: {count} 个物体UV已旋转")
        return {'FINISHED'}

# =============================================================================
# 功能 5：清理工具
# =============================================================================

class CleanupSelectedOperator(bpy.types.Operator):
    bl_idname = "spio.cleanup_selected"
    bl_label = "重置网格与材质"
    bl_description = "清理选中物体：应用变换、清除材质、重置原点、删除重叠点/松散元素等"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objs = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objs:
            self.report({'WARNING'}, "请先选择网格物体")
            return {'CANCELLED'}

        # 设置合并阈值
        MERGE_DISTANCE = 0.0001
        
        # 确保在物体模式开始
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        processed_count = 0
        
        for obj in selected_objs:
            try:
                # 设置为活动对象
                context.view_layer.objects.active = obj
                
                # 1. 应用变换 (旋转和缩放)
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

                # 2. 进入编辑模式清理网格
                bpy.ops.object.mode_set(mode='EDIT')
                
                # 有限融并 (清理平面多余线)
                bpy.ops.mesh.select_mode(type='FACE')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.dissolve_limited()

                # 合并重叠点
                bpy.ops.mesh.select_mode(type='VERT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles(threshold=MERGE_DISTANCE)

                # 删除松散元素
                bpy.ops.mesh.delete_loose()
                
                # 3. 返回物体模式清理属性
                bpy.ops.object.mode_set(mode='OBJECT')
                
                # 更新网格并清除自定义法向
                obj.data.update()
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                    
                # 设置平直着色
                bpy.ops.mesh.faces_shade_flat() # 针对面
                bpy.ops.object.shade_flat()     # 针对物体
                
                # 清除材质槽
                obj.data.materials.clear()
                
                # 重置原点到几何中心
                bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
                
                processed_count += 1
                
            except Exception as e:
                print(f"处理物体 {obj.name} 时出错: {e}")

        # 清理未使用的数据块
        bpy.ops.outliner.orphans_purge()
        
        self.report({'INFO'}, f"清理完成！已处理 {processed_count} 个物体")
        return {'FINISHED'}

class DeleteAllMaterialsOperator(bpy.types.Operator):
    bl_idname = "spio.delete_all_materials"
    bl_label = "删除所有材质"
    bl_description = "警告：此操作将删除场景中所有的材质！"
    bl_options = {'REGISTER', 'UNDO'} # 支持撤销

    def execute(self, context):
        # 创建列表副本，避免遍历时出错
        all_materials = list(bpy.data.materials)
        
        if not all_materials:
            self.report({'WARNING'}, "当前场景中没有任何材质。")
            return {'CANCELLED'}

        count = len(all_materials)
        
        # 移除材质
        for mat in all_materials:
            bpy.data.materials.remove(mat)

        self.report({'INFO'}, f"已成功删除 {count} 个材质！")
        return {'FINISHED'}

# =============================================================================
# UI 面板
# =============================================================================

class PBRToolboxPanel(bpy.types.Panel):
    bl_label = "PBR & SBSAR 工具箱"
    bl_idname = "PBR_TOOLBOX_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PBR工具"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 1. 资源导入区
        layout.label(text="1. 资源导入", icon='IMPORT')
        box1 = layout.box()
        box1.prop(scene, "toolbox_folder_path", text="")
        box1.prop(scene, "toolbox_recursion_depth", text="递归深度")
        col1 = box1.column(align=True)
        col1.operator("spio.import_pbr_textures", icon='IMAGE_DATA')
        col1.operator("spio.import_sbsar_files", icon='NODE_MATERIAL')

        # 2. 预览生成区
        layout.label(text="2. 预览生成", icon='SPHERE')
        box2 = layout.box()
        row2 = box2.row(align=True)
        op_all = row2.operator("spio.generate_previews", text="所有材质")
        op_all.target_mode = 'ALL'
        op_sel = row2.operator("spio.generate_previews", text="选中材质")
        op_sel.target_mode = 'SELECTED'

        # 3. 批量处理区
        layout.label(text="3. 批量处理", icon='MOD_BUILD')
        box3 = layout.box()
        
        # 3a. 集合操作
        box3.label(text="基于集合的操作:", icon='OUTLINER_COLLECTION')
        box3.prop(scene, "batch_target_collection", text="目标集合")
        box3.prop(scene, "batch_target_material", text="应用材质")
        box3.prop(scene, "batch_cube_size", text="UV 尺寸")
        
        col_col = box3.column(align=True)
        col_col.operator("spio.batch_apply_mat_uv", text="对集合应用材质&UV")
        col_col.operator("spio.batch_rotate_uv_90", text="旋转集合UV 90°")
        
        box3.separator()
        
        # 3b. 选中物体操作
        box3.label(text="基于选中的操作:", icon='RESTRICT_SELECT_OFF')
        col_sel = box3.column(align=True)
        col_sel.operator("spio.rotate_uv_selected_90", text="旋转UV 90°", icon='DRIVER_ROTATIONAL_DIFFERENCE')
        
        # 3c. 清理工具
        box3.separator()
        box3.label(text="清理工具:", icon='BRUSH_DATA')
        row_clean = box3.row()
        row_clean.scale_y = 1.2 
        # 原有：选中物体网格重置
        row_clean.operator("spio.cleanup_selected", text="重置网格/材质", icon='MESH_DATA')
        # 新增：删除所有材质
        row_clean.operator("spio.delete_all_materials", text="删所有材质", icon='TRASH')

# =============================================================================
# 注册
# =============================================================================

classes = (
    ImportPBRTexturesOperator,
    ImportSBSAROperator,
    GeneratePreviewsOperator,
    BatchApplyMaterialUVOperator,
    BatchRotateUVOperator,
    RotateUVSelectedOperator, 
    CleanupSelectedOperator,
    DeleteAllMaterialsOperator, # 新类注册
    PBRToolboxPanel
)

def register():
    """注册类与场景属性"""
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.toolbox_folder_path = bpy.props.StringProperty(subtype='DIR_PATH')
    bpy.types.Scene.toolbox_recursion_depth = bpy.props.IntProperty(default=0, min=0, max=10)
    bpy.types.Scene.batch_target_collection = bpy.props.PointerProperty(type=bpy.types.Collection)
    bpy.types.Scene.batch_target_material = bpy.props.PointerProperty(type=bpy.types.Material)
    bpy.types.Scene.batch_cube_size = bpy.props.FloatProperty(default=5.12, min=0.01)

def unregister():
    """注销类与清理属性"""
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.toolbox_folder_path
    del bpy.types.Scene.toolbox_recursion_depth
    del bpy.types.Scene.batch_target_collection
    del bpy.types.Scene.batch_target_material
    del bpy.types.Scene.batch_cube_size

if __name__ == "__main__":
    register()