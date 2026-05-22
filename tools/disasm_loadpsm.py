"""
Disassemble PHI_LoadPSM and fn_C to understand ctx usage.
"""
import ctypes, ctypes.wintypes, struct, os

DLL_PATH    = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library\tiPHIChar.dll'
SHARED_PATH = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Shared Library'
os.add_dll_directory(os.path.dirname(DLL_PATH))
os.add_dll_directory(SHARED_PATH)
dll = ctypes.WinDLL(DLL_PATH)

GetModuleHandle = ctypes.windll.kernel32.GetModuleHandleW
GetModuleHandle.restype = ctypes.wintypes.HMODULE
dll_base = GetModuleHandle('tiPHIChar.dll')

print(f'dll_base=0x{dll_base:08X}')

def read_bytes(addr, n):
    buf = ctypes.create_string_buffer(n)
    nread = ctypes.c_size_t(0)
    ctypes.windll.kernel32.ReadProcessMemory(
        ctypes.windll.kernel32.GetCurrentProcess(),
        ctypes.c_void_p(addr), buf, n, ctypes.byref(nread))
    return buf.raw[:nread.value]

def hex_dump(addr, data, cols=16):
    for i in range(0, len(data), cols):
        chunk = data[i:i+cols]
        hex_str = ' '.join(f'{b:02X}' for b in chunk)
        print(f'  0x{addr+i:08X}: {hex_str}')

# PHI_LoadPSM is at dll_base + 0x17310
FN_LOADPSM_RVA = 0x17310
fn_loadpsm = dll_base + FN_LOADPSM_RVA
print(f'\nPHI_LoadPSM at 0x{fn_loadpsm:08X}:')
data = read_bytes(fn_loadpsm, 256)
hex_dump(fn_loadpsm, data)

# fn_C (PHI_InitializePSM offset 0x110 calls fn_C) was identified as 0x74088560
# RVA = 0x88560 - but we need to recompute relative to current dll_base
FN_C_RVA = 0x38560  # 0x74088560 - 0x74050000 = 0x38560
fn_c = dll_base + FN_C_RVA
print(f'\nfn_C at 0x{fn_c:08X}:')
data2 = read_bytes(fn_c, 128)
hex_dump(fn_c, data2)

# Also dump PHI_InitializePSM
FN_INITPSM_RVA = 0x17100  # 0x74067100 - 0x74050000
fn_init = dll_base + FN_INITPSM_RVA
print(f'\nPHI_InitializePSM at 0x{fn_init:08X} (first 256 bytes):')
data3 = read_bytes(fn_init, 256)
hex_dump(fn_init, data3)
