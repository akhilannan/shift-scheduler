import pytest
import sys
from pathlib import Path
import tempfile
import os
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shift_scheduler.data_manager import DataManager


@pytest.fixture
def data_manager():
    """Fixture for a clean, isolated DataManager instance for each test."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as temp_file:
        temp_path = temp_file.name
        json.dump({}, temp_file)

    dm = DataManager(temp_path)
    # Add a standard set of employees for consistent testing
    dm.add_employee("Alice", "High")
    dm.add_employee("Bob", "Low")
    yield dm
    os.unlink(temp_path)


def test_update_employee_name_updates_quotas(data_manager):
    """
    Why this is important: If a user renames an employee, the system must update
    all related data. Otherwise, the old name would persist in the quotas,
    effectively breaking the link to that employee.
    """
    old_name = "Alice"
    new_name = "Alicia"
    alice = data_manager.get_employee_by_name(old_name)

    # Verify initial state
    quotas_31 = data_manager.get_quotas_for_month(31)
    assert old_name in quotas_31
    assert new_name not in quotas_31

    # Perform the update
    data_manager.update_employee(alice.id, name=new_name)
    data_manager.save_data()

    # Verify the change was propagated to quotas
    reloaded_dm = DataManager(data_manager.data_file)
    new_quotas_31 = reloaded_dm.get_quotas_for_month(31)
    assert old_name not in new_quotas_31
    assert new_name in new_quotas_31


def test_update_employee_experience_recalculates_quotas(data_manager):
    """
    Why this is important: An employee's experience level is a core business
    rule that directly impacts their shift quota. This test ensures that when
    an employee is promoted (or demoted), their workload is automatically
    adjusted according to the rules in the BRD.
    """
    bob = data_manager.get_employee_by_name("Bob")
    assert bob.experience == "Low"

    # Check initial quota for a 31-day month (Low experience)
    assert data_manager.get_quotas_for_month(31)["Bob"] == 21

    # Update experience to High
    data_manager.update_employee(bob.id, experience="High")

    # Verify quota was automatically updated
    assert data_manager.get_quotas_for_month(31)["Bob"] == 24


def test_delete_employee_removes_all_data(data_manager):
    """
    Why this is important: When an employee is deleted, all their associated
    data must be scrubbed from the system to prevent data clutter and potential
    errors where the application tries to reference a non-existent user.
    """
    bob = data_manager.get_employee_by_name("Bob")

    # Ensure Bob exists in quotas
    assert "Bob" in data_manager.get_quotas_for_month(31)

    # Delete Bob
    data_manager.delete_employee(bob.id)
    data_manager.save_data()

    # Reload and verify deletion
    reloaded_dm = DataManager(data_manager.data_file)
    assert reloaded_dm.get_employee_by_id(bob.id) is None
    assert "Bob" not in reloaded_dm.get_quotas_for_month(31)


def test_data_migration_offdays_to_offshifts(tmp_path):
    """
    Why this is important: This test ensures backward compatibility. If you
    release a new version of the application, this logic prevents data loss
    for users upgrading from an older version that used a different data format.
    """
    old_data_file = tmp_path / "old_data.json"

    # Manually create a data file using the old "offDays" format
    old_data_content = {
        "employees": [
            {
                "id": 1,
                "name": "OldUser",
                "isActive": True,
                "experience": "High",
                "preferences": {"offDays": ["2025-01-10"]},
            }
        ]
    }
    old_data_file.write_text(json.dumps(old_data_content))

    # Initialize DataManager with the old file format
    dm = DataManager(str(old_data_file))

    # Verify that the old data was correctly migrated to the new format
    migrated_user = dm.get_employee_by_name("OldUser")
    prefs = migrated_user.preferences

    # The single "offDay" should have been converted to two "off_shifts"
    expected_off_shifts = {("2025-01-10", "day"), ("2025-01-10", "night")}
    assert set(prefs.off_shifts) == expected_off_shifts
