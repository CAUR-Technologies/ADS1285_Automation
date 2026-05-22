"""
Deeper analysis: read string constants in PHI_LoadPSM,
disassemble fn at 0x740629CE, and check what arg3=ctx is actually used for.
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

P = ctypes.POINTER(ctypes.c_int32)
dll.PHI_CheckforDevices.restype  = ctypes.c_int32
dll.PHI_CheckforDevices.argtypes = [P]
dll.PHI_Initialize.restype  = ctypes.c_int32
dll.PHI_Initialize.argtypes  = [ctypes.c_int32, P]
dll.PHI_InitializePSM.restype  = ctypes.c_int32
dll.PHI_InitializePSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_char_p]

c = ctypes.c_int32(0); dll.PHI_CheckforDevices(ctypes.byref(c))
h = ctypes.c_int32(0); dll.PHI_Initialize(0, ctypes.byref(h))
handle = h.value
print(f'handle=0x{handle:08X}  dll_base=0x{dll_base:08X}')

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

def read_string(addr, maxlen=128):
    raw = read_bytes(addr, maxlen)
    end = raw.find(b'\x00')
    return raw[:end].decode('latin1', errors='replace') if end >= 0 else raw.decode('latin1', errors='replace')

# Read the string constants passed to fn calls in PHI_LoadPSM
STR1_ADDR = dll_base + (0x740BA77C - 0x74050000)
STR2_ADDR = dll_base + (0x740BA7C8 - 0x74050000)
print(f'\nString at 0x{STR1_ADDR:08X}: "{read_string(STR1_ADDR)}"')
print(f'String at 0x{STR2_ADDR:08X}: "{read_string(STR2_ADDR)}"')

# Disassemble fn at 0x740629CE (called with ctx as first arg)
FN_RVA = 0x740629CE - 0x74050000
fn_addr = dll_base + FN_RVA
print(f'\nfn at 0x{fn_addr:08X} (first arg = ctx):')
data = read_bytes(fn_addr, 128)
hex_dump(fn_addr, data)

# Also disassemble fn at 0x740629D0 (2 bytes later, second ctx call)
fn2_addr = fn_addr + 2
print(f'\nfn at 0x{fn2_addr:08X} (+2):')
# Same data

# Read handle+0x90 area context - show MORE handle fields
print('\n--- Extended handle area ---')
for offset in range(0, 0x100, 4):
    v = ctypes.c_uint32.from_address(handle + offset).value
    if v != 0:
        print(f'  handle+0x{offset:03X} = 0x{v:08X}')

# Read PSM area at handle+0x44 (which is PSM slot structure)
ptr_44 = ctypes.c_uint32.from_address(handle + 0x44).value
if ptr_44:
    print(f'\nhandle+0x44 -> 0x{ptr_44:08X} (first 64 bytes):')
    data44 = read_bytes(ptr_44, 64)
    hex_dump(ptr_44, data44)

# Also check handle+0x88 which had non-zero data
ptr_88 = ctypes.c_uint32.from_address(handle + 0x88).value
if ptr_88:
    print(f'\nhandle+0x88 -> 0x{ptr_88:08X} (first 64 bytes):')
    data88 = read_bytes(ptr_88, 64)
    hex_dump(ptr_88, data88)
    # Check if [0] looks like a vtable pointer (in DLL range)
    if data88:
        vt_candidate = struct.unpack('<I', data88[:4])[0]
        dll_lo = dll_base
        dll_hi = dll_base + 0x100000
        print(f'  [0]=0x{vt_candidate:08X}  in_dll={dll_lo <= vt_candidate <= dll_hi}')
