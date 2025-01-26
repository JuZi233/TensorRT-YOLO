-- 设置项目信息
set_project("TensorRT-YOLO")
set_version("6.0.0")
set_languages("cxx17")
set_allowedplats("windows", "linux")

-- 添加编译规则
add_rules("plugin.compile_commands.autoupdate", {outputdir = "build"})
add_rules("mode.release")

-- 全局添加 Python 和 pybind11 依赖
add_requires("python", {system = true, optional = true})  -- 设置为可选依赖
add_requires("pybind11", {optional = true})              -- 设置为可选依赖

-- 定义选项
option("build_python")
    set_showmenu(true)
    set_description("Build Python bindings")
    set_default(false)
    on_check(function (option)
        if option:enabled() then
            -- 启用 Python 和 pybind11 依赖
            add_requires("python", {system = true})
            add_requires("pybind11")
        end
    end)

-- 定义选项
option("tensorrt")
    set_showmenu(true)
    set_description("TensorRT Path. Example: /usr/local/tensorrt")
    on_check(function (option)
        if not option:enabled() then 
            raise("TensorRT path is not set. Please specify the TensorRT path.")
        end 
    end)

-- 定义一个函数来处理 TensorRT 和 CUDA 的配置
function configure_tensorrt(target)
    if has_config("tensorrt") then
        local tensorrt_path = get_config("tensorrt")
        add_includedirs(path.join(tensorrt_path, "include"))
        add_linkdirs(path.join(tensorrt_path, "lib"))
        local libs = is_plat("windows") and os.exists(path.join(get_config("tensorrt"), "lib", "nvinfer_10.dll")) and "nvinfer_10 nvinfer_plugin_10 nvonnxparser_10" or "nvinfer nvinfer_plugin nvonnxparser"
        add_links(libs:split("%s+"))
    end
end

-- 定义一个函数来添加 CUDA 支持
function configure_cuda(target)
    add_rules("cuda")
    add_cugencodes("sm_89", "sm_86", "sm_75", "sm_70", "sm_61")
    add_cuflags("-allow-unsupported-compiler")
end

-- 定义一个函数来添加公共配置
function common_config(target)
    -- 添加库目录
    add_includedirs("$(projectdir)")

    -- 添加文件
    add_files(
        "$(projectdir)/deploy/core/*.cpp",
        "$(projectdir)/deploy/utils/*.cpp",
        "$(projectdir)/deploy/infer/*.cpp",
        "$(projectdir)/deploy/infer/*.cu",
        "$(projectdir)/deploy/model.cpp"
    )

    -- 添加 cuda
    configure_cuda(target)

    -- 添加TensorRT链接目录和链接库
    configure_tensorrt(target)
end

-- 包含插件
includes("plugin/xmake.lua")

-- 定义目标
target("deploy")
    -- 设置目标类型
    set_kind("shared")

    -- 设置编译路径
    set_targetdir("$(projectdir)/lib")

    -- 公共配置
    common_config("deploy")

-- 定义目标（仅在 build_python 为 true 时编译）
if has_config("build_python") then
    target("pydeploy")
        -- 定义规则
        add_rules("python.library")

        -- 添加依赖
        add_packages("pybind11")

        -- 设置编译路径
        set_targetdir("$(projectdir)/python/tensorrt_yolo/libs")

        -- 公共配置
        common_config("pydeploy")

        -- 添加文件
        add_files("$(projectdir)/deploy/pybind.cpp")

        -- 在配置阶段查找 CUDA SDK
        local cuda
        on_load(function (target)
            import("detect.sdks.find_cuda")
            cuda = assert(find_cuda(nil, {verbose = true}), "Cuda SDK not found!")

            -- 设置配置变量
            target:set("configvar", "CUDA_PATH", cuda.bindir)
            target:set("configvar", "TENSORRT_PATH", "$(tensorrt)")

            -- 设置配置目录和配置文件
            target:set("configdir", "$(projectdir)/python/tensorrt_yolo")
            target:add("configfiles", "$(projectdir)/python/tensorrt_yolo/c_lib_wrap.py.in")
        end)
end