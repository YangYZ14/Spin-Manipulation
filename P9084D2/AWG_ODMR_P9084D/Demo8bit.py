import time
import numpy as np
import pyvisa as visa

AWGIP = '169.254.88.73'
#此处改成你仪器的IP
channel = int(1)
segment = int(1)
SampleRate = int(8e9)
WfmPoints = int(162e-6 * SampleRate)
WfmVpp = 0.55
WfmDCoff = 0
MkrVpp = 0.5
MkrDCoff = 0.25
WfmLoop = int(500)
## 特别注意*波形循环播放的次数,我们波形的长度为162us，循环500次就是81ms，所以后面触发的间隔需要大于81ms，否则会出现部分波形触发失败 

# Waveform Calculation
Waveform = np.zeros((WfmPoints,), dtype=np.uint8)
Waveform += np.uint8(128)
Waveform[24000:823999] = np.uint8(255)
Waveform[848000:1247999] = np.uint8(255)

Marker1 = np.zeros((int(WfmPoints/8),), dtype=np.uint8)
Marker1[3000:102999] = 1
Marker1[106000:155999] = 1
Marker2 = Marker1
Marker3 = Marker1
Marker4 = Marker1
## Maker 需要交织成一个序列，交织方法如下
Marker = (Marker1 + Marker2 * 2 + Marker3 * 4 + Marker4 * 8).astype(np.uint8)

# Open Connection to Proteus Instrument
try:
    resourceManager = visa.ResourceManager()
    dev = 'TCPIP0::' + AWGIP + '::5025::SOCKET'
    proteus = resourceManager.open_resource(dev)
    print('\n 仪器连接成功!')
    proteus.read_termination = '\n'
    proteus.write_termination = '\n'
    proteus.timeout = 30000
    print(' 仪器型号:' + str(proteus.query('*IDN?')))
except Exception as e:
    print('[!] Exception:' + str(e))

# Intrument Initialize
proteus.write('*CLS; *RST')
proteus.write(':FREQ:RAST ' + str(SampleRate))
proteus.write(':TRAC:FORM U8')
proteus.write(':INST:CHAN ' + str(channel))
proteus.write(':FUNC:MODE ARB')
proteus.write(':MODE DIR')
proteus.write(':OUTP OFF')
print('\n 仪器初始化完毕!')

# Waveform and Marker Download
proteus.write('TRAC:DEL:ALL')
proteus.write(':TRAC:DEF ' + str(segment) + ',' + str(WfmPoints))
proteus.write(':TRAC:SEL 1')

proteus.write_binary_values(':TRAC:DATA 0', Waveform, datatype='B')
proteus.write_binary_values(':MARK:DATA 0', Marker, datatype='B')
print(proteus.query(':SYST:ERR?'))

print('\n 波形下载完毕!')

# Output Level Setting
proteus.write(':FUNC:MODE ARB')
proteus.write(':FUNC:MODE:SEGM ' + str(segment))
proteus.write(':VOLT ' + str(WfmVpp))
proteus.write(':VOLT:OFFS '+ str(WfmDCoff))
print(proteus.query(':SYST:ERR?'))
for i in range(1, 5):
    proteus.write(':MARK:SEL' + str(i))
    proteus.write(':MARK:VOLT:PTOP ' + str(MkrVpp))
    proteus.write(':MARK:VOLT:OFFS ' + str(MkrDCoff))

# Task Edit
proteus.write(':TASK:COMP:LENG 1')
proteus.write(':TASK:COMP:SEL 1')
proteus.write(':TASK:COMP:SEGM 1;:TASK:COMP:LOOP ' + str(WfmLoop))
proteus.write(':TASK:COMP:DEF:IDLE:LEV 128')
proteus.write(':TASK:COMP:ENAB CPU')
proteus.write(':TASK:COMP:JUMP EVEN')
proteus.write(':TASK:COMP:NEXT1 1')
proteus.write(':TASK:COMP:WRITE')
proteus.write(':FUNC:MODE TASK')
print('\n 播放条件设置完毕\n 通道1、Marker1~4同时输出\n 输出任务为两个矩形脉冲，重复播放1000次\n 该任务重复十次 ')
for i in range(1, 5):
    proteus.write(':MARK:SEL ' + str(i))
    proteus.write(':MARK ON')
proteus.write(':OUTP ON')
## TASK模式下打开开关后，先暂停一段时间，待输出状况稳定后再触发；
# 根据我的验证，在此之前Channel、Marker输出不在0位；现在输出才为0V
time.sleep(10)
###到此为止，可以理解为仪器播放波形前的设置

###后面的代码用于控制输出波形
# Waveform and Marker Playing
for i in range(1, 101):
    print('\n 波形任务5秒后开始播放! 第' + str(i) + '次')
    time.sleep(0.1)
    # 单位秒，用这个语句控制每次播放的延迟时间，也就是间隔时间，注意需要大于一条task播放的时间，本例是81ms
    proteus.write('*TRG')
    # 用这个指令发起脉冲串播放的触发
print('\n 十次任务播放结束!')
