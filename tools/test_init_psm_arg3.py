"""
Test PHI_InitializePSM with various arg3 values to find which one
causes the ctx struct (at handle+0x90) to be properly initialized (vtable != 0).
"""
import ctypes, os, struct

DLL_PATH    = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library\tiPHIChar.dll'
SHARED_PATH = r'C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Shared Library'
os.add_dll_directory(os.path.dirname(DLL_PATH))
os.add_dll_directory(SHARED_PATH)
dll = ctypes.WinDLL(DLL_PATH)
P = ctypes.POINTER(ctypes.c_int32)

dll.PHI_CheckforDevices.restype = ctypes.c_int32
dll.PHI_CheckforDevices.argtypes = [P]
dll.PHI_Initialize.restype = ctypes.c_int32
dll.PHI_Initialize.argtypes = [ctypes.c_int32, P]
dll.PHI_InitializePSM.restype = ctypes.c_int32
dll.PHI_InitializePSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_char_p]

import ctypes.wintypes
GetModuleHandle = ctypes.windll.kernel32.GetModuleHandleW
GetModuleHandle.restype = ctypes.wintypes.HMODULE

dll_base = GetModuleHandle('tiPHIChar.dll')

c = ctypes.c_int32(0)
dll.PHI_CheckforDevices(ctypes.byref(c))
h = ctypes.c_int32(0)
dll.PHI_Initialize(0, ctypes.byref(h))
handle = h.value
PSM_ARRAY_BASE = dll_base + 0x79340
print(f'handle=0x{handle:08X}  PSM_ARRAY_BASE=0x{PSM_ARRAY_BASE:08X}  dll_base=0x{dll_base:08X}')

def test_init_psm(arg3_bytes, label):
    """Call PHI_InitializePSM with given arg3 bytes and return ctx struct."""
    # Reset ctx slot
    buf = ctypes.create_string_buffer(len(arg3_bytes))
    buf.raw = arg3_bytes
    ret = dll.PHI_InitializePSM(h, ctypes.c_int32(0), buf)
    ctx_ptr = ctypes.c_int32.from_address(handle + 0x90).value
    if ctx_ptr:
        try:
            ctx_raw = bytes((ctypes.c_byte * 32).from_address(ctx_ptr))
            dwords = struct.unpack('<8I', ctx_raw)
            vtable = dwords[0]
        except:
            vtable = -1
    else:
        vtable = 0
    print(f'  {label:40s} ret={ret} ctx=0x{ctx_ptr:08X} vtable=0x{vtable:08X}')
    return vtable

print('\n--- Testing arg3 values ---')

# 1. Zero buffer (current)
test_init_psm(b'\x00' * 512, 'zero buffer (current)')

# 2. Try with dll_base in first dword
arg3 = struct.pack('<I', dll_base) + b'\x00' * 508
test_init_psm(arg3, 'arg3[0] = dll_base')

# 3. Try with PSM_ARRAY_BASE
arg3 = struct.pack('<I', PSM_ARRAY_BASE) + b'\x00' * 508
test_init_psm(arg3, 'arg3[0] = PSM_ARRAY_BASE')

# 4. Try with handle
arg3 = struct.pack('<I', handle) + b'\x00' * 508
test_init_psm(arg3, 'arg3[0] = handle')

# Scan DLL .rdata for vtable-like patterns (function ptr arrays)
# A vtable starts with a series of DLL function pointers
# Try reading known function addresses and finding vtable patterns
print('\n--- Scanning DLL for vtable candidates ---')
fn_init = ctypes.cast(dll.PHI_InitializePSM, ctypes.c_void_p).value
fn_load = ctypes.cast(dll.PHI_LoadPSM, ctypes.c_void_p).value
print(f'fn_InitializePSM=0x{fn_init:08X}  fn_LoadPSM=0x{fn_load:08X}')

# Read .rdata section (typical for vtables) -- scan 64KB starting at dll_base + 0x75000
RDATA_START = dll_base + 0x75000
SCAN_SIZE   = 0x4000  # 16KB
scan_buf = ctypes.create_string_buffer(SCAN_SIZE)
nread = ctypes.c_size_t(0)
ctypes.windll.kernel32.ReadProcessMemory(
    ctypes.windll.kernel32.GetCurrentProcess(),
    ctypes.c_void_p(RDATA_START), scan_buf, SCAN_SIZE, ctypes.byref(nread))
raw = scan_buf.raw[:nread.value]

# Look for patterns: 4+ consecutive dwords pointing into DLL text section
dll_text_lo = dll_base + 0x1000
dll_text_hi = dll_base + 0x75000  # before .rdata
vtable_candidates = []
for i in range(0, len(raw)-32, 4):
    dwords = struct.unpack_from('<8I', raw, i)
    # Check if first 3 dwords look like function pointers
    n_valid = sum(1 for v in dwords[:4] if dll_text_lo <= v <= dll_text_hi)
    if n_valid >= 3:
        addr = RDATA_START + i
        vtable_candidates.append((addr, dwords))

print(f'Found {len(vtable_candidates)} vtable candidates in .rdata')
for addr, dw in vtable_candidates[:20]:
    print(f'  0x{addr:08X}: {["0x{:08X}".format(v) for v in dw[:4]]}')

# Try each vtable as the first dword of arg3
print('\n--- Testing arg3 with vtable candidates ---')
for addr, dw in vtable_candidates[:10]:
    arg3 = struct.pack('<I', addr) + b'\x00' * 508
    vtable = test_init_psm(arg3, f'arg3[0]=vtable@0x{addr:08X}')
    if vtable != 0:
        print(f'  *** VTABLE SET! ctx has vtable=0x{vtable:08X} ***')
        break
