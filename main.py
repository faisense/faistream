import time

import cv2
from faivision.camio.managers.opencv_camera_manager import OpencvCameraManager
from faivision.configs.camera_config import CamerasConfig
from faivision.command_line_observer import CLIObserver
from faivision.strutures.frame_grabber import FrameGrabber
import torch
import torch.multiprocessing as mp
import supervision as sv


from ultralytics.models.yolo import YOLO
def display_frame(frame):
    pass
def worker_inference(model:YOLO,cam_name,cam_resolution:tuple[int,int],interface,port,n_threads=1,protocol="tcp"):
    frame_grabber = FrameGrabber(cam_resolution,interface,port,n_threads,protocol)
    bounding_box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()

    while True:
        t1 = time.time()
        frame = frame_grabber.execute()

        output = model.predict(frame)[0]

        detections = sv.Detections.from_ultralytics(output)

        labels = [
            model.model.names[class_id]
            for class_id
            in detections.class_id
        ]
        annotated_image = bounding_box_annotator.annotate(
            scene=frame, detections=detections)

        annotated_image = label_annotator.annotate(
            scene=annotated_image, detections=detections, labels=labels)
        t2 = time.time()
        print(f"{cam_name}, elapsed time: {(t2 - t1)*1000} milliseconds")
        cv2.imshow(cam_name,annotated_image)
        key = cv2.waitKey(1)
        if key != -1 and chr(key) == "q":
            break



if __name__ == "__main__":
# Load cameras from YAML
    cameras_dict = CamerasConfig.from_yaml("cameras.yaml")


    camerasManager = OpencvCameraManager(cameras_dict)
    camerasManager.start_all()

    m = YOLO("yolo11n.pt")

    #
    for cam in camerasManager.cameras.values():
        interface = cam.publisher_info['interface']
        port = cam.publisher_info['port']
        n_threads = cam.publisher_info['n_threads']
        protocol = cam.publisher_info['protocol']
        for i in range(n_threads):
            p = mp.Process(target=worker_inference, args=(m, f"{cam.camera_id}_{i}", cam.resolution,interface,port,n_threads,protocol))
            p.start()





