"""
After InitializePSM (with vtable in arg3):
- Examine ALL non-zero handles around handle+0x88..0x98
- Try PHI_LoadPSM with ctx = handle+0x88 value, arg4=1
- Also: try with ctx = handle+0x94 directly (the inline slot)
- Also: read more of InitializePSM to find malloc+vtable assignment
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

def read_bytes_safe(addr, n):
    try:
        buf = ctypes.create_string_buffer(n)
        nread = ctypes.c_size_t(0)
        ctypes.windll.kernel32.ReadProcessMemory(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.c_void_p(addr), buf, n, ctypes.byref(nread))
        return buf.raw[:nread.value]
    except:
        return b''

def hex_dump(addr, data, cols=16):
    for i in range(0, len(data), cols):
        chunk = data[i:i+cols]
        print(f'  0x{addr+i:08X}: {" ".join(f"{b:02X}" for b in chunk)}')

c = ctypes.c_int32(0); dll.PHI_CheckforDevices(ctypes.byref(c))
h = ctypes.c_int32(0); dll.PHI_Initialize(0, ctypes.byref(h))
handle = h.value
dll_base = GetModuleHandle('tiPHIChar.dll')
print(f'handle=0x{handle:08X}  dll_base=0x{dll_base:08X}', flush=True)

VTABLE_RVA = 0x772F4
vtable_addr = dll_base + VTABLE_RVA

# Read InitializePSM bytes from offset 0x140 onward to find malloc+vtable set
FN_INITPSM = dll_base + 0x17100
print('\nPHI_InitializePSM from +0x140 to +0x200:')
data = read_bytes_safe(FN_INITPSM + 0x140, 192)
hex_dump(FN_INITPSM + 0x140, data)

# Call InitializePSM with vtable at arg3[0]
arg3_buf = bytearray(512)
struct.pack_into('<I', arg3_buf, 0, vtable_addr)
arg3 = ctypes.create_string_buffer(bytes(arg3_buf), 512)
ret = dll.PHI_InitializePSM(h, ctypes.c_int32(0), arg3)
print(f'\nPHI_InitializePSM(vtable) -> ret={ret}', flush=True)

# Show all handles
print('\nhandle+0x80 to handle+0xB0:')
for off in range(0x80, 0xB4, 4):
    v = ctypes.c_uint32.from_address(handle + off).value
    tag = ''
    if v > 0x10000:
        # Try to read what's there
        raw = read_bytes_safe(v, 4)
        if len(raw) >= 4:
            vt = struct.unpack('<I', raw)[0]
            dll_lo = dll_base; dll_hi = dll_base + 0x100000
            if dll_lo <= vt <= dll_hi:
                tag = f' -> [0]=0x{vt:08X} (DLL ptr, vtable?)'
            else:
                tag = f' -> [0]=0x{vt:08X}'
    print(f'  handle+0x{off:03X} = 0x{v:08X}{tag}')

ptr_88 = ctypes.c_uint32.from_address(handle + 0x88).value
ptr_90 = ctypes.c_uint32.from_address(handle + 0x90).value
ptr_94_inline = handle + 0x94

print(f'\nhandle+0x88 -> 0x{ptr_88:08X} (64 bytes):')
hex_dump(ptr_88, read_bytes_safe(ptr_88, 64))

print(f'\nhandle+0x90 -> 0x{ptr_90:08X} (64 bytes):')
hex_dump(ptr_90, read_bytes_safe(ptr_90, 64))

print(f'\nhandle+0x94 inline (64 bytes at 0x{ptr_94_inline:08X}):')
hex_dump(ptr_94_inline, read_bytes_safe(ptr_94_inline, 64))

# Try various ctx values with PHI_LoadPSM(handle, 0, ctx, 1)
print('\n--- Testing PHI_LoadPSM candidates ---', flush=True)
candidates = [
    ('handle+0x88 value', ptr_88),
    ('handle+0x90 value', ptr_90),
    ('handle+0x94 inline', ptr_94_inline),
]
for label, ctx in candidates:
    print(f'  ctx={label} (0x{ctx:08X}):', flush=True)
    sys.stdout.flush()
    try:
        ret2 = dll.PHI_LoadPSM(h, ctypes.c_int32(0), ctypes.c_int32(ctx), ctypes.c_int32(1))
        print(f'    -> ret={ret2}', flush=True)
    except Exception as e:
        print(f'    -> EXCEPTION: {e}', flush=True)
