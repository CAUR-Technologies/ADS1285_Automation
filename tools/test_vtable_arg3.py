"""
Test PHI_InitializePSM with vtable candidate as arg3[0], then patch ctx manually.
"""
import ctypes, ctypes.wintypes, struct, os, sys

print("Step 1: imports done", flush=True)

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
dll.PHI_LoadPSM.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]

print("Step 2: DLL loaded", flush=True)

GetModuleHandle = ctypes.windll.kernel32.GetModuleHandleW
GetModuleHandle.restype = ctypes.wintypes.HMODULE
dll_base = GetModuleHandle('tiPHIChar.dll')

c = ctypes.c_int32(0)
dll.PHI_CheckforDevices(ctypes.byref(c))
print(f"Step 3: devices={c.value}", flush=True)

h = ctypes.c_int32(0)
dll.PHI_Initialize(0, ctypes.byref(h))
handle = h.value
print(f"Step 4: handle=0x{handle:08X}  dll_base=0x{dll_base:08X}", flush=True)

# The vtable candidate: at RVA 0x772F4 = 0x740C72F4 - 0x74050000
VTABLE_RVA = 0x772F4
vtable_addr = dll_base + VTABLE_RVA
print(f"Step 5: vtable_addr=0x{vtable_addr:08X}", flush=True)

# Verify vtable contents
vt_raw = bytes((ctypes.c_byte * 16).from_address(vtable_addr))
vt = struct.unpack('<4I', vt_raw)
print(f"Step 6: vtable[0:4] = {['0x{:08X}'.format(v) for v in vt]}", flush=True)

# Call PHI_InitializePSM with zero arg3 (standard path)
dummy = ctypes.create_string_buffer(512)
ret = dll.PHI_InitializePSM(h, ctypes.c_int32(0), dummy)
ctx_ptr = ctypes.c_int32.from_address(handle + 0x90).value
print(f"Step 7: PHI_InitializePSM(zero) -> ret={ret}  ctx=0x{ctx_ptr:08X}", flush=True)

if ctx_ptr:
    raw = bytes((ctypes.c_byte * 32).from_address(ctx_ptr))
    dw = struct.unpack('<8I', raw)
    print(f"  ctx[0:8] = {['0x{:08X}'.format(v) for v in dw]}", flush=True)

    # Manually patch vtable pointer into ctx[0]
    print(f"Step 8: patching ctx[0] = 0x{vtable_addr:08X}", flush=True)
    ctypes.c_uint32.from_address(ctx_ptr).value = vtable_addr

    # Verify patch
    new_vt = ctypes.c_uint32.from_address(ctx_ptr).value
    print(f"  ctx[0] after patch = 0x{new_vt:08X}", flush=True)

    # Now call PHI_LoadPSM
    print(f"Step 9: calling PHI_LoadPSM(ctx=0x{ctx_ptr:08X})", flush=True)
    sys.stdout.flush()
    ret2 = dll.PHI_LoadPSM(h, ctypes.c_int32(0), ctypes.c_int32(ctx_ptr))
    print(f"  PHI_LoadPSM -> ret={ret2}", flush=True)
else:
    print("ctx_ptr is 0, cannot proceed", flush=True)
