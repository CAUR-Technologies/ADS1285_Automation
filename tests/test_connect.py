from equipment.ads1285 import ADS1285

with ADS1285() as ads:
    print("Handle OK")
    v = ads.get_version()
    print("Version:", v)
