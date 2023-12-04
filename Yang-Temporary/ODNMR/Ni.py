import nidaqmx
import numpy as np

class NI:
    def __init__(self,Samples,buff_size,Continue=False):
        self.DAQCounterTask = None #用于存储数据采集任务的引用
        self.Samples = Samples  #用于存储采样数
        self.buff_size=buff_size  #用于存储缓冲区大小
        self.Continue=Continue  #用于标识是否为连续模式
        self.setCounterTask(self.Samples,self.buff_size)   #调用setCounterTask方法来配置计数器任务
        self.TempData = np.zeros(Samples + 1, dtype=np.uint32) #创建一个长度为Samples + 1的零数组，用于存储临时计数数据
        self.data = np.zeros(Samples, dtype=np.uint32) #创建一个长度为Samples的零数组，用于存储实际计数差值数据

    def setCounterTask(self,Samples,buff_size,counter=b"Dev1/ctr2",TriggerGate=b"PFI9",SamplingRate=1000):
        #这个方法用于配置计数器任务的参数
        self.DAQCounterTask = nidaqmx.Task()  #创建一个新的数据采集任务。
        self.DAQCounterTask.ci_channels.add_ci_count_edges_chan(counter)  #将计数器通道添加到任务中
        #接下来，根据连续模式和其他参数，配置采样时钟、触发器等
        if self.Continue:
            if Samples > buff_size:
                raise ValueError('sample size larger than buff_size in continuous mode,increase buff_size to solve problem')
            #配置采样时钟参数
            self.DAQCounterTask.timing.cfg_samp_clk_timing(active_edge=nidaqmx.constants.Edge.FALLING,  #选择在下降沿触发采样
                                                           rate=SamplingRate,  #设置采样率
                                                           sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS,  #选择连续模式
                                                           samps_per_chan=buff_size, source=TriggerGate)#设置每个通道的采样数为缓冲区大小，设置采样触发源为指定的触发通道
        else:
            #同样地，配置采样时钟参数
            self.DAQCounterTask.timing.cfg_samp_clk_timing(active_edge=nidaqmx.constants.Edge.FALLING,#选择在下降沿触发采样
                                                           rate=SamplingRate,#设置采样率
                                                           sample_mode=nidaqmx.constants.AcquisitionType.FINITE, #选择有限模式
                                                           samps_per_chan=Samples, source=TriggerGate)#设置每个通道的采样数为指定的Samples，

        self.DAQCounterTask.triggers.pause_trigger.trig_type = nidaqmx.constants.TriggerType.DIGITAL_LEVEL #设置触发类型为数字电平触发
        self.DAQCounterTask.triggers.pause_trigger.dig_lvl_src = TriggerGate  #设置数字电平触发源为指定的触发通道
        self.DAQCounterTask.triggers.pause_trigger.dig_lvl_when = nidaqmx.constants.Level.LOW  #设置在低电平触发时暂停任务

    def Read(self, TimeOut=10.0):
        #用于读取计数值数据
        self.TempData[1:] = self.DAQCounterTask.read(self.Samples, TimeOut) #从数据采集任务中读取计数数据到临时数组，其中[1:]用于忽略临时数组的第一个元素
        self.data = np.diff(self.TempData) #计算临时数组中相邻元素的差值，得到实际计数差值数组
        if self.Continue:
            #如果是连续模式，将临时数组的最后一个元素赋值给self.TempData[0]，以保留上一次读取的计数值
            self.TempData[0] = self.TempData[-1]
        else:
            #如果不是连续模式，停止计数器任务
            self.DAQCounterTask.stop()
        return self.data