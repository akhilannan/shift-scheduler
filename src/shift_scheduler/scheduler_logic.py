"""
Scheduler Logic for Shift Scheduling System

Implements CP-SAT optimization for generating shift schedules with
experience-based allocation and rest constraints.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import calendar
import logging
import time

from ortools.sat.python import cp_model

from .data_manager import DataManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ShiftType(Enum):
    DAY = "day_shift"
    NIGHT = "night_shift"


@dataclass
class Shift:
    """Represents a single shift slot"""
    date: date
    shift_type: ShiftType
    assigned_employee: Optional[int] = None


@dataclass
class ScheduleResult:
    """Result of schedule generation"""
    success: bool
    schedule: Dict[str, Dict[str, Optional[int]]]
    violations: List[str]
    statistics: Dict[str, Any]
    message: str


class ConstraintViolation:
    """Types of constraint violations"""
    ABSENCE = "Employee absent on this date"
    OFF_DAY = "Employee has off-day on this date"
    SHIFT_PREFERENCE = "Shift type does not match employee preferences"
    QUOTA_EXCEEDED = "Employee quota exceeded"
    SAME_DAY_CONFLICT = "Cannot work day and night shift on same day"
    POST_NIGHT_CONFLICT = "Cannot work any shift on the day after a night shift"
    CONSECUTIVE_NIGHT_CONFLICT = "Cannot work consecutive night shifts"
    NO_AVAILABLE_EMPLOYEE = "No available employee for this shift"
    NEXT_DAY_CONFLICT = "Cannot work on day following this night shift"


class ShiftScheduler:
    """Main scheduler class implementing CP-SAT optimization for shift scheduling"""
    
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self.employees = {}  # Cache employees by ID
        self.quotas = {}  # Cache quotas
        self.absences = {}  # Cache absences
        
    def generate_schedule(self, year: int, month: int,
                             allow_quota_violations: bool = False,
                             emergency_mode: bool = False,
                             warm_start: bool = False,
                             partial_generation: bool = False) -> ScheduleResult:
        """
        Generate schedule for given month using CP-SAT optimization

        Args:
            year: Target year
            month: Target month (1-12)
            allow_quota_violations: Allow exceeding quotas in emergencies
            emergency_mode: Prefer high experience employees for extra shifts
            warm_start: Use previous solution as starting point for re-optimization
            partial_generation: Enable partial generation for ongoing months
        """
        start_time = time.time()
        month_key = f"{year}-{month:02d}"
        logger.info(f"Starting schedule generation for {month_key} (partial_generation={partial_generation})")

        if partial_generation:
            is_partial, current_day, existing_schedule, days_to_generate = self._detect_partial_generation_scope(year, month)
            
            if is_partial:
                logger.info(f"Detected partial generation for {len(days_to_generate)} days.")
                return self._generate_schedule_cp_sat_partial(year, month, existing_schedule, current_day, days_to_generate, start_time)
            else:
                logger.info(f"No partial generation needed for {month_key}, falling back to full generation.")
                return self._generate_full_schedule_cp_sat(year, month, allow_quota_violations, emergency_mode, warm_start, start_time)
        else:
            return self._generate_full_schedule_cp_sat(year, month, allow_quota_violations, emergency_mode, warm_start, start_time)

    def _generate_schedule_cp_sat_partial(self, year: int, month: int, existing_schedule: Dict,
                                          current_day: int, days_to_generate: List[int], start_time: float) -> ScheduleResult:
        """Generate a partial schedule using CP-SAT"""
        month_key = f"{year}-{month:02d}"
        
        # Calculate adjusted quotas for remaining period
        adjusted_quotas = self._calculate_partial_quotas(year, month, existing_schedule, current_day)

        # Create partial CP-SAT model
        model, variables = self._create_partial_cp_sat_model(year, month, existing_schedule, current_day, adjusted_quotas, days_to_generate)
        logger.info(f"Created partial CP-SAT model for days: {days_to_generate}")

        # Solve the model
        solver = self._solve_cp_sat_model(model, variables, time_limit_seconds=30.0)

        success = solver is not None
        schedule = {}
        violations = []
        message = ""

        if success:
            partial_schedule = self._extract_partial_schedule_from_solution(solver, variables, year, month, existing_schedule)
            schedule = self._merge_partial_schedule(existing_schedule, partial_schedule, days_to_generate)
            message = f"Partial schedule generated successfully for {len(days_to_generate)} days."
            violations = self._validate_cp_sat_solution(schedule, year, month)
            if violations:
                message += f" with {len(violations)} constraint violations found."
            self.data_manager.save_schedule_with_statistics(month_key, schedule)
        else:
            message = f"Failed to generate partial schedule for days: {days_to_generate}"
            schedule = existing_schedule  # Return original schedule on failure

        statistics = self.data_manager.calculate_employee_stats(month_key)
        duration = time.time() - start_time
        logger.info(f"Partial CP-SAT generation completed in {duration:.2f}s. Success: {success}")

        return ScheduleResult(
            success=success,
            schedule=schedule,
            violations=violations,
            statistics=statistics,
            message=message
        )

    def _generate_full_schedule_cp_sat(self, year: int, month: int,
                                        allow_quota_violations: bool, emergency_mode: bool,
                                        warm_start: bool, start_time: float) -> ScheduleResult:
        """Generate full schedule using CP-SAT optimization (original logic)"""
        month_key = f"{year}-{month:02d}"
        
        # Create CP-SAT model
        model, variables = self._create_cp_sat_model(year, month, allow_quota_violations, warm_start)
        logger.info(f"Created full CP-SAT model with {len(self.employees)} employees and {variables['num_days']} days")

        # Solve the model
        solver = self._solve_cp_sat_model(model, variables, time_limit_seconds=30.0)

        success = solver is not None
        schedule = {}
        violations = []
        message = ""

        if success:
            schedule = self._extract_schedule_from_solution(solver, variables, year, month)
            message = "Schedule generated successfully using CP-SAT"
            violations = self._validate_cp_sat_solution(schedule, year, month)
            if violations:
                message += f" with {len(violations)} constraint violations"
            self.data_manager.save_schedule_with_statistics(month_key, schedule)
        else:
            message = "Failed to generate complete schedule using CP-SAT"

        statistics = self.data_manager.calculate_employee_stats(month_key)
        duration = time.time() - start_time
        logger.info(f"Full CP-SAT generation completed in {duration:.2f}s. Success: {success}")

        return ScheduleResult(
            success=success,
            schedule=schedule,
            violations=violations,
            statistics=statistics,
            message=message
        )

    
    def _initialize_for_month(self, year: int, month: int):
        """Initialize caches for the target month"""
        # Cache employees
        self.employees = {emp.id: emp for emp in self.data_manager.get_employees()}

        # Cache quotas for month length using bucket system
        days_in_month = calendar.monthrange(year, month)[1]
        self.quotas = {}
        for emp in self.employees.values():
            # Use bucket-based quota (handles custom overrides internally)
            self.quotas[emp.name] = self.data_manager.get_bucket_quota_for_employee(emp.name, days_in_month)

        # Cache absences
        self.absences = {}
        for emp_id in self.employees:
            self.absences[emp_id] = set(self.data_manager.get_absences(emp_id))

    def _detect_partial_generation_scope(self, year: int, month: int) -> Tuple[bool, int, Dict[str, Dict[str, Optional[int]]], List[int]]:
        """
        Detect if this is a partial generation scenario and return scope information.

        Returns:
            Tuple of (is_partial, current_day, existing_schedule, days_to_generate)
            - is_partial: True if month is ongoing and has days to generate
            - current_day: Current day of month (1-based)
            - existing_schedule: Current schedule data for the month
            - days_to_generate: List of days (1-based) to generate schedule for
        """
        today = date.today()
        current_year = today.year
        current_month = today.month
        current_day = today.day

        # Check if this is a future month
        if year > current_year or (year == current_year and month > current_month):
            return False, current_day, {}, []

        # Check if this is the current month
        is_current_month = (year == current_year and month == current_month)

        month_key = f"{year}-{month:02d}"
        existing_schedule = self.data_manager.get_schedule(month_key) or {}
        days_in_month = calendar.monthrange(year, month)[1]

        days_to_generate = []

        if is_current_month:
            # Include unfilled past days
            for day in range(1, current_day + 1):
                date_str = date(year, month, day).strftime("%Y-%m-%d")
                day_schedule = existing_schedule.get(date_str, {})
                day_shift_info = day_schedule.get("day_shift")
                night_shift_info = day_schedule.get("night_shift")
                
                day_assigned = day_shift_info is not None and day_shift_info.get("employee_id") is not None
                night_assigned = night_shift_info is not None and night_shift_info.get("employee_id") is not None
                
                if not day_assigned or not night_assigned:
                    days_to_generate.append(day)

            # Always include future days
            for day in range(current_day + 1, days_in_month + 1):
                days_to_generate.append(day)
        else: # Past month with gaps
            for day in range(1, days_in_month + 1):
                date_str = date(year, month, day).strftime("%Y-%m-%d")
                day_schedule = existing_schedule.get(date_str, {})
                day_shift_info = day_schedule.get("day_shift")
                night_shift_info = day_schedule.get("night_shift")

                day_assigned = day_shift_info is not None and day_shift_info.get("employee_id") is not None
                night_assigned = night_shift_info is not None and night_shift_info.get("employee_id") is not None

                if not day_assigned or not night_assigned:
                    days_to_generate.append(day)



        is_partial = len(days_to_generate) > 0

        return is_partial, current_day, existing_schedule, sorted(list(set(days_to_generate)))

    def _calculate_partial_quotas(self, year: int, month: int, existing_schedule: Dict[str, Dict[str, Optional[int]]],
                                   current_day: int) -> Dict[str, int]:
        """
        Calculate adjusted quotas for partial generation based on remaining days and existing assignments.

        Args:
            year: Target year
            month: Target month
            existing_schedule: Existing schedule data
            current_day: Current day of month (1-based)

        Returns:
            Dict mapping employee names to adjusted quotas for remaining period
        """
        days_in_month = calendar.monthrange(year, month)[1]
        
        # Initialize month data
        self._initialize_for_month(year, month)

        # Calculate shifts already worked in the current month
        shifts_worked = {emp.name: 0 for emp in self.employees.values()}

        for day in range(1, days_in_month + 1):
            date_str = date(year, month, day).strftime("%Y-%m-%d")
            day_schedule = existing_schedule.get(date_str, {})

            for shift_type, emp_info in day_schedule.items():
                if emp_info:
                    emp_id = emp_info.get("employee_id")
                    if emp_id and emp_id in self.employees:
                        emp = self.employees[emp_id]
                        shift_value = 2 if shift_type == "night_shift" else 1
                        shifts_worked[emp.name] += shift_value

        # Calculate adjusted quotas for remaining period
        adjusted_quotas = {}
        for emp in self.employees.values():
            original_quota = self.quotas.get(emp.name, 0)
            worked = shifts_worked.get(emp.name, 0)
            adjusted_quotas[emp.name] = max(0, original_quota - worked)

        return adjusted_quotas

    def _create_partial_cp_sat_model(self, year: int, month: int, existing_schedule: Dict[str, Dict[str, Optional[int]]],
                                      current_day: int, adjusted_quotas: Dict[str, int], days_to_generate: List[int]) -> Tuple[Any, Dict]:
        """
        Create CP-SAT model for partial schedule generation.

        Args:
            year: Target year
            month: Target month
            existing_schedule: Existing schedule data
            current_day: Current day of month (1-based)
            adjusted_quotas: Adjusted quotas for remaining period
            days_to_generate: List of days to generate schedule for

        Returns:
            Tuple of (model, variables_dict)
        """
        # Initialize data for the month
        self._initialize_for_month(year, month)

        # Get month information
        days_in_month = calendar.monthrange(year, month)[1]
        
        # Create model
        model = cp_model.CpModel()

        # Decision variables: x[e][d][s] = 1 if employee e is assigned to shift s on day d
        x = {}
        for emp_id in self.employees:
            x[emp_id] = {}
            for day in days_to_generate:
                x[emp_id][day] = {}
                for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                    var_name = f"x_{emp_id}_{day}_{shift_type.value}"
                    x[emp_id][day][shift_type] = model.NewBoolVar(var_name)

        # Create eligibility matrix for days_to_generate
        eligible = self._create_eligibility_matrix_partial(year, month, days_to_generate)

        # Handle cross-date constraints for partial generation
        self._handle_cross_date_constraints_partial(model, x, existing_schedule, year, month, days_to_generate)

        # Constraint 1: Eligibility (respect absences, off-days, preferences) for days_to_generate
        for emp_id in self.employees:
            for day in days_to_generate:
                for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                    if not eligible[emp_id][day][shift_type]:
                        model.Add(x[emp_id][day][shift_type] == 0)

        # Constraint 2: No employee works both shifts on same day (days_to_generate)
        for emp_id in self.employees:
            for day in days_to_generate:
                model.Add(x[emp_id][day][ShiftType.DAY] + x[emp_id][day][ShiftType.NIGHT] <= 1)

        # Constraint 3: Each shift is assigned to exactly one employee (days_to_generate)
        for day in days_to_generate:
            for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                shift_vars = [x[emp_id][day][shift_type] for emp_id in self.employees if day in x[emp_id]]
                # Only enforce if the day needs generation
                date_str = date(year, month, day).strftime("%Y-%m-%d")
                shift_key = "day_shift" if shift_type == ShiftType.DAY else "night_shift"
                if existing_schedule.get(date_str, {}).get(shift_key) is None:
                    model.Add(sum(shift_vars) == 1)

        # Constraint 4: Quota constraints for remaining period (soft constraint)
        quota_penalty_terms = []
        for emp_id, emp in self.employees.items():
            adjusted_quota = adjusted_quotas.get(emp.name, 0)
            total_shifts_in_gen_days = sum(
                x[emp_id][day][ShiftType.DAY] + 2 * x[emp_id][day][ShiftType.NIGHT]
                for day in days_to_generate if day in x[emp_id]
            )
            # Soft constraint for quota
            model.Add(total_shifts_in_gen_days <= adjusted_quota + 5) # Allow some leeway
            
            # Penalize going over the adjusted quota
            overage = model.NewIntVar(0, 10, f"overage_{emp_id}")
            model.Add(total_shifts_in_gen_days - adjusted_quota <= overage)
            quota_penalty_terms.append(overage)

        # Minimize total penalty
        if quota_penalty_terms:
            model.Minimize(sum(quota_penalty_terms))

        # Store variables for later use
        variables = {
            'x': x,
            'num_days': days_in_month,
            'num_employees': len(self.employees),
            'days_to_generate': days_to_generate
        }

        return model, variables

    def _handle_cross_date_constraints_partial(self, model: Any, x: Dict[int, Dict[int, Dict[ShiftType, Any]]],
                                                existing_schedule: Dict[str, Dict[str, Optional[int]]],
                                                year: int, month: int, days_to_generate: List[int]):
        """
        Handle cross-date constraints for partial generation, considering existing assignments.
        """
        days_in_month = calendar.monthrange(year, month)[1]

        for emp_id in self.employees:
            for day in days_to_generate:
                # No day shift after night shift
                if day > 1:
                    prev_day = day - 1
                    if prev_day in days_to_generate:
                        # Constraint is between two generated days
                        model.Add(x[emp_id][day][ShiftType.DAY] + x[emp_id][prev_day][ShiftType.NIGHT] <= 1)
                    else:
                        # Constraint is between a generated day and an existing day
                        prev_date_str = date(year, month, prev_day).strftime("%Y-%m-%d")
                        prev_night_emp = existing_schedule.get(prev_date_str, {}).get("night_shift")
                        if prev_night_emp and prev_night_emp.get("employee_id") == emp_id:
                            model.Add(x[emp_id][day][ShiftType.DAY] == 0)

                # No consecutive night shifts
                if day < days_in_month:
                    next_day = day + 1
                    if next_day in days_to_generate:
                         model.Add(x[emp_id][day][ShiftType.NIGHT] + x[emp_id][next_day][ShiftType.NIGHT] <= 1)
                    else:
                        next_date_str = date(year, month, next_day).strftime("%Y-%m-%d")
                        next_night_emp = existing_schedule.get(next_date_str, {}).get("night_shift")
                        if next_night_emp and next_night_emp.get("employee_id") == emp_id:
                             model.Add(x[emp_id][day][ShiftType.NIGHT] == 0)

    def _create_eligibility_matrix_partial(self, year: int, month: int, days_to_generate: List[int]) -> Dict[int, Dict[int, Dict[ShiftType, bool]]]:
        """Create eligibility matrix for days_to_generate in partial generation"""
        eligible = {}

        for emp_id, emp in self.employees.items():
            eligible[emp_id] = {}
            for day in days_to_generate:
                eligible[emp_id][day] = {}
                shift_date = date(year, month, day)
                
                for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                    eligible[emp_id][day][shift_type] = self._is_employee_eligible_for_shift(emp_id, shift_date, shift_type)

        return eligible

    def _extract_partial_schedule_from_solution(self, solver: Any, variables: Dict,
                                                 year: int, month: int, existing_schedule: Dict[str, Dict[str, Optional[int]]]) -> Dict[str, Dict[str, Optional[int]]]:
        """Extract partial schedule from CP-SAT solution for days_to_generate"""
        x = variables['x']
        days_to_generate = variables['days_to_generate']
        partial_schedule = {}

        for day in days_to_generate:
            date_str = date(year, month, day).strftime("%Y-%m-%d")
            partial_schedule[date_str] = {}

            # Find who was assigned
            day_emp, night_emp = None, None
            for emp_id in self.employees:
                if day in x[emp_id]:
                    if solver.Value(x[emp_id][day][ShiftType.DAY]) == 1:
                        day_emp = {"employee_id": emp_id, "is_manual": False}
                    if solver.Value(x[emp_id][day][ShiftType.NIGHT]) == 1:
                        night_emp = {"employee_id": emp_id, "is_manual": False}

            partial_schedule[date_str]["day_shift"] = day_emp
            partial_schedule[date_str]["night_shift"] = night_emp
            
        return partial_schedule

    def _merge_partial_schedule(self, existing_schedule: Dict, partial_schedule: Dict, days_to_generate: List[int]) -> Dict:
        """Merge existing schedule with newly generated partial schedule, only filling gaps."""
        merged = existing_schedule.copy()
        
        for day in days_to_generate:
            date_str = date(int(list(partial_schedule.keys())[0][:4]), int(list(partial_schedule.keys())[0][5:7]), day).strftime("%Y-%m-%d")

            if date_str not in merged:
                merged[date_str] = {}
            
            # Only update if the existing shift was None
            if merged[date_str].get("day_shift") is None and partial_schedule.get(date_str, {}).get("day_shift"):
                merged[date_str]["day_shift"] = partial_schedule[date_str]["day_shift"]
            if merged[date_str].get("night_shift") is None and partial_schedule.get(date_str, {}).get("night_shift"):
                merged[date_str]["night_shift"] = partial_schedule[date_str]["night_shift"]
                
        return merged
    
    def _create_cp_sat_model(self, year: int, month: int, allow_quota_violations: bool, warm_start: bool = False) -> Tuple[Any, Dict]:
        """
        Create CP-SAT model for shift scheduling

        Returns:
            Tuple of (model, variables_dict)
        """
        # Initialize data for the month
        self._initialize_for_month(year, month)

        # Get month information
        days_in_month = calendar.monthrange(year, month)[1]
        num_employees = len(self.employees)
        
        # Create model
        model = cp_model.CpModel()

        # Decision variables: x[e][d][s] = 1 if employee e is assigned to shift s on day d
        x = {}
        for emp_id in self.employees:
            x[emp_id] = {}
            for day in range(1, days_in_month + 1):
                x[emp_id][day] = {}
                for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                    var_name = f"x_{emp_id}_{day}_{shift_type.value}"
                    x[emp_id][day][shift_type] = model.NewBoolVar(var_name)

        # Preprocessing: Create eligibility matrix
        eligible = self._create_eligibility_matrix(year, month)

        # Constraint 1: Eligibility (respect absences, off-days, preferences)
        for emp_id in self.employees:
            for day in range(1, days_in_month + 1):
                for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                    if not eligible[emp_id][day][shift_type]:
                        model.Add(x[emp_id][day][shift_type] == 0)

        # Constraint 2: No employee works both shifts on same day
        for emp_id in self.employees:
            for day in range(1, days_in_month + 1):
                model.Add(x[emp_id][day][ShiftType.DAY] + x[emp_id][day][ShiftType.NIGHT] <= 1)

        # Constraint 3: No day shift after night shift (rest rule)
        for emp_id in self.employees:
            for day in range(2, days_in_month + 1):  # Start from day 2
                model.Add(x[emp_id][day][ShiftType.DAY] + x[emp_id][day-1][ShiftType.NIGHT] <= 1)

        # Constraint 4: No consecutive night shifts
        for emp_id in self.employees:
            for day in range(2, days_in_month + 1):
                model.Add(x[emp_id][day][ShiftType.NIGHT] + x[emp_id][day-1][ShiftType.NIGHT] <= 1)

        # Constraint 5: Each shift is assigned to exactly one employee
        for day in range(1, days_in_month + 1):
            for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                shift_vars = [x[emp_id][day][shift_type] for emp_id in self.employees]
                model.Add(sum(shift_vars) == 1)

        # Constraint 6: Quota constraints (as soft constraints)
        total_shifts_per_employee = {}
        for emp_id in self.employees:
            shifts = []
            for day in range(1, days_in_month + 1):
                shifts.append(x[emp_id][day][ShiftType.DAY])
                shifts.append(2 * x[emp_id][day][ShiftType.NIGHT])
            total_shifts_per_employee[emp_id] = sum(shifts)
            
        quota_penalty_terms = []
        for emp_id, emp in self.employees.items():
            quota = self.quotas.get(emp.name, 0)
            deviation = model.NewIntVar(-days_in_month*2, days_in_month*2, f"dev_{emp_id}")
            model.Add(total_shifts_per_employee[emp_id] - quota == deviation)
            
            # Penalize deviation from quota
            penalty = model.NewIntVar(0, days_in_month*2, f"pen_{emp_id}")
            model.AddAbsEquality(penalty, deviation)
            quota_penalty_terms.append(penalty)

        # Set objective to minimize total penalty
        if quota_penalty_terms:
            model.Minimize(sum(quota_penalty_terms))

        # Store variables for later use
        variables = {
            'x': x,
            'num_days': days_in_month,
            'num_employees': num_employees
        }
        return model, variables


    def _set_warm_start_hints(self, model: Any, x: Dict[int, Dict[int, Dict[ShiftType, Any]]], year: int, month: int):
        """Set warm-start hints from previous solution"""
        month_key = f"{year}-{month:02d}"
        prior_schedule = self.data_manager.get_schedule(month_key)

        if not prior_schedule:
            logger.info("No prior schedule found for warm-start")
            return

        logger.info("Setting warm-start hints from prior schedule")

        # Set hints for each shift based on prior assignments
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            shift_date = date(year, month, day)
            date_str = shift_date.strftime("%Y-%m-%d")
            prior_day_schedule = prior_schedule.get(date_str, {})

            for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                shift_key = "day_shift" if shift_type == ShiftType.DAY else "night_shift"
                prior_shift_info = prior_day_schedule.get(shift_key)

                if prior_shift_info is not None:
                    # Handle both old (int) and new (dict) formats
                    if isinstance(prior_shift_info, dict):
                        prior_emp_id = prior_shift_info.get("employee_id")
                    else:
                        prior_emp_id = prior_shift_info

                    if prior_emp_id is not None and prior_emp_id in self.employees:
                        # Set hint: this employee was assigned this shift
                        model.AddHint(x[prior_emp_id][day][shift_type], 1)
                        logger.debug(f"Hint: {self.employees[prior_emp_id].name} assigned to {shift_type.value} on {date_str}")

                        # Set hints for other employees: they were NOT assigned this shift
                        for other_emp_id in self.employees:
                            if other_emp_id != prior_emp_id:
                                model.AddHint(x[other_emp_id][day][shift_type], 0)

    def _create_eligibility_matrix(self, year: int, month: int) -> Dict[int, Dict[int, Dict[ShiftType, bool]]]:
        """Create matrix of employee eligibility for each shift"""
        days_in_month = calendar.monthrange(year, month)[1]
        eligible = {}

        for emp_id, emp in self.employees.items():
            eligible[emp_id] = {}
            for day in range(1, days_in_month + 1):
                eligible[emp_id][day] = {}
                shift_date = date(year, month, day)
                date_str = shift_date.strftime("%Y-%m-%d")

                for shift_type in [ShiftType.DAY, ShiftType.NIGHT]:
                    # Check basic eligibility
                    is_eligible = self._is_employee_eligible_for_shift(emp_id, shift_date, shift_type)
                    eligible[emp_id][day][shift_type] = is_eligible

        return eligible

    def _is_employee_eligible_for_shift(self, emp_id: int, shift_date: date, shift_type: ShiftType) -> bool:
        """Check if employee is eligible for specific shift on specific date"""
        emp = self.employees[emp_id]
        date_str = shift_date.strftime("%Y-%m-%d")

        # Check absence
        if date_str in self.absences.get(emp_id, set()):
            return False

        # Check off-shifts
        shift_type_str = "day" if shift_type == ShiftType.DAY else "night"
        if (date_str, shift_type_str) in emp.preferences.off_shifts:
            return False

        # Check preferred shift types
        preferred_types = emp.preferences.preferred_shift_types
        if preferred_types != ["both"] and shift_type_str not in preferred_types:
            return False

        return True

    def _solve_cp_sat_model(self, model: Any, variables: Dict,
                           time_limit_seconds: float = 30.0) -> Optional[Any]:
        """Solve the CP-SAT model with time limit"""
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds

        # Solve the model
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            return solver
        else:
            logger.warning(f"CP-SAT solver failed with status: {solver.StatusName(status)}")
            return None

    def _extract_schedule_from_solution(self, solver: Any, variables: Dict,
                                       year: int, month: int) -> Dict[str, Dict[str, Optional[int]]]:
        """Extract schedule from CP-SAT solution"""
        x = variables['x']
        schedule = {}

        for day in range(1, variables['num_days'] + 1):
            shift_date = date(year, month, day)
            date_str = shift_date.strftime("%Y-%m-%d")
            schedule[date_str] = {
                "day_shift": None,
                "night_shift": None
            }
            for emp_id in self.employees:
                if solver.Value(x[emp_id][day][ShiftType.DAY]) == 1:
                    schedule[date_str]["day_shift"] = {"employee_id": emp_id, "is_manual": False}
                if solver.Value(x[emp_id][day][ShiftType.NIGHT]) == 1:
                    schedule[date_str]["night_shift"] = {"employee_id": emp_id, "is_manual": False}
        return schedule

    def _validate_cp_sat_solution(self, schedule: Dict[str, Dict[str, Optional[int]]],
                                 year: int, month: int) -> List[str]:
        """Validate the CP-SAT solution for constraint violations"""
        violations = []
        if not schedule: return violations

        # Check each day for violations
        for date_str, day_schedule in schedule.items():
            try:
                shift_date = date.fromisoformat(date_str)
            except (ValueError, IndexError) as e:
                logger.error(f"Failed to parse date {date_str}: {e}")
                continue

            day_shift_info = day_schedule.get("day_shift")
            night_shift_info = day_schedule.get("night_shift")
            day_emp = day_shift_info.get("employee_id") if day_shift_info else None
            night_emp = night_shift_info.get("employee_id") if night_shift_info else None

            if day_emp is None:
                violations.append(f"No employee assigned to day shift on {date_str}")
            if night_emp is None:
                violations.append(f"No employee assigned to night shift on {date_str}")

            if day_emp is not None and day_emp == night_emp:
                violations.append(f"Employee {day_emp} assigned to both shifts on {date_str}")

            if day_emp is not None:
                prev_date = shift_date - timedelta(days=1)
                prev_date_str = prev_date.strftime("%Y-%m-%d")
                prev_night_emp = schedule.get(prev_date_str, {}).get("night_shift")
                if prev_night_emp and prev_night_emp.get("employee_id") == day_emp:
                    violations.append(f"Employee {day_emp} assigned day shift on {date_str} after night shift on {prev_date_str}")

            if night_emp is not None:
                prev_date = shift_date - timedelta(days=1)
                prev_date_str = prev_date.strftime("%Y-%m-%d")
                prev_night_emp = schedule.get(prev_date_str, {}).get("night_shift")
                if prev_night_emp and prev_night_emp.get("employee_id") == night_emp:
                    violations.append(f"Employee {night_emp} assigned consecutive night shifts on {prev_date_str} and {date_str}")

        return violations

    def validate_manual_assignment(self, emp_id: int, date_str: str,
                                   shift_type: str, current_schedule: Dict) -> List[str]:
        """
        Validate a manual shift assignment against all business rules.
        Returns list of constraint violations (empty if valid).
        """
        violations = []
        emp = self.data_manager.get_employee_by_id(emp_id)

        if not emp:
            violations.append("Employee not found")
            return violations

        if not emp.is_active:
            violations.append("Employee is inactive")

        # Helper to safely get employee_id from shift info (which can be a dict or int)
        def get_assigned_id(shift_info):
            if shift_info is None:
                return None
            return shift_info.get("employee_id") if isinstance(shift_info, dict) else shift_info

        # 1. Check inherent properties of the shift itself
        shift_type_short = "day" if shift_type == "day_shift" else "night"
        
        # Check absence
        if self.data_manager.is_employee_absent(emp_id, date_str):
            violations.append(ConstraintViolation.ABSENCE)

        # Check off-shifts (already checked in UI, but good for robustness)
        if self.data_manager.is_employee_off_shift(emp_id, date_str, shift_type_short):
            violations.append(ConstraintViolation.OFF_DAY)
            
        # Check preferred shift types
        preferred_types = emp.preferences.preferred_shift_types
        if preferred_types != ["both"] and shift_type_short not in preferred_types:
            violations.append(ConstraintViolation.SHIFT_PREFERENCE)

        # If basic eligibility fails, no need to check relational constraints
        if violations:
            return violations
            
        # 2. Check relational constraints against other shifts
        try:
            shift_date = date.fromisoformat(date_str)
        except ValueError:
            violations.append(f"Invalid date format: {date_str}")
            return violations

        # Check same-day conflict
        day_schedule = current_schedule.get(date_str, {})
        if shift_type == "day_shift":
            assigned_night_emp = get_assigned_id(day_schedule.get("night_shift"))
            if assigned_night_emp == emp_id:
                violations.append(ConstraintViolation.SAME_DAY_CONFLICT)
        elif shift_type == "night_shift":
            assigned_day_emp = get_assigned_id(day_schedule.get("day_shift"))
            if assigned_day_emp == emp_id:
                violations.append(ConstraintViolation.SAME_DAY_CONFLICT)

        # Check backwards: Cannot work today if worked night shift yesterday
        previous_date = shift_date - timedelta(days=1)
        prev_date_str = previous_date.strftime("%Y-%m-%d")
        prev_day_schedule = current_schedule.get(prev_date_str, {})
        prev_night_emp = get_assigned_id(prev_day_schedule.get("night_shift"))
        if prev_night_emp == emp_id:
            violations.append(ConstraintViolation.POST_NIGHT_CONFLICT)

        # Check forwards: If assigning a night shift, ensure next day is free
        if shift_type == "night_shift":
            next_date = shift_date + timedelta(days=1)
            next_date_str = next_date.strftime("%Y-%m-%d")
            next_day_schedule = current_schedule.get(next_date_str, {})
            next_day_emp = get_assigned_id(next_day_schedule.get("day_shift"))
            next_night_emp = get_assigned_id(next_day_schedule.get("night_shift"))
            
            if next_day_emp == emp_id:
                violations.append(f"{ConstraintViolation.NEXT_DAY_CONFLICT} (next day's day shift)")
            if next_night_emp == emp_id:
                violations.append(f"{ConstraintViolation.CONSECUTIVE_NIGHT_CONFLICT}")
                
        return violations
    
    def get_schedule_statistics(self, schedule: Dict[str, Dict[str, Optional[int]]],
                               month_key: str) -> Dict[str, Any]:
        """Calculate comprehensive schedule statistics"""
        stats = {
            "total_shifts": 0,
            "day_shifts": 0,
            "night_shifts": 0,
            "unassigned_shifts": 0,
            "employee_stats": {},
            "experience_distribution": {"High": 0, "Low": 0},
            "quota_violations": [],
            "constraint_violations": []
        }
        
        # Initialize employee stats
        for emp in self.data_manager.get_employees():
            stats["employee_stats"][emp.name] = {
                "day_shifts": 0,
                "night_shifts": 0,
                "total_shifts": 0,
                "experience": emp.experience,
                "quota": self.quotas.get(emp.name, 0),
                "quota_deviation": 0
            }
        
        # Count shifts
        for date_str, day_schedule in schedule.items():
            for shift_type, emp_id in day_schedule.items():
                stats["total_shifts"] += 1
                
                if emp_id is None:
                    stats["unassigned_shifts"] += 1
                    continue
                
                emp = self.data_manager.get_employee_by_id(emp_id)
                if not emp:
                    continue
                
                emp_stats = stats["employee_stats"][emp.name]
                
                if shift_type == "day_shift":
                    stats["day_shifts"] += 1
                    emp_stats["day_shifts"] += 1
                    emp_stats["total_shifts"] += 1
                    stats["experience_distribution"][emp.experience] += 1
                elif shift_type == "night_shift":
                    stats["night_shifts"] += 1
                    emp_stats["night_shifts"] += 1
                    emp_stats["total_shifts"] += 2  # Night shifts count as 2
                    stats["experience_distribution"][emp.experience] += 2
        
        # Calculate quota deviations
        for emp_name, emp_stats in stats["employee_stats"].items():
            emp_stats["quota_deviation"] = emp_stats["total_shifts"] - emp_stats["quota"]
            
            if emp_stats["quota_deviation"] != 0:
                stats["quota_violations"].append({
                    "employee": emp_name,
                    "deviation": emp_stats["quota_deviation"],
                    "actual": emp_stats["total_shifts"],
                    "quota": emp_stats["quota"]
                })
        
        return stats
    
    def suggest_schedule_improvements(self, schedule: Dict[str, Dict[str, Optional[int]]]) -> List[str]:
        """Suggest improvements for current schedule"""
        suggestions = []
        stats = self.get_schedule_statistics(schedule, "")
        
        # Check for unassigned shifts
        if stats["unassigned_shifts"] > 0:
            suggestions.append(f"Fill {stats['unassigned_shifts']} unassigned shifts")
        
        # Check quota balance
        over_quota = [v for v in stats["quota_violations"] if v["deviation"] > 0]
        under_quota = [v for v in stats["quota_violations"] if v["deviation"] < 0]
        
        if over_quota and under_quota:
            suggestions.append("Redistribute shifts to balance quotas")
        
        # Check experience distribution
        high_exp_ratio = stats["experience_distribution"]["High"] / max(stats["total_shifts"], 1)
        if high_exp_ratio < 0.6:  # High experience should handle majority
            suggestions.append("Consider assigning more shifts to high experience employees")
        
        return suggestions