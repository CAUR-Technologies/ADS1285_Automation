"""
Configuration centralisee — valeurs lues depuis config.ini.
Modifier config.ini (ou l'interface graphique) pour changer les parametres.
"""

from config.config_manager import get

# --- ADS1285 EVM ---
ADS1285_REGISTER_MAP  = get("ADS1285", "register_map")
ADS1285_BRIDGE_PORT   = int(get("ADS1285", "bridge_port"))
ADS1285_PYTHON32_PATH = get("ADS1285", "python32_path")
ADS1285_SAMPLE_RATE   = int(get("ADS1285", "sample_rate"))
ADS1285_NUM_SAMPLES   = int(get("ADS1285", "num_samples"))

# --- Table de vibration APS ---
APS_BAUD    = int(get("APS", "baud"))
APS_TIMEOUT = float(get("APS", "timeout"))

APS_CONTROLLER_VERTICAL_PORT   = get("APS", "controller_vertical_port")
APS_CONTROLLER_HORIZONTAL_PORT = get("APS", "controller_horizontal_port")
APS_AMPLIFIER_VERTICAL_PORT    = get("APS", "amplifier_vertical_port")
APS_AMPLIFIER_HORIZONTAL_PORT  = get("APS", "amplifier_horizontal_port")
APS125_GAIN_VERTICAL           = get("APS", "amplifier_gain_vertical")
APS125_GAIN_HORIZONTAL         = get("APS", "amplifier_gain_horizontal")

# --- Wavetek Model 39A ---
WAVETEK_PORT    = get("Wavetek", "port")
WAVETEK_BAUD    = int(get("Wavetek", "baud"))
WAVETEK_TIMEOUT = float(get("Wavetek", "timeout"))

# --- Accelerometres (NI USB-6221) ---
NI_DEVICE_NAME        = get("NI", "device_name")
NI_AI_CHANNELS        = get("NI", "ai_channels")
NI_SAMPLE_RATE        = int(get("NI", "sample_rate"))
NI_SAMPLES_PER_CHANNEL = int(get("NI", "samples_per_channel"))
NI_REF_CHANNEL_VERTICAL   = int(get("NI", "ref_channel_vertical"))
NI_REF_CHANNEL_HORIZONTAL = int(get("NI", "ref_channel_horizontal"))

# --- Banc shaker / calibration geophone ---
SHAKER_STROKE_MM          = float(get("Shaker", "stroke_mm"))
SHAKER_ENVELOPE_FRACTION  = float(get("Shaker", "envelope_fraction"))
SHAKER_ACCEL_CAP_G        = float(get("Shaker", "accel_cap_g"))
SHAKER_ACCEL_FLOOR_G      = float(get("Shaker", "accel_floor_g"))
ACCEL_SENSITIVITY_V_PER_G = float(get("Shaker", "accel_sensitivity_v_per_g"))
SHAKER_SERVO_TOLERANCE    = float(get("Shaker", "servo_tolerance"))
SHAKER_SERVO_MAX_ITER     = int(get("Shaker", "servo_max_iter"))
SHAKER_SERVO_START_VPP    = float(get("Shaker", "servo_start_vpp"))
SHAKER_GEOPHONE           = get("Shaker", "geophone")

# --- Acquisition generale ---
DATA_OUTPUT_DIR = get("General", "data_output_dir")
