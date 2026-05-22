"""
Trace what PHI_InitializePSM actually writes:
- handle+0x90 = heap ptr to ctx (what PHI_LoadPSM should receive as arg3)
- handle+0x94 = inline slot where fn_C copies arg3 (PSM_ARRAY_BASE+0x98)
Shows before and after InitializePSM, with different arg3 values.
"""
import ctypes, ctypes.wintypes, struct, os, sys

DLL_PATH    = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library\tiPHIChar.dll'
SHARED_PATH = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Shared Library'
os.add_dll_directory(os.path.dirname(DLL_PATH))
os.add_dll_directory(SHARED_PATH)
dll = ctypes.WinDLL(DLL_PATH)
P = ctypes.POINTER(ctypes.c_int32)
dll.PHI_CheckforDevices.restype  = ctypes.c_int32
dll.PHI_CheckforDevices.argtypes = [P]
dll.PHI_Initialize.restype  = ctypes.c_int32
dll.PHI_Initialize.argtypes  = [ctypes.c_int32, P]
dll.PHI_InitializePSM.restype  = ctypes.c_int32
dll.PHI_InitializePSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_char_p]
dll.PHI_LoadPSM.restype  = ctypes.c_int32
dll.PHI_LoadPSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]

GetModuleHandle = ctypes.windll.kernel32.GetModuleHandleW
GetModuleHandle.restype = ctypes.wintypes.HMODULE
dll_base = GetModuleHandle('tiPHIChar.dll')

def read_dwords(addr, count):
    raw = bytes((ctypes.c_byte * (count*4)).from_address(addr))
    return struct.unpack(f'<{count}I', raw)

c = ctypes.c_int32(0); dll.PHI_CheckforDevices(ctypes.byref(c))
h = ctypes.c_int32(0); dll.PHI_Initialize(0, ctypes.byref(h))
handle = h.value
PSM_BASE = handle - 4  # PSM_ARRAY_BASE = handle - 4

print(f'handle=0x{handle:08X}  PSM_BASE=0x{PSM_BASE:08X}  dll_base=0x{dll_base:08X}', flush=True)

# Show handle area BEFORE InitializePSM
print('\n--- Before InitializePSM ---')
print('handle+0x88 to handle+0xA0:')
for off in range(0x88, 0xA4, 4):
    v = ctypes.c_uint32.from_address(handle + off).value
    print(f'  handle+0x{off:03X} = 0x{v:08X}')

# handle+0x94 = PSM_BASE + 0x98 = fn_C destination
PSM_SLOT_OFFSET_98 = PSM_BASE + 0x98  # = handle + 0x94
print(f'\nPSM_BASE+0x98 = handle+0x94 = 0x{PSM_SLOT_OFFSET_98:08X}')
print('Contents (16 dwords):')
dw = read_dwords(PSM_SLOT_OFFSET_98, 16)
print(f'  {["0x{:08X}".format(v) for v in dw]}')

# Build arg3 with vtable pointer at [0]
VTABLE_RVA = 0x772F4  # RVA of vtable candidate
vtable_addr = dll_base + VTABLE_RVA
print(f'\nUsing vtable_addr=0x{vtable_addr:08X}', flush=True)

# Construct arg3: vtable pointer at dword 0
arg3_buf = bytearray(512)
struct.pack_into('<I', arg3_buf, 0, vtable_addr)
arg3 = ctypes.create_string_buffer(bytes(arg3_buf), 512)

print('Calling PHI_InitializePSM with vtable at arg3[0]...', flush=True)
ret = dll.PHI_InitializePSM(h, ctypes.c_int32(0), arg3)
print(f'ret={ret}', flush=True)

# Read all key locations AFTER InitializePSM
print('\n--- After InitializePSM ---')
print('handle+0x88 to handle+0xA4:')
for off in range(0x88, 0xA8, 4):
    v = ctypes.c_uint32.from_address(handle + off).value
    print(f'  handle+0x{off:03X} = 0x{v:08X}')

ctx_at_90 = ctypes.c_uint32.from_address(handle + 0x90).value
print(f'\nhandle+0x90 (ctx heap ptr?) = 0x{ctx_at_90:08X}')
if ctx_at_90 > 0x1000:
    heap_dw = read_dwords(ctx_at_90, 8)
    print(f'  -> heap[0:8] = {["0x{:08X}".format(v) for v in heap_dw]}')
    print(f'  -> vtable at heap[0] = 0x{heap_dw[0]:08X}')

print(f'\nPSM_BASE+0x98 = handle+0x94 (fn_C dest) after call:')
dw_after = read_dwords(PSM_SLOT_OFFSET_98, 16)
print(f'  {["0x{:08X}".format(v) for v in dw_after]}')
print(f'  -> vtable at [0] = 0x{dw_after[0]:08X}')

# Now try PHI_LoadPSM with ctx = handle+0x90 value AND arg4=1
print(f'\n--- Trying PHI_LoadPSM with ctx=0x{ctx_at_90:08X}, arg4=1 ---', flush=True)
sys.stdout.flush()
ret2 = dll.PHI_LoadPSM(h, ctypes.c_int32(0), ctypes.c_int32(ctx_at_90), ctypes.c_int32(1))
print(f'ret={ret2}', flush=True)
