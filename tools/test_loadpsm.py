import ctypes, os, sys
print('start', flush=True)

DLL_PATH    = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library\tiPHIChar.dll'
SHARED_PATH = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Shared Library'
os.add_dll_directory(os.path.dirname(DLL_PATH))
os.add_dll_directory(SHARED_PATH)
dll = ctypes.WinDLL(DLL_PATH)
print('dll loaded', flush=True)

P = ctypes.POINTER(ctypes.c_int32)
dll.PHI_CheckforDevices.restype = ctypes.c_int32
dll.PHI_CheckforDevices.argtypes = [P]
dll.PHI_Initialize.restype = ctypes.c_int32
dll.PHI_Initialize.argtypes = [ctypes.c_int32, P]
dll.PHI_InitializePSM.restype = ctypes.c_int32
dll.PHI_InitializePSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_char_p]
dll.PHI_LoadPSM.restype = ctypes.c_int32
dll.PHI_LoadPSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
dll.PHI_ClosePSM.restype = ctypes.c_int32
dll.PHI_ClosePSM.argtypes = [ctypes.c_int32, ctypes.c_int32]

c = ctypes.c_int32(0)
dll.PHI_CheckforDevices(ctypes.byref(c))
print(f'devices={c.value}', flush=True)

h = ctypes.c_int32(0)
r = dll.PHI_Initialize(0, ctypes.byref(h))
print(f'handle=0x{h.value:08X}  ret={r}', flush=True)

buf = ctypes.create_string_buffer(512)
r2 = dll.PHI_InitializePSM(h, ctypes.c_int32(0), buf)
print(f'PHI_InitializePSM -> {r2}', flush=True)

ctx = ctypes.c_int32.from_address(h.value + 0x90).value
print(f'ctx = 0x{ctx:08X}', flush=True)

r3 = dll.PHI_LoadPSM(h, ctypes.c_int32(0), ctypes.c_int32(ctx))
print(f'PHI_LoadPSM -> {r3}', flush=True)

r4 = dll.PHI_ClosePSM(h, ctypes.c_int32(0))
print(f'PHI_ClosePSM -> {r4}', flush=True)
print('SUCCESS', flush=True)
