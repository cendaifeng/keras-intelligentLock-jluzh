import cv2
import os
import time
import numpy as np
from net.mtcnn import mtcnn
import utils.utils as utils
from net.inception import InceptionResNetV1
import RPi.GPIO as GPIO
import signal
import atexit


# 初始化舵机
atexit.register(GPIO.cleanup)
servopin = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(servopin, GPIO.OUT, initial=False)
pwm = GPIO.PWM(servopin, 50)  # 50HZ
pwm.start(0)


def ControlMotor(angle):
    # 舵机的频率为50HZ，占空比为2.5%-12.5%，线性对应舵机转动角度的0-180度
    pwm.ChangeDutyCycle(2.5 + angle / 360 * 20)


class face_rec:

    def __init__(self):

        # 创建 mtcnn 对象
        # 检测图片中的人脸
        self.mtcnn_model = mtcnn()
        # 门限函数
        self.threshold = [0.5, 0.8, 0.9]

        # 载入 facenet
        # 将检测到的人脸转化为128维的向量
        self.facenet_model = InceptionResNetV1()
        # model.summary()
        # 加载模型权重只需要15s 而加载图像文件夹则需30s以上
        model_path = './model_data/facenet_keras.h5'
        self.facenet_model.load_weights(model_path)

        time2 = time.time()
        # ----------------------------------------------- #
        #   对数据库中的人脸进行编码
        #   known_face_encodings中存储的是编码后的人脸
        #   known_face_names为人脸的名字
        # ----------------------------------------------- #
        face_list = os.listdir("face_dataset")

        self.known_face_encodings = []

        self.known_face_names = []

        for face in face_list:
            name = face.split(".")[0]

            img = cv2.imread("./face_dataset/"+face)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # 检测人脸
            rectangles = self.mtcnn_model.detectFace(img, self.threshold)

            # 转化成正方形
            rectangles = utils.rect2square(np.array(rectangles))
            # facenet要传入一个160x160的图片
            rectangle = rectangles[0]
            # 记下他们的landmark
            landmark = (np.reshape(rectangle[5:15],(5,2)) - np.array([int(rectangle[0]),int(rectangle[1])]))/(rectangle[3]-rectangle[1])*160

            crop_img = img[int(rectangle[1]):int(rectangle[3]), int(rectangle[0]):int(rectangle[2])]
            crop_img = cv2.resize(crop_img,(160,160))

            new_img,_ = utils.Alignment_1(crop_img,landmark)

            new_img = np.expand_dims(new_img,0)
            # 将检测到的人脸传入到facenet的模型中，实现128维特征向量的提取
            face_encoding = utils.calc_128_vec(self.facenet_model,new_img)

            self.known_face_encodings.append(face_encoding)
            self.known_face_names.append(name)

        time3 = time.time()
        print(time3-time2)



    def recognize(self, draw):
        # -----------------------------------------------#
        #   人脸识别
        #   先定位，再进行数据库匹配
        # -----------------------------------------------#
        height, width, _ = np.shape(draw)
        draw_rgb = cv2.cvtColor(draw, cv2.COLOR_BGR2RGB)

        # 检测人脸
        rectangles = self.mtcnn_model.detectFace(draw_rgb, self.threshold)

        if len(rectangles) == 0:
            return

        # 转化成正方形
        rectangles = utils.rect2square(np.array(rectangles, dtype=np.int32))
        rectangles[:, 0] = np.clip(rectangles[:, 0], 0, width)
        rectangles[:, 1] = np.clip(rectangles[:, 1], 0, height)
        rectangles[:, 2] = np.clip(rectangles[:, 2], 0, width)
        rectangles[:, 3] = np.clip(rectangles[:, 3], 0, height)
        # -----------------------------------------------#
        #   对检测到的人脸进行编码
        # -----------------------------------------------#
        face_encodings = []
        for rectangle in rectangles:
            landmark = (np.reshape(rectangle[5:15], (5, 2)) - np.array([int(rectangle[0]), int(rectangle[1])])) / (
                        rectangle[3] - rectangle[1]) * 160

            crop_img = draw_rgb[int(rectangle[1]):int(rectangle[3]), int(rectangle[0]):int(rectangle[2])]
            crop_img = cv2.resize(crop_img, (160, 160))

            new_img, _ = utils.Alignment_1(crop_img, landmark)
            new_img = np.expand_dims(new_img, 0)

            face_encoding = utils.calc_128_vec(self.facenet_model, new_img)
            face_encodings.append(face_encoding)

        face_names = []
        distances = []
        for face_encoding in face_encodings:
            # 取出一张脸并与数据库中所有的人脸进行对比，计算得分
            matches = utils.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.7)
            name = "Unknown"
            # 找出距离最近的人脸
            face_distances = utils.face_distance(self.known_face_encodings, face_encoding)
            # 取出这个最近人脸的评分
            best_match_index = np.argmin(face_distances)
            dis = face_distances[best_match_index]
            if matches[best_match_index]:
                name = self.known_face_names[best_match_index]
                print(name+" ---> "+str(dis))

                ControlMotor(180)
                time.sleep(4)
                ControlMotor(0)
                time.sleep(1)


            face_names.append(name)
            distances.append(dis)

        rectangles = rectangles[:, 0:4]
        # -----------------------------------------------#
        #   画框~!~
        # -----------------------------------------------#
        for (left, top, right, bottom), name, dis in zip(rectangles, face_names, distances):
            cv2.rectangle(draw, (left, top), (right, bottom), (0, 0, 255), 2)

            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(draw, name, (left, bottom - 15), font, 0.75, (255, 255, 255), 2)
            cv2.putText(draw, str(dis), (right, bottom - 15), font, 0.75, (0, 0, 255), 2)
        return draw


if __name__ == "__main__":

    diudiudiu = face_rec()
    video_capture = cv2.VideoCapture(0)

    num_frames = 0
    since = time.time()
    while True:
        time.sleep(1)
        ret, draw = video_capture.read()
        diudiudiu.recognize(draw)
        # put the text into video
        num_frames += 1
        cv2.putText(draw, f'FPS{num_frames / (time.time() - since):.2f}', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                    (0, 0, 255), 2)
        cv2.imshow('Video', draw)
        if cv2.waitKey(20) & 0xFF == ord('q'):
            break


    video_capture.release()
    cv2.destroyAllWindows()
