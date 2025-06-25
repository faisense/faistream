
import cv2

from faivision.strutures.pipelines.blocks.frame_grabber import FrameGrabber




if __name__ == '__main__':
    cam1_grabber = FrameGrabber((1080,1920),"localhost",5555,1,"tcp")
    while True:
        frame = cam1_grabber.execute()
        cv2.imshow("cam1",frame)
        cv2.waitKey(1)