from PySide2.QtWidgets import QApplication
from PySide2 import QtCore
from PySide2.QtUiTools import QUiLoader
import pyqtgraph as pg
import numpy as np
import time
import os
import threading
import Ni
from point_lock import Lock
import AWG_Set

class Interface:
	def __init__(self):
		self.ui = QUiLoader().load('Rabi.ui')
		self.ui.pushButton.clicked.connect(self.start)
		self.ui.pushButton_2.clicked.connect(self.stop)
		self.ui.pushButton_7.clicked.connect(self.show)

		self.plotwin1 = pg.GraphicsLayoutWidget()
		self.ui.verticalLayout.addWidget(self.plotwin1)
		self.p1 = self.plotwin1.addPlot(title='single')
		self.p1.setLabel('left',text='Contrast',color='#ffffff')
		self.p1.showGrid(x=False,y=False)
		self.p1.setLogMode(x=False,y=False)
		self.p1.setLabel('bottom',text='time',units='us')
		self.p1.addLegend()

		self.plotwin2 = pg.GraphicsLayoutWidget()
		self.ui.verticalLayout_6.addWidget(self.plotwin2)
		self.p2 = self.plotwin2.addPlot(title='average')
		self.p2.setLabel('left', text='Contrast', color='#ffffff')
		self.p2.showGrid(x=False, y=False)
		self.p2.setLogMode(x=False, y=False)
		self.p2.setLabel('bottom', text='time', units='us')
		self.p2.addLegend()

		# 连接AWG，并且提取仪器参数，预设一些参数
		self.AWG_TASK = AWG_Set.AWG(IP='169.254.88.73')
		self.sample_rate = 9E9  # 采样率设置
		self.power = 0.2  # 设置微波输出的幅值
		self.ptop1 = 0.5  # 设置marker1输出的幅值
		self.ptop2 = 0.5  # 设置marker2输出的幅值
		self.offs1 = 0.25 # 设置marker1的偏置
		self.offs2 = 0.25 # 设置marker2的偏置


		# 初始化NI，预设取样值个数
		self.singlecys = 100000
		self.loop_num = 0  # AWG的Task模式循环，0就是无限循环
		self.counter = Ni.NI(Samples=self.singlecys, buff_size=4 * self.singlecys)
		self.data = np.zeros(2 * self.singlecys)

	def start(self):
		self.MWPower = self.ui.doubleSpinBox_4.value()      #暂时不用，就先用AWG的power代替
		self.MWFrequency = self.ui.doubleSpinBox_5.value()  #设置微波共振频率
		self.MWFrequency = self.MWFrequency * 1E6          #统一单位
		self.starttime = self.ui.doubleSpinBox.value() - 0.009      #最小驰豫时间
		self.stoptime = self.ui.doubleSpinBox_2.value()		#最大驰豫时间
		print(self.starttime)
		print(self.stoptime)
		self.N = self.ui.spinBox_3.value()                #测量点的个数
		self.steptime =(self.stoptime-self.starttime)/(self.N)  #根据开始结束和点个数推出的步进
		self.timelist = np.array(self.steptime * np.array(range(self.N + 1)) + self.starttime)
		self.All_sequence_on = []
		self.All_sequence_off = []
		print(self.timelist)                              #不同驰豫时间的Rabi序列列表

		self.showLockPoint = Interface2()
		self.a=0
		self.b=0

		#遍历生成不同驰豫时间长度的序列
		for t in self.timelist:
			# 不同的step代表脉冲序列的不同阶段，不同序列的step数目不同，step内容不同。第二列的数字转换为
			# 二进制后   第一位：微波的开关；第二位：AOM的开关；第三位：NI的开关。第三列为每个step的持续时间，单位ns
			# 对于8G/s的采样率，每1ns为16个wave-point，分配wave-point内存时为64的倍数，64个wave-point为4ns的区别
			self.On_sequence = [['step1', 2, 3 * 1000],  
							 ['step2', 0, 1 * 1000],
							 ['stpe3', 1, t * 1000],
							 ['step4', 0, (self.stoptime-t+0.2) * 1000],
							 ['step5', 2, 0.31 * 1000],
							 ['step6', 6, 0.55 * 1000],
							 ['stpe7', 2, 3 * 1000]]

			self.Off_sequence = [['step8', 2, 3 * 1000],
							 ['step9', 0, 1 * 1000],
							 ['step10',0, (self.stoptime+0.2) * 1000],
							 ['step10', 2, 0.31 * 1000],
							 ['step11', 6, 0.55 * 1000],
							 ['stpe12', 2, 3 * 1000]]
			
			self.All_sequence_on.append(self.On_sequence)
			self.All_sequence_off.append(self.Off_sequence)
		
		#运行循环有关
		self.cycle = 0
		self.i = 0
		self.running = True
		self.termination = False
		self.rabi_contrast1 = np.zeros(self.N + 1)
		self.rabi_contrast2 = np.zeros(self.N + 1)
		self.lock_count = 0

		self.Lock_point = Lock(rate=0.85, step=0.02)

		#线程相关
		self.thd = threading.Thread(target=self.loop)
		self.thd.start()
		self.refresh = QtCore.QTimer()
		self.refresh.timeout.connect(self.update)
		self.refresh.start(1000)
		self.initial = True


	def loop(self):
		while self.running:
			if self.i == self.N + 1:
				self.rabi_contrast2 = (self.rabi_contrast2 * (self.cycle) + self.rabi_contrast1)/(self.cycle + 1)
				self.rabi_contrast1 = np.zeros(self.N + 1)
				self.i = 0
				self.cycle += 1
				if self.ui.checkBox.isChecked():
					if self.cycle > self.ui.spinBox.value():
						self.termination = True
			# 波形定义，输出需要导入到仪器中的channel1的长度，片段；marker1的片段；marker2的片段
			# 不同的self.All_sequence[i]就是不同的弛豫时间设定
			# 对于每一个微波频率定义到一个segment中去
			# 将定义好的segment下载到相应的channel和marker段上去
			self.task_num = 1
			self.seglen, self.Channel1_Segment, self.Marker_Segment = self.AWG_TASK.sequence_set(self.All_sequence_on[self.i],self.MWFrequency,self.sample_rate)
			self.AWG_TASK.download_channel_segment(self.seglen, self.Channel1_Segment, self.power, self.task_num)
			self.AWG_TASK.download_marker_segment(self.Marker_Segment, self.ptop1, self.ptop2, self.offs1, self.offs2, self.task_num)
			self.AWG_TASK.sequence_task(self.loop_num, self.task_num)
			self.counter.DAQCounterTask.start()
			self.AWG_TASK.start_sequence()
			self.data = self.counter.Read()
			self.On_data = self.data[1:]   #Ni读取的第一个数据总有问题，不采用
			self.On_counts = sum(self.On_data)
			self.AWG_TASK.stop_sequence()
			self.counter.DAQCounterTask.stop()


			self.seglen, self.Channel1_Segment, self.Marker_Segment = self.AWG_TASK.sequence_set(self.All_sequence_off[self.i],self.MWFrequency,self.sample_rate)
			self.AWG_TASK.download_channel_segment(self.seglen, self.Channel1_Segment, self.power, self.task_num)
			self.AWG_TASK.download_marker_segment(self.Marker_Segment, self.ptop1, self.ptop2, self.offs1, self.offs2, self.task_num)
			self.AWG_TASK.sequence_task(self.loop_num, self.task_num)
			self.counter.DAQCounterTask.start()
			self.AWG_TASK.start_sequence()
			self.data = self.counter.Read()
			self.Off_data = self.data[1:]   #Ni读取的第一个数据总有问题，不采用
			self.Off_counts = sum(self.Off_data)
			self.AWG_TASK.stop_sequence()
			self.counter.DAQCounterTask.stop()


			self.rabi_contrast1[self.i] = (self.On_counts - self.Off_counts) / self.Off_counts
			self.i += 1
			self.lock_count = self.Off_counts + 100


	def update(self):
		self.ui.lineEdit.setText(str(self.cycle))
		self.p1.plot(self.timelist,self.rabi_contrast1,pen='g',clear=True)
		self.p2.plot(self.timelist,self.rabi_contrast2,pen='g',clear=True)
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