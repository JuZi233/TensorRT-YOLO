[简体中文](README.md) | English

# Object Detection Inference Example

This example uses the yolo11n model to demonstrate how to perform Object Detection inference using the Command Line Interface (CLI), Python, and C++.

[yolo11n.pt](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt)，[【TestImages】COCO-part.zip](https://www.ilanzou.com/s/N5Oyq8hZ)

Please download the required `yolo11n.pt` model file and test images through the provided link, and save the model file to the `models` folder, and place the extracted test images into the `images` folder after unzipping.

## Model Export

> [!IMPORTANT]
>
> If you only want to export the ONNX model (with TensorRT plugins) that can be used for inference in this project through the `tensorrt_yolo` provided Command Line Interface (CLI) tool `trtyolo`, you can install it via [PyPI](https://pypi.org/project/tensorrt-yolo) by simply executing the following command:
>
> ```bash
> pip install -U tensorrt_yolo
> ```
> 
> If you want to experience the same inference speed as C++, please refer to [Install-tensorrt_yolo](../../docs/en/build_and_install.md#install-tensorrt_yolo) to build the latest version of `tensorrt_yolo` yourself.

Use the following command to export the ONNX format with the [EfficientNMS](https://github.com/NVIDIA/TensorRT/tree/main/plugin/efficientNMSPlugin) plugin. For detailed `trtyolo` CLI export methods, please read [Model Export](../../docs/en/model_export.md):

```bash
trtyolo export -w models/yolo11n.pt -v yolo11 -o models -s
```

After running the above command, a `yolo11n.onnx` file with a `batch_size` of 1 will be generated in the `models` folder. Next, use the `trtexec` tool to convert the ONNX file to a TensorRT engine (fp16):

```bash
trtexec --onnx=models/yolo11n.onnx --saveEngine=models/yolo11n.engine --fp16
```

## Model Inference

> [!IMPORTANT]
>
> The `tensorrt_yolo` installed via [PyPI](https://pypi.org/project/tensorrt-yolo) only provides the ONNX model (with TensorRT plugins) for inference in this project and does not provide inference capabilities.
> If you want to experience the same inference speed as C++, please refer to [Install-tensorrt_yolo](../../docs/en/build_and_install.md#install-tensorrt_yolo) to build the latest version of `tensorrt_yolo` yourself.

### Inference Using CLI

1. Use the `trtyolo` command-line tool from the `tensorrt_yolo` library for inference. Run the following command to view help information:

    ```bash
    trtyolo infer --help
    ```

2. Run the following command for inference:

    ```bash
    trtyolo infer -e models/yolo11n.engine -m 1 -i images -o output -l labels.txt
    ```

    The inference results will be saved in the `output` folder, and a visualization result will be generated.

### Inference Using Python

1. Use the `tensorrt_yolo` library to run the example script `detect.py` for inference.
2. Run the following command for inference:

    ```bash
    python detect.py -e models/yolo11n.engine -i images -o output -l labels.txt
    ```

### Inference Using C++

1. Ensure that the project has been compiled according to the [`TensorRT-YOLO` Compilation](../../docs/en/build_and_install.md#tensorrt-yolo-compile).
2. Compile `detect.cpp` into an executable:

    ```bash
    # Compile using xmake
    xmake f -P . --tensorrt="/path/to/your/TensorRT" --deploy="/path/to/your/TensorRT-YOLO"
    xmake -P . -r

    # Compile using cmake
    cmake -S . -B build -DTENSORRT_PATH="/path/to/your/TensorRT" -DDEPLOY_PATH="/path/to/your/TensorRT-YOLO"
    cmake --build build -j8 --config Release
    ```

    After compilation, the executable file will be generated in the `bin` folder of the project root directory.

3. Run the following command for inference:

    ```bash
    cd bin
    ./detect -e ../models/yolo11n.engine -i ../images -o ../output -l ../labels.txt
    ```

Through the above methods, you can successfully complete model inference.
