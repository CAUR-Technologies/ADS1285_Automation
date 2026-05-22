"""
Read more bytes of PHI_LoadPSM + search for arg3 usage ([ebp+0x10] = 0x55).
Also try to find where the vtable is dereferenced.
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

FN_LOADPSM_RVA = 0x17310
fn_loadpsm = dll_base + FN_LOADPSM_RVA

# Read 768 bytes total
data = read_bytes(fn_loadpsm, 768)
print(f'\nPHI_LoadPSM full (768 bytes):')
hex_dump(fn_loadpsm, data)

# Search for references to [ebp+0x10] (arg3 = ctx)
# In x86: mov reg, [ebp+10h] = 8B ?? 10 or 8B 45 10 or 8B 55 10 etc.
# Also CALL through ptr [reg] or CALL [eax] = FF 10, FF D0, etc.
print('\n--- Searching for [ebp+0x10] references ---')
for i in range(len(data)-2):
    # 8B ?? 10 pattern (MOV reg, [ebp+10h])
    if data[i] == 0x8B and data[i+2] == 0x10:
        print(f'  0x{fn_loadpsm+i:08X}: {" ".join(f"{b:02X}" for b in data[i:i+3])}  MOV reg, [ebp+10h]?')
    # Also look for 8B 4D 10 specifically (MOV ecx, [ebp+10h])
    if data[i:i+3] == bytes([0x8B, 0x4D, 0x10]):
        print(f'  0x{fn_loadpsm+i:08X}: 8B 4D 10  MOV ecx, [ebp+10h] (arg3=ctx)')
    if data[i:i+3] == bytes([0x8B, 0x45, 0x10]):
        print(f'  0x{fn_loadpsm+i:08X}: 8B 45 10  MOV eax, [ebp+10h] (arg3=ctx)')
    if data[i:i+3] == bytes([0x8B, 0x55, 0x10]):
        print(f'  0x{fn_loadpsm+i:08X}: 8B 55 10  MOV edx, [ebp+10h] (arg3=ctx)')

# Search for CALL through vtable (FF 10 = call [eax], FF 11 = call [ecx], etc.)
print('\n--- Virtual dispatch candidates (FF 1x / FF 5x 00) ---')
for i in range(len(data)-1):
    if data[i] == 0xFF and (data[i+1] & 0xF8) == 0x10:
        reg = ['eax','ecx','edx','ebx','esp','ebp','esi','edi'][data[i+1] & 7]
        print(f'  0x{fn_loadpsm+i:08X}: FF {data[i+1]:02X}  CALL [{reg}]  (virtual call)')
    # Also FF 50 00 = CALL [eax+0x00], etc.
    if i+2 < len(data) and data[i] == 0xFF and data[i+1] == 0x50 and data[i+2] == 0x00:
        print(f'  0x{fn_loadpsm+i:08X}: FF 50 00  CALL [eax+0]  (virtual call vtable[0])')
    if i+2 < len(data) and data[i] == 0xFF and data[i+1] == 0x51 and data[i+2] == 0x00:
        print(f'  0x{fn_loadpsm+i:08X}: FF 51 00  CALL [ecx+0]  (virtual call vtable[0])')
    if i+2 < len(data) and data[i] == 0xFF and data[i+1] == 0x52 and data[i+2] == 0x00:
        print(f'  0x{fn_loadpsm+i:08X}: FF 52 00  CALL [edx+0]  (virtual call vtable[0])')
