import pytest
from pathlib import Path
import sys
import tempfile
import os
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shift_scheduler.data_manager import (
    DataManager,
    DataValidationError,
    DataFileCorruptedError,
)


@pytest.fixture
def data_manager():
    """
    Fixture for a clean, isolated DataManager instance for each test.
    It creates a temporary data file that is destroyed after the test runs.
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as temp_file:
        temp_path = temp_file.name
        json.dump({}, temp_file)
    dm = DataManager(temp_path)
    yield dm
    os.unlink(temp_path)


def check_deviation_flag(flag, expected_type, expected_severity, expected_units):
    assert flag is not None
    assert flag["deviation_type"] == expected_type
    assert flag["severity"] == expected_severity
    assert f"{expected_units} units" in flag["description"]


def test_deviation_calculation_and_flagging(data_manager):
    """
    Test the deviation tracking functionality with a controlled, predictable scenario.
    This test verifies that calculated deviations and their severity flags are correct.
    """
    month_key = "2025-08"

    emp_high = data_manager.add_employee("EmpHigh", "High")
    emp_low = data_manager.add_employee("EmpLow", "Low")

    schedule = {
        "2025-08-01": {
            "day_shift": {"employee_id": emp_high.id, "is_manual": False},
            "night_shift": {"employee_id": emp_low.id, "is_manual": False},
        },
        "2025-08-02": {
            "day_shift": {"employee_id": emp_high.id, "is_manual": False},
            "night_shift": {"employee_id": emp_low.id, "is_manual": False},
        },
        "2025-08-03": {
            "day_shift": None,
            "night_shift": {"employee_id": emp_high.id, "is_manual": False},
        },
        # EmpLow assignments (continued)
        "2025-08-04": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": {"employee_id": emp_low.id, "is_manual": False},
        },
        "2025-08-05": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": {"employee_id": emp_low.id, "is_manual": False},
        },
        "2025-08-06": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": {"employee_id": emp_low.id, "is_manual": False},
        },
        "2025-08-07": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": None,
        },
        "2025-08-08": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": None,
        },
        "2025-08-09": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": None,
        },
        "2025-08-10": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": None,
        },
        "2025-08-11": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": None,
        },
        "2025-08-12": {
            "day_shift": {"employee_id": emp_low.id, "is_manual": False},
            "night_shift": None,
        },
    }
    data_manager.save_schedule(month_key, schedule)

    emp_stats = data_manager.calculate_employee_stats(month_key)
    team_stats = data_manager.get_team_stats(month_key)

    assert emp_stats is not None
    assert "EmpHigh" in emp_stats
    assert "EmpLow" in emp_stats

    # Verify EmpHigh's stats
    high_stats = emp_stats["EmpHigh"]
    assert high_stats["total_shifts"] == 4
    assert high_stats["quota"] == 24
    assert high_stats["quota_deviation"] == -20
    check_deviation_flag(high_stats["deviation_flag"], "under_quota", "high", 20)

    # Verify EmpLow's stats
    low_stats = emp_stats["EmpLow"]
    assert low_stats["total_shifts"] == 19
    assert low_stats["quota"] == 21
    assert low_stats["quota_deviation"] == -2
    check_deviation_flag(low_stats["deviation_flag"], "under_quota", "low", 2)

    # Team-level assertions
    assert team_stats is not None
    assert team_stats["total_employees"] == 2
    assert team_stats["high_experience_count"] == 1
    assert team_stats["low_experience_count"] == 1
    assert team_stats["total_shifts_assigned"] == 23
    assert team_stats["quota_violations"] == 2
    assert len(team_stats["high_severity_deviations"]) == 1
    assert len(team_stats["medium_severity_deviations"]) == 0
    assert len(team_stats["low_severity_deviations"]) == 1
    assert team_stats["high_severity_deviations"][0]["employee_name"] == "EmpHigh"
    assert sorted(team_stats["under_quota_employees"]) == ["EmpHigh", "EmpLow"]
    assert team_stats["over_quota_employees"] == []


def test_deviation_over_quota(data_manager):
    """
    Test for over-quota case.
    """
    month_key = "2025-09"
    emp = data_manager.add_employee("EmpOver", "High")
    # Assign 28 shifts (over 24 quota)
    schedule = {}
    for day in range(1, 15):
        key = f"2025-09-{day:02d}"
        schedule[key] = {
            "day_shift": {"employee_id": emp.id, "is_manual": False},
            "night_shift": {"employee_id": emp.id, "is_manual": False},
        }
    data_manager.save_schedule(month_key, schedule)
    stats = data_manager.calculate_employee_stats(month_key)
    flag = stats["EmpOver"]["deviation_flag"]

    units_in_flag = flag["deviation_units"]
    assert units_in_flag > 0
    assert f"over quota by {units_in_flag} units" in flag["description"]
    assert flag["deviation_type"] == "over_quota"
    assert flag["severity"] == "high"


def test_empty_schedule(data_manager):
    """
    Check no error on empty schedule/stat calculation.
    """
    month_key = "2026-01"
    emp_stats = data_manager.calculate_employee_stats(month_key)
    assert emp_stats == {}


def test_broken_data_raises(tmp_path):
    """
    Test that malformed file raises validation error (pipeline reliability).
    Accepts DataFileCorruptedError because code now raises it if both main and backup fail.
    """
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json }")
    with pytest.raises((DataValidationError, DataFileCorruptedError)):
        DataManager(str(bad))
