from ultralytics import YOLO

# Build a YOLOv9c model from scratch
# model = YOLO("yolov9c.yaml")

# Build a YOLOv9c model from pretrained weight
# model = YOLO("yolov9c.pt")
model_name = "yolo11n"
model = YOLO(model_name)

# Display model information (optional)
model.info()
imgsz = 320
batch = 1
model.export(format="openvino", imgsz=imgsz, batch=batch)
ov_model = YOLO(f"{model_name}_openvino_model/")

# Train the model on the COCO8 example dataset for 100 epochs
# results = model.train(data="coco8.yaml", epochs=100, imgsz=640)

# Evaluate the model on the validation dataset to get mAP metrics
val_results = ov_model.val(data="coco.yaml", imgsz=imgsz, batch=batch)

# Extract and print mAP metrics
# mAP_50_95 = val_results.metrics['map50_95']
# mAP_50 = val_results.metrics['map50']
#
# print(f"mAP@50-95: {mAP_50_95}, mAP@50: {mAP_50}")

# Run inference with the YOLOv9c model on the 'bus.jpg' image
# results = model("path/to/bus.jpg")
