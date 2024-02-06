#!/usr/bin/env python
# -*-coding:utf-8 -*-
# ==============================================================================
# Copyright (c) 2024 laugh12321 Authors. All Rights Reserved.
#
# Licensed under the GNU General Public License v3.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.gnu.org/licenses/gpl-3.0.html
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
# File    :   graphsurgeon.py
# Version :   2.0
# Author  :   laugh12321
# Contact :   laugh12321@vip.qq.com
# Date    :   2024/01/28 14:37:43
# Desc    :   PP-YOLOE Graph Surgeon for TensorRT inference.
# ==============================================================================
"""
This code is based on the following repository:
    - https://github.com/zhiqwang/yolort/blob/main/yolort/relay/trt_graphsurgeon.py
"""
import logging
from pathlib import Path
from typing import Tuple
from collections import OrderedDict

import onnx_graphsurgeon as gs
import numpy as np
import onnx

logging.basicConfig(level=logging.INFO)
logging.getLogger("PPYOLOEGraphSurgeon").setLevel(logging.INFO)
logger = logging.getLogger("PPYOLOEGraphSurgeon")

__all__ = ["PPYOLOEGraphSurgeon"]


class PPYOLOEGraphSurgeon:
    """
    PP-YOLOE Graph Surgeon for TensorRT inference.

    Args:
        model_dir (str): Path of directory saved PaddleDetection PP-YOLOE model.
        onnx_path (str): The path to the ONNX graph to load.
        model_filename (str): The PP-YOLOE model file name.
        params_filename (str): The PP-YOLOE parameters file name.
        opset (int): ONNX opset version. Default: 11
        batch_size (int): Batch size for inference. Default: 1
        imgsz (Tuple[int, int]): Input image size. Default: (640, 640)
        half (bool, optional): FP16 half-precision export. Default: False
        simplify (bool, optional): Whether to simplify the exported ONNX. Default to False
    """

    def __init__(
        self,
        model_dir: str,
        onnx_path: str,
        model_filename: str,
        params_filename: str,
        *,
        opset: int = 11,
        batch_size: int = 1,
        imgsz: Tuple[int, int] = (640, 640),
        half: bool = False,
        simplify: bool = False,
    ):
        # Ensure the required modules are imported within the function scope
        from paddle2onnx.command import c_paddle_to_onnx
        import paddle2onnx.paddle2onnx_cpp2py_export as c_p2o

        model_dir = Path(model_dir)

        # Validate model directory
        assert model_dir.exists() and model_dir.is_dir(), f"Invalid model directory: {model_dir}"

        # Define input shape dictionary
        input_shape_dict = {
            'image': [batch_size, 3, *imgsz], 
            'scale_factor': [batch_size, 2]
        }

        # Export the model to ONNX
        c_paddle_to_onnx(
            model_file=str(model_dir / model_filename),
            params_file=str(model_dir / params_filename),
            save_file=onnx_path,
            opset_version=opset,
            export_fp16_model=half,
            auto_upgrade_opset=True,
            enable_onnx_checker=True
        )

        # Convert Static Shape
        c_p2o.optimize(onnx_path, onnx_path, input_shape_dict)

        # Use YOLOTRTInference to modify an existed ONNX graph.
        self.graph = gs.import_onnx(onnx.load(onnx_path))
        assert self.graph

        # Fold constants via ONNX-GS
        self.graph.fold_constants()
        self.half = half
        self.simplify = simplify
        self.batch_size = batch_size

    def infer(self):
        """
        Sanitize the graph by cleaning any unconnected nodes, do a topological resort,
        and fold constant inputs values. When possible, run shape inference on the
        ONNX graph to determine tensor shapes.
        """
        for _ in range(2):
            count_before = len(self.graph.nodes)

            self.graph.cleanup().toposort()
            try:
                for node in self.graph.nodes:
                    for o in node.outputs:
                        if o in self.graph.outputs:
                            continue
                        o.shape = None
                model = gs.export_onnx(self.graph)
                model = onnx.shape_inference.infer_shapes(model)
                self.graph = gs.import_onnx(model)
            except Exception as e:
                logger.info(f"Shape inference could not be performed at this time:\n{e}")
            try:
                self.graph.fold_constants(fold_shapes=True)
            except TypeError as e:
                logger.error(
                    "This version of ONNX GraphSurgeon does not support folding shapes, "
                    f"please upgrade your onnx_graphsurgeon module. Error:\n{e}"
                )
                raise

            count_after = len(self.graph.nodes)
            if count_before == count_after:
                # No new folding occurred in this iteration, so we can stop for now.
                break

    def _process(self, dtype):

        # Find Mul node
        mul_node = next((node.i(0) for node in self.graph.nodes if node.op == 'Div' and node.i(0).op == 'Mul'), None)

        # Find Concat node
        concat_node = next((node for node in self.graph.nodes if node.op == 'Concat' and len(node.inputs) == 3
                            and all(node.i(idx).op == 'Reshape' for idx in range(3))), None)

        # Ensure Mul and Concat nodes are found
        assert mul_node is not None, "Mul node not found."
        assert concat_node is not None, "Concat node not found."

        # Extract relevant information from nodes
        anchors = int(mul_node.inputs[1].shape[0])
        classes = int(concat_node.i(0).inputs[1].values[1])
        sum_anchors = int(concat_node.i(0).inputs[1].values[2] + concat_node.i(1).inputs[1].values[2] + concat_node.i(2).inputs[1].values[2])

        # Check equality condition
        assert anchors == sum_anchors, f"{mul_node.inputs[1].name}.shape[0] must equal the sum of values[2] from the three Concat nodes."

        # Create a new variable for 'scores' and transpose it
        scores = gs.Variable(name='scores', shape=[self.batch_size, anchors, classes], dtype=dtype)
        self.graph.layer(op='Transpose', name='last.Transpose',
                    inputs=[concat_node.outputs[0]],
                    outputs=[scores],
                    attrs=OrderedDict(perm=[0, 2, 1]))
        self.graph.inputs[0].name = 'images'
        self.graph.inputs = [self.graph.inputs[0]]
        self.graph.outputs = [mul_node.outputs[0], scores]

    def save(self, output_path):
        """
        Save the ONNX model to the given location.

        Args:
            output_path: Path pointing to the location where to write
                out the updated ONNX model.
        """
        self.graph.cleanup().toposort()
        model = gs.export_onnx(self.graph)
        if self.simplify:
            try:
                from onnxsim import simplify
                model, check = simplify(model)
                assert check, "assert check failed, save origin onnx"
            except Exception as e:
                logger.info(f"Simplifier failure: {e}")
        onnx.save(model, output_path)
        logger.info(f"Saved ONNX model to {output_path}")

    def register_nms(
        self,
        *,
        score_thresh: float = 0.25,
        nms_thresh: float = 0.45,
        detections_per_img: int = 100,
    ):
        """
        Register the ``EfficientNMS_TRT`` plugin node.

        NMS expects these shapes for its input tensors:
            - box_net: [batch_size, number_boxes, 4]
            - class_net: [batch_size, number_boxes, number_labels]

        Args:
            score_thresh (float): The scalar threshold for score (low scoring boxes are removed).
            nms_thresh (float): The scalar threshold for IOU (new boxes that have high IOU
                overlap with previously selected boxes are removed).
            detections_per_img (int): Number of best detections to keep after NMS.
        """

        self.infer()

        dtype = np.float16 if self.half else np.float32
        self._process(dtype)

        op = "EfficientNMS_TRT"
        attrs = OrderedDict(
            plugin_version="1",
            background_class=-1,  # no background class
            max_output_boxes=detections_per_img,
            score_threshold=score_thresh,
            iou_threshold=nms_thresh,
            score_activation=False,
            box_coding=0,
        )

        op_outputs = [
            gs.Variable(
                name="num_detections",
                dtype=np.int32,
                shape=[self.batch_size, 1],
            ),
            gs.Variable(
                name="detection_boxes",
                dtype=dtype,
                shape=[self.batch_size, detections_per_img, 4],
            ),
            gs.Variable(
                name="detection_scores",
                dtype=dtype,
                shape=[self.batch_size, detections_per_img],
            ),
            gs.Variable(
                name="detection_classes",
                dtype=np.int32,
                shape=[self.batch_size, detections_per_img],
            ),
        ]

        # Create the NMS Plugin node with the selected inputs. The outputs of the node will also
        # become the final outputs of the graph.
        self.graph.layer(
            op=op, name="batched_nms", inputs=self.graph.outputs, outputs=op_outputs, attrs=attrs
        )
        logger.info(f"Created NMS plugin '{op}' with attributes: {attrs}")

        self.graph.outputs = op_outputs

        self.infer()