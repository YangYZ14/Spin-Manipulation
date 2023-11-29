#ODNMR  对比度模式

import numpy as np
from PySide2 import QtCore
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QFileDialog
import pyqtgraph as pg
import threading
import time
import Ni
import AWG_Set


class Interface:
    def __init__(self):
        #导入UI
        self.ui = QUiLoader().load('AWG_ODNMR.ui')
        self.ui.pushButton.clicked.connect(self.start)
        self.ui.pushButton_2.clicked.connect(self.stop)

        #设置画布的颜色标题等等，主要是两个画布，第一个是单圈，第二个是平均
        self.plotwin1 = pg.GraphicsLayoutWidget()
        self.ui.verticalLayout.addWidget(self.plotwin1)
        self.p1 = self.plotwin1.addPlot(title='single')
        self.p1.setLabel('left', text='Contrast', color='#ffffff')
        self.p1.showGrid(x=False, y=False)
        self.p1.setLogMode(x=False, y=False)
        self.p1.setLabel('bottom', text='RF Frequency', units='MHz')
        self.p1.addLegend()
        
        self.plotwin2 = pg.GraphicsLayoutWidget()
        self.ui.verticalLayout_6.addWidget(self.plotwin2)
        self.p2 = self.plotwin2.addPlot(title='average')
        self.p2.setLabel('left', text='Contrast', color='#ffffff')
        self.p2.showGrid(x=False, y=False)
        self.p2.setLogMode(x=False, y=False)
        self.p2.setLabel('bottom', text='RF Frequency', units='MHz')
        self.p2.addLegend()

        #连接AWG，并且提取仪器参数，预设一些参数
        self.AWG_TASK= AWG_Set.AWG(IP = '169.254.88.73')
        self.power1 = 0.1  # 设置微波输出的幅值
        self.power2 = 0.1  #设置射频输出的幅值
        self.ptop1 = 0.5  # 设置marker1输出的幅值
        self.ptop2 = 0.5  # 设置marker2输出的幅值
        self.offs1 = 0.25 # 设置marker1的偏置
        self.offs2 = 0.25 # 设置marker2的偏置

        # 不同的step代表脉冲序列的不同阶段，不同序列的step数目不同，step内容不同。第二列的数字转换为
        # 二进制后第一位：微波的开关；第二位：AOM的开关；第三位：NI的开关。第三列为每个step的持续时间，单位ns
        # 对于8G/s的采样率，每1ns为16个wave-point，分配wave-point内存时为64的倍数，64个wave-point为4ns的区别
        

        #初始化NI，预设值
        self.singlecys = 1000
        self.loop_num1 = 0
        self.loop_num2 = 0
        self.counter = Ni.NI(Samples=self.singlecys, buff_size=4 * self.singlecys)
        self.data = np.zeros(self.singlecys)

    def start(self):
        self.sample_rate = self.ui.doubleSpinBox_9.value()  #采样率设置
        self.sample_rate = self.sample_rate * 1E6
        self.MWPower = self.ui.doubleSpinBox_4.value()
        self.MWFreq = self.ui.doubleSpinBox.value()
        self.MWFreq = self.MWFreq * 1E6  #输入RF起始频率
        self.MW_t_pi = self.ui.doubleSpinBox_5.value()
        self.RFFreq_start = self.ui.doubleSpinBox_3.value()
        self.RFFreq_start = self.RFFreq_start * 1E6  #输入RF结束频率
        self.RFFreq_stop = self.ui.doubleSpinBox_2.value()  #设置RF变化步长
        self.RFFreq_stop = self.RFFreq_stop * 1E6
        self.RFFreq_step = self.ui.doubleSpinBox_8.value()
        self.RFFreq_step = self.RFFreq_step * 1E6
        self.RF_t = self.ui.doubleSpinBox_6.value()

        #On模式（加微波pi）通道一输出段：包含控制输出微波、AOM、NI
        self.odmr_sequence1_1 = [['step1', 2, 100000],
                             ['step2', 1, self.MW_t_pi*1000],
                             ['step3', 0, self.RF_t*1000],
                             ['step4', 1, self.MW_t_pi*1000],
                             ['step5', 6, 50000]]
        # On模式（加微波pi）通道二输出段：仅包含控制输出射频
        self.odmr_sequence1_2 = [['step1', 0, 100000],
                             ['step2', 0, self.MW_t_pi*1000],
                             ['step3', 1, self.RF_t*1000],
                             ['step4', 0, self.MW_t_pi*1000],
                             ['step5', 0, 50000]]

        # Off模式（不加微波pi）通道一输出段：包含控制输出微波、AOM、NI
        self.odmr_sequence2_1 = [['step1', 2, 100000],
                             ['step2', 0, self.MW_t_pi*1000],
                             ['step3', 0, self.RF_t*1000],
                             ['step4', 0, self.MW_t_pi*1000],
                             ['step5', 6, 50000]]
        # Off模式（不加微波pi）通道二输出段：仅包含控制输出射频
        self.odmr_sequence2_2 = [['step1', 0, 100000],
                             ['step2', 0, self.MW_t_pi*1000],
                             ['step3', 1, self.RF_t*1000],
                             ['step4', 0, self.MW_t_pi*1000],
                             ['step5', 0, 50000]]

        self.N = int((self.RFFreq_stop - self.RFFreq_start) / self.RFFreq_step)  # 测个ODMR需要扫频频率数
        self.RF_list = np.array(self.RFFreq_step * np.array(range(self.N + 1)) + self.RFFreq_start)  # x列表中每个值为低频微波到高频微波的值
        self.cycle = 0   #圈数
        self.i = 0   #动态频率位置
        self.running = True
        self.termination = False
        self.contrast_1 = np.zeros(self.N + 1)  #存储单次循环MW_list时的数据
        self.contrast_2 = np.zeros(self.N + 1)   #存储多次循环MW_list时的平均数据
        #前面配置好参数，调用loop开始跑loop线程
        self.thd = threading.Thread(target=self.loop)
        self.thd.start()
        self.refresh = QtCore.QTimer()
        self.refresh.timeout.connect(self.update)
        self.refresh.start(1000)


    def loop(self):
        while self.running:
            if self.i == self.N + 1:  #初始i等于1
                self.contrast_2 = (self.contrast_2*self.cycle+self.contrast_1)/(self.cycle+1)  #多圈平均
                self.contrast_1 = np.zeros(self.N + 1)  #单圈
                self.i = 0
                self.cycle += 1  #改变圈数
                if self.ui.checkBox.isChecked():   #锁定总圈数
                    if self.cycle > self.ui.spinBox.value():   #当当前圈数大于设置固定圈数时就停止跑程序
                        self.termination = True
            #波形定义，输出需要导入到仪器中的channel1的长度，片段；marker1的片段；marker2的片段
            #不同的x[i]就是不同的射频设定
            # 对于每一个微波频率定义到一个segment中去
            self.chann_num1 = 1
            self.chann_num2 = 2
            self.seg_num1 = 1
            self.seg_num2 = 2
            self.task_num1 = 1
            self.task_num2 = 2
            self.total_task = 2


            self.seglen1_1, self.Channel1_Segment, self.Marker_Segment1 = self.AWG_TASK.sequence_set(self.odmr_sequence1_1, self.MWFreq, self.sample_rate)
            self.seglen1_2, self.Channel2_Segment, self.Marker_Segment2 = self.AWG_TASK.sequence_set(self.odmr_sequence1_2, self.RF_list[self.i], self.sample_rate)
            print('Marker_Segment:')
            print(self.Marker_Segment1)

            # 将定义好的segment下载到相应的channel和marker段上去
            self.AWG_TASK.download_channel_segment(self.seglen1_1, self.Channel1_Segment, self.power1, self.chann_num1, self.seg_num1)
            self.AWG_TASK.download_marker_segment(self.Marker_Segment1, self.ptop1, self.ptop2, self.offs1, self.offs2, self.chann_num1, self.seg_num1)
            self.AWG_TASK.download_channel_segment(self.seglen1_2, self.Channel2_Segment, self.power2, self.chann_num2, self.seg_num2)
            #self.AWG_TASK.download_marker_segment(self.Marker_Segment2, self.ptop1, self.ptop2, self.offs1, self.offs2, self.chann_num2, self.seg_num2)
            self.AWG_TASK.sequence_task(self.loop_num1,self.chann_num1, self.total_task, self.task_num1, self.seg_num1)
            self.AWG_TASK.sequence_task(self.loop_num2,self.chann_num2, self.total_task, self.task_num2, self.seg_num2)
            self.counter.DAQCounterTask.start()
            self.AWG_TASK.start_sequence()
            self.On_data = self.counter.Read()  #从NI计数卡读取数据
            print(self.On_data)
            time.sleep(20)
            self.On_data = self.data[1:]
            self.AWG_TASK.stop_sequence()
            self.counter.DAQCounterTask.stop()

            self.seglen2_1, self.Channel1_Segment, self.Marker_Segment1 = self.AWG_TASK.sequence_set(self.odmr_sequence2_1, self.MWFreq, self.sample_rate)
            self.seglen2_2, self.Channel2_Segment, self.Marker_Segment2 = self.AWG_TASK.sequence_set(self.odmr_sequence2_2, self.RF_list[self.i], self.sample_rate)
            # 将定义好的segment下载到相应的channel和marker段上去
            self.AWG_TASK.download_channel_segment(self.seglen2_1, self.Channel1_Segment, self.power1, self.chann_num1,self.seg_num1)
            self.AWG_TASK.download_marker_segment(self.Marker_Segment1, self.ptop1, self.ptop2, self.offs1, self.offs2,self.chann_num1, self.seg_num1)
            self.AWG_TASK.download_channel_segment(self.seglen2_2, self.Channel2_Segment, self.power2, self.chann_num2,self.seg_num2)
            #self.AWG_TASK.download_marker_segment(self.Marker_Segment2, self.ptop1, self.ptop2, self.offs1, self.offs2,self.chann_num2, self.seg_num2)
            self.AWG_TASK.sequence_task(self.loop_num1, self.chann_num1, self.total_task, self.task_num1, self.seg_num1)
            self.AWG_TASK.sequence_task(self.loop_num2, self.chann_num2, self.total_task, self.task_num2, self.seg_num2)
            self.counter.DAQCounterTask.start()
            self.AWG_TASK.start_sequence()
            self.Off_data = self.counter.Read()  #从NI计数卡读取数据
            self.Off_data = self.data[1:]
            self.AWG_TASK.stop_sequence()
            self.counter.DAQCounterTask.stop()

            self.On_counts = sum(self.On_data)
            self.Off_counts = sum(self.Off_data)
            self.contrast_1[self.i] = (self.On_counts - self.Off_counts) / self.Off_counts
            self.i += 1  #i开始迭代


    def update(self):
        self.ui.lineEdit.setText(str(self.cycle))
        self.p1.plot(self.RF_list, self.contrast_1, pen='g', clear=True)
        self.p2.plot(self.RF_list, self.contrast_2,pen='r',clear=True)
        self.p1.addLine(y=0, pen='r')
        self.p2.addLine(y=0, pen='r')
        if self.termination:
            self.stop()

    def stop(self):
        #停止执行
        self.running = False
        if self.thd is not None:
            self.thd.join()
        self.refresh.stop()
        print('stop')
        self.AWG_TASK.disconnect_awg()

if __name__ == '__main__':
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QApplication([])
    stats = Interface()
    stats.ui.show()
    app.exec_()