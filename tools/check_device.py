import ctypes, os
os.add_dll_directory(r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library')
os.add_dll_directory(r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Shared Library')
dll = ctypes.WinDLL(r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library\tiPHIChar.dll')
dll.PHI_CheckforDevices.restype = ctypes.c_int32
dll.PHI_CheckforDevices.argtypes = [ctypes.POINTER(ctypes.c_int32)]
c = ctypes.c_int32(0)
ret = dll.PHI_CheckforDevices(ctypes.byref(c))
print(f'ret={ret}  devices={c.value}', flush=True)
