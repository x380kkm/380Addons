Fix for Adobe Substance 3D Plugin Compilation Errors (For Unity 2021/2022)
首先使用商城安装插件
U3DCN用户请使用globe hub加载c版本引擎. 以便进入插件商城

问题原因：
如果你当前使用的是 Unity 2021 或 2022，会出现 "CS0103" 错误。需要修改两个脚本文件来兼容旧版本。
修复步骤：
1.  修改 Runtime 脚本
    文件路径：Assets/Adobe/Substance3DForUnity/Runtime/Runtime/Scripts/SubstanceRuntime.cs
    位置：约第 28 行
    修改方法：
    将：\_instance = FindFirstObjectByType\<SubstanceRuntime\>();
    改为：\_instance = FindObjectOfType\<SubstanceRuntime\>();

2.  修改 Editor 脚本
    文件路径：Assets/Adobe/Substance3DForUnity/Editor/Scripts/SubstanceEditorEngine.cs
    位置：约第 268 行
    修改方法：
    将：var runtimeGraphcsBehavior = FindObjectsByType\<Substance.Runtime.SubstanceRuntimeGraph\>(FindObjectsSortMode.None);
    改为：var runtimeGraphcsBehavior = FindObjectsOfType\<Substance.Runtime.SubstanceRuntimeGraph\>();

修改完成后保存，回到 Unity 等待编译即可。

-----

Issue Cause:
The installed Substance plugin version is designed for Unity 2023+ and uses new APIs. If you are using Unity 2021 or 2022, you will encounter "CS0103" errors. You need to modify two scripts to make them compatible with older versions.

Fix Steps:

1.  Modify Runtime Script
    File Path: Assets/Adobe/Substance3DForUnity/Runtime/Runtime/Scripts/SubstanceRuntime.cs
    Location: Around line 28
    Action:
    Change: \_instance = FindFirstObjectByType\<SubstanceRuntime\>();
    To:     \_instance = FindObjectOfType\<SubstanceRuntime\>();

2.  Modify Editor Script
    File Path: Assets/Adobe/Substance3DForUnity/Editor/Scripts/SubstanceEditorEngine.cs
    Location: Around line 268
    Action:
    Change: var runtimeGraphcsBehavior = FindObjectsByType\<Substance.Runtime.SubstanceRuntimeGraph\>(FindObjectsSortMode.None);
    To:     var runtimeGraphcsBehavior = FindObjectsOfType\<Substance.Runtime.SubstanceRuntimeGraph\>();

Save the files and return to Unity to recompile.
