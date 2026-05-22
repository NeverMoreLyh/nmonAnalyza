from pathlib import Path

import pandas as pd

from nmon_report.metrics import group_sections
from nmon_report.parser import parse_nmon


SAMPLE = Path(__file__).resolve().parents[1] / "sample" / "server-a.nmon"


def test_parse_zzzz_timestamp_mapping() -> None:
    nmon = parse_nmon(SAMPLE)

    assert nmon.timestamps["T0001"] == pd.Timestamp("2026-05-21 10:00:00")
    assert nmon.host == "server-a"


def test_parse_generic_sections_and_unknown_section() -> None:
    nmon = parse_nmon(SAMPLE)

    assert "CPU_ALL" in nmon.sections
    assert "CUSTOMX" in nmon.sections
    assert list(nmon.sections["CUSTOMX"]["value"]) == [1, 2, 3]


def test_group_common_and_unknown_sections() -> None:
    grouped = group_sections(["CPU_ALL", "MEM", "DISKBUSY", "NET", "JFSFILE", "SYS", "CUSTOMX"])

    assert grouped["cpu"][0].section == "CPU_ALL"
    assert grouped["memory"][0].section == "MEM"
    assert grouped["disk"][0].section == "DISKBUSY"
    assert grouped["network"][0].section == "NET"
    assert grouped["filesystem"][0].section == "JFSFILE"
    assert grouped["system"][0].section == "SYS"
    assert grouped["unclassified"][0].section == "CUSTOMX"


def test_standard_nmon_description_header_is_skipped(tmp_path: Path) -> None:
    sample = tmp_path / "standard.nmon"
    sample.write_text(
        "\n".join(
            [
                "AAA,host,standard",
                "ZZZZ,T0001,17:52:50,21-MAY-2026",
                "CPU_ALL,CPU Total standard,User%,Sys%,Wait%,Idle%,Steal%,Busy,CPUs",
                "CPU_ALL,T0001,38.5,3.3,0.0,58.1,0.0,,128",
            ]
        ),
        encoding="utf-8",
    )

    nmon = parse_nmon(sample)
    frame = nmon.sections["CPU_ALL"]

    assert "CPU Total standard" not in frame.columns
    assert frame.loc[0, "User%"] == 38.5
    assert frame.loc[0, "Idle%"] == 58.1
    assert frame.loc[0, "CPUs"] == 128
    assert frame.loc[0, "Busy"] == ""
