"""
Tests for enforcement of employee preferences (off-shifts and preferred shift types)
in shift schedule generation.
"""

import pytest
from pathlib import Path
import sys
import tempfile
import os
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shift_scheduler.data_manager import DataManager, EmployeePreferences
from shift_scheduler.scheduler_logic import ShiftScheduler

@pytest.fixture
def data_manager():
    """Fixture for a clean DataManager instance for each test."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
        temp_path = temp_file.name
        json.dump({}, temp_file)

    dm = DataManager(temp_path)
    # Add basic employees for fallback
    dm.add_employee("emp1", "High")
    dm.add_employee("emp2", "Low")
    dm.add_employee("emp3", "High")
    dm.add_employee("emp4", "Low")
    yield dm
    os.unlink(temp_path)

@pytest.fixture
def scheduler(data_manager):
    """Fixture for a ShiftScheduler instance."""
    return ShiftScheduler(data_manager)

@pytest.mark.parametrize(
    "off_shifts, preferred_types, check_night, should_fail",
    [
        (
            [("2025-08-15", "day"), ("2025-08-15", "night"), ("2025-08-20", "day"), ("2025-08-20", "night")],
            ["day"],
            True,
            True,  # Should never assign night shift if only prefers day
        ),
        (
            [("2025-08-15", "day"), ("2025-08-20", "day")],
            ["both"],
            False,
            False,  # Can do both shifts, so only off-day really matters
        ),
    ]
)
def test_employee_preferences_enforced(data_manager, scheduler, off_shifts, preferred_types, check_night, should_fail):
    """
    Test that employee shift preferences and off-shifts are enforced:
    - Not scheduled for off-shifts
    - Not given non-preferred shift types
    """
    test_preferences = EmployeePreferences(
        off_shifts=off_shifts,
        preferred_shift_types=preferred_types,
        availability_notes="Test employee preference scenario"
    )
    test_employee = data_manager.add_employee("TestEmployee", "High", True, preferences=test_preferences)
    result = scheduler.generate_schedule(2025, 8)
    assert result.success, "Schedule generation should succeed with enough employees"

    schedule = result.schedule
    for datestr, dayschedule in schedule.items():
        # Check explicit off-shifts
        for off_date, off_type in off_shifts:
            if datestr == off_date:
                shift_id = dayschedule.get(f"{off_type}_shift")
                assert shift_id != test_employee.id, f"TestEmployee assigned to off-shift ({off_type}) on {datestr}"

        # Check preferred shift types (should not assign night if only prefers day)
        if check_night and dayschedule.get("night_shift") == test_employee.id:
            pytest.fail(f"TestEmployee assigned to non-preferred night shift on {datestr}")

def test_off_day_enforced(data_manager, scheduler):
    """
    If both shifts on a date are in 'off_shifts', treat it as an off-day: no assignment at all for that day.
    """
    test_preferences = EmployeePreferences(
        off_shifts=[("2025-08-15", "day"), ("2025-08-15", "night")],
        preferred_shift_types=["day", "night"]
    )
    test_employee = data_manager.add_employee("PrefersOffDay", "High", True, preferences=test_preferences)
    result = scheduler.generate_schedule(2025, 8)
    assert result.success
    schedule = result.schedule

    for date_str, day_schedule in schedule.items():
        if date_str == "2025-08-15":
            assert day_schedule.get("day_shift") != test_employee.id
            assert day_schedule.get("night_shift") != test_employee.id

