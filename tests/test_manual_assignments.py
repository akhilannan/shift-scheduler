import pytest
from datetime import date
from pathlib import Path
import sys
import tempfile
import os
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shift_scheduler.data_manager import DataManager, EmployeePreferences
from shift_scheduler.scheduler_logic import ShiftScheduler, ConstraintViolation

@pytest.fixture
def data_manager():
    """Fixture for a clean DataManager instance for each test."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
        temp_path = temp_file.name
        json.dump({}, temp_file)
    
    dm = DataManager(temp_path)
    # Add enough employees for a feasible schedule
    dm.add_employee("TestHigh", "High", True)
    dm.add_employee("TestLow", "Low", True)
    dm.add_employee("Emp3", "High", True)
    dm.add_employee("Emp4", "Low", True)
    yield dm
    os.unlink(temp_path)

@pytest.fixture
def scheduler(data_manager):
    """Fixture for a ShiftScheduler instance."""
    return ShiftScheduler(data_manager)

def test_set_manual_assignment(data_manager):
    """Tests that a manual assignment is correctly saved and persisted."""
    month_key = "2025-01"
    date_str = "2025-01-01"
    emp1 = data_manager.get_employee_by_name("TestHigh")
    data_manager.set_shift_assignment(month_key, date_str, "day_shift", emp1.id, is_manual=True)
    data_manager.save_data()
    
    # Reload and check
    reloaded = DataManager(data_manager.data_file)
    schedule = reloaded.get_schedule(month_key)
    shift_info = schedule[date_str]["day_shift"]
    
    assert isinstance(shift_info, dict)
    assert shift_info["employee_id"] == emp1.id
    assert shift_info["is_manual"]
    assert reloaded.is_manual_assignment(month_key, date_str, "day_shift")

def test_partial_generation_respects_manual(scheduler):
    """Tests that partial generation does not overwrite existing manual assignments."""
    month_key = "2025-08"
    date_str = "2025-08-15"
    emp1 = scheduler.data_manager.get_employee_by_name("TestHigh")
    # Set manual assignment
    scheduler.data_manager.set_shift_assignment(month_key, date_str, "day_shift", emp1.id, is_manual=True)
    
    # Generate partial (simulate ongoing month)
    result = scheduler.generate_schedule(2025, 8, partial_generation=True)
    assert result.success, f"Generation failed: {result.message}"
    
    # Check manual assignment is preserved
    schedule = scheduler.data_manager.get_schedule(month_key)
    shift_info = schedule[date_str]["day_shift"]
    
    assert isinstance(shift_info, dict)
    assert shift_info["employee_id"] == emp1.id
    assert shift_info["is_manual"]

def test_full_generation_overwrites_manual(scheduler):
    """Tests that a full generation overwrites all previous assignments, including manual ones."""
    month_key = "2025-09"
    date_str = "2025-09-01"
    emp1 = scheduler.data_manager.get_employee_by_name("TestHigh")
    scheduler.data_manager.set_shift_assignment(month_key, date_str, "day_shift", emp1.id, is_manual=True)
    
    # Generate full schedule
    result = scheduler.generate_schedule(2025, 9, partial_generation=False)
    assert result.success, f"Generation failed: {result.message}"
    
    # Check that the assignment on that date is no longer marked as manual
    schedule = scheduler.data_manager.get_schedule(month_key)
    shift_info = schedule[date_str]["day_shift"]
    
    assert isinstance(shift_info, dict)
    assert not shift_info["is_manual"]

def test_manual_assignment_validation(scheduler, data_manager):
    """
    Tests the validation logic for manual assignments to ensure business rules
    are correctly enforced before an assignment is made.
    """
    emp_high = data_manager.get_employee_by_name("TestHigh")
    date_str = "2025-10-10"
    prev_date_str = "2025-10-09"
    next_date_str = "2025-10-11"

    # Scenario 1: VALID assignment
    violations = scheduler.validate_manual_assignment(emp_high.id, date_str, "day_shift", {})
    assert not violations, "A valid assignment should have no violations."

    # Scenario 2: Assigning on an off-shift
    preferences = EmployeePreferences(off_shifts=[(date_str, "day")])
    data_manager.update_employee(emp_high.id, preferences=preferences)
    violations = scheduler.validate_manual_assignment(emp_high.id, date_str, "day_shift", {})
    assert ConstraintViolation.OFF_DAY in violations

    # RESET preferences for next scenario to ensure isolation
    data_manager.update_employee(emp_high.id, preferences=EmployeePreferences())

    # Scenario 3: Same-day conflict (day shift already assigned)
    current_schedule = {
        date_str: {"day_shift": {"employee_id": emp_high.id, "is_manual": False}}
    }
    violations = scheduler.validate_manual_assignment(emp_high.id, date_str, "night_shift", current_schedule)
    assert ConstraintViolation.SAME_DAY_CONFLICT in violations

    # RESET preferences for next scenario
    data_manager.update_employee(emp_high.id, preferences=EmployeePreferences())
    
    # Scenario 4: Post-night shift conflict (trying to assign shift day after night shift)
    current_schedule = {
        prev_date_str: {"night_shift": {"employee_id": emp_high.id, "is_manual": False}}
    }
    violations = scheduler.validate_manual_assignment(emp_high.id, date_str, "day_shift", current_schedule)
    assert ConstraintViolation.POST_NIGHT_CONFLICT in violations

    # RESET preferences for next scenario
    data_manager.update_employee(emp_high.id, preferences=EmployeePreferences())

    # Scenario 5: Next-day conflict (trying to assign night shift before another shift)
    current_schedule = {
        next_date_str: {"day_shift": {"employee_id": emp_high.id, "is_manual": False}}
    }
    violations = scheduler.validate_manual_assignment(emp_high.id, date_str, "night_shift", current_schedule)
    assert f"{ConstraintViolation.NEXT_DAY_CONFLICT} (next day's day shift)" in violations