#作者：曾晓东
#ODMR  对比度模式模式
#存在人为纠正On、Off数据顺序问题

import numpy as np
from PySide2 import QtCore
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QFileDialog
import pyqtgraph as pg
import threading
import time
import Ni
import AWG_Set
import pprint
from point_lock import Lock

class Interface:
    def __init__(self):
        #导入UI
        self.ui = QUiLoader().load('AWG_ODMR.ui')
        self.ui.pushButton.clicked.connect(self.start)
        self.ui.pushButton_2.clicked.connect(self.stop)
        self.ui.pushButton_3.clicked.connect(self.show)

        #设置画布的颜色标题等等，主要是两个画布，第一个是单圈，第二个是平均
        self.plotwin1 = pg.GraphicsLayoutWidget()
        self.ui.verticalLayout.addWidget(self.plotwin1)
        self.p1 = self.plotwin1.addPlot(title='single')
        self.p1.setLabel('left', text='Contrast', color='#ffffff')
        self.p1.showGrid(x=False, y=False)
        self.p1.setLogMode(x=False, y=False)
        self.p1.setLabel('bottom', text='Frequency', units='MHz')
        self.p1.addLegend()
        
        self.plotwin2 = pg.GraphicsLayoutWidget()
        self.ui.verticalLayout_6.addWidget(self.plotwin2)
        self.p2 = self.plotwin2.addPlot(title='average')
        self.p2.setLabel('left', text='Contrast', color='#ffffff')
        self.p2.showGrid(x=False, y=False)
        self.p2.setLogMode(x=False, y=False)
        self.p2.setLabel('bottom', text='Frequency', units='MHz')
        self.p2.addLegend()

        #连接AWG，并且提取仪器参数，预设一些参数
        self.AWG_TASK= AWG_Set.AWG(IP = '169.254.88.73')
        self.sample_rate = 9E9  #采样率设置
        self.power = 0.1  # 设置微波输出的幅值
        self.ptop1 = 0.5  # 设置marker1输出的幅值
        self.ptop2 = 0.5  # 设置marker2输出的幅值
        self.offs1 = 0.25 # 设置marker1的偏置
        self.offs2 = 0.25 # 设置marker2的偏置
        
        # 不同的step代表脉冲序列的不同阶段，不同序列的step数目不同，step内容不同。第二列的数字转换为
        # 二进制后第一位：微波的开关；第二位：AOM的开关；第三位：NI的开关。第三列为每个step的持续时间，单位ns
        # 对于8G/s的采样率，每1ns为16个wave-point，分配wave-point内存时为64的倍数，64个wave-point为4ns的区别
        self.On_odmr_sequence = [['step1', 0, 3000],
                             ['step2', 7,100000],
                             ['step3', 0, 3000]]

        self.Off_odmr_sequence = [['step1', 0, 3000],
                             ['step2', 6,100000],
                             ['step1', 0, 3000]]


        self.showLockPoint = Interface2()
        self.a=0
        self.b=0

        #初始化NI，预设值
        self.singlecys = 1000
        self.loop_num = 0
        self.counter = Ni.NI(Samples=self.singlecys, buff_size=4 * self.singlecys)
        self.data = np.zeros(self.singlecys)

    def start(self):
        #配置微波扫频列表
        self.MWPower = self.ui.doubleSpinBox_4.value()
        self.startFreq = self.ui.doubleSpinBox.value()
        self.startFreq = self.startFreq * 1E6
        self.stopFreq = self.ui.doubleSpinBox_2.value()
        self.stopFreq = self.stopFreq * 1E6
        self.stepFreq = self.ui.doubleSpinBox_3.value()
        self.stepFreq = self.stepFreq * 1E6
        self.N = int((self.stopFreq - self.startFreq) / self.stepFreq)   #测个ODMR需要扫频频率数
        self.MW_list = np.array(self.stepFreq * np.array(range(self.N + 1)) + self.startFreq)   #x列表中每个值为低频微波到高频微波的值
        self.cycle = 0   #圈数
        self.i = 0   #动态频率位置
        self.running = True
        self.termination = False
        self.contrast_1 = np.zeros(self.N + 1)  #存储单次循环MW_list时的数据
        self.contrast_2 = np.zeros(self.N + 1)   #存储多次循环MW_list时的平均数据
        self.lock_count = 0

        self.Lock_point = Lock(rate=0.85, step=0.02)
        
        #前面配置好参数，调用loop开始跑loop线程
        self.thd = threading.Thread(target=self.loop)
        self.thd.start()
        self.refresh = QtCore.QTimer()
        self.refresh.timeout.connect(self.update)
        self.refresh.start(1000)
        self.initial = True


    def loop(self):
    	while self.running:
            if self.i == self.N + 1:  #初始i等于1
                self.contrast_2 = (self.contrast_2*self.cycle+self.contrast_1)/(self.cycle+1)  #平均效应
                self.contrast_1 = np.zeros(self.N + 1)  #单圈
                self.i = 0
                self.cycle += 1  #改变圈数
                if self.ui.checkBox.isChecked():   #锁定总圈数
                    if self.cycle > self.ui.spinBox.value():   #当当前圈数大于设置固定圈数时就停止跑程序
                        self.termination = True
            #波形定义，输出需要导入到仪器中的channel1的长度，片段；marker1的片段；marker2的片段
            #不同的x[i]就是不同的频率设定
            # 对于每一个微波频率定义到一个segment中去
            self.task_num = 1

            self.seglen, self.Channel1_Segment, self.Marker_Segment = self.AWG_TASK.sequence_set(self.On_odmr_sequence,self.MW_list[self.i],self.sample_rate)
            # 将定义好的segment下载到相应的channel和marker段上去
            self.AWG_TASK.download_channel_segment(self.seglen, self.Channel1_Segment, self.power, self.task_num)
            self.AWG_TASK.download_marker_segment(self.Marker_Segment, self.ptop1, self.ptop2, self.offs1, self.offs2, self.task_num)
            self.AWG_TASK.sequence_task(self.loop_num, self.task_num)
            self.counter.DAQCounterTask.start()
            self.AWG_TASK.start_sequence()
            self.data = self.counter.Read()  #从NI计数卡读取数据
            self.On_data = self.data[1:]   #Ni读取的第一个数据总有问题，不采用
            self.On_counts = sum(self.On_data) 
            self.AWG_TASK.stop_sequence()
            self.counter.DAQCounterTask.stop()

            self.seglen, self.Channel1_Segment, self.Marker_Segment = self.AWG_TASK.sequence_set(self.Off_odmr_sequence,self.MW_list[self.i],self.sample_rate)
            # 将定义好的segment下载到相应的channel和marker段上去
            self.AWG_TASK.download_channel_segment(self.seglen, self.Channel1_Segment, self.power, self.task_num)
            self.AWG_TASK.download_marker_segment(self.Marker_Segment, self.ptop1, self.ptop2, self.offs1, self.offs2, self.task_num)
            self.AWG_TASK.sequence_task(self.loop_num, self.task_num)
            self.counter.DAQCounterTask.start()
            self.AWG_TASK.start_sequence()
            self.data = self.counter.Read()  #从NI计数卡读取数据
            self.Off_data = self.data[1:]   #Ni读取的第一个数据总有问题，不采用
            self.Off_counts = sum(self.Off_data) 
            self.AWG_TASK.stop_sequence()
            self.counter.DAQCounterTask.stop()

            self.contrast_1[self.i] = (self.On_counts - self.Off_counts) / self.Off_counts
            if self.contrast_1[self.i] > 0:
                self.contrast_1[self.i] = -self.contrast_1[self.i]
            print('ODMR contrast:')
            print(self.contrast_1)
            self.i += 1  #i开始迭代
            self.lock_count = self.Off_counts + 100


    def update(self):
        self.ui.lineEdit.setText(str(self.cycle))
        self.p1.plot(self.MW_list, self.contrast_1, pen='g', clear=True)
        self.p2.plot(self.MW_list, self.contrast_2,pen='r',clear=True)
        self.p1.addLine(y=0, pen='r')
        self.p2.addLine(y=0, pen='r')
        if self.termination:
            self.stop()

        self.Lock_Thread = threading.Thread(target=self.Lock_point.lockPosition_V1, args=[self.lock_count])
        self.Lock_Thread.daemon = True
        self.Lock_Thread.start()
        if self.initial and self.lock_count != 0:
            self.showLockPoint.ui.lineEdit.setText(str(self.Lock_point.getPosition()['1']))
            self.showLockPoint.ui.lineEdit_3.setText(str(self.Lock_point.getPosition()['2']))
            self.showLockPoint.ui.lineEdit_5.setText(str(self.Lock_point.getPosition()['3']))
            self.showLockPoint.ui.lineEdit_8.setText(str(self.lock_count))
            self.initial = False
        self.showLockPoint.ui.lineEdit_2.setText(str(self.Lock_point.getPosition()['1']))
        self.showLockPoint.ui.lineEdit_4.setText(str(self.Lock_point.getPosition()['2']))
        self.showLockPoint.ui.lineEdit_6.setText(str(self.Lock_point.getPosition()['3']))
        self.showLockPoint.ui.lineEdit_7.setText(str(self.lock_count))

    def stop(self):
        #停止执行
        self.running = False
        if self.thd is not None:
            self.thd.join()
        if self.Lock_Thread is not None:
            self.Lock_Thread.join()
        self.refresh.stop()
        print('stop')
        self.AWG_TASK.disconnect_awg()

    def show(self):
        self.showLockPoint.ui.show()


class Interface2:
    def __init__(self):
        self.ui = QUiLoader().load('锁点详情.ui')


if __name__ == '__main__':
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QApplication([])
    stats = Interface()
    stats.ui.show()
    app.exec_()