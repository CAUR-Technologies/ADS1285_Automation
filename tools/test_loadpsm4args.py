"""
Test PHI_LoadPSM with 4 args (arg4=1 as seen in call_log.json).
Also check string constants used in PHI_LoadPSM and surrounding data.
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
# PHI_LoadPSM has 4 args: (handle, psm_id, ctx, arg4)
dll.PHI_LoadPSM.restype  = ctypes.c_int32
dll.PHI_LoadPSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]

GetModuleHandle = ctypes.windll.kernel32.GetModuleHandleW
GetModuleHandle.restype = ctypes.wintypes.HMODULE
dll_base = GetModuleHandle('tiPHIChar.dll')

def read_bytes(addr, n):
    buf = ctypes.create_string_buffer(n)
    nread = ctypes.c_size_t(0)
    ctypes.windll.kernel32.ReadProcessMemory(
        ctypes.windll.kernel32.GetCurrentProcess(),
        ctypes.c_void_p(addr), buf, n, ctypes.byref(nread))
    return buf.raw[:nread.value]

def read_string(addr, maxlen=256):
    try:
        raw = read_bytes(addr, maxlen)
        end = raw.find(b'\x00')
        return raw[:end].decode('latin1', errors='replace') if end >= 0 else '?'
    except:
        return '?'

print(f'dll_base=0x{dll_base:08X}', flush=True)

# Check all string constants used in PHI_LoadPSM
STR1_RVA = 0x740BA77C - 0x74050000  # "DataMem.bin"
STR2_RVA = 0x740BA7C8 - 0x74050000  # "CMdMem.bin"
STR3_RVA = 0x740B87AC - 0x74050000  # seen in fn at 0x740629D0
STR4_RVA = 0x740BA744 - 0x74050000  # seen in PHI_LoadPSM prologue
STR5_RVA = 0x740BA788 - 0x74050000  # guess another string
for rva, name in [(STR1_RVA,'str1'), (STR2_RVA,'str2'), (STR3_RVA,'str3'), (STR4_RVA,'str4')]:
    addr = dll_base + rva
    s = read_string(addr)
    print(f'  RVA 0x{rva:05X} = "{s}"', flush=True)

# More InitializePSM bytes (past offset 0x100)
FN_INITPSM = dll_base + 0x17100
extra_bytes = read_bytes(FN_INITPSM + 0x100, 192)
print(f'\nPHI_InitializePSM from +0x100:')
for i in range(0, len(extra_bytes), 16):
    chunk = extra_bytes[i:i+16]
    print(f'  0x{FN_INITPSM+0x100+i:08X}: {" ".join(f"{b:02X}" for b in chunk)}')

# Init
c = ctypes.c_int32(0); dll.PHI_CheckforDevices(ctypes.byref(c))
h = ctypes.c_int32(0); dll.PHI_Initialize(0, ctypes.byref(h))
handle = h.value
print(f'\nhandle=0x{handle:08X}', flush=True)

# Call InitializePSM with zero arg3
dummy = ctypes.create_string_buffer(512)
ret = dll.PHI_InitializePSM(h, ctypes.c_int32(0), dummy)
ctx_ptr = ctypes.c_int32.from_address(handle + 0x90).value
print(f'PHI_InitializePSM(zero) -> ret={ret}  ctx=0x{ctx_ptr:08X}', flush=True)

# Patch vtable
VTABLE_RVA = 0x772F4
vtable_addr = dll_base + VTABLE_RVA
ctypes.c_uint32.from_address(ctx_ptr).value = vtable_addr
print(f'Patched ctx[0] = 0x{vtable_addr:08X}', flush=True)

# Call PHI_LoadPSM with 4 args (arg4=1 per call_log)
print(f'Calling PHI_LoadPSM(handle, 0, ctx=0x{ctx_ptr:08X}, 1)...', flush=True)
sys.stdout.flush()
ret2 = dll.PHI_LoadPSM(h, ctypes.c_int32(0), ctypes.c_int32(ctx_ptr), ctypes.c_int32(1))
print(f'PHI_LoadPSM -> ret={ret2}', flush=True)

# Also check files in TI installation dir
TI_DIR = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM'
print(f'\nFiles in {TI_DIR}:')
for root, dirs, files in os.walk(TI_DIR):
    for f in files:
        print(f'  {os.path.join(root, f)}')
