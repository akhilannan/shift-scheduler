"""
Data Manager for Shift Scheduling System

Handles all file I/O operations, JSON persistence, and CRUD operations
for employees, quotas, schedules, and application settings.
"""

import json
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path
from calendar import monthrange
import calendar


class DataManagerError(Exception):
    """Base exception for DataManager operations"""
    pass


class DataFileCorruptedError(DataManagerError):
    """Raised when the data file is corrupted"""
    pass


class DataFileNotFoundError(DataManagerError):
    """Raised when the data file is not found"""
    pass


class DataSaveError(DataManagerError):
    """Raised when saving data fails"""
    pass


class DataValidationError(DataManagerError):
    """Raised when data validation fails"""
    pass


@dataclass
class ExperienceBucket:
    """Experience bucket configuration for dynamic quota allocation"""
    experience_level: str  # "High" or "Low"
    target_shifts: Dict[str, int] = field(default_factory=dict)  # {month_length: total_target_shifts}
    distribution_method: str = "equal"  # "equal", "weighted", or "proportional"
    weight_factors: Dict[str, float] = field(default_factory=dict)  # {employee_name: weight} for weighted distribution

@dataclass
class DeviationFlag:
    """Deviation flag for quota violations"""
    employee_name: str
    deviation_type: str  # "over_quota", "under_quota", "exact"
    deviation_units: int  # Positive for over, negative for under
    severity: str  # "low", "medium", "high"
    description: str

@dataclass
class EmployeePreferences:
    """Employee preferences for scheduling"""
    off_shifts: List[Tuple[str, str]] = field(default_factory=list)  # List of (date_str, shift_type) tuples
    preferred_shift_types: List[str] = field(default_factory=lambda: ["both"])  # ["day", "night", "both"]
    custom_quotas: Dict[str, int] = field(default_factory=dict)  # {month_length: quota} e.g., {"31": 25}
    availability_notes: str = ""  # Additional notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "offShifts": [(date, shift) for date, shift in self.off_shifts],
            "preferredShiftTypes": self.preferred_shift_types,
            "customQuotas": self.custom_quotas,
            "availabilityNotes": self.availability_notes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmployeePreferences':
        # Handle backward compatibility for old "offDays" format
        off_shifts = []
        if "offShifts" in data:
            # New format: list of [date, shift] pairs
            off_shifts = [(item[0], item[1]) for item in data.get("offShifts", [])]
        elif "offDays" in data:
            # Old format: list of date strings - convert to both shifts off
            off_days = data.get("offDays", [])
            for date_str in off_days:
                off_shifts.extend([(date_str, "day"), (date_str, "night")])

        return cls(
            off_shifts=off_shifts,
            preferred_shift_types=data.get("preferredShiftTypes", ["both"]),
            custom_quotas=data.get("customQuotas", {}),
            availability_notes=data.get("availabilityNotes", "")
        )


@dataclass
class Employee:
    """Employee data structure with experience level and preferences"""
    id: int
    name: str
    is_active: bool
    experience: str  # "High" or "Low"
    preferences: EmployeePreferences

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "isActive": self.is_active,
            "experience": self.experience,
            "preferences": self.preferences.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Employee':
        return cls(
            id=data["id"],
            name=data["name"],
            is_active=data.get("isActive", True),
            experience=data.get("experience", "Low"),
            preferences=EmployeePreferences.from_dict(data.get("preferences", {}))
        )


