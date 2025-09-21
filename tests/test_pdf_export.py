import pytest
import sys
from pathlib import Path
import tempfile
import os
import json

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shift_scheduler.data_manager import DataManager
from shift_scheduler.reporting import ExportManager


@pytest.fixture
def data_manager():
    """Fixture for a DataManager instance with actual temp file (safe for tests)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tempfile_obj:
        temp_path = tempfile_obj.name
        # Begin with a minimal valid object
        tempfile_obj.write("{}")
    dm = DataManager(temp_path)
    # Seed with one employee and a schedule row
    emp = dm.add_employee("Alice", "High")
    dm.save_schedule(
        "2025-08",
        {
            "2025-08-01": {
                "day_shift": {"employee_id": emp.id, "is_manual": False},
                "night_shift": None,
            }
        },
    )
    yield dm
    os.unlink(temp_path)


@pytest.fixture
def export_manager(data_manager):
    """Fixture for an ExportManager instance."""
    return ExportManager(data_manager)


def test_pdf_export_basic(export_manager):
    """Test PDF export works on valid seeded data."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpfile:
        output_path = tmpfile.name
    success = export_manager.export_calendar(2025, 8, "pdf", output_path)
    assert success
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 200  # Allowing header + minimal table
    os.unlink(output_path)


def test_pdf_export_no_schedule(export_manager):
    """Test PDF export on month with no schedule returns success, but file may be minimal."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpfile:
        output_path = tmpfile.name
    # Try exporting a month without schedule data
    success = export_manager.export_calendar(2020, 1, "pdf", output_path)
    assert success
    assert os.path.exists(output_path)
    os.unlink(output_path)


def test_pdf_export_bad_path(export_manager):
    """Test PDF export failure if path is unwritable (should not throw, just return False)."""
    # Intentionally use an unwritable location, likely to raise
    result = export_manager.export_calendar(
        2025, 8, "pdf", "/not_a_dir/this_file_should_fail.pdf"
    )
    assert result is False


def test_excel_export_basic(export_manager):
    """
    Why this is important: Ensures the Excel export functionality works
    without crashing and produces a valid file.
    """
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmpfile:
        output_path = tmpfile.name

    success = export_manager.export_calendar(2025, 8, "excel", output_path)

    assert success
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
    os.unlink(output_path)


def test_csv_export_basic(export_manager):
    """
    Why this is important: Ensures the CSV export functionality works
    without crashing and produces a valid file.
    """
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmpfile:
        output_path = tmpfile.name

    success = export_manager.export_calendar(2025, 8, "csv", output_path)

    assert success
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
    os.unlink(output_path)
