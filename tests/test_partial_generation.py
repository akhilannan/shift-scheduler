import pytest
import sys
from pathlib import Path
from datetime import date, timedelta
import json
import tempfile
import os
import calendar  # Import the calendar module

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shift_scheduler.data_manager import DataManager
from shift_scheduler.scheduler_logic import ShiftScheduler

@pytest.fixture
def data_manager():
    """Fixture for a clean DataManager instance with enough employees for feasible schedules."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
        temp_path = temp_file.name
        json.dump({}, temp_file)
    
    dm = DataManager(temp_path)
    dm.add_employee("Emp1", "High", True)
    dm.add_employee("Emp2", "Low", True)
    dm.add_employee("Emp3", "High", True)
    dm.add_employee("Emp4", "Low", True)
    yield dm
    os.unlink(temp_path)

@pytest.fixture
def scheduler(data_manager):
    """Fixture for a ShiftScheduler instance."""
    return ShiftScheduler(data_manager)

def test_partial_generation_for_current_month(scheduler, data_manager):
    """
    Tests partial generation for the current month.
    Verifies that it preserves filled past shifts, fills in empty past shifts,
    and generates schedules for all future dates.
    """
    today = date.today()
    # Ensure the test runs correctly even at the start or end of a month
    if today.day < 3:
        pytest.skip("Skipping test, too early in the month for a robust partial generation test.")
    
    month_key = f"{today.year}-{today.month:02d}"
    
    # Setup: Create a schedule for the current month with some assignments
    emp1 = data_manager.get_employee_by_name("Emp1")
    preserved_date_str = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    empty_date_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # This assignment should be preserved
    data_manager.set_shift_assignment(month_key, preserved_date_str, "day_shift", emp1.id, is_manual=True)
    # This empty shift (from yesterday) should be filled
    data_manager.set_shift_assignment(month_key, empty_date_str, "day_shift", None, is_manual=False)

    # Action: Run partial generation
    result = scheduler.generate_schedule(today.year, today.month, partial_generation=True)
    
    # Assertions
    assert result.success, f"Partial generation failed: {result.message}"
    
    schedule = data_manager.get_schedule(month_key)
    
    # Verify the manually assigned past shift was preserved
    preserved_shift = schedule.get(preserved_date_str, {}).get("day_shift")
    assert preserved_shift is not None, "Preserved shift should not be None."
    assert preserved_shift.get("employee_id") == emp1.id, "Manually assigned past shift was changed."
    
    # Verify the empty past shift was filled
    filled_shift = schedule.get(empty_date_str, {}).get("day_shift")
    assert filled_shift is not None, "Empty past shift was not filled."
    assert filled_shift.get("employee_id") is not None, "Empty past shift should now have an employee."

    # Verify a future shift was filled
    future_date_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if future_date_str in schedule: # Check if today is not the last day of the month
        future_shift = schedule.get(future_date_str, {}).get("day_shift")
        assert future_shift is not None, "Future shift was not filled."
        assert future_shift.get("employee_id") is not None, "Future shift should have an employee."

def test_partial_generation_falls_back_to_full_for_future_month(scheduler):
    """
    Tests that when partial generation is requested for a future month,
    it correctly performs a full schedule generation instead.
    """
    today = date.today()
    future_month = today.month + 1 if today.month < 12 else 1
    future_year = today.year if today.month < 12 else today.year + 1
    
    # Action
    result = scheduler.generate_schedule(future_year, future_month, partial_generation=True)
    
    # Assertions
    assert result.success, f"Generation for future month failed: {result.message}"
    assert "partial schedule" not in result.message.lower(), "Message should not indicate partial generation for a future month."
    
    # Check if the entire schedule is filled
    schedule = result.schedule
    # CORRECTED: Use calendar.monthrange for a reliable day count
    days_in_month = calendar.monthrange(future_year, future_month)[1]
    assert len(schedule) == days_in_month, "Schedule should be generated for the full month."

def test_partial_generation_fills_gaps_in_past_month(scheduler, data_manager):
    """
    Tests using partial generation to fill gaps in a completed past month
    without altering existing assignments.
    """
    past_year, past_month = (2024, 10)
    month_key = f"{past_year}-{past_month:02d}"
    
    emp1 = data_manager.get_employee_by_name("Emp1")
    
    # Setup: A past month's schedule with a preserved shift and a gap
    preserved_date = "2024-10-05"
    gap_date = "2024-10-06"
    
    data_manager.set_shift_assignment(month_key, preserved_date, "day_shift", emp1.id, is_manual=True)
    data_manager.set_shift_assignment(month_key, gap_date, "day_shift", None, is_manual=False) # This is the gap
    
    # Action
    result = scheduler.generate_schedule(past_year, past_month, partial_generation=True)
    
    # Assertions
    assert result.success, f"Gap-filling generation failed: {result.message}"
    
    schedule = data_manager.get_schedule(month_key)
    
    # Verify the existing shift was preserved
    preserved_shift = schedule.get(preserved_date, {}).get("day_shift")
    assert preserved_shift is not None
    assert preserved_shift.get("employee_id") == emp1.id
    
    # Verify the gap was filled
    filled_gap = schedule.get(gap_date, {}).get("day_shift")
    assert filled_gap is not None, "Gap was not filled."
    assert filled_gap.get("employee_id") is not None, "Gap should now have an employee."