class DataManager:
    """Manages all data persistence and CRUD operations"""
    
    def __init__(self, data_file: str = "data/schedule_data.json"):
        if data_file == "data/schedule_data.json":
            # Use path relative to the package directory
            data_file = Path(__file__).parent.parent / "data" / "schedule_data.json"
        self.data_file = Path(data_file)
        self.data = self._load_or_create_data()
    
    def _load_or_create_data(self) -> Dict[str, Any]:
        """Load existing data or create default structure with recovery from backup"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Ensure all required sections exist
                    return self._validate_and_migrate_data(data)
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Error loading main data file {self.data_file}: {e}")
                # Try to recover from backup
                backup_file = self.data_file.with_suffix('.bak')
                if backup_file.exists():
                    try:
                        logging.info(f"Attempting recovery from backup file {backup_file}")
                        with open(backup_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            # Restore backup to main file
                            backup_file.replace(self.data_file)
                            logging.info(f"Successfully recovered data from backup")
                            return self._validate_and_migrate_data(data)
                    except (json.JSONDecodeError, IOError) as backup_e:
                        logging.error(f"Backup file also corrupted: {backup_e}")
                        logging.info(f"Creating default data due to corrupted files")
                        return self._create_default_data()
                else:
                    raise DataFileCorruptedError(f"Main data file corrupted and no backup available: {e}")
        else:
            # Check if backup exists to recover from
            backup_file = self.data_file.with_suffix('.bak')
            if backup_file.exists():
                try:
                    logging.info(f"Main data file missing, attempting recovery from backup {backup_file}")
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Restore backup to main file
                        backup_file.replace(self.data_file)
                        logging.info(f"Successfully recovered data from backup")
                        return self._validate_and_migrate_data(data)
                except (json.JSONDecodeError, IOError) as backup_e:
                    logging.error(f"Backup file corrupted: {backup_e}")
                    logging.info(f"Creating default data due to corrupted backup")
                    return self._create_default_data()
            else:
                logging.info(f"No data file found, creating default data")
                return self._create_default_data()
    
    def _validate_and_migrate_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and migrate data structure to current version"""
        default_data = self._create_default_data()

        # Merge with defaults to ensure all keys exist
        for key in default_data:
            if key not in data:
                data[key] = default_data[key]

        # Ensure employees have experience field and preferences
        for emp in data.get("employees", []):
            if "experience" not in emp:
                emp["experience"] = "Low"
            if "preferences" not in emp:
                emp["preferences"] = EmployeePreferences().to_dict()

        # Ensure experience buckets exist
        if "experience_buckets" not in data:
            data["experience_buckets"] = {
                "High": {
                    "experience_level": "High",
                    "target_shifts": {"28": 44, "29": 44, "30": 46, "31": 48},
                    "distribution_method": "equal",
                    "weight_factors": {}
                },
                "Low": {
                    "experience_level": "Low",
                    "target_shifts": {"28": 18, "29": 21, "30": 21, "31": 21},
                    "distribution_method": "equal",
                    "weight_factors": {}
                }
            }

        return data
    
    def _create_default_data(self) -> Dict[str, Any]:
        """Create default data structure with sample employees"""
        return {
            "settings": {
                "appVersion": "1.0.0",
                "lastUsedMonth": datetime.now().strftime("%Y-%m"),
                "dataFile": str(self.data_file)
            },
            "employees": [],
            "experience_buckets": {
                "High": {
                    "experience_level": "High",
                    "target_shifts": {},
                    "distribution_method": "equal",
                    "weight_factors": {}
                },
                "Low": {
                    "experience_level": "Low",
                    "target_shifts": {},
                    "distribution_method": "equal",
                    "weight_factors": {}
                }
            },
            "quotas": {
                "31": {},
                "30": {},
                "29": {},
                "28": {}
            },
            "absences": {},  # {employee_id: [date_strings]}
            "schedules": {},  # {month_key: {date: {day_shift: emp_id, night_shift: emp_id}}}
            "manual_adjustments": {},  # Track manual changes
            "statistics": {}  # Cached stats for performance
        }

    def _validate_saved_data(self) -> bool:
        """Validate that the saved data file matches current data"""
        try:
            if not self.data_file.exists():
                raise DataFileNotFoundError(f"Saved data file {self.data_file} does not exist")

            with open(self.data_file, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)

            # Check required sections exist
            required_keys = ["settings", "employees", "experience_buckets", "quotas", "absences", "schedules"]
            for key in required_keys:
                if key not in saved_data:
                    raise DataValidationError(f"Required section '{key}' missing from saved data")

            # Check settings version
            if saved_data.get("settings", {}).get("appVersion") != self.data.get("settings", {}).get("appVersion"):
                raise DataValidationError("App version mismatch in saved data")

            return True

        except (json.JSONDecodeError, IOError) as e:
            raise DataValidationError(f"Failed to validate saved data: {e}")

    def _prepare_data_for_json(self) -> Dict[str, Any]:
        """Prepare data for JSON serialization by converting objects to dicts"""
        prepared_data = self.data.copy()

        # Convert DeviationFlag objects in statistics to dicts
        if "statistics" in prepared_data:
            for month_key, stats_data in prepared_data["statistics"].items():
                if "deviation_flags" in stats_data:
                    deviation_flags = stats_data["deviation_flags"]
                    prepared_flags = []
                    for flag in deviation_flags:
                        if hasattr(flag, '__dataclass_fields__'):
                            prepared_flags.append(asdict(flag))
                        else:
                            prepared_flags.append(flag)
                    stats_data["deviation_flags"] = prepared_flags

        return prepared_data

    def save_data(self) -> bool:
        """Save current data to file atomically with validation"""
        temp_file = None
        backup_file = self.data_file.with_suffix('.bak')

        try:
            # Create backup of existing file if it exists
            if self.data_file.exists():
                self.data_file.replace(backup_file)

            # Write to temporary file first (atomic operation)
            temp_file = self.data_file.with_suffix('.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self._prepare_data_for_json(), f, indent=2, ensure_ascii=False)

            # Atomic rename: move temp file to final location
            temp_file.replace(self.data_file)

            # Validate the saved data
            self._validate_saved_data()

            return True

        except DataValidationError as e:
            logging.error(f"Data validation failed after save: {e}", exc_info=True)
            # Try to restore from backup
            if backup_file.exists():
                try:
                    backup_file.replace(self.data_file)
                except Exception as restore_e:
                    logging.error(f"Failed to restore from backup: {restore_e}", exc_info=True)
            raise DataSaveError(f"Save operation failed validation: {e}")

        except (IOError, OSError) as e:
            logging.error(f"I/O error during save operation: {e}", exc_info=True)
            raise DataSaveError(f"Failed to save data due to I/O error: {e}")

        except Exception as e:
            logging.error(f"Unexpected error during save operation: {e}", exc_info=True)
            raise DataSaveError(f"Unexpected error during save: {e}")

        finally:
            # Clean up temp file if it still exists
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception as cleanup_e:
                    logging.error(f"Failed to clean up temporary file {temp_file}: {cleanup_e}", exc_info=True)
    
    # Employee Management
    def get_employees(self, active_only: bool = True) -> List[Employee]:
        """Get list of employees"""
        employees = []
        for emp_data in self.data.get("employees", []):
            emp = Employee.from_dict(emp_data)
            if not active_only or emp.is_active:
                employees.append(emp)
        return employees
    
    def get_employee_by_id(self, emp_id: int) -> Optional[Employee]:
        """Get employee by ID"""
        for emp_data in self.data.get("employees", []):
            if emp_data["id"] == emp_id:
                return Employee.from_dict(emp_data)
        return None
    
    def get_employee_by_name(self, name: str) -> Optional[Employee]:
        """Get employee by name"""
        for emp_data in self.data.get("employees", []):
            if emp_data["name"] == name:
                return Employee.from_dict(emp_data)
        return None
    
    def add_employee(self, name: str, experience: str = "Low", is_active: bool = True,
                    preferences: Optional[EmployeePreferences] = None) -> Employee:
        """Add new employee"""
        # Get next ID
        existing_ids = [emp["id"] for emp in self.data.get("employees", [])]
        next_id = max(existing_ids, default=0) + 1

        # Create employee
        if preferences is None:
            preferences = EmployeePreferences()

        employee = Employee(
            id=next_id,
            name=name,
            is_active=is_active,
            experience=experience,
            preferences=preferences
        )

        # Add to data
        self.data.setdefault("employees", []).append(employee.to_dict())

        # Add default quotas for all month lengths
        self._add_default_quotas_for_employee(name, experience)

        # Update bucket targets to maintain static per-employee quotas
        self._update_bucket_targets_for_experience(experience)

        # Redistribute quotas in the experience bucket
        for month_length in [28, 29, 30, 31]:
            self._redistribute_bucket_quotas(experience, month_length)

        return employee
    
    def update_employee(self, emp_id: int, name: str = None, experience: str = None,
                        is_active: bool = None, preferences: EmployeePreferences = None) -> bool:
        """Update employee information"""
        for emp_data in self.data.get("employees", []):
            if emp_data["id"] == emp_id:
                old_name = emp_data["name"]
                old_experience = emp_data["experience"]
                old_active = emp_data["isActive"]

                if name is not None:
                    emp_data["name"] = name
                if experience is not None:
                    emp_data["experience"] = experience
                if is_active is not None:
                    emp_data["isActive"] = is_active
                if preferences is not None:
                    emp_data["preferences"] = preferences.to_dict()

                # Update quotas if name or experience changed
                if name and name != old_name:
                    self._update_quotas_for_renamed_employee(old_name, name)
                if experience and experience != old_experience:
                    self._update_quotas_for_experience_change(emp_data["name"], experience)
                    # Update bucket targets for old and new experience levels
                    if old_experience:
                        self._update_bucket_targets_for_experience(old_experience)
                    self._update_bucket_targets_for_experience(experience)
                    # Redistribute in old and new buckets
                    for month_length in [28, 29, 30, 31]:
                        if old_experience:
                            self._redistribute_bucket_quotas(old_experience, month_length)
                        self._redistribute_bucket_quotas(experience, month_length)
                elif is_active is not None and is_active != old_active:
                    # Update bucket targets when active status changes
                    current_experience = experience or old_experience
                    self._update_bucket_targets_for_experience(current_experience)
                    # Redistribute when active status changes
                    for month_length in [28, 29, 30, 31]:
                        self._redistribute_bucket_quotas(current_experience, month_length)

                return True
        return False
    
    def delete_employee(self, emp_id: int) -> bool:
        """Delete employee (hard delete)"""
        employees = self.data.get("employees", [])
        employee_to_delete = None
        for emp in employees:
            if emp["id"] == emp_id:
                employee_to_delete = emp
                break

        if employee_to_delete:
            employees.remove(employee_to_delete)
            # Also remove any related data if necessary (e.g., quotas)
            for month_quotas in self.data.get("quotas", {}).values():
                if employee_to_delete["name"] in month_quotas:
                    del month_quotas[employee_to_delete["name"]]
            return True
        return False

    def get_employee_preferences(self, emp_id: int) -> Optional[EmployeePreferences]:
        """Get employee preferences"""
        emp = self.get_employee_by_id(emp_id)
        return emp.preferences if emp else None

    def update_employee_preferences(self, emp_id: int, preferences: EmployeePreferences) -> bool:
        """Update employee preferences"""
        return self.update_employee(emp_id, preferences=preferences)

    def is_employee_off_shift(self, emp_id: int, date_str: str, shift_type: str) -> bool:
        """Check if specific shift is off for employee"""
        prefs = self.get_employee_preferences(emp_id)
        if not prefs:
            return False
        return (date_str, shift_type) in prefs.off_shifts

    def is_employee_off_day(self, emp_id: int, date_str: str) -> bool:
        """Check if date is an off-day for employee (backward compatibility)"""
        prefs = self.get_employee_preferences(emp_id)
        if not prefs:
            return False
        # Check if both shifts are off for this date
        return (date_str, "day") in prefs.off_shifts and (date_str, "night") in prefs.off_shifts

    def get_employee_preferred_shift_types(self, emp_id: int) -> List[str]:
        """Get employee's preferred shift types"""
        prefs = self.get_employee_preferences(emp_id)
        return prefs.preferred_shift_types if prefs else ["both"]
    
    # Quota Management
    def get_quotas_for_month(self, days_in_month: int) -> Dict[str, int]:
        """Get quotas for specific month length using bucket system"""
        month_key = str(days_in_month)
        quotas = {}

        # Get quotas from bucket system
        for emp in self.get_employees(active_only=True):
            quota = self.get_bucket_quota_for_employee(emp.name, days_in_month)
            quotas[emp.name] = quota

        # Fallback to old system if no bucket quotas
        if not quotas:
            old_quotas = {
                31: {'high': 24, 'low': 21},
                30: {'high': 23, 'low': 21},
                29: {'high': 22, 'low': 21},
                28: {'high': 22, 'low': 18}
            }
            default_quotas = old_quotas.get(days_in_month, {})
            for emp in self.get_employees(active_only=True):
                quotas[emp.name] = default_quotas.get(emp.experience.lower(), 20)

        return quotas
    
    def set_quota(self, employee_name: str, days_in_month: int, quota: int):
        """Set quota for employee and month length"""
        month_key = str(days_in_month)
        if month_key not in self.data.setdefault("quotas", {}):
            self.data["quotas"][month_key] = {}
        self.data["quotas"][month_key][employee_name] = quota

        # Also set as custom quota in employee preferences
        emp = self.get_employee_by_name(employee_name)
        if emp:
            emp.preferences.custom_quotas[month_key] = quota
            # Update the employee data
            for emp_data in self.data.get("employees", []):
                if emp_data["name"] == employee_name:
                    emp_data["preferences"] = emp.preferences.to_dict()
                    break
    
    def get_default_quota_for_experience(self, experience: str, days_in_month: int) -> int:
        """Get default quota based on experience level and month length"""
        defaults = {
            "High": {28: 22, 29: 22, 30: 23, 31: 24},
            "Low": {28: 18, 29: 21, 30: 21, 31: 21}
        }
        return defaults.get(experience, defaults["Low"]).get(days_in_month, 20)
    
    def _add_default_quotas_for_employee(self, name: str, experience: str):
        """Add default quotas for new employee"""
        for days in [28, 29, 30, 31]:
            default_quota = self.get_default_quota_for_experience(experience, days)
            self.set_quota(name, days, default_quota)
    
    def _update_quotas_for_renamed_employee(self, old_name: str, new_name: str):
        """Update quotas when employee is renamed"""
        for month_quotas in self.data.get("quotas", {}).values():
            if old_name in month_quotas:
                month_quotas[new_name] = month_quotas.pop(old_name)
    
    def _update_quotas_for_experience_change(self, name: str, new_experience: str):
        """
        Update quotas when employee experience changes.
        This sets the new default quota as a custom quota to ensure it is respected
        during the subsequent bucket redistribution.
        """
        # Find the specific employee's data to update their preferences
        emp_data_to_update = None
        for emp_data in self.data.get("employees", []):
            if emp_data["name"] == name:
                emp_data_to_update = emp_data
                break

        if not emp_data_to_update:
            logging.warning(f"Could not find employee '{name}' to update experience-based quotas.")
            return

        # Ensure the preferences and customQuotas dictionaries exist
        emp_data_to_update.setdefault("preferences", {}).setdefault("customQuotas", {})

        # Iterate through all month lengths (28, 29, 30, 31 days)
        for days, month_quotas in self.data.get("quotas", {}).items():
            if name in month_quotas:
                # Calculate the new default quota for the new experience level
                new_quota = self.get_default_quota_for_experience(new_experience, int(days))
                
                # Update the main quotas dictionary (for immediate access)
                month_quotas[name] = new_quota
                
                # Also save this new quota to the employee's customQuotas.
                # This prevents the redistribution logic from overwriting this specific value.
                emp_data_to_update["preferences"]["customQuotas"][days] = new_quota

    # Experience Bucket Management
    def get_experience_buckets(self) -> Dict[str, ExperienceBucket]:
        """Get all experience buckets"""
        buckets = {}
        for exp_level, bucket_data in self.data.get("experience_buckets", {}).items():
            buckets[exp_level] = ExperienceBucket(
                experience_level=bucket_data["experience_level"],
                target_shifts=bucket_data["target_shifts"],
                distribution_method=bucket_data.get("distribution_method", "equal"),
                weight_factors=bucket_data.get("weight_factors", {})
            )
        return buckets

    def get_experience_bucket(self, experience_level: str) -> Optional[ExperienceBucket]:
        """Get specific experience bucket"""
        bucket_data = self.data.get("experience_buckets", {}).get(experience_level)
        if bucket_data:
            return ExperienceBucket(
                experience_level=bucket_data["experience_level"],
                target_shifts=bucket_data["target_shifts"],
                distribution_method=bucket_data.get("distribution_method", "equal"),
                weight_factors=bucket_data.get("weight_factors", {})
            )
        return None

    def set_experience_bucket_target(self, experience_level: str, month_length: int, target_shifts: int):
        """Set target shifts for an experience bucket"""
        if "experience_buckets" not in self.data:
            self.data["experience_buckets"] = {}

        if experience_level not in self.data["experience_buckets"]:
            self.data["experience_buckets"][experience_level] = {
                "experience_level": experience_level,
                "target_shifts": {},
                "distribution_method": "equal",
                "weight_factors": {}
            }

        self.data["experience_buckets"][experience_level]["target_shifts"][str(month_length)] = target_shifts
        self._redistribute_bucket_quotas(experience_level, month_length)

    def set_bucket_distribution_method(self, experience_level: str, method: str, weight_factors: Optional[Dict[str, float]] = None):
        """Set distribution method for bucket (equal, weighted, proportional)"""
        if experience_level in self.data.get("experience_buckets", {}):
            self.data["experience_buckets"][experience_level]["distribution_method"] = method
            if weight_factors:
                self.data["experience_buckets"][experience_level]["weight_factors"] = weight_factors

            # Redistribute quotas for all month lengths
            bucket = self.get_experience_bucket(experience_level)
            if bucket:
                for month_length in bucket.target_shifts.keys():
                    self._redistribute_bucket_quotas(experience_level, int(month_length))

    def _update_bucket_targets_for_experience(self, experience_level: str):
        """Update bucket targets to maintain static per-employee quotas when employees are added/removed"""
        bucket = self.get_experience_bucket(experience_level)
        if not bucket:
            return

        # Get active employees in this experience bucket
        bucket_employees = [emp for emp in self.get_employees() if emp.experience == experience_level and emp.is_active]
        num_employees = len(bucket_employees)

        if num_employees == 0:
            return

        # Get default quota for this experience
        default_quota_31 = self.get_default_quota_for_experience(experience_level, 31)
        default_quota_30 = self.get_default_quota_for_experience(experience_level, 30)
        default_quota_29 = self.get_default_quota_for_experience(experience_level, 29)
        default_quota_28 = self.get_default_quota_for_experience(experience_level, 28)

        # Update target shifts to maintain static per-employee quotas
        bucket.target_shifts["31"] = num_employees * default_quota_31
        bucket.target_shifts["30"] = num_employees * default_quota_30
        bucket.target_shifts["29"] = num_employees * default_quota_29
        bucket.target_shifts["28"] = num_employees * default_quota_28

        # Update the data
        if "experience_buckets" not in self.data:
            self.data["experience_buckets"] = {}
        if experience_level not in self.data["experience_buckets"]:
            self.data["experience_buckets"][experience_level] = {
                "experience_level": experience_level,
                "target_shifts": {},
                "distribution_method": "equal",
                "weight_factors": {}
            }
        self.data["experience_buckets"][experience_level]["target_shifts"] = bucket.target_shifts

    def _redistribute_bucket_quotas(self, experience_level: str, month_length: int):
        """Redistribute quotas within a bucket based on current employees and distribution method"""
        bucket = self.get_experience_bucket(experience_level)
        if not bucket:
            return

        target_shifts = bucket.target_shifts.get(str(month_length))
        if target_shifts is None or target_shifts == 0:
            # If no target set, calculate it dynamically
            bucket_employees = [emp for emp in self.get_employees() if emp.experience == experience_level and emp.is_active]
            num_employees = len(bucket_employees)
            if num_employees > 0:
                default_quota = self.get_default_quota_for_experience(experience_level, month_length)
                target_shifts = num_employees * default_quota
                bucket.target_shifts[str(month_length)] = target_shifts
                # Update data
                if "experience_buckets" in self.data and experience_level in self.data["experience_buckets"]:
                    self.data["experience_buckets"][experience_level]["target_shifts"][str(month_length)] = target_shifts

        if target_shifts == 0:
            return

        # Get active employees in this experience bucket
        bucket_employees = [emp for emp in self.get_employees() if emp.experience == experience_level and emp.is_active]

        if not bucket_employees:
            return

        # Calculate individual quotas based on distribution method
        individual_quotas = self._calculate_bucket_distribution(bucket, bucket_employees, month_length, target_shifts)

        # Update quotas in data
        month_key = str(month_length)
        if month_key not in self.data.setdefault("quotas", {}):
            self.data["quotas"][month_key] = {}

        for emp in bucket_employees:
            # Check if employee has custom override
            custom_quota = emp.preferences.custom_quotas.get(month_key)
            if custom_quota is not None:
                self.data["quotas"][month_key][emp.name] = custom_quota
            else:
                self.data["quotas"][month_key][emp.name] = individual_quotas.get(emp.name, 0)

    def _calculate_bucket_distribution(self, bucket: ExperienceBucket, employees: List[Employee],
                                      month_length: int, target_shifts: int) -> Dict[str, int]:
        """Calculate individual quotas within a bucket"""
        if not employees:
            return {}

        quotas = {}

        if bucket.distribution_method == "equal":
            # Equal distribution
            base_quota = target_shifts // len(employees)
            remainder = target_shifts % len(employees)

            for i, emp in enumerate(employees):
                quota = base_quota
                if i < remainder:
                    quota += 1
                quotas[emp.name] = quota

        elif bucket.distribution_method == "weighted":
            # Weighted distribution based on weight_factors
            total_weight = sum(bucket.weight_factors.get(emp.name, 1.0) for emp in employees)
            if total_weight > 0:
                for emp in employees:
                    weight = bucket.weight_factors.get(emp.name, 1.0)
                    quota = round((weight / total_weight) * target_shifts)
                    quotas[emp.name] = quota
            else:
                # Fallback to equal if no weights
                return self._calculate_bucket_distribution(bucket, employees, month_length, target_shifts)

        elif bucket.distribution_method == "proportional":
            # Proportional based on some metric (could be extended)
            # For now, fallback to equal
            return self._calculate_bucket_distribution(bucket, employees, month_length, target_shifts)

        return quotas

    def get_bucket_quota_for_employee(self, employee_name: str, month_length: int) -> int:
        """Get quota for employee from bucket system (with custom override support)"""
        emp = self.get_employee_by_name(employee_name)
        if not emp:
            return 0

        # Check for custom override first
        custom_quota = emp.preferences.custom_quotas.get(str(month_length))
        if custom_quota is not None:
            return custom_quota

        # Get from bucket system
        bucket = self.get_experience_bucket(emp.experience)
        if bucket:
            target_shifts = bucket.target_shifts.get(str(month_length))
            if target_shifts is not None:
                # Get bucket employees
                bucket_employees = [e for e in self.get_employees()
                                  if e.experience == emp.experience and e.is_active]
                individual_quotas = self._calculate_bucket_distribution(bucket, bucket_employees, month_length, target_shifts)
                quota = individual_quotas.get(employee_name, 0)
                return quota

        # Fallback to old system
        fallback_quota = self.get_default_quota_for_experience(emp.experience, month_length)
        return fallback_quota
    
    # Absence Management
    def get_absences(self, emp_id: int) -> List[str]:
        """Get absence dates for employee"""
        return self.data.get("absences", {}).get(str(emp_id), [])
    
    def add_absence(self, emp_id: int, date_str: str):
        """Add absence date for employee"""
        emp_key = str(emp_id)
        if emp_key not in self.data.setdefault("absences", {}):
            self.data["absences"][emp_key] = []
        if date_str not in self.data["absences"][emp_key]:
            self.data["absences"][emp_key].append(date_str)
    
    def remove_absence(self, emp_id: int, date_str: str):
        """Remove absence date for employee"""
        emp_key = str(emp_id)
        if emp_key in self.data.get("absences", {}):
            if date_str in self.data["absences"][emp_key]:
                self.data["absences"][emp_key].remove(date_str)
    
    def is_employee_absent(self, emp_id: int, date_str: str) -> bool:
        """Check if employee is absent on specific date"""
        return date_str in self.get_absences(emp_id)
    
    # Schedule Management
    def get_schedule(self, month_key: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get schedule for specific month, converting old format to new structure if needed"""
        raw_schedule = self.data.get("schedules", {}).get(month_key, {})
        schedule = {}
        for date_str, day_data in raw_schedule.items():
            schedule[date_str] = {}
            for shift_type in ["day_shift", "night_shift"]:
                if shift_type in day_data:
                    shift_info = day_data[shift_type]
                    if isinstance(shift_info, int):
                        # Old format: direct employee ID
                        schedule[date_str][shift_type] = {
                            "employee_id": shift_info,
                            "is_manual": False  # Assume non-manual for old data
                        }
                    else:
                        # New format: dict
                        schedule[date_str][shift_type] = shift_info
                else:
                    schedule[date_str][shift_type] = None
        return schedule
    
    def save_schedule(self, month_key: str, schedule: Dict[str, Dict[str, Dict[str, Any]]]):
        """Save schedule for specific month, ensuring dict format"""
        # Ensure all shifts are in dict format
        for date_str, day_data in schedule.items():
            for shift_type in ["day_shift", "night_shift"]:
                if shift_type in day_data and day_data[shift_type] is not None and not isinstance(day_data[shift_type], dict):
                    # Convert old format
                    day_data[shift_type] = {
                        "employee_id": day_data[shift_type],
                        "is_manual": False
                    }
        self.data.setdefault("schedules", {})[month_key] = schedule

    def save_schedule_with_statistics(self, month_key: str, schedule: Dict[str, Dict[str, Optional[int]]]):
        """Save schedule and calculate/store statistics with deviation flags"""
        # Save the schedule
        self.save_schedule(month_key, schedule)

        # Calculate and store statistics with deviation flags
        emp_stats = self.calculate_employee_stats(month_key)
        team_stats = self.get_team_stats(month_key)

        # Store in statistics section
        self.data.setdefault("statistics", {})[month_key] = {
            "employee_stats": emp_stats,
            "team_stats": team_stats,
            "generated_at": datetime.now().isoformat(),
            "deviation_flags": [asdict(flag) if hasattr(flag, '__dataclass_fields__') else flag for flag in team_stats.get("deviation_flags", [])]
        }

        # Save to file
        self.save_data()
    
    def get_shift_assignment(self, month_key: str, date_str: str, shift_type: str) -> Optional[int]:
        """Get employee ID assigned to specific shift, handling old and new formats"""
        schedule = self.get_schedule(month_key)
        day_data = schedule.get(date_str, {})
        shift_info = day_data.get(shift_type)
        if shift_info is None:
            return None
        if isinstance(shift_info, dict):
            return shift_info.get("employee_id")
        else:
            # Old format
            return shift_info
    
    def set_shift_assignment(self, month_key: str, date_str: str, shift_type: str, emp_id: Optional[int], is_manual: bool = False):
        """Set employee assignment for specific shift with manual flag"""
        if month_key not in self.data.setdefault("schedules", {}):
            self.data["schedules"][month_key] = {}
        if date_str not in self.data["schedules"][month_key]:
            self.data["schedules"][month_key][date_str] = {}
        
        if emp_id is None:
            self.data["schedules"][month_key][date_str][shift_type] = None
        else:
            self.data["schedules"][month_key][date_str][shift_type] = {
                "employee_id": emp_id,
                "is_manual": is_manual
            }
        
        # Track manual adjustment if manual
        if is_manual:
            self._track_manual_adjustment(month_key, date_str, shift_type, emp_id)
    
    def _track_manual_adjustment(self, month_key: str, date_str: str, shift_type: str, emp_id: Optional[int]):
        """Track manual adjustments for reporting"""
        adj_key = f"{month_key}_{date_str}_{shift_type}"
        self.data.setdefault("manual_adjustments", {})[adj_key] = {
            "month": month_key,
            "date": date_str,
            "shift_type": shift_type,
            "employee_id": emp_id,
            "timestamp": datetime.now().isoformat()
        }
    
    # Settings Management
    def get_setting(self, key: str, default=None):
        """Get application setting"""
        return self.data.get("settings", {}).get(key, default)
    
    def set_setting(self, key: str, value):
        """Set application setting"""
        self.data.setdefault("settings", {})[key] = value
    
    # Statistics and Reporting
    def calculate_employee_stats(self, month_key: str) -> Dict[str, Dict[str, Any]]:
        """Calculate statistics for all employees in given month with deviation flagging"""
        schedule = self.get_schedule(month_key)
        employees = self.get_employees()
        stats = {}

        # Calculate days in month and get quotas
        year, month = map(int, month_key.split('-'))
        days_in_month = monthrange(year, month)[1]
        quotas = self.get_quotas_for_month(days_in_month)

        for emp in employees:
            # Use bucket-based quota (which already handles custom overrides)
            emp_quota = self.get_bucket_quota_for_employee(emp.name, days_in_month)

            emp_stats = {
                "name": emp.name,
                "experience": emp.experience,
                "day_shifts": 0,
                "night_shifts": 0,
                "total_shifts": 0,
                "quota": emp_quota,
                "quota_deviation": 0,
                "absences": len(self.get_absences(emp.id)),
                "deviation_flag": None  # Will be set below
            }

            # Count shifts
            for date_data in schedule.values():
                day_shift_info = date_data.get("day_shift")
                if day_shift_info and day_shift_info.get("employee_id") == emp.id:
                    emp_stats["day_shifts"] += 1
                
                night_shift_info = date_data.get("night_shift")
                if night_shift_info and night_shift_info.get("employee_id") == emp.id:
                    emp_stats["night_shifts"] += 1

            # Calculate totals (night shifts count as 2)
            emp_stats["total_shifts"] = emp_stats["day_shifts"] + (emp_stats["night_shifts"] * 2)
            emp_stats["quota_deviation"] = emp_stats["total_shifts"] - emp_stats["quota"]

            # Generate deviation flag
            deviation_flag = self._generate_deviation_flag(
                emp.name, emp_stats["quota_deviation"], emp_stats["total_shifts"], emp_quota
            )
            emp_stats["deviation_flag"] = asdict(deviation_flag) if deviation_flag else None

            stats[emp.name] = emp_stats

        return stats
    
    def _generate_deviation_flag(self, employee_name: str, deviation: int, actual_shifts: int, quota: int) -> Optional[DeviationFlag]:
        """Generate deviation flag based on quota deviation"""
        if deviation == 0:
            return DeviationFlag(
                employee_name=employee_name,
                deviation_type="exact",
                deviation_units=0,
                severity="none",
                description="Quota met exactly"
            )

        # Determine deviation type and severity
        if deviation > 0:
            deviation_type = "over_quota"
            if deviation <= 2:
                severity = "low"
                description = f"Slightly over quota by {deviation} units"
            elif deviation <= 5:
                severity = "medium"
                description = f"Moderately over quota by {deviation} units"
            else:
                severity = "high"
                description = f"Significantly over quota by {deviation} units"
        else:
            deviation_type = "under_quota"
            abs_deviation = abs(deviation)
            if abs_deviation <= 2:
                severity = "low"
                description = f"Slightly under quota by {abs_deviation} units"
            elif abs_deviation <= 5:
                severity = "medium"
                description = f"Moderately under quota by {abs_deviation} units"
            else:
                severity = "high"
                description = f"Significantly under quota by {abs_deviation} units"

        return DeviationFlag(
            employee_name=employee_name,
            deviation_type=deviation_type,
            deviation_units=deviation,
            severity=severity,
            description=description
        )

    def clear_future_schedules(self, month_key: str) -> Dict[str, Any]:
        """
        Clear all schedule assignments for dates greater than today's date in the specified month.

        Args:
            month_key: Month key in format "YYYY-MM"

        Returns:
            Dict with information about cleared assignments
        """
        year, month = map(int, month_key.split('-'))
        today = date.today()

        schedule = self.get_schedule(month_key)

        if not schedule:
            return {
                "cleared_count": 0,
                "affected_dates": [],
                "message": "No schedule found for the specified month"
            }

        cleared_count = 0
        affected_dates = []

        # Iterate through all dates in the schedule
        for date_str, day_schedule in schedule.items():
            # Robust date parsing to handle both zero-padded and non-zero-padded months
            try:
                parts = date_str.split('-')
                if len(parts) == 3:
                    year = int(parts[0])
                    month = int(parts[1])
                    day = int(parts[2])
                    schedule_date = date(year, month, day)
                else:
                    logging.error(f"Invalid date format: {date_str}")
                    continue
            except (ValueError, IndexError) as e:
                logging.error(f"Failed to parse date {date_str}: {e}")
                continue

            # Only clear future dates
            if schedule_date > today:
                # Check if there are assignments to clear
                day_shift = day_schedule.get("day_shift")
                night_shift = day_schedule.get("night_shift")

                day_shift_info = day_schedule.get("day_shift")
                night_shift_info = day_schedule.get("night_shift")
                has_assignment = False
                if day_shift_info and day_shift_info != {}:
                    has_assignment = True
                if night_shift_info and night_shift_info != {}:
                    has_assignment = True

                if has_assignment:
                    # Clear the assignments for the future date
                    schedule[date_str]['day_shift'] = None
                    schedule[date_str]['night_shift'] = None
                    cleared_count += 1
                    affected_dates.append(date_str)

        # Save the updated schedule
        if cleared_count > 0:
            self.save_schedule_with_statistics(month_key, schedule)
            return {
                "cleared_count": cleared_count,
                "affected_dates": affected_dates,
                "message": f"Cleared {cleared_count} future schedule assignments"
            }
        else:
            return {
                "cleared_count": 0,
                "affected_dates": [],
                "message": "No future schedule assignments to clear"
            }

    def get_team_stats(self, month_key: str) -> Dict[str, Any]:
        """Get team-level statistics with bucket information and deviation flags"""
        emp_stats = self.calculate_employee_stats(month_key)

        high_exp_employees = [s for s in emp_stats.values() if s["experience"] == "High"]
        low_exp_employees = [s for s in emp_stats.values() if s["experience"] == "Low"]

        # Get bucket targets
        year, month = map(int, month_key.split('-'))
        days_in_month = calendar.monthrange(year, month)[1]

        bucket_targets = {}
        buckets = self.get_experience_buckets()
        for exp_level, bucket in buckets.items():
            target = bucket.target_shifts.get(str(days_in_month), 0)
            bucket_targets[exp_level] = target

        # Collect deviation flags
        deviation_flags = []
        for emp_stat in emp_stats.values():
            if emp_stat["deviation_flag"]:
                deviation_flags.append(asdict(emp_stat["deviation_flag"]) if hasattr(emp_stat["deviation_flag"], '__dataclass_fields__') else emp_stat["deviation_flag"])

        # Add manual assignment stats
        manual_count = 0
        schedule = self.get_schedule(month_key)
        for date_data in schedule.values():
            for shift_type in ["day_shift", "night_shift"]:
                shift_info = date_data.get(shift_type)
                if shift_info and isinstance(shift_info, dict) and shift_info.get("is_manual"):
                    manual_count += 1

        return {
            "total_employees": len(emp_stats),
            "high_experience_count": len(high_exp_employees),
            "low_experience_count": len(low_exp_employees),
            "total_shifts_assigned": sum(s["total_shifts"] for s in emp_stats.values()),
            "total_quota": sum(s["quota"] for s in emp_stats.values()),
            "high_exp_shifts": sum(s["total_shifts"] for s in high_exp_employees),
            "low_exp_shifts": sum(s["total_shifts"] for s in low_exp_employees),
            "bucket_targets": bucket_targets,
            "high_exp_target": bucket_targets.get("High", 0),
            "low_exp_target": bucket_targets.get("Low", 0),
            "high_exp_target_deviation": sum(s["total_shifts"] for s in high_exp_employees) - bucket_targets.get("High", 0),
            "low_exp_target_deviation": sum(s["total_shifts"] for s in low_exp_employees) - bucket_targets.get("Low", 0),
            "quota_violations": len([s for s in emp_stats.values() if s["quota_deviation"] != 0]),
            "over_quota_employees": [s["name"] for s in emp_stats.values() if s["quota_deviation"] > 0],
            "under_quota_employees": [s["name"] for s in emp_stats.values() if s["quota_deviation"] < 0],
            "deviation_flags": deviation_flags,
            "high_severity_deviations": [f for f in deviation_flags if f["severity"] == "high"],
            "medium_severity_deviations": [f for f in deviation_flags if f["severity"] == "medium"],
            "low_severity_deviations": [f for f in deviation_flags if f["severity"] == "low"],
            "manual_assignments": manual_count
        }

    def is_manual_assignment(self, month_key: str, date_str: str, shift_type: str) -> bool:
        """Check if assignment is manual"""
        schedule = self.get_schedule(month_key)
        day_data = schedule.get(date_str, {})
        shift_info = day_data.get(shift_type)
        if isinstance(shift_info, dict):
            return shift_info.get("is_manual", False)
        return False
