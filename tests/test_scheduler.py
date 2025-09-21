"""
Test Suite for Shift Scheduler Logic and Data Manager

Covers the backtracking algorithm, constraint validation,
experience-based scheduling, and data management.
"""

import pytest
from datetime import date
import sys
from pathlib import Path
import tempfile
import os
import json

# Setup import path for src
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shift_scheduler.data_manager import DataManager, Employee
from shift_scheduler.scheduler_logic import ShiftScheduler, ConstraintViolation


@pytest.fixture
def data_manager():
    """Clean DataManager for each test - isolated temp file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp:
        temp_path = temp.name
        json.dump({}, temp)
    dm = DataManager(temp_path)
    # Standard test employee set
    dm.add_employee("Alice", "High", True)
    dm.add_employee("Bob", "High", True)
    dm.add_employee("Charlie", "Low", True)
    dm.add_employee("Diana", "Low", True)
    yield dm
    os.unlink(temp_path)


@pytest.fixture
def scheduler(data_manager):
    """Clean ShiftScheduler instance for each test."""
    return ShiftScheduler(data_manager)


def test_employee_creation(data_manager):
    """Employee creation and info."""
    employees = data_manager.get_employees()
    assert len(employees) == 4
    alice = data_manager.get_employee_by_name("Alice")
    assert alice and alice.experience == "High" and alice.is_active


def test_quota_management(data_manager):
    """Default quotas + custom overwrite."""
    quotas_31 = data_manager.get_quotas_for_month(31)
    assert quotas_31.get("Alice", 0) > 0
    quotas_28 = data_manager.get_quotas_for_month(28)
    assert quotas_28.get("Charlie", 0) > 0
    data_manager.set_quota("Alice", 31, 26)
    assert data_manager.get_quotas_for_month(31)["Alice"] == 26


def test_absence_tracking(data_manager):
    """Test adding/removing absences."""
    alice = data_manager.get_employee_by_name("Alice")
    data_manager.add_absence(alice.id, "2024-01-15")
    assert data_manager.is_employee_absent(alice.id, "2024-01-15")
    data_manager.remove_absence(alice.id, "2024-01-15")
    assert not data_manager.is_employee_absent(alice.id, "2024-01-15")


@pytest.mark.parametrize(
    "shift_type, schedule, expect_violation",
    [
        ("day_shift", {"2024-01-15": {"day_shift": 1, "night_shift": None}}, None),
        (
            "night_shift",
            {"2024-01-15": {"day_shift": 1, "night_shift": None}},
            ConstraintViolation.SAME_DAY_CONFLICT,
        ),
        (
            "day_shift",
            {
                "2024-01-14": {"day_shift": None, "night_shift": 1},
                "2024-01-15": {"day_shift": None, "night_shift": None},
            },
            ConstraintViolation.POST_NIGHT_CONFLICT,
        ),
    ],
)
def test_constraint_validation(scheduler, shift_type, schedule, expect_violation):
    """Parameterized check for scheduling rules: same day/night conflict, post night rest."""
    alice = scheduler.data_manager.get_employee_by_name("Alice")
    violations = scheduler.validate_manual_assignment(
        alice.id, "2024-01-15", shift_type, schedule
    )
    if expect_violation:
        assert expect_violation in violations
    else:
        assert not violations


def test_absence_constraint_validation(scheduler):
    """Scheduling should flag violation if employee absent."""
    alice = scheduler.data_manager.get_employee_by_name("Alice")
    scheduler.data_manager.add_absence(alice.id, "2024-01-15")
    violations = scheduler.validate_manual_assignment(
        alice.id, "2024-01-15", "day_shift", {}
    )
    assert ConstraintViolation.ABSENCE in violations


def test_schedule_generation_and_statistics(scheduler):
    """Test schedule generation for small month and check stats."""
    # February 2024, leap year - 29 days
    result = scheduler.generate_schedule(2024, 2, allow_quota_violations=True)
    assert result.success and result.schedule
    assert len(result.schedule) == 29
    assert hasattr(result, "statistics")


def test_experience_based_allocation_with_emergency(scheduler):
    """High experience employees get more shifts during emergencies."""
    result = scheduler.generate_schedule(
        2024, 1, allow_quota_violations=True, emergency_mode=True
    )
    assert result.success
    stats = result.statistics
    highs = [data for data in stats.values() if data["experience"] == "High"]
    lows = [data for data in stats.values() if data["experience"] == "Low"]
    if highs and lows:
        avg_high = sum(p["total_shifts"] for p in highs) / len(highs)
        avg_low = sum(p["total_shifts"] for p in lows) / len(lows)
        assert avg_high >= avg_low


def test_schedule_statistics_manual(scheduler):
    """Check stats calc utility."""
    test_schedule = {
        "2024-01-01": {"day_shift": 1, "night_shift": 2},
        "2024-01-02": {"day_shift": 3, "night_shift": 4},
        "2024-01-03": {"day_shift": 1, "night_shift": None},
    }
    stats = scheduler.get_schedule_statistics(test_schedule, "2024-01")
    assert stats["total_shifts"] == 6  # 3 days * 2 shifts
    assert stats["day_shifts"] == 3
    assert stats["night_shifts"] == 2
    assert stats["unassigned_shifts"] == 1


def test_scheduler_empty_inputs():
    """Edge case: handle with no employees safely (pipeline edge-case)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as temp:
        temp_path = temp.name
        json.dump({}, temp)
    dm = DataManager(temp_path)
    scheduler = ShiftScheduler(dm)
    result = scheduler.generate_schedule(2024, 1, allow_quota_violations=True)
    assert not result.success or not result.schedule  # Should not crash
    os.unlink(temp_path)


def test_schedule_generation_fails_gracefully_when_infeasible(scheduler, data_manager):
    """
    Why this is important: The scheduler must not crash or enter an infinite
    loop if the user provides constraints that make a solution impossible.
    This test ensures it fails gracefully and informs the user.
    """
    # Get all 4 employees
    employees = data_manager.get_employees()

    # Make a schedule impossible by having most employees absent
    for i, emp in enumerate(employees):
        if i < 3:  # Make the first 3 employees absent for the whole month
            for day in range(1, 32):
                date_str = f"2025-01-{day:02d}"
                data_manager.add_absence(emp.id, date_str)

    # Attempt to generate the schedule
    result = scheduler.generate_schedule(2025, 1)

    # An impossible schedule should not succeed
    assert not result.success
    assert "Failed" in result.message
