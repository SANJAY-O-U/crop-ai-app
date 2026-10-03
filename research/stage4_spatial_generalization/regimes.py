"""
Geographic regime of every Karnataka Taluka Panchayat, for Stage 4
selection and regional holdout.

IMPORTANT: this is a CONVENTIONAL, project-authored grouping of Zila
Panchayats (with a few named Taluka Panchayat overrides where a district
clearly straddles the Western Ghats or the coast). It is NOT an official
agro-climatic zonation and is not derived from weather data. It exists so
the selection is forced to span visibly different geography; it should be
reviewed, and any change is a deliberate, versioned design decision.
"""

REGIMES = [
    "western_ghats_malnad",
    "coastal_inland_coast",
    "northern_dry_plains",
    "central_plateau",
    "southern_plateau",
    "eastern_plateau",
]

ZILA_DEFAULT = {
    # coastal / inland coast
    "Dakshina Kannada": "coastal_inland_coast",
    "Udupi": "coastal_inland_coast",
    # Western Ghats / Malnad
    "Kodagu": "western_ghats_malnad",
    "Chikkamagaluru": "western_ghats_malnad",
    "Shivamogga": "western_ghats_malnad",
    "Uttara Kannada": "western_ghats_malnad",
    # northern dry plains
    "Bagalkot": "northern_dry_plains",
    "Belagavi": "northern_dry_plains",
    "Bidar": "northern_dry_plains",
    "Dharwad": "northern_dry_plains",
    "Gadag": "northern_dry_plains",
    "Kalaburagi": "northern_dry_plains",
    "Koppal": "northern_dry_plains",
    "Raichur": "northern_dry_plains",
    "Vijayapura": "northern_dry_plains",
    "Yadgir": "northern_dry_plains",
    # central plateau
    "Ballari": "central_plateau",
    "Chitradurga": "central_plateau",
    "Davangere": "central_plateau",
    "Haveri": "central_plateau",
    "Tumakuru": "central_plateau",
    "Vijayanagara": "central_plateau",
    # southern plateau
    "Bengaluru South": "southern_plateau",
    "Chamarajanagar": "southern_plateau",
    "Hassan": "southern_plateau",
    "Mandya": "southern_plateau",
    "Mysuru": "southern_plateau",
    # eastern plateau
    "Bengaluru Rural": "eastern_plateau",
    "Bengaluru Urban": "eastern_plateau",
    "Chikballapur": "eastern_plateau",
    "Kolar": "eastern_plateau",
}

# (Zila Panchayat, Taluka Panchayat) -> regime, where it differs from the district default.
TALUKA_OVERRIDES = {
    # Uttara Kannada: coastal taluks (inland taluks keep the Malnad default)
    ("Uttara Kannada", "Karwar"): "coastal_inland_coast",
    ("Uttara Kannada", "Ankola"): "coastal_inland_coast",
    ("Uttara Kannada", "Kumta"): "coastal_inland_coast",
    ("Uttara Kannada", "Honavar"): "coastal_inland_coast",
    ("Uttara Kannada", "Bhatkal"): "coastal_inland_coast",
    # Hassan: Western Ghats taluks
    ("Hassan", "Sakaleshpur"): "western_ghats_malnad",
    ("Hassan", "Alur"): "western_ghats_malnad",
    ("Hassan", "Belur"): "western_ghats_malnad",
    # Belagavi: Western Ghats taluk
    ("Belagavi", "Khanapur"): "western_ghats_malnad",
    # Chikkamagaluru: eastern plains taluks
    ("Chikkamagaluru", "Kadur"): "central_plateau",
    ("Chikkamagaluru", "Tarikere"): "central_plateau",
    ("Chikkamagaluru", "Ajjampura"): "central_plateau",
    # Shivamogga: eastern (non-Malnad) taluks
    ("Shivamogga", "Bhadravati"): "central_plateau",
    ("Shivamogga", "Shikarpur"): "central_plateau",
    ("Shivamogga", "Shivamogga"): "central_plateau",
}


def regime_of(zp_name: str, tp_name: str) -> str:
    if (zp_name, tp_name) in TALUKA_OVERRIDES:
        return TALUKA_OVERRIDES[(zp_name, tp_name)]
    if zp_name not in ZILA_DEFAULT:
        raise KeyError(f"No regime defined for Zila Panchayat '{zp_name}'")
    return ZILA_DEFAULT[zp_name]
