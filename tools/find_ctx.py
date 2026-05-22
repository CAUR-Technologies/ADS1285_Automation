"""
Diagnostic: find origin of ctx value for PHI_LoadPSM.

Steps:
1. Load DLL, call PHI_Initialize
2. Call PHI_InitializePSM
3. Scan DLL globals (handle area ± 1KB) for address-like values
4. Dump PHI_InitializePSM disassembly to see what it writes where
5. Try reading a 1KB window around the handle struct post-InitializePSM
"""
import ctypes
import struct
import os, sys

DLL_PATH    = r"C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Library\tiPHIChar.dll"
SHARED_PATH = r"C:\Program Files (x86)\Texas Instruments\ADS1285 EVM\Shared Library"

os.add_dll_directory(os.path.dirname(DLL_PATH))
os.add_dll_directory(SHARED_PATH)
dll = ctypes.WinDLL(DLL_PATH)

# ---- prototypes ----
P = ctypes.POINTER(ctypes.c_int32)
dll.PHI_CheckforDevices.restype  = ctypes.c_int32
dll.PHI_CheckforDevices.argtypes = [P]
dll.PHI_Initialize.restype  = ctypes.c_int32
dll.PHI_Initialize.argtypes = [ctypes.c_int32, P]
dll.PHI_InitializePSM.restype  = ctypes.c_int32
dll.PHI_InitializePSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_char_p]

# ---- get DLL base ----
import ctypes.wintypes
GetModuleHandle = ctypes.windll.kernel32.GetModuleHandleW
GetModuleHandle.restype = ctypes.wintypes.HMODULE
dll_base = GetModuleHandle("tiPHIChar.dll")
print(f"DLL base: 0x{dll_base:08X}")

# ---- initialize ----
count = ctypes.c_int32(0)
dll.PHI_CheckforDevices(ctypes.byref(count))
print(f"Devices: {count.value}")

handle = ctypes.c_int32(0)
ret = dll.PHI_Initialize(0, ctypes.byref(handle))
h = handle.value
print(f"PHI_Initialize -> ret={ret}  handle=0x{h:08X}  (RVA=0x{h - dll_base:05X})")
if h == 0:
    print("ERROR: handle is 0 — device not connected?")
    sys.exit(1)

# ---- snapshot DLL memory around handle area BEFORE InitializePSM ----
handle_rva = h - dll_base
# read 256 dwords (1KB) starting 512B before handle
SCAN_START_RVA = handle_rva - 512
SCAN_LEN = 1024
scan_addr = dll_base + SCAN_START_RVA

kernel32 = ctypes.windll.kernel32
ReadProcessMemory = kernel32.ReadProcessMemory
HANDLE_SELF = kernel32.GetCurrentProcess()

buf_before = ctypes.create_string_buffer(SCAN_LEN)
nread = ctypes.c_size_t(0)
ReadProcessMemory(HANDLE_SELF, ctypes.c_void_p(scan_addr), buf_before, SCAN_LEN, ctypes.byref(nread))
print(f"Read {nread.value}B from DLL globals (before InitializePSM)")

# ---- call PHI_InitializePSM ----
ctx_buf = ctypes.create_string_buffer(512)
ret2 = dll.PHI_InitializePSM(handle, ctypes.c_int32(0), ctx_buf)
print(f"PHI_InitializePSM -> ret={ret2}")

# ---- snapshot AFTER ----
buf_after = ctypes.create_string_buffer(SCAN_LEN)
ReadProcessMemory(HANDLE_SELF, ctypes.c_void_p(scan_addr), buf_after, SCAN_LEN, ctypes.byref(nread))
print(f"Read {nread.value}B from DLL globals (after  InitializePSM)")

# ---- diff: find changed dwords ----
before_dwords = struct.unpack_from(f'<{SCAN_LEN//4}I', buf_before.raw)
after_dwords  = struct.unpack_from(f'<{SCAN_LEN//4}I', buf_after.raw)

print("\n--- Changes in DLL globals (handle±512B) after InitializePSM ---")
changed = False
for i, (b, a) in enumerate(zip(before_dwords, after_dwords)):
    if b != a:
        rva = SCAN_START_RVA + i*4
        abs_addr = dll_base + rva
        print(f"  RVA=0x{rva:05X}  addr=0x{abs_addr:08X}  before=0x{b:08X}  after=0x{a:08X}")
        changed = True
if not changed:
    print("  (aucun changement)")

# ---- ctx_buf contents ----
print("\n--- ctx_buf (first 64 bytes after InitializePSM) ---")
raw = ctx_buf.raw[:64]
dwords = struct.unpack_from('<16I', raw)
for i, v in enumerate(dwords):
    print(f"  [{i*4:3d}] 0x{v:08X}  ({v})")

# ---- scan larger DLL data for pointer-looking values ----
# Read 8KB around handle
LARGE_SCAN_BYTES = 8192
large_buf = ctypes.create_string_buffer(LARGE_SCAN_BYTES)
scan2_addr = dll_base + handle_rva - 1024
ReadProcessMemory(HANDLE_SELF, ctypes.c_void_p(scan2_addr), large_buf, LARGE_SCAN_BYTES, ctypes.byref(nread))
large_dwords = struct.unpack_from(f'<{LARGE_SCAN_BYTES//4}I', large_buf.raw)
print(f"\n--- Pointers in ±4KB of handle (after InitializePSM) ---")
# Look for values that look like heap pointers (roughly 0x00400000-0x7FFFFFFF)
# and exclude DLL image region
dll_range_lo = dll_base
dll_range_hi = dll_base + 0xA3000
interesting = []
for i, v in enumerate(large_dwords):
    if 0x00400000 <= v <= 0x7FFFFFFF and not (dll_range_lo <= v <= dll_range_hi):
        rva2 = (handle_rva - 1024) + i*4
        abs2 = dll_base + rva2
        interesting.append((rva2, abs2, v))
for rva2, abs2, v in interesting[:40]:
    print(f"  RVA=0x{rva2:05X}  addr=0x{abs2:08X}  val=0x{v:08X}  ({v})")

# ---- get PHI_InitializePSM entry point and dump bytes ----
print("\n--- PHI_InitializePSM entry point ---")
fn_addr = ctypes.cast(dll.PHI_InitializePSM, ctypes.c_void_p).value
fn_rva = fn_addr - dll_base
print(f"  addr=0x{fn_addr:08X}  RVA=0x{fn_rva:05X}")

fn_bytes = ctypes.create_string_buffer(512)
ReadProcessMemory(HANDLE_SELF, ctypes.c_void_p(fn_addr), fn_bytes, 512, ctypes.byref(nread))
raw_fn = fn_bytes.raw[:nread.value]
print(f"  First 64 bytes: {raw_fn[:64].hex()}")

# ---- also get PHI_LoadPSM entry point ----
dll.PHI_LoadPSM.restype  = ctypes.c_int32
dll.PHI_LoadPSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
fn2_addr = ctypes.cast(dll.PHI_LoadPSM, ctypes.c_void_p).value
fn2_rva = fn2_addr - dll_base
print(f"\n--- PHI_LoadPSM ---")
print(f"  addr=0x{fn2_addr:08X}  RVA=0x{fn2_rva:05X}")
fn2_bytes = ctypes.create_string_buffer(512)
ReadProcessMemory(HANDLE_SELF, ctypes.c_void_p(fn2_addr), fn2_bytes, 512, ctypes.byref(nread))
raw_fn2 = fn2_bytes.raw[:nread.value]
print(f"  First 64 bytes: {raw_fn2[:64].hex()}")
