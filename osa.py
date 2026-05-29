'''
光谱仪控制类
支持yokogawa AQ6370B
data: 2025-10-10
author: wuxiao
email: 2050712279@qq.com
version: 1.0
'''

import socket
import time
import numpy as np


# operation 状态寄存器 bit0 = Sweep finished（扫描完成）
SWEEP_FINISHED_BIT = 0b1


class osa:
    '''
    yokogawa AQ6370B光谱仪
    通过socket进行SCPI通信
    '''

    def __init__(self, ip, port, rst=False):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_address = (ip, port)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2**30)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2**30)
            self.sock.settimeout(30)  # 设置超时10秒
            self.sock.connect(self.server_address)
            self.query('open "anonymous"\n')  # 登录
            self.query('123456\n')  # 密码

            self.idn  # 查询设备ID
            if rst:
                '''
                复位会删除当前扫描数据和所有设置
                '''
                self.send('*RST\n')  # 复位
                self.send('*CLS\n')  # 清除状态
            self.send(':FORMAT:DATA REAL,64\n')

            # 默认参数
            # self.wl_center = 1550e-9
            # self.wl_span = 10e-9
            # self.resolution = 0.02e-9

        except socket.timeout:
            self.close()
            raise TimeoutError("Socket timed out!")

        except ConnectionResetError:
            self.close()
            raise ConnectionResetError("Connection was reset by the remote host!")

    def query(self, message, print_cmd=True):
        '''
        发送命令，并接收返回值
        类似于VISA的query
        '''
        try:
            self.sock.sendall(message.encode())
            data = self.recv_all()
            if print_cmd:
                print('Received:', data)  # 是否打印命令和返回值
            return data
        except socket.timeout:
            self.close()
            print("Socket timed out!")
            return None
        except ConnectionResetError:
            self.close()
            print("Connection was reset by the remote host!")
            return None

    def send(self, message):
        '''
        发送命令，不接收返回值
        '''
        try:
            self.sock.sendall(message.encode())
        except socket.timeout:
            self.close()
            print("Socket timed out!")
        except ConnectionResetError:
            self.close()
            print("Connection was reset by the remote host!")

    def recv_all(self, end=b'\r\n'):
        '''
        光谱仪发送的数据以\r\n结尾
        以此作为结束符，来接收全部数据
        '''
        data = b''
        while True:
            part = self.sock.recv(4096)
            if not part:
                break
            data += part
            if data.endswith(end):
                break
        return data

    @staticmethod
    def parse_scpi_binblock(data, dtype='float64'):
        '''
        解析SCPI二进制块数据
        转换为np.array
        '''
        # 找到#号和长度描述
        if data[0:1] != b'#':
            raise ValueError("Not a SCPI binblock!")
        n_len = int(data[1:2])  # 这里是字节数的位数
        n_bytes = int(data[2 : 2 + n_len])  # 数据字节数
        bin_data = data[2 + n_len : 2 + n_len + n_bytes]
        # 解析为numpy数组
        arr = np.round(np.frombuffer(bin_data, dtype=dtype), 12)  # 1pm
        return arr

    def init(self, mode=1, trace='TRA'):
        self.send(f':TRACe:ACTive {trace}\n')
        self.send(f':TRAC:ATTR:{trace} WRIT\n')  # 扫描数据存储到trace B

        self.send(
            f':init:smode {mode}\n'
        )  # 1，单次扫描模式；2，连续扫描模式；3，AUTO模式
        self.send('*CLS\n')  # 清除状态
        self.send(':init\n')
        self.send(':FORMAT:DATA REAL,64\n')

    def get_spectrum(self, display=True, trace='TRA'):
        try:
            self.query(f":TRAC:SNUM? {trace}\n")
            lambda1 = self.query(f':TRACE:X? {trace}\n', print_cmd=False)
            lambda_array = self.parse_scpi_binblock(lambda1, dtype='float64')
            power1 = self.query(f':TRACE:Y? {trace}\n', print_cmd=False)
            power_array = self.parse_scpi_binblock(power1, dtype='float64')
        except Exception as e:
            self.close()
            raise e
        return lambda_array, power_array

    def save_screenshot(self, filename="screenshot"):
        self.send(':MMEMory:CDRive INTernal\n')
        self.send(f':MMEMory:STORe:GRAPhics COLor,BMP,"{filename}",INTernal\n')
        time.sleep(5)

    def _recv_binblock(self):
        # Read until we find '#' marker (skip leading whitespace/etc)
        while True:
            byte = self.sock.recv(1)
            if not byte:
                raise ConnectionError("Connection closed while reading binblock header")
            if byte == b'#':
                break
        # Read byte count digits
        n_len = int(self.sock.recv(1))
        count_bytes = b''
        while len(count_bytes) < n_len:
            chunk = self.sock.recv(n_len - len(count_bytes))
            if not chunk:
                raise ConnectionError("Connection closed reading byte count")
            count_bytes += chunk
        n_bytes = int(count_bytes)
        # Read payload in large chunks
        payload = b''
        while len(payload) < n_bytes:
            chunk_size = min(65536, n_bytes - len(payload))
            chunk = self.sock.recv(chunk_size)
            if not chunk:
                raise ConnectionError("Connection closed during binblock payload")
            payload += chunk
        # Consume trailing \r\n
        trailer = b''
        while len(trailer) < 2:
            chunk = self.sock.recv(2 - len(trailer))
            if not chunk:
                break
            trailer += chunk
        return payload

    def read_device_file(self, filename):
        # Device auto-appends .BMP for graphics files
        if not filename.upper().endswith('.BMP'):
            filename += '.BMP'
        self.sock.sendall(f':MMEMory:DATA? "{filename}"\n'.encode())
        return self._recv_binblock()

    def display(self, trace='TRA'):
        try:
            self.send(f':TRACe:ACTive {trace}\n')
            self.send(f':TRAC:STAT:{trace} 1\n')  # 显示trace
        except Exception as e:
            self.close()
            raise e

    def hide(self, trace='TRA'):
        try:
            self.send(f':TRACe:ACTive {trace}\n')
            self.send(f':TRAC:STAT:{trace} 0\n')  # 隐藏trace
        except Exception as e:
            self.close()
            raise e

    def abort(self):
        '''立即中止扫描'''
        self.send(':ABORt\n')

    def start_sweep(self):
        '''按当前扫描模式启动/恢复扫描'''
        self.send(':init\n')

    def poll_sweep_finished(self):
        '''读取并清除"扫描完成"事件；返回自上次读取以来是否完成过一次扫描'''
        resp = self.query(':STATus:OPERation:EVENt?\n', print_cmd=False)
        return bool(self._parse_int(resp) & SWEEP_FINISHED_BIT)

    @staticmethod
    def _parse_int(resp):
        '''把 b'1\\r\\n' 这类响应安全转成 int；None / 解析失败返回 0'''
        if resp is None:
            return 0
        try:
            return int(resp.decode().strip())
        except (ValueError, AttributeError):
            return 0

    def close(self):
        self.sock.close()

    @staticmethod
    def osa_property(query_cmd, set_cmd=None, unit=''):
        def getter(self):
            return self.query(query_cmd)

        def setter(self, value):
            if set_cmd:
                self.send(set_cmd.format(value=value, unit=unit))
            else:
                raise AttributeError("This property is read-only.")

        return property(getter, setter if set_cmd else None)

    # osa的属性：
    # wl_center, wl_span, resolution, idn, pdiv, ylevel
    # 中心波长，扫描范围，分辨率，设备ID，Y轴刻度，参考电平
    wl_center = osa_property(
        ':SENSe:WAVelength:CENTer?\n', ':SENSe:WAVelength:CENTer {value}NM\n'
    )
    wl_span = osa_property(
        ':SENSe:WAVelength:SPAN?\n', ':SENSe:WAVelength:SPAN {value}NM\n'
    )
    resolution = osa_property('SENS:BWID?\n', 'SENS:BWID {value}NM\n')
    idn = osa_property('*IDN?\n')
    pdiv = osa_property('DISP:TRAC:Y1:PDIV?\n', 'DISP:TRAC:Y1:PDIV {value}DB\n')
    ylevel = osa_property('DISP:TRAC:Y1:RLEV?\n', 'DISP:TRAC:Y1:RLEV {value}DBM\n')
    sensitivity = osa_property(
        ':SENSe:SENSe?\n', ':SENSe:SENSe {value}\n'
    )
