"""
Stage 5B source discovery (Gate 1). Records what was found about each
candidate observation source, from the sources' own pages (accessed
2026-09-30). Writes results/observation_source_manifest.json.
"""

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"

SOURCES = [
    {
        "source": "India Meteorological Department (IMD) — Data Supply Portal, National Data Centre, Pune",
        "official_provenance": "Government of India, Ministry of Earth Sciences; https://dsp.imdpune.gov.in/",
        "variables": "historical surface observations incl. hourly temperature, humidity, wind, rainfall (per portal request forms)",
        "station_metadata": "'List of Stations Available' on the portal (behind the request workflow)",
        "access_method": "account enrolment + online data request; charges estimated for users outside MoES; "
                         "contact data.service@imd.gov.in",
        "licensing": "portal: reproduction for commercial purpose not permitted without permission",
        "historical_obtainable_now": False,
        "reason": "requires account creation and a data request/possible payment -- a step the user must take; "
                  "not performed in this stage",
        "suitable_for_2021_2023": "likely (portal lists historical hourly series), unverified without a request",
        "evidence_urls": ["https://dsp.imdpune.gov.in/",
                          "https://mausam.imd.gov.in/ahmedabad/docs/data-procedure.pdf"],
    },
    {
        "source": "Karnataka State Natural Disaster Monitoring Centre (KSNDMC)",
        "official_provenance": "Government of Karnataka; ~6,000 telemetric rain gauges (Gram Panchayat level) and "
                               ">750 telemetric weather stations, 15-minute reporting",
        "variables": "rainfall (TRG); temperature, humidity, wind speed/direction (TWS)",
        "station_metadata": "station lists republished on data.opencity.in (third-party mirror -- not used as source)",
        "access_method": "request by e-mail (dmc.kar@nic.in); reported free for researchers/NGOs",
        "licensing": "not published; terms set per request",
        "historical_obtainable_now": False,
        "reason": "no public download; obtaining data requires sending a request on the user's behalf -- not "
                  "performed in this stage. KSNDMC Panchayat-level gauges are the most direct route to a PRIMARY "
                  "(inside-Panchayat) validation set.",
        "suitable_for_2021_2023": "reportedly (Panchayat gauges from 2014), unverified",
        "evidence_urls": ["https://biometrust.org/accessing-the-data-and-rainfall-analysis-for-halanayakanahalli-gram-panchayat-data-from-karnataka-state-natural-disaster-monitoring-center-ksndmc/",
                          "https://data.opencity.in/dataset/karnataka-telemetric-weather-stations-and-rain-gauges"],
    },
    {
        "source": "NOAA NCEI Integrated Surface Database (ISD) / Global Surface Hourly (DSI 3505_03)",
        "official_provenance": "U.S. Government archive of WMO-exchanged surface reports (SYNOP FM-12, METAR FM-15 ...); "
                               "the reporting agency per Indian station was NOT verified in this stage (report types "
                               "in the 2023 files are FM-12 SYNOP and, at Mangalore, FM-15 METAR)",
        "variables": "TMP air temperature degC x10; DEW dew point degC x10; WND speed m/s x10; AA1-AA4 liquid "
                     "precipitation depth mm x10 over an explicit period in hours; per-value quality codes",
        "station_metadata": "isd-history.csv (USAF-WBAN id, name, lat, lon, elevation, begin/end)",
        "observation_frequency": "SYNOP typically 3-hourly (often incomplete); METAR hourly/half-hourly at airports",
        "timestamps": "UTC (format document: GEOPHYSICAL-POINT-OBSERVATION time in UTC)",
        "access_method": "HTTPS: https://www.ncei.noaa.gov/data/global-hourly/access/<year>/<USAF><WBAN>.csv",
        "licensing": "cite as: NOAA National Centers for Environmental Information (2001): Global Surface Hourly "
                     "[subset]. No warranty as to accuracy, reliability or completeness.",
        "quality_control": "automated NCEI QC (format, extreme limits, internal consistency, continuity); quality codes preserved",
        "historical_obtainable_now": True,
        "suitable_for_2021_2023": True,
        "caveats": ["stations are at towns/observatories/airports, not inside rural Panchayat polygons",
                    "3-hourly SYNOP with gaps; precipitation only in some reports, with varying periods",
                    "not a substitute for IMD/KSNDMC Panchayat-level networks"],
        "evidence_urls": ["https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database",
                          "https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf",
                          "https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc:C00532"],
    },
]

NOT_USED = ["third-party weather websites or apps (not authoritative; excluded by design)",
            "IMD gridded 0.25 deg rainfall (gridded analysis, not station observations)"]


def run() -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = {"accessed": "2026-09-30", "sources": SOURCES, "not_used": NOT_USED,
           "gate1_conclusion": ("IMD DSP and KSNDMC hold the most relevant networks but require a request/account the "
                                "user must initiate. NOAA NCEI ISD is the only authoritative source obtainable now; it "
                                "is used, with its limitations recorded.")}
    (RESULTS / "observation_source_manifest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    run()
