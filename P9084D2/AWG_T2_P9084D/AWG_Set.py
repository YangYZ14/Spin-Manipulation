#import pyvisa
import matplotlib.pyplot as plt
import numpy as np
import time
from teproteus import TEProteusAdmin, TEProteusInst
from tevisainst import TEVisaInst


class AWG:
    def __init__(self,IP=None):
        #初始化，连接AWG
        self.awg = TEVisaInst(IP)
        self.awg._init_vi_inst()

        #输出仪器型号
        self.sample_rate_dac = 9E9
        print(self.awg.send_scpi_query('*IDN?'))

        # 重置仪器
        print(self.awg.send_scpi_query('*CLS; *RST;*OPC?'))

        # 获取通道数
        resp = self.awg.send_scpi_query(":INST:CHAN? MAX")
        print("Number of channels: " + resp)
        num_channels = int(resp)

        # 获取允许的最大段数
        resp = self.awg.send_scpi_query(":TRAC:SEL:SEGM? MAX")
        print("Max segment number: " + resp)
        self.max_seg_number = int(resp)

        # 以字节为单位获取可用内存(每个DDR):
        resp = self.awg.send_scpi_query(":TRAC:FREE?")
        arbmem_capacity = int(resp)
        print("Available memory per DDR: {0:,} wave-bytes".format(arbmem_capacity))
        self.awg.send_scpi_cmd(':FREQ 9e9')

        # 删除所有跟踪（Trace），初始化连续模式
        self.paranoia_level = 2  #方便debug
        self.awg.send_scpi_cmd(':TRAC:DEL:ALL', self.paranoia_level)

        #self.awg.send_scpi_cmd(':INIT:CONT ON')
        # 获取用户的波形格式
        resp = self.awg.send_scpi_query(":TRAC:FORM?")
        print("User's waveform format: " + resp)

        # 推断用户波形中波点的宽度
        if resp == 'U8':
            self.wpt_width = 8
        elif resp == 'U16':
            self.wpt_width = 16
        print("User's waveform format: {0} bits-per-point".format(self.wpt_width))
        self.wpt_width = 8
        self.max_wpt = 2 ** 8 - 1
        self.mid_wpt = self.max_wpt / 2.0

        # 用于直流空闲波形的DAC电平，DAC的模式查询，M0代表16位宽度，M1代表8位宽度
        resp = self.awg.send_scpi_query(':SYST:INF:DAC?')
        self.dac_mode = resp
        print('DAC mode {0} '.format(self.dac_mode))

        # 用于直流空闲波形的DAC电平，DAC的模式查询，M0代表16位宽度，M1代表8位宽度
        if self.dac_mode == 'M0':
            self.max_dac = 65535
            self.data_type = np.uint16
        else:
            self.max_dac = 255
            self.data_type = np.uint8
        self.half_dac = self.max_dac // 2.0
        
        resp = self.awg.send_scpi_query(':FREQ?')
        print("Sample Rate: {0}".format(resp))


    def sequence_set(self,sequence, freq=3E9,sample_rate=9E9):
        self.time_scale = 10 ** (9)
        self.freq = freq
        self.sample_rate = sample_rate
        self.period = 1 / self.freq * self.time_scale
        self.ODMR_sequence = sequence
        
        # 提取每个步骤的二进制数
        self.ODMR_squence_mode = [time[1] for time in self.ODMR_sequence]
        
        # 将持续时间长度转换为wave_points长度
        self.ODMR_sequence_wavelength = [[step, param, int(duration * self.sample_rate) * 10 ** (-9)] for step, param, duration in self.ODMR_sequence]
        self.seglen = sum(duration for _, _, duration in self.ODMR_sequence_wavelength)
        self.seglen = int(self.seglen)
        print("未动态调节前的总长度:", self.seglen)
        print(self.ODMR_sequence_wavelength)
        # 动态调节长度到64的倍数
        for item in self.ODMR_sequence_wavelength:
            item[2] = (int(item[2] + 63) // 64) * 64 if (int(item[2] + 63) // 64) * 64 > 0 else 0

        self.Sequence_wavelength = np.array(self.ODMR_sequence_wavelength)[:, -1]
        self.seglen = sum(int(value) for value in self.Sequence_wavelength)
        print("动态调节后的总长度:", self.seglen)
        print(self.Sequence_wavelength)
        # 提取最后一列并计算允许到每个步骤所需的总时间
        self.ODMR_sequence_length = [sum(duration for _, _, duration in self.ODMR_sequence[:i + 1])
                                for i in range(len(self.ODMR_sequence_wavelength))]
        self.Squence_time_all = [sum(duration for _, _, duration in self.ODMR_sequence_wavelength[:i + 1])
                            for i in range(len(self.ODMR_sequence_wavelength))]

        # 对channel1、marker1和marker2建立波形
        self.number_squence = len(self.Squence_time_all)
        print('Build wave-data and markers-data for ODMR')
        self.squence_start = 0
        self.Channel1_Segment = []  # channel总脉冲序列段落
        self.Marker1_Segment = []  # marker1总脉冲序列段落
        self.Marker2_Segment = []  # marker2总脉冲序列段落
        self.Marker_Segment = [] #marker最后输入到仪器
        self.channel1 = []  # 用于存储channel1每个step的段落
        self.marker1 = []  # 用于存储marker1每个step的段落
        self.marker2 = []  # 用于存储marker2每个step的段落

        # 第一个循环是对于ODMR测量的微波频率循环
        self.num_cycles_list = []
        self.default_num_cycles = 1000

        # 计算channel段微波序列，给定微波频率（周期），给定对应段长度，在对应长度内的周期个数
        for step in self.ODMR_sequence_wavelength:
            # 这个循环是将每个段的根据波形换算出的多少个周期
            step_name, step_type, wave_point = step
            if step_type == 1 or step_type == 3 or step_type == 5 or step_type == 7:  # 正弦波形步骤
                ncycles = wave_point / (2 * (self.sample_rate / self.time_scale) * self.period)
            else:  # 非正弦波形步骤
                ncycles = self.default_num_cycles
                ncycles = np.round(ncycles)
            self.num_cycles_list.append(ncycles)
        print('num_cycles_list')
        print(self.num_cycles_list)

        self.squence_start = 0
        for squence_end, mode_value, ncycles in zip(self.Sequence_wavelength, self.ODMR_squence_mode, self.num_cycles_list):
            self.x = np.linspace(start=0, stop=2 * np.pi * ncycles *2, num=int(squence_end), endpoint=False)
            self.bit0 = mode_value & 1  # 控制channel1是否输出波形
            self.bit1 = (mode_value >> 1) & 1  # 控制marker1是否输出波形
            self.bit2 = (mode_value >> 2) & 1  # 控制marker2是否输出波形

            # 根据不同的二进制位生成波形和标记
            # 对于bit0为0则不输出波形，为1输出微波
            if self.bit0 == 0:
                self.channel1 = np.zeros(len(self.x))+128
                self.channel1 = np.round(self.channel1)
                self.channel1 = np.clip(self.channel1, 0, self.max_wpt)
                if self.wpt_width == 16:
                    self.channel1 = self.channel1.astype(np.uint16)
                    self.channel1_bytes = self.channel1 * 2
                else:
                    self.channel1 = self.channel1.astype(np.uint8)
                    self.channel1_bytes = self.channel1
            else:
                self.channel1 = (np.sin(self.x) + 1.0) * self.mid_wpt
                self.channel1 = np.round(self.channel1)
                self.channel1 = np.clip(self.channel1, 0, self.max_wpt)
                if self.wpt_width == 16:
                    self.channel1 = self.channel1.astype(np.uint16)
                    self.channel1_bytes = self.channel1 * 2
                else:
                    self.channel1 = self.channel1.astype(np.uint8)
                    self.channel1_bytes = self.channel1 * 2

            if self.bit1 == 0:
                self.marker1 = np.zeros(len(self.x))
                self.marker1 = np.round(self.marker1)
                self.marker1 = np.clip(self.marker1, 0, self.max_wpt)
                if self.wpt_width == 16:
                    self.marker1 = self.marker1.astype(np.uint16)
                    self.marker1_bytes = len(self.x) // 4
                else:
                    self.marker1 = self.marker1.astype(np.uint8)
                    self.marker1_bytes = len(self.x) // 8
                self.marker1 = np.zeros(self.marker1_bytes, np.uint8)
            else:
                self.marker1 = np.ones(len(self.x)) * self.max_wpt
                self.marker1 = np.round(self.marker1)
                self.marker1 = np.clip(self.marker1, 0, self.max_wpt)
                if self.wpt_width == 16:
                    self.marker1 = self.marker1.astype(np.uint16)
                    self.marker1_bytes = len(self.x) // 4
                else:
                    self.marker1 = self.marker1.astype(np.uint8)
                    self.marker1_bytes = len(self.x) // 8
                self.marker1 = np.ones(self.marker1_bytes, np.uint8)

            if self.bit2 == 0:
                self.marker2 = np.zeros(len(self.x))
                self.marker2 = np.round(self.marker2)
                self.marker2 = np.clip(self.marker2, 0, self.max_wpt)
                if self.wpt_width == 16:
                    self.marker2 = self.marker2.astype(np.uint16)
                    self.marker2_bytes = len(self.x) // 4
                else:
                    self.marker2 = self.marker2.astype(np.uint8)
                    self.marker2_bytes = len(self.x) // 8
                self.marker2 = np.zeros(self.marker2_bytes, np.uint8)
            else:
                self.marker2 = np.ones(len(self.x)) * self.max_wpt
                self.marker2 = np.round(self.marker2)
                self.marker2 = np.clip(self.marker2, 0, self.max_wpt)
                if self.wpt_width == 16:
                    self.marker2 = self.marker2.astype(np.uint16)
                    self.marker2_bytes = len(self.x) // 4
                else:
                    self.marker2 = self.marker2.astype(np.uint8)
                    self.marker2_bytes = len(self.x) // 8
                self.marker2 = np.ones(self.marker2_bytes, np.uint8)

            self.Channel1_Segment.extend(self.channel1)
            self.Marker1_Segment.extend(self.marker1)
            self.Marker2_Segment.extend(self.marker2)
            self.squence_start = squence_end

        print('Channel1_Segment Len:')
        print(len(self.Channel1_Segment))
        print('Marker1_Segment Len:')
        print(len(self.Marker1_Segment))
        print('Marker2_Segment Len:')
        print(len(self.Marker2_Segment))

        self.Channel1_Segment = np.array(self.Channel1_Segment)
        self.Channel1_Segment = self.Channel1_Segment.astype(np.uint8)
        self.Channel1_Segment.reshape(-1)
        self.seglen = len(self.Channel1_Segment)
        self.Marker1_Segment = np.array(self.Marker1_Segment)
        self.Marker1_Segment = self.Marker1_Segment.astype(np.uint8)
        self.Marker1_Segment.reshape(-1)
        self.Marker2_Segment = np.array(self.Marker2_Segment)
        self.Marker2_Segment = self.Marker2_Segment.astype(np.uint8)
        self.Marker2_Segment.reshape(-1)
        self.Marker_Segment = [self.Marker1_Segment[i] | (self.Marker2_Segment[i] << 1) for i in range(len(self.Marker1_Segment))]
        self.Marker_Segment = np.array(self.Marker_Segment)
        self.Marker_Segment = self.Marker_Segment.astype(np.uint8)

        return self.seglen, self.Channel1_Segment, self.Marker_Segment


    def download_channel_segment(self,seglen = 640000, Channel1_Segment = np.array([]).astype(np.uint8), power = 1.3,segnum = 1):
        self.seglen = seglen
        self.Channel1_Segment = Channel1_Segment
        self.power = power
        self.segnum = segnum
        print('Download sequence wave segment 1 to channel 1')
        # 选择通道
        self.awg.send_scpi_cmd(':INST:CHAN 1')
        #self.awg.send_scpi_cmd('INST:CONT ON')
        #定义第几段和这个段对长度
        self.awg.send_scpi_cmd(':TRAC:DEF {0},{1}'.format(self.segnum, self.seglen))
        # 选择定义的segment
        self.awg.send_scpi_cmd(':TRAC:SEL {0}'.format(self.segnum))
        # 在写入二进制数据之前增加超时时间
        self.awg.timeout = 30000
        resp = self.awg.send_scpi_query(':SYST:ERR?')
        resp = resp.rstrip()
        if not resp.startswith('0'):
            print('ERROR: "{0}" after writing binary values'.format(resp))
        # 发送二进制数据给AWG，*OPC?加到前缀的开头以询问前一个语句是否执行完毕
        self.awg.write_binary_data(':TRAC:DATA', self.Channel1_Segment)
        self.awg.timeout = 10000
        #设置channel1输出的幅值
        self.awg.send_scpi_cmd(':SOUR:VOLT {0}'.format(self.power))
        resp = self.awg.send_scpi_query(':VOLT?')
        print('VOLT: ' + resp)
        

    def download_marker_segment(self, Marker_Segment = np.array([]).astype(np.uint8), marker1_ptop = 0, marker2_ptop = 0, marker1_offs = 0, marker2_offs = 0, segnum = 1):
        print('Download marker segment')
        # 在写入二进制数据之前增加超时时间
        self.awg.timeout = 300000
        self.segnum = segnum
        self.marker1_ptop = marker1_ptop
        self.marker2_ptop = marker2_ptop
        self.marker1_offs = marker1_offs
        self.marker2_offs = marker2_offs

        # 将Marker的波形用二进制数据写入仪器
        self.awg.send_scpi_cmd(":INST:CHAN 1")
        self.awg.send_scpi_cmd(':TRAC:SEL {0}'.format(self.segnum))
        self.awg.write_binary_data('*OPC?; :MARK:DATA', self.Marker_Segment)
        # 设置超时时间
        self.awg.timeout = 10000
        self.awg.send_scpi_cmd('*OPC?; :MARK:SEL 1')
        self.awg.send_scpi_cmd(':MARK:VOLT:PTOP {0}'.format(self.marker1_ptop))
        self.awg.send_scpi_cmd(':MARK:VOLT:OFFS {0}'.format(self.marker1_offs))
        self.awg.send_scpi_cmd('*OPC?; :MARK:SEL 2')
        self.awg.send_scpi_cmd(':MARK:VOLT:PTOP {0}'.format(self.marker2_ptop))
        self.awg.send_scpi_cmd(':MARK:VOLT:OFFS {0}'.format(self.marker2_offs))
        
        #设置偏置，默认值为0
        resp = self.awg.send_scpi_query(':SYST:ERR?')
        resp = resp.rstrip()
        if not resp.startswith('0'):
            print('ERROR: "{0}" after2 writing binary values'.format(resp))
        else:
            print('没有报错')

    def sequence_task(self, loop_num = 100, segnb = 1):
        print('Setting to Task mode')
        self.loop_num = loop_num
        self.segnb = segnb
        self.curr_segnb = segnb
        self.awg.send_scpi_cmd('INST:CHAN 1')
        resp = self.awg.send_scpi_query(':SYST:ERR?')
        resp = resp.rstrip()
        if not resp.startswith('0'):
            print('ERROR: "{0}" before set task loop'.format(resp))
        # self.awg.send_scpi_cmd(':TRAC:SEL:TIM IMM')
        # self.awg.send_scpi_cmd(':TRIG:MODE IMM')
        # self.awg.send_scpi_cmd(':TASK:COMP:DTR ON')
        # self.awg.send_scpi_cmd(':DIG:TRIG:SOUR TASK1')
        # self.awg.send_scpi_cmd(':TASK:SYNC')
        self.awg.send_scpi_cmd(':TASK:COMP:LENG 1')
        self.awg.send_scpi_cmd('TASK:COMP:SEL 1')
        self.awg.send_scpi_cmd(':TASK:COMP:TYPE SING')
        self.awg.send_scpi_cmd(':TASK:COMP:LOOP 0')
        #self.awg.send_scpi_cmd(':TASK:COMP:SEQ 1000000')
        self.awg.timeout = 300000
        
        resp = self.awg.send_scpi_query(':SYST:ERR?')
        resp = resp.rstrip()
        if not resp.startswith('0'):
            print('ERROR: "{0}" after set task loop'.format(resp))
        #self.awg.send_scpi_cmd((':TASK:COMP:SEGM {0}'.format(self.curr_segnb+1)))
        
        self.awg.send_scpi_cmd(':TASK:COMP:WRIT')
        print('Downloading Task table of channel1')
        print(resp)


    def start_sequence(self):
        self.awg.send_scpi_cmd(':INST:CHAN 1')
        self.awg.send_scpi_cmd('FUNC:MODE ARB')

        #time.sleep(10)
        #self.awg.send_scpi_cmd('FUNC:MODE TASK')
        #self.awg.send_scpi_cmd(':FUNC:MODE:TASK 1')
        self.awg.send_scpi_cmd('OUTP ON')
        resp = self.awg.send_scpi_query(':SYST:ERR?')
        resp = resp.rstrip()
        if not resp.startswith('0'):
            print('ERROR: "{0}" after start task loop'.format(resp))
        resp = self.awg.send_scpi_query('OUTP?')
        self.awg.send_scpi_cmd('FUNC:MODE TASK')
        self.awg.send_scpi_cmd(':MARK:SEL 1')
        self.awg.send_scpi_cmd(':MARK:STAT ON')
        self.awg.send_scpi_cmd(':MARK:SEL 2')
        self.awg.send_scpi_cmd(':MARK:STAT ON')
        resp = self.awg.send_scpi_query(':SYST:ERR?')
        resp = resp.rstrip()
        if not resp.startswith('0'):
            print('ERROR: "{0}" after marker task loop'.format(resp))
        print(resp)
        print('运行到这了')


    def stop_sequence(self):
        self.awg.send_scpi_cmd(':INST:CHAN 1')
        self.awg.send_scpi_cmd('OUTP OFF')
        #self.awg.send_scpi_cmd('FUNC:MODE TASK')

        self.awg.send_scpi_cmd(':MARK:SEL 1')
        self.awg.send_scpi_cmd(':MARK:STAT OFF')
        self.awg.send_scpi_cmd(':MARK:SEL 2')
        self.awg.send_scpi_cmd(':MARK:STAT OFF')
        #self.awg.send_scpi_cmd(':TRACe:DELete:ALL', 2)


    def disconnect_awg(self,CLEAR_TEST = True, num_channels = 2):
        if CLEAR_TEST:
            cmd = ':INST:CHAN 1'
            self.awg.send_scpi_cmd(cmd, self.paranoia_level)
            cmd = ':TRAC:ZERO:ALL'
            self.awg.send_scpi_cmd(cmd, self.paranoia_level)
        chanlist = [1]
        imarker = 2
        for channb in chanlist:
            if channb <= num_channels:
                cmd = ':INST:CHAN {0}'.format(channb)
                self.awg.send_scpi_cmd(cmd, self.paranoia_level)
                cmd = ':MARK:SEL {0}; :MARK:STAT OFF'.format(imarker)
                self.awg.send_scpi_cmd(cmd, self.paranoia_level)
        self.awg.close_instrument()



