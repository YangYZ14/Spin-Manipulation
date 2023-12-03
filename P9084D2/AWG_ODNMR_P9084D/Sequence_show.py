import matplotlib.pyplot as plt
import time
import numpy as np



class Seq_show:
        def __init__(self):
            print('用于展示目前用于操控的时序序列')

        def On_sequence_show(self, On_plot=None, Channel1_Segment = np.array([]), Marker1_Segment = np.array([]), Marker2_Segment = np.array([]), Channel2_Segment = np.array([]), Squence_time_all = [] ):
            # 创建包含3个子图的画布
            self.On_plot = On_plot
            self.Channel1_Segment = Channel1_Segment
            self.Marker1_Segment = Marker1_Segment
            self.Marker2_Segment = Marker2_Segment
            self.Channel2_Segment = Channel2_Segment
            self.Squence_time_all = Squence_time_all

            # 横向拉伸的倍数（恢复Marke对齐Channel图形）
            stretch_factor = 4
            # 横向拉伸后的数据点数量
            new_Marker1_Segment = len(Marker1_Segment) * stretch_factor
            new_Marker2_Segment = len(Marker2_Segment) * stretch_factor
            # 使用线性插值进行横向拉伸
            Marker1_Segment = np.interp(np.linspace(0, len(Marker1_Segment) - 1, new_Marker1_Segment),
                                       np.arange(len(Marker1_Segment)), Marker1_Segment)
            Marker2_Segment = np.interp(np.linspace(0, len(Marker2_Segment) - 1, new_Marker2_Segment),
                                        np.arange(len(Marker2_Segment)), Marker2_Segment)
            fig, (ax1, ax2, ax3, ax4) = self.On_plot.subplots(4, 1, sharex=True, figsize=(10, 8))
            #绘制Channel1_Segment图
            ax1.plot(self.Channel1_Segment,color='r')
            ax3.set_xlabel('WavePoints')
            ax1.set_ylabel('Amplitude')
            ax1.set_title('Channel1 Waveform')
            # # 绘制Marker1_Segment图
            ax2.plot(Marker1_Segment, color='b')
            ax3.set_xlabel('WavePoints')
            ax2.set_ylabel('Amplitude')
            ax2.set_title('Marker1 Waveform')
            # # 绘制Marker2_Segment图
            ax3.plot(Marker2_Segment, color='g')
            ax3.set_xlabel('WavePoints')
            ax3.set_ylabel('Marker2')
            ax3.set_title('Marker2 Waveform')

            ax4.plot(self.Channel2_Segment, color='m')
            ax4.set_xlabel('WavePoints')
            ax4.set_ylabel('Marker2')
            ax4.set_title('Channel2_Segment')
            # # 在不同的channel1段绘制虚线
            for x_value in self.Squence_time_all:
                ax1.axvline(x=x_value, color='gray', linestyle='--')
                ax2.axvline(x=x_value, color='gray', linestyle='--')
                ax3.axvline(x=x_value, color='gray', linestyle='--')
                ax4.axvline(x=x_value, color='gray', linestyle='--')
            self.On_plot.tight_layout()

        def Off_sequence_show(self, Off_plot=None, Channel1_Segment = np.array([]), Marker1_Segment = np.array([]), Marker2_Segment = np.array([]), Channel2_Segment = np.array([]), Squence_time_all = [] ):
            # 创建包含3个子图的画布
            self.Off_plot = Off_plot
            self.Channel1_Segment = Channel1_Segment
            self.Marker1_Segment = Marker1_Segment
            self.Marker2_Segment = Marker2_Segment
            self.Channel2_Segment = Channel2_Segment
            self.Squence_time_all = Squence_time_all

            # 横向拉伸的倍数（恢复Marke对齐Channel图形）
            stretch_factor = 4
            # 横向拉伸后的数据点数量
            new_Marker1_Segment = len(Marker1_Segment) * stretch_factor
            new_Marker2_Segment = len(Marker2_Segment) * stretch_factor
            # 使用线性插值进行横向拉伸
            Marker1_Segment = np.interp(np.linspace(0, len(Marker1_Segment) - 1, new_Marker1_Segment),
                                       np.arange(len(Marker1_Segment)), Marker1_Segment)
            Marker2_Segment = np.interp(np.linspace(0, len(Marker2_Segment) - 1, new_Marker2_Segment),
                                        np.arange(len(Marker2_Segment)), Marker2_Segment)
            fig, (ax1, ax2, ax3, ax4) = self.Off_plot.subplots(4, 1, sharex=True, figsize=(10, 8))
            #绘制Channel1_Segment图
            ax1.plot(self.Channel1_Segment,color='r')
            ax3.set_xlabel('WavePoints')
            ax1.set_ylabel('Amplitude')
            ax1.set_title('Channel1 Waveform')
            # # 绘制Marker1_Segment图
            ax2.plot(Marker1_Segment, color='b')
            ax3.set_xlabel('WavePoints')
            ax2.set_ylabel('Amplitude')
            ax2.set_title('Marker1 Waveform')
            # # 绘制Marker2_Segment图
            ax3.plot(Marker2_Segment, color='g')
            ax3.set_xlabel('WavePoints')
            ax3.set_ylabel('Marker2')
            ax3.set_title('Marker2 Waveform')

            ax4.plot(Marker2_Segment, color='m')
            ax4.set_xlabel('WavePoints')
            ax4.set_ylabel('Marker2')
            ax4.set_title('Channel2_Segment')
            # # 在不同的channel1段绘制虚线
            for x_value in self.Squence_time_all:
                ax1.axvline(x=x_value, color='gray', linestyle='--')
                ax2.axvline(x=x_value, color='gray', linestyle='--')
                ax3.axvline(x=x_value, color='gray', linestyle='--')
                ax4.axvline(x=x_value, color='gray', linestyle='--')
            self.Off_plot.tight_layout()


