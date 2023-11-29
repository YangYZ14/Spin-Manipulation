from pipython import GCSDevice

class Lock:
    def __init__(self,rate=0.8,step=0.04,DeviceType='E-727',USBindex='0119007862'):
        self.gcs = GCSDevice(DeviceType)
        self.gcs.ConnectUSB(USBindex)
        self.lock_state = False
        self.count_init = 0
        self.start_lock_num = 0
        self.lock_num = 0
        self.rate = rate
        self.step = step
        self.PI_axis = 0
        self.count_list = []
        self.position_list = []

    def getPosition(self):
        posi = self.gcs.qPOS()
        return posi
        #1:x轴位置；2:y轴位置；3:z轴位置（字典）

    def close(self):
        self.gcs.CloseConnection()

    def __del__(self):
        self.close()

    def lockPosition_V1(self,count):
        if self.count_init == 0:
            self.count_init = count
        elif self.count_init < count and count < 1.06 * self.count_init:
            self.count_init = count

        if (self.count_init * self.rate > count) and not self.lock_state:
            self.start_lock_num += 1
        elif (self.count_init * self.rate < count) and not self.lock_state:
            self.start_lock_num = 0

        if (self.start_lock_num == 2) and not self.lock_state:
            self.start_lock_num = 0
            self.lock_state = True
            self.position_init = self.getPosition()
            self.position_list.append(self.position_init)
            self.PI_axis = 1

        if self.lock_state:
            print('start lock')
            self.count_list.append(count)
            try:
                flag = (self.count_list[-3] > self.count_list[-2]) and (self.count_list[-3] > self.count_list[-1])
            except:
                flag = False

            if flag:
                self.gcs.MOV(self.position_list[-3])
                self.PI_axis += 1
                self.PI_axis = self.PI_axis % 7

            if self.PI_axis == 0:
                if (self.count_list[-3] < 1.06 * self.count_init) and (self.count_list[-3] > 0.9 * self.count_init):
                    self.count_init = self.count_list[-3]
                    self.lock_num = 0
                else:
                    self.lock_num += 1

                if self.lock_num == 10:
                    self.count_init = self.count_list[-3]
                    self.lock_num = 0

                self.count_list = []
                self.position_list = []
                self.lock_state = False

            elif self.PI_axis == 1:
                # self.gcs.MVR(self.position_list[-1]['3'], self.step)
                self.gcs.MVR(u'3', self.step)
                pp = self.getPosition()
                self.position_list.append(pp)
            elif self.PI_axis == 2:
                # self.gcs.MVR(self.position_list[-1]['3'], -self.step)
                self.gcs.MVR(u'3', -self.step)
                pp = self.getPosition()
                self.position_list.append(pp)
            elif self.PI_axis == 3:
                # self.gcs.MVR(self.position_list[-1]['1'], self.step)
                self.gcs.MVR(u'1', self.step)
                pp = self.getPosition()
                self.position_list.append(pp)
            elif self.PI_axis == 4:
                # self.gcs.MVR(self.position_list[-1]['1'], -self.step)
                self.gcs.MVR(u'1', -self.step)
                pp = self.getPosition()
                self.position_list.append(pp)
            elif self.PI_axis == 5:
                # self.gcs.MVR(self.position_list[-1]['2'], self.step)
                self.gcs.MVR(u'2', self.step)
                pp = self.getPosition()
                self.position_list.append(pp)
            elif self.PI_axis == 6:
                # self.gcs.MVR(self.position_list[-1]['2'], -self.step)
                self.gcs.MVR(u'2', -self.step)
                pp = self.getPosition()
                self.position_list.append(pp)