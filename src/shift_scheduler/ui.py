"""
User Interface for Shift Scheduling System

CustomTkinter-based GUI with calendar view, drag-and-drop functionality,
employee management, and real-time dashboards with experience filtering.
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog
from datetime import datetime, date
import calendar
from typing import Dict, List, Optional, Callable, Tuple
import threading
import logging

from .data_manager import DataManager, Employee, EmployeePreferences
from .scheduler_logic import ShiftScheduler, ScheduleResult
from .reporting import ExportManager

logger = logging.getLogger(__name__)


# Configure CustomTkinter
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class ClearScheduleDialog(ctk.CTkToplevel):
    """Dialog for confirming future schedule clearing"""

    def __init__(self, parent, month_key: str, clear_info: Dict, callback: Callable = None):
        super().__init__(parent)
        self.month_key = month_key
        self.clear_info = clear_info
        self.callback = callback
        self.result = None

        self.title("Clear Future Schedules")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()

        self._create_widgets()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        # Main frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="🗑️ Clear Future Schedules",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(0, 10))

        # Month information
        month_frame = ctk.CTkFrame(main_frame)
        month_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            month_frame,
            text="Target Month:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        year, month = map(int, self.month_key.split('-'))
        month_name = calendar.month_name[month]
        month_text = f"{month_name} {year}"

        ctk.CTkLabel(month_frame, text=month_text, justify="left").pack(anchor="w", padx=20, pady=5)

        # Clear information
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            info_frame,
            text="Assignments to be Cleared:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        cleared_count = self.clear_info.get("cleared_count", 0)
        affected_dates = self.clear_info.get("affected_dates", [])

        info_text = f"""
• Total assignments to clear: {cleared_count}
• Future dates affected: {len(affected_dates)}
        """

        if affected_dates:
            # Show first few affected dates
            dates_preview = affected_dates[:5]
            info_text += f"\n• Dates: {', '.join(dates_preview)}"
            if len(affected_dates) > 5:
                info_text += f"\n  ... and {len(affected_dates) - 5} more"

        ctk.CTkLabel(info_frame, text=info_text, justify="left").pack(anchor="w", padx=20, pady=5)

        # Warning
        warning_frame = ctk.CTkFrame(main_frame, fg_color="orange")
        warning_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            warning_frame,
            text="⚠️ Warning: This action cannot be undone. Future schedule assignments will be permanently cleared.",
            font=ctk.CTkFont(size=10)
        ).pack(pady=5)

        # Buttons
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self._cancel,
            width=100,
            fg_color="red"
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            button_frame,
            text="Clear Future Schedules",
            command=self._confirm_clear,
            width=180,
            fg_color="orange"
        ).pack(side="right")

    def _confirm_clear(self):
        self.result = "clear"
        if self.callback:
            self.callback(self.result)
        self.destroy()

    def _cancel(self):
        self.result = "cancel"
        if self.callback:
            self.callback(self.result)
        self.destroy()


class EmployeeDialog(ctk.CTkToplevel):
    """Dialog for adding/editing employees"""

    def __init__(self, parent, employee: Optional[Employee] = None, callback: Callable = None):
        super().__init__(parent)
        self.employee = employee
        self.callback = callback
        self.result = None

        self.title("Add Employee" if employee is None else "Edit Employee")
        self.geometry("400x300")
        self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._populate_fields()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
    
    def _create_widgets(self):
        # Main frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Name field
        ctk.CTkLabel(main_frame, text="Name:").pack(anchor="w", pady=(0, 5))
        self.name_entry = ctk.CTkEntry(main_frame, width=300)
        self.name_entry.pack(pady=(0, 15))
        
        # Experience field
        ctk.CTkLabel(main_frame, text="Experience Level:").pack(anchor="w", pady=(0, 5))
        self.experience_var = ctk.StringVar(value="Low")
        self.experience_menu = ctk.CTkOptionMenu(
            main_frame, 
            values=["High", "Low"],
            variable=self.experience_var,
            width=300
        )
        self.experience_menu.pack(pady=(0, 15))
        
        # Active status
        self.active_var = ctk.BooleanVar(value=True)
        self.active_checkbox = ctk.CTkCheckBox(
            main_frame, 
            text="Active Employee",
            variable=self.active_var
        )
        self.active_checkbox.pack(pady=(0, 20))
        
        # Buttons
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(
            button_frame, 
            text="Cancel",
            command=self._cancel,
            width=100
        ).pack(side="right", padx=(10, 0))
        
        ctk.CTkButton(
            button_frame, 
            text="Save",
            command=self._save,
            width=100
        ).pack(side="right")
    
    def _populate_fields(self):
        if self.employee:
            self.name_entry.insert(0, self.employee.name)
            self.experience_var.set(self.employee.experience)
            self.active_var.set(self.employee.is_active)
    
    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Name is required")
            return
        
        self.result = {
            "name": name,
            "experience": self.experience_var.get(),
            "is_active": self.active_var.get()
        }
        
        if self.callback:
            self.callback(self.result)
        
        self.destroy()
    
    def _cancel(self):
        self.destroy()


class CalendarCell(ctk.CTkFrame):
    """Individual calendar cell with dropdowns for manual assignment"""

    def __init__(self, parent, date_obj: date, data_manager: DataManager, on_manual_assign: Callable):
        super().__init__(parent, corner_radius=5)
        self.date_obj = date_obj
        self.data_manager = data_manager
        self.on_manual_assign = on_manual_assign
        self.day_shift_emp = None
        self.night_shift_emp = None

        self._create_widgets()

    def _create_widgets(self):
        # Date label
        self.date_label = ctk.CTkLabel(
            self,
            text=str(self.date_obj.day),
            font=ctk.CTkFont(weight="bold")
        )
        self.date_label.pack(pady=(5, 0))

        # Employee list for dropdowns
        self.employee_names = [emp.name for emp in self.data_manager.get_employees(active_only=True)]
        self.employee_map = {emp.name: emp.id for emp in self.data_manager.get_employees(active_only=True)}
        self.options = ["Unassigned"] + self.employee_names

        # Day shift dropdown
        self.day_var = ctk.StringVar()
        self.day_menu = ctk.CTkOptionMenu(
            self,
            variable=self.day_var,
            values=self.options,
            command=lambda choice: self._on_shift_assignment_change("day_shift", choice)
        )
        self.day_menu.pack(fill="x", padx=5, pady=2)

        # Night shift dropdown
        self.night_var = ctk.StringVar()
        self.night_menu = ctk.CTkOptionMenu(
            self,
            variable=self.night_var,
            values=self.options,
            command=lambda choice: self._on_shift_assignment_change("night_shift", choice)
        )
        self.night_menu.pack(fill="x", padx=5, pady=2)

    def _on_shift_assignment_change(self, shift_type: str, choice: str):
        emp_id = self.employee_map.get(choice)  # None if "Unassigned"

        if emp_id is not None:
            # Validate off-day
            date_str = self.date_obj.strftime("%Y-%m-%d")
            shift_type_short = "day" if shift_type == "day_shift" else "night"
            if self.data_manager.is_employee_off_shift(emp_id, date_str, shift_type_short):
                messagebox.showerror(
                    "Assignment Error",
                    f"Cannot assign {choice} to this shift. The employee has marked this shift as an off-day."
                )
                # Revert dropdown to original value
                self.update_assignments(self.day_shift_emp, self.night_shift_emp)
                return

        self.on_manual_assign(self.date_obj, shift_type, emp_id)

    def update_assignments(self, day_emp: Optional[Employee], night_emp: Optional[Employee]):
        """Update displayed assignments in dropdowns"""
        self.day_shift_emp = day_emp
        self.night_shift_emp = night_emp

        # Update day shift dropdown
        if day_emp:
            self.day_var.set(day_emp.name)
            self.day_menu.configure(fg_color="#28a745")
        else:
            self.day_var.set("Unassigned")
            self.day_menu.configure(fg_color="#dc3545")

        # Update night shift dropdown
        if night_emp:
            self.night_var.set(night_emp.name)
            self.night_menu.configure(fg_color="darkgreen")
        else:
            self.night_var.set("Unassigned")
            self.night_menu.configure(fg_color="darkred")


class CalendarView(ctk.CTkScrollableFrame):
    """Monthly calendar view with shift assignments"""
    
    def __init__(self, parent, data_manager: DataManager, main_window):
        super().__init__(parent)
        self.data_manager = data_manager
        self.main_window = main_window
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self.cells = {}  # date -> CalendarCell
        self.schedule = {}

        self._create_calendar()
    
    def _create_calendar(self):
        # Clear existing widgets
        for widget in self.winfo_children():
            widget.destroy()
        
        self.cells = {}
        
        # Calendar header
        header_frame = ctk.CTkFrame(self)
        header_frame.pack(fill="x", padx=10, pady=10)

        # Previous month button
        prev_button = ctk.CTkButton(
            header_frame,
            text="<",
            width=30,
            command=self._prev_month
        )
        prev_button.pack(side="left", padx=5)

        # Month/Year label
        month_name = calendar.month_name[self.current_month]
        title_label = ctk.CTkLabel(
            header_frame,
            text=f"{month_name} {self.current_year}",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left", expand=True)

        # Next month button
        next_button = ctk.CTkButton(
            header_frame,
            text=">",
            width=30,
            command=self._next_month
        )
        next_button.pack(side="left", padx=5)
        
        # Days of week header
        days_frame = ctk.CTkFrame(self)
        days_frame.pack(fill="x", padx=10, pady=(0, 10))

        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            day_label = ctk.CTkLabel(
                days_frame,
                text=day,
                font=ctk.CTkFont(weight="bold"),
                justify="center"
            )
            day_label.grid(row=0, column=i, padx=2, pady=2, sticky="nsew")

        # Configure column weights for days_frame
        for i in range(7):
            days_frame.columnconfigure(i, weight=1)
        
        # Calendar grid
        self.grid_frame = ctk.CTkFrame(self)
        self.grid_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Generate calendar cells
        cal = calendar.monthcalendar(self.current_year, self.current_month)

        for week_num, week in enumerate(cal):
            for day_num, day in enumerate(week):
                if day == 0:
                    # Empty cell for days from other months
                    empty_frame = ctk.CTkFrame(self.grid_frame, height=100)
                    empty_frame.grid(row=week_num, column=day_num, padx=2, pady=2, sticky="nsew")
                else:
                    # Create calendar cell
                    date_obj = date(self.current_year, self.current_month, day)
                    cell = CalendarCell(
                        self.grid_frame,
                        date_obj,
                        self.data_manager,
                        self._on_manual_assign
                    )
                    cell.grid(row=week_num, column=day_num, padx=2, pady=2, sticky="nsew")
                    self.cells[date_obj] = cell
        
        # Configure grid weights
        for i in range(7):
            self.grid_frame.columnconfigure(i, weight=1)
        for i in range(len(cal)):
            self.grid_frame.rowconfigure(i, weight=1)

    def _on_manual_assign(self, date_obj: date, shift_type: str, emp_id: Optional[int]):
        """Handle manual assignment from calendar cell dropdown with validation"""
        month_key = f"{self.current_year}-{self.current_month:02d}"
        date_str = date_obj.strftime("%Y-%m-%d")

        # If unassigning, no validation is needed
        if emp_id is None:
            self.data_manager.set_shift_assignment(month_key, date_str, shift_type, None, is_manual=True)
            self.data_manager.save_data()
            self.update_schedule_display()
            self.main_window.dashboard.update_dashboard(month_key)
            return

        # Get the complete current schedule for validation context
        current_schedule = self.data_manager.get_schedule(month_key)
        
        # Perform comprehensive validation using the scheduler logic
        violations = self.main_window.scheduler.validate_manual_assignment(
            emp_id, date_str, shift_type, current_schedule
        )
        
        if violations:
            # If validation fails, show an error and revert the UI
            error_message = "Assignment failed due to the following violations:\n\n" + "\n".join(f"• {v}" for v in violations)
            messagebox.showerror("Validation Error", error_message)
            self.update_schedule_display()  # Reverts dropdown change by reloading from data
            return

        # If valid, proceed to set the assignment
        self.data_manager.set_shift_assignment(month_key, date_str, shift_type, emp_id, is_manual=True)

        # Save data and refresh the entire UI
        self.data_manager.save_data()
        self.update_schedule_display()
        self.main_window.dashboard.update_dashboard(month_key)
    
    def set_month(self, year: int, month: int):
        """Change displayed month"""
        self.current_year = year
        self.current_month = month
        self._create_calendar()
        self.update_schedule_display()

    def _prev_month(self):
        """Navigate to previous month"""
        self.current_month -= 1
        if self.current_month == 0:
            self.current_month = 12
            self.current_year -= 1
        self.set_month(self.current_year, self.current_month)
        # Sync with MainWindow
        self.main_window.current_year = self.current_year
        self.main_window.current_month = self.current_month
        self.main_window.month_var.set(str(self.current_month))
        self.main_window.year_var.set(str(self.current_year))
        self.main_window.dashboard.update_dashboard(f"{self.current_year}-{self.current_month:02d}")

    def _next_month(self):
        """Navigate to next month"""
        self.current_month += 1
        if self.current_month == 13:
            self.current_month = 1
            self.current_year += 1
        self.set_month(self.current_year, self.current_month)
        # Sync with MainWindow
        self.main_window.current_year = self.current_year
        self.main_window.current_month = self.current_month
        self.main_window.month_var.set(str(self.current_month))
        self.main_window.year_var.set(str(self.current_year))
        self.main_window.dashboard.update_dashboard(f"{self.current_year}-{self.current_month:02d}")
    
    def update_schedule_display(self):
        """Update calendar with current schedule"""
        month_key = f"{self.current_year}-{self.current_month:02d}"
        logger.info(f"DEBUG: update_schedule_display called for {month_key}")

        for date_obj, cell in self.cells.items():
            date_str = date_obj.strftime("%Y-%m-%d")

            # Get employee IDs using the proper method
            day_emp_id = self.data_manager.get_shift_assignment(month_key, date_str, "day_shift")
            night_emp_id = self.data_manager.get_shift_assignment(month_key, date_str, "night_shift")

            logger.debug(f"DEBUG: {date_str} - day_emp_id: {day_emp_id}, night_emp_id: {night_emp_id}")

            day_emp = self.data_manager.get_employee_by_id(day_emp_id) if day_emp_id else None
            night_emp = self.data_manager.get_employee_by_id(night_emp_id) if night_emp_id else None

            cell.update_assignments(day_emp, night_emp)


class CalendarPicker(ctk.CTkFrame):
    """Calendar widget for selecting individual shifts"""

    def __init__(self, parent, selected_shifts: List[Tuple[str, str]] = None, on_shift_selected=None):
        super().__init__(parent)
        self.selected_shifts = set(selected_shifts or [])
        self.on_shift_selected = on_shift_selected
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month

        self._create_widgets()
        self._update_calendar()

    def _create_widgets(self):
        # Header with month/year navigation
        header_frame = ctk.CTkFrame(self)
        header_frame.pack(fill="x", padx=10, pady=10)

        self.prev_button = ctk.CTkButton(
            header_frame,
            text="◀",
            width=30,
            command=self._prev_month
        )
        self.prev_button.pack(side="left", padx=5)

        self.month_year_label = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.month_year_label.pack(side="left", expand=True)

        self.next_button = ctk.CTkButton(
            header_frame,
            text="▶",
            width=30,
            command=self._next_month
        )
        self.next_button.pack(side="left", padx=5)

        # Days of week header
        days_frame = ctk.CTkFrame(self)
        days_frame.pack(fill="x", padx=10, pady=(0, 10))

        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            day_label = ctk.CTkLabel(
                days_frame,
                text=day,
                font=ctk.CTkFont(weight="bold"),
                justify="center"
            )
            day_label.grid(row=0, column=i, padx=2, pady=2, sticky="nsew")

        # Configure column weights for days_frame
        for i in range(7):
            days_frame.columnconfigure(i, weight=1)

        # Calendar grid
        self.calendar_frame = ctk.CTkFrame(self)
        self.calendar_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def _update_calendar(self):
        # Clear existing calendar
        for widget in self.calendar_frame.winfo_children():
            widget.destroy()

        # Update header
        month_name = calendar.month_name[self.current_month]
        self.month_year_label.configure(text=f"{month_name} {self.current_year}")

        # Create calendar grid
        cal = calendar.monthcalendar(self.current_year, self.current_month)

        for week_idx, week in enumerate(cal):
            for day_idx, day in enumerate(week):
                if day == 0:
                    # Empty cell
                    empty_label = ctk.CTkLabel(self.calendar_frame, text="", height=60)
                    empty_label.grid(row=week_idx, column=day_idx, padx=2, pady=2, sticky="nsew")
                else:
                    # Date cell with two shift areas
                    date_str = f"{self.current_year}-{self.current_month:02d}-{day:02d}"

                    # Container frame for the date
                    date_frame = ctk.CTkFrame(self.calendar_frame, height=60)
                    date_frame.grid(row=week_idx, column=day_idx, padx=2, pady=2, sticky="nsew")
                    date_frame.pack_propagate(False)

                    # Date label
                    date_label = ctk.CTkLabel(date_frame, text=str(day), font=ctk.CTkFont(weight="bold"))
                    date_label.pack(pady=(2, 0))

                    # Day shift button
                    day_selected = (date_str, "day") in self.selected_shifts
                    day_button = ctk.CTkButton(
                        date_frame,
                        text="D",
                        width=35,
                        height=20,
                        font=ctk.CTkFont(size=10),
                        fg_color="#007BFF" if day_selected else "lightgray",
                        text_color="white" if day_selected else "black",
                        command=lambda d=date_str: self._toggle_shift(d, "day")
                    )
                    day_button.pack(side="left", padx=2, pady=2)

                    # Night shift button
                    night_selected = (date_str, "night") in self.selected_shifts
                    night_button = ctk.CTkButton(
                        date_frame,
                        text="N",
                        width=35,
                        height=20,
                        font=ctk.CTkFont(size=10),
                        fg_color="darkblue" if night_selected else "gray",
                        text_color="white" if night_selected else "black",
                        command=lambda d=date_str: self._toggle_shift(d, "night")
                    )
                    night_button.pack(side="right", padx=2, pady=2)

        # Configure grid weights for proper expansion and alignment
        for i in range(7):
            self.calendar_frame.columnconfigure(i, weight=1)
        for i in range(len(cal)):
            self.calendar_frame.rowconfigure(i, weight=1)

    def _toggle_shift(self, date_str: str, shift_type: str):
        shift_tuple = (date_str, shift_type)
        if shift_tuple in self.selected_shifts:
            self.selected_shifts.remove(shift_tuple)
        else:
            self.selected_shifts.add(shift_tuple)

        self._update_calendar()

        if self.on_shift_selected:
            self.on_shift_selected(list(self.selected_shifts))

    def _prev_month(self):
        self.current_month -= 1
        if self.current_month == 0:
            self.current_month = 12
            self.current_year -= 1
        self._update_calendar()

    def _next_month(self):
        self.current_month += 1
        if self.current_month == 13:
            self.current_month = 1
            self.current_year += 1
        self._update_calendar()

    def get_selected_shifts(self) -> List[Tuple[str, str]]:
        return list(self.selected_shifts)

    def set_selected_shifts(self, shifts: List[Tuple[str, str]]):
        self.selected_shifts = set(shifts)
        self._update_calendar()

    # Backward compatibility methods
    def get_selected_dates(self) -> List[str]:
        """Get dates where both shifts are selected (backward compatibility)"""
        date_count = {}
        for date_str, shift_type in self.selected_shifts:
            date_count[date_str] = date_count.get(date_str, 0) + 1

        # Return dates where both shifts are selected
        return [date for date, count in date_count.items() if count == 2]

    def set_selected_dates(self, dates: List[str]):
        """Set dates as both shifts selected (backward compatibility)"""
        self.selected_shifts = set()
        for date_str in dates:
            self.selected_shifts.add((date_str, "day"))
            self.selected_shifts.add((date_str, "night"))
        self._update_calendar()


class PreferencesGrid(ctk.CTkFrame):
    """Grid for managing employee preferences"""

    def __init__(self, parent, employee: Employee = None, on_preferences_changed=None):
        super().__init__(parent)
        self.employee = employee
        self.on_preferences_changed = on_preferences_changed
        self.preferences = employee.preferences if employee else EmployeePreferences()

        self._create_widgets()
        self._populate_fields()

    def _create_widgets(self):
        # Title
        title_label = ctk.CTkLabel(
            self,
            text="Employee Preferences",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(10, 20))

        # Off-days section
        off_days_frame = ctk.CTkFrame(self)
        off_days_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            off_days_frame,
            text="Off Shifts:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        self.off_days_text = ctk.CTkTextbox(off_days_frame, height=60)
        self.off_days_text.pack(fill="x", padx=10, pady=(0, 10))

        # Calendar picker for off-shifts
        self.calendar_picker = CalendarPicker(off_days_frame, on_shift_selected=self._on_off_days_changed)
        self.calendar_picker.pack(fill="x", padx=10, pady=(0, 10))

        # Preferred shift types
        shift_frame = ctk.CTkFrame(self)
        shift_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            shift_frame,
            text="Preferred Shift Types:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        self.shift_vars = {}
        shifts = ["day", "night", "both"]
        for shift in shifts:
            var = ctk.BooleanVar()
            checkbox = ctk.CTkCheckBox(
                shift_frame,
                text=shift.capitalize(),
                variable=var,
                command=self._on_shift_preference_changed
            )
            checkbox.pack(anchor="w", padx=20, pady=2)
            self.shift_vars[shift] = var

        # Custom quotas
        quota_frame = ctk.CTkFrame(self)
        quota_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            quota_frame,
            text="Custom Quotas (per month length):",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        self.quota_entries = {}
        for days in [28, 29, 30, 31]:
            frame = ctk.CTkFrame(quota_frame)
            frame.pack(fill="x", padx=10, pady=2)

            ctk.CTkLabel(frame, text=f"{days} days:").pack(side="left", padx=5)
            entry = ctk.CTkEntry(frame, width=60)
            entry.pack(side="left", padx=5)
            self.quota_entries[days] = entry

        # Availability notes
        notes_frame = ctk.CTkFrame(self)
        notes_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            notes_frame,
            text="Availability Notes:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        self.notes_text = ctk.CTkTextbox(notes_frame, height=80)
        self.notes_text.pack(fill="x", padx=10, pady=(0, 10))

    def _populate_fields(self):
        # Off shifts
        off_shift_texts = []
        for date_str, shift_type in self.preferences.off_shifts:
            off_shift_texts.append(f"{date_str} ({shift_type})")
        self.off_days_text.delete("1.0", "end")
        self.off_days_text.insert("1.0", "\n".join(off_shift_texts))
        self.calendar_picker.set_selected_shifts(self.preferences.off_shifts)

        # Shift preferences
        for shift in self.shift_vars:
            self.shift_vars[shift].set(shift in self.preferences.preferred_shift_types)

        # Custom quotas
        for days, entry in self.quota_entries.items():
            quota = self.preferences.custom_quotas.get(str(days), "")
            entry.delete(0, "end")
            entry.insert(0, str(quota) if quota else "")

        # Notes
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", self.preferences.availability_notes)

    def _on_off_days_changed(self, shifts: List[Tuple[str, str]]):
        self.preferences.off_shifts = shifts
        off_shift_texts = []
        for date_str, shift_type in shifts:
            off_shift_texts.append(f"{date_str} ({shift_type})")
        self.off_days_text.delete("1.0", "end")
        self.off_days_text.insert("1.0", "\n".join(off_shift_texts))
        self._notify_change()

    def _on_shift_preference_changed(self):
        self.preferences.preferred_shift_types = [
            shift for shift, var in self.shift_vars.items() if var.get()
        ]
        self._notify_change()

    def get_preferences(self) -> EmployeePreferences:
        # Update from custom quotas
        custom_quotas = {}
        for days, entry in self.quota_entries.items():
            value = entry.get().strip()
            if value and value.isdigit():
                custom_quotas[str(days)] = int(value)

        self.preferences.custom_quotas = custom_quotas
        self.preferences.availability_notes = self.notes_text.get("1.0", "end").strip()

        return self.preferences

    def _notify_change(self):
        if self.on_preferences_changed:
            self.on_preferences_changed(self.get_preferences())


class EmployeeForm(ctk.CTkFrame):
    """Form for adding/editing employees with validation"""

    def __init__(self, parent, data_manager: DataManager, employee: Employee = None, on_save=None, on_cancel=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.employee = employee
        self.on_save = on_save
        self.on_cancel = on_cancel
        self.preferences = employee.preferences if employee else EmployeePreferences()

        self._create_widgets()
        self._populate_fields()

    def _create_widgets(self):
        # Title
        title_text = "Edit Employee" if self.employee else "Add New Employee"
        title_label = ctk.CTkLabel(
            self,
            text=title_text,
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(20, 10))

        # Main form frame
        form_frame = ctk.CTkScrollableFrame(self)
        form_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Name field
        name_frame = ctk.CTkFrame(form_frame)
        name_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(name_frame, text="Name:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        self.name_entry = ctk.CTkEntry(name_frame, width=300)
        self.name_entry.pack(padx=10, pady=(0, 5))

        self.name_error_label = ctk.CTkLabel(name_frame, text="", text_color="red", font=ctk.CTkFont(size=10))
        self.name_error_label.pack(anchor="w", padx=10)

        # Experience field
        exp_frame = ctk.CTkFrame(form_frame)
        exp_frame.pack(fill="x", pady=10)

        ctk.CTkLabel(exp_frame, text="Experience Level:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        self.experience_var = ctk.StringVar(value="Low")
        self.experience_menu = ctk.CTkOptionMenu(
            exp_frame,
            values=["High", "Low"],
            variable=self.experience_var,
            width=300
        )
        self.experience_menu.pack(padx=10, pady=(0, 5))

        # Active status
        self.active_var = ctk.BooleanVar(value=True)
        self.active_checkbox = ctk.CTkCheckBox(
            form_frame,
            text="Employee is Active",
            variable=self.active_var
        )
        self.active_checkbox.pack(anchor="w", padx=20, pady=10)

        # Preferences section
        prefs_title = ctk.CTkLabel(
            form_frame,
            text="Preferences",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        prefs_title.pack(anchor="w", padx=10, pady=(20, 10))

        self.preferences_grid = PreferencesGrid(form_frame, self.employee)
        self.preferences_grid.pack(fill="x", padx=10, pady=10)

        # Buttons
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(fill="x", padx=20, pady=20)

        self.cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self._cancel,
            width=100
        )
        self.cancel_button.pack(side="right", padx=(10, 0))

        self.save_button = ctk.CTkButton(
            button_frame,
            text="Save",
            command=self._save,
            width=100,
            fg_color="green"
        )
        self.save_button.pack(side="right")

    def _populate_fields(self):
        if self.employee:
            self.name_entry.insert(0, self.employee.name)
            self.experience_var.set(self.employee.experience)
            self.active_var.set(self.employee.is_active)

    def _validate_form(self) -> tuple[bool, str]:
        """Validate form data and return (is_valid, error_message)"""
        name = self.name_entry.get().strip()

        if not name:
            return False, "Name is required"

        if len(name) < 2:
            return False, "Name must be at least 2 characters long"

        # Check for duplicate names (if adding new employee or changing name)
        existing_employee = self.data_manager.get_employee_by_name(name)
        if existing_employee and (not self.employee or existing_employee.id != self.employee.id):
            return False, f"An employee with name '{name}' already exists"

        return True, ""

    def _save(self):
        if not self._validate_form()[0]:
            is_valid, error_msg = self._validate_form()
            self.name_error_label.configure(text=error_msg)
            return

        # Clear any previous error
        self.name_error_label.configure(text="")

        # Get form data
        name = self.name_entry.get().strip()
        experience = self.experience_var.get()
        is_active = self.active_var.get()
        preferences = self.preferences_grid.get_preferences()

        employee_data = {
            "name": name,
            "experience": experience,
            "is_active": is_active,
            "preferences": preferences
        }

        if self.on_save:
            self.on_save(employee_data)

    def _cancel(self):
        if self.on_cancel:
            self.on_cancel()


class EmployeeList(ctk.CTkFrame):
    """List component for displaying and managing employees"""

    def __init__(self, parent, data_manager: DataManager, on_employee_selected=None, on_add_employee=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.on_employee_selected = on_employee_selected
        self.on_add_employee = on_add_employee
        self.selected_employee = None

        self._create_widgets()
        self._load_employees()

    def _create_widgets(self):
        # Header with title and add button
        header_frame = ctk.CTkFrame(self)
        header_frame.pack(fill="x", padx=10, pady=10)

        title_label = ctk.CTkLabel(
            header_frame,
            text="Employees",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(side="left", padx=10, pady=10)

        self.add_button = ctk.CTkButton(
            header_frame,
            text="+ Add Employee",
            command=self._add_employee,
            width=120
        )
        self.add_button.pack(side="right", padx=10, pady=10)

        # Search/filter frame
        filter_frame = ctk.CTkFrame(self)
        filter_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkLabel(filter_frame, text="Filter:").pack(side="left", padx=10, pady=5)

        self.filter_var = ctk.StringVar(value="All")
        self.filter_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["All", "Active", "Inactive", "High Experience", "Low Experience"],
            variable=self.filter_var,
            command=self._on_filter_change,
            width=150
        )
        self.filter_menu.pack(side="left", padx=10, pady=5)

        # Employee list
        self.list_frame = ctk.CTkScrollableFrame(self, height=300)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def _load_employees(self):
        """Load and display employees"""
        # Clear existing list
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        # Get employees based on filter
        filter_value = self.filter_var.get()
        employees = self.data_manager.get_employees(active_only=False)

        if filter_value == "Active":
            employees = [e for e in employees if e.is_active]
        elif filter_value == "Inactive":
            employees = [e for e in employees if not e.is_active]
        elif filter_value == "High Experience":
            employees = [e for e in employees if e.experience == "High"]
        elif filter_value == "Low Experience":
            employees = [e for e in employees if e.experience == "Low"]
        else:
            pass

        # Display employees
        for employee in employees:
            self._create_employee_item(employee)

    def _create_employee_item(self, employee: Employee):
        """Create a display item for an employee"""
        item_frame = ctk.CTkFrame(self.list_frame)
        item_frame.pack(fill="x", padx=5, pady=2)

        # Employee info
        info_frame = ctk.CTkFrame(item_frame)
        info_frame.pack(fill="x", padx=5, pady=5)

        # Name and experience badge
        exp_badge = "★" if employee.experience == "High" else "○"
        name_text = f"{exp_badge} {employee.name}"

        name_label = ctk.CTkLabel(
            info_frame,
            text=name_text,
            font=ctk.CTkFont(weight="bold")
        )
        name_label.pack(side="left", padx=10)

        # Status badge
        status_text = "Active" if employee.is_active else "Inactive"
        status_color = "green" if employee.is_active else "red"

        status_label = ctk.CTkLabel(
            info_frame,
            text=status_text,
            text_color=status_color,
            font=ctk.CTkFont(size=10)
        )
        status_label.pack(side="right", padx=10)

        # Preferences summary
        prefs_text = f"Off shifts: {len(employee.preferences.off_shifts)}"
        if employee.preferences.preferred_shift_types != ["both"]:
            prefs_text += f" | Pref: {', '.join(employee.preferences.preferred_shift_types)}"

        prefs_label = ctk.CTkLabel(
            info_frame,
            text=prefs_text,
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        prefs_label.pack(side="left", padx=20)

        # Action buttons
        button_frame = ctk.CTkFrame(item_frame)
        button_frame.pack(fill="x", padx=5, pady=(0, 5))

        edit_button = ctk.CTkButton(
            button_frame,
            text="Edit",
            width=60,
            height=25,
            command=lambda: self._edit_employee(employee)
        )
        edit_button.pack(side="left", padx=5)

        if employee.is_active:
            deactivate_button = ctk.CTkButton(
                button_frame,
                text="Deactivate",
                width=80,
                height=25,
                fg_color="orange",
                command=lambda: self._toggle_employee_status(employee)
            )
            deactivate_button.pack(side="left", padx=5)
        else:
            activate_button = ctk.CTkButton(
                button_frame,
                text="Activate",
                width=80,
                height=25,
                fg_color="green",
                command=lambda: self._toggle_employee_status(employee)
            )
            activate_button.pack(side="left", padx=5)

        delete_button = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=60,
            height=25,
            fg_color="red",
            command=lambda: self._delete_employee(employee)
        )
        delete_button.pack(side="right", padx=5)

        # Make item clickable
        item_frame.bind("<Button-1>", lambda e: self._select_employee(employee))
        for child in item_frame.winfo_children():
            child.bind("<Button-1>", lambda e: self._select_employee(employee))

    def _select_employee(self, employee: Employee):
        """Handle employee selection"""
        self.selected_employee = employee
        if self.on_employee_selected:
            self.on_employee_selected(employee)

    def _add_employee(self):
        """Handle add employee action"""
        if self.on_add_employee:
            self.on_add_employee()

    def _edit_employee(self, employee: Employee):
        """Handle edit employee action"""
        if self.on_employee_selected:
            self.on_employee_selected(employee)

    def _toggle_employee_status(self, employee: Employee):
        """Toggle employee active status"""
        new_status = not employee.is_active
        if self.data_manager.update_employee(employee.id, is_active=new_status):
            logger.info(f"Employee {employee.name} was toggled.")
            self._load_employees()
            messagebox.showinfo("Success", f"Employee {employee.name} {'activated' if new_status else 'deactivated'}")
        else:
            logger.error(f"Failed to update status for employee {employee.name}")
            messagebox.showerror("Error", "Failed to update employee status")

    def _delete_employee(self, employee: Employee):
        """Handle employee deletion"""
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {employee.name}?"):
            if self.data_manager.delete_employee(employee.id):
                if self.data_manager.save_data():
                    logger.info(f"Employee '{employee.name}' (ID: {employee.id}) was successfully deleted by the user.")
                    self._load_employees()
                    messagebox.showinfo("Success", f"Employee {employee.name} deleted")
                else:
                    logger.error(f"Failed to save data after deleting employee {employee.name}")
                    messagebox.showerror("Error", "Failed to save changes. Employee may not be properly deleted.")
            else:
                logger.error(f"Failed to delete employee {employee.name}")
                messagebox.showerror("Error", "Failed to delete employee")
        else:
            pass

    def _on_filter_change(self, value):
        """Handle filter change"""
        self._load_employees()

    def refresh(self):
        """Refresh the employee list"""
        self._load_employees()


class EmployeeManagementWindow(ctk.CTkToplevel):
    """Main window for employee management"""

    def __init__(self, parent, data_manager: DataManager):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_employee = None

        self.title("Employee Management")
        self.geometry("1200x800")
        self.transient(parent)
        self.grab_set()

        self._create_widgets()
        self._setup_layout()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        # Main container
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel - Employee list
        self.list_panel = ctk.CTkFrame(self.main_frame, width=400)
        self.list_panel.pack(side="left", fill="y", padx=(0, 5), pady=5)
        self.list_panel.pack_propagate(False)

        self.employee_list = EmployeeList(
            self.list_panel,
            self.data_manager,
            on_employee_selected=self._on_employee_selected,
            on_add_employee=self._on_add_employee
        )
        self.employee_list.pack(fill="both", expand=True, padx=5, pady=5)

        # Right panel - Employee details/form
        self.details_panel = ctk.CTkFrame(self.main_frame)
        self.details_panel.pack(side="right", fill="both", expand=True, padx=(5, 0), pady=5)

        # Initially show welcome message
        self._show_welcome_message()

    def _setup_layout(self):
        """Setup responsive layout"""
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=2)
        self.main_frame.rowconfigure(0, weight=1)

    def _show_welcome_message(self):
        """Show welcome message when no employee is selected"""
        # Clear details panel
        for widget in self.details_panel.winfo_children():
            widget.destroy()

        welcome_frame = ctk.CTkFrame(self.details_panel)
        welcome_frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            welcome_frame,
            text="👥 Employee Management",
            font=ctk.CTkFont(size=24, weight="bold")
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            welcome_frame,
            text="Select an employee from the list to view/edit details,\nor click 'Add Employee' to create a new one.",
            font=ctk.CTkFont(size=14)
        ).pack(pady=20)

        # Quick stats
        stats_frame = ctk.CTkFrame(welcome_frame)
        stats_frame.pack(fill="x", padx=20, pady=20)

        employees = self.data_manager.get_employees(active_only=False)
        active_count = len([e for e in employees if e.is_active])
        high_exp_count = len([e for e in employees if e.experience == "High" and e.is_active])

        stats_text = f"""
        Total Employees: {len(employees)}
        Active Employees: {active_count}
        High Experience: {high_exp_count}
        Low Experience: {active_count - high_exp_count}
        """

        ctk.CTkLabel(
            stats_frame,
            text=stats_text,
            font=ctk.CTkFont(size=12),
            justify="left"
        ).pack(pady=10)

    def _on_employee_selected(self, employee: Employee):
        """Handle employee selection for editing"""
        self.current_employee = employee
        self._show_employee_form(employee)

    def _on_add_employee(self):
        """Handle add new employee"""
        self.current_employee = None
        self._show_employee_form(None)

    def _show_employee_form(self, employee: Employee = None):
        """Show employee form for add/edit"""
        # Clear details panel
        for widget in self.details_panel.winfo_children():
            widget.destroy()

        # Create form
        self.employee_form = EmployeeForm(
            self.details_panel,
            self.data_manager,
            employee,
            on_save=self._on_employee_saved,
            on_cancel=self._on_form_cancelled
        )
        self.employee_form.pack(fill="both", expand=True, padx=5, pady=5)

    def _on_employee_saved(self, employee_data: Dict):
        """Handle employee save"""
        try:
            if self.current_employee:
                # Update existing employee
                success = self.data_manager.update_employee(
                    self.current_employee.id,
                    name=employee_data["name"],
                    experience=employee_data["experience"],
                    is_active=employee_data["is_active"],
                    preferences=employee_data["preferences"]
                )
                if success:
                    # Save data to persist changes
                    self.data_manager.save_data()
                    messagebox.showinfo("Success", f"Employee {employee_data['name']} updated successfully")
                else:
                    logger.error("Failed to update employee")
                    messagebox.showerror("Error", "Failed to update employee")
            else:
                # Add new employee
                new_employee = self.data_manager.add_employee(
                    name=employee_data["name"],
                    experience=employee_data["experience"],
                    is_active=employee_data["is_active"],
                    preferences=employee_data["preferences"]
                )
                # Save data to persist changes
                self.data_manager.save_data()
                messagebox.showinfo("Success", f"Employee {new_employee.name} added successfully")

            # Refresh list and show welcome
            self.employee_list.refresh()
            self._show_welcome_message()

        except Exception as e:
            logger.error(f"Failed to save employee: {str(e)}")
            messagebox.showerror("Error", f"Failed to save employee: {str(e)}")

    def _on_form_cancelled(self):
        """Handle form cancellation"""
        self._show_welcome_message()


class DashboardPanel(ctk.CTkFrame):
    """Dashboard showing statistics and violations"""

    def __init__(self, parent, data_manager: DataManager):
        super().__init__(parent, width=350)
        self.data_manager = data_manager

        self._create_widgets()
    
    def _create_widgets(self):
        # Title
        title_label = ctk.CTkLabel(
            self,
            text="Dashboard",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(10, 20))
        
        # Statistics frame
        self.stats_frame = ctk.CTkScrollableFrame(self, height=200)
        self.stats_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Experience filter
        filter_frame = ctk.CTkFrame(self)
        filter_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(filter_frame, text="Filter by Experience:").pack(side="left", padx=10)
        
        self.experience_filter = ctk.StringVar(value="All")
        filter_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["All", "High", "Low"],
            variable=self.experience_filter,
            command=self._on_filter_change
        )
        filter_menu.pack(side="left", padx=10)
    
    def _on_filter_change(self, value):
        """Handle experience filter change"""
        self.update_dashboard()
    
    def update_dashboard(self, month_key: str = None):
        """Update dashboard with current statistics"""
        if not month_key:
            now = datetime.now()
            month_key = f"{now.year}-{now.month:02d}"
        
        # Clear existing stats
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        
        # Get statistics
        emp_stats = self.data_manager.calculate_employee_stats(month_key)
        team_stats = self.data_manager.get_team_stats(month_key)
        
        # Filter by experience if needed
        filter_exp = self.experience_filter.get()
        if filter_exp != "All":
            emp_stats = {name: stats for name, stats in emp_stats.items() 
                        if stats["experience"] == filter_exp}
        
        # Team summary
        team_frame = ctk.CTkFrame(self.stats_frame)
        team_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            team_frame,
            text="Team Summary",
            font=ctk.CTkFont(weight="bold")
        ).pack(pady=5)
        
        summary_text = f"""
        Total Employees: {team_stats['total_employees']}
        High Experience: {team_stats['high_experience_count']}
        Low Experience: {team_stats['low_experience_count']}
        Total Shifts: {team_stats['total_shifts_assigned']}
        Quota Violations: {team_stats['quota_violations']}
        """
        
        ctk.CTkLabel(team_frame, text=summary_text, justify="left").pack(pady=5)
        
        # Individual employee stats
        for emp_name, stats in emp_stats.items():
            emp_frame = ctk.CTkFrame(self.stats_frame)
            emp_frame.pack(fill="x", pady=2)
            
            exp_badge = "★" if stats["experience"] == "High" else "○"
            
            # Employee header
            header_text = f"{exp_badge} {emp_name} ({stats['experience']})"
            ctk.CTkLabel(
                emp_frame,
                text=header_text,
                font=ctk.CTkFont(weight="bold")
            ).pack(anchor="w", padx=10, pady=2)
            
            # Stats
            stats_text = f"Shifts: {stats['total_shifts']} | Quota: {stats['quota']} | Deviation: {stats['quota_deviation']:+d}"
            ctk.CTkLabel(emp_frame, text=stats_text).pack(anchor="w", padx=20, pady=2)
            
            # Color code based on quota deviation
            if stats['quota_deviation'] > 0:
                emp_frame.configure(fg_color="lightcoral")
            elif stats['quota_deviation'] < 0:
                emp_frame.configure(fg_color="lightyellow")
            else:
                emp_frame.configure(fg_color="lightgreen")


class MainWindow(ctk.CTk):
    """Main application window"""
    
    # ADD arguments to accept the dependencies
    def __init__(self, data_manager: DataManager, scheduler: ShiftScheduler):
        super().__init__()
        
        self.title("Shift Scheduling System")
        self.geometry("1400x900")
        
        # REMOVE the lines that create new instances
        # self.data_manager = DataManager()
        # self.scheduler = ShiftScheduler(self.data_manager)
        
        # ADD these lines to store the passed-in instances
        self.data_manager = data_manager
        self.scheduler = scheduler
        
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        
        self._create_widgets()
        self._load_initial_data()
    
    def _create_widgets(self):
        # Top control panel
        control_frame = ctk.CTkFrame(self, height=80)
        control_frame.pack(fill="x", padx=10, pady=10)
        control_frame.pack_propagate(False)
        
        # Month/Year selectors
        ctk.CTkLabel(control_frame, text="Month:").pack(side="left", padx=10)
        
        self.month_var = ctk.StringVar(value=str(self.current_month))
        month_menu = ctk.CTkOptionMenu(
            control_frame,
            values=[str(i) for i in range(1, 13)],
            variable=self.month_var,
            command=self._on_month_change,
            width=80
        )
        month_menu.pack(side="left", padx=5)
        
        ctk.CTkLabel(control_frame, text="Year:").pack(side="left", padx=10)
        
        self.year_var = ctk.StringVar(value=str(self.current_year))
        year_menu = ctk.CTkOptionMenu(
            control_frame,
            values=[str(i) for i in range(2024, 2030)],
            variable=self.year_var,
            command=self._on_year_change,
            width=80
        )
        year_menu.pack(side="left", padx=5)
        
        # Action buttons
        ctk.CTkButton(
            control_frame,
            text="Generate Schedule",
            command=self._generate_schedule,
            width=150
        ).pack(side="left", padx=20)

        ctk.CTkButton(
            control_frame,
            text="Clear Future Schedules",
            command=self._clear_future_schedules,
            width=170,
            fg_color="orange"
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            control_frame,
            text="Manage Employees",
            command=self._manage_employees,
            width=150
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            control_frame,
            text="Export",
            command=self._export_schedule,
            width=100
        ).pack(side="left", padx=10)
        
        # Main content area
        content_frame = ctk.CTkFrame(self)
        content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Calendar view (left side)
        self.calendar_view = CalendarView(content_frame, self.data_manager, self)
        self.calendar_view.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # Dashboard (right side)
        self.dashboard = DashboardPanel(content_frame, self.data_manager)
        self.dashboard.pack(side="right", fill="y", padx=(5, 0))
        
        # Status bar
        self.status_var = ctk.StringVar(value="Ready")
        status_bar = ctk.CTkLabel(self, textvariable=self.status_var)
        status_bar.pack(side="bottom", fill="x", padx=10, pady=5)
    
    def _load_initial_data(self):
        """Load initial data and update displays"""
        self.calendar_view.set_month(self.current_year, self.current_month)
        self.dashboard.update_dashboard()
        self.status_var.set("Data loaded successfully")
    
    def _on_month_change(self, value):
        """Handle month selection change"""
        self.current_month = int(value)
        self.calendar_view.set_month(self.current_year, self.current_month)
        self.dashboard.update_dashboard(f"{self.current_year}-{self.current_month:02d}")
    
    def _on_year_change(self, value):
        """Handle year selection change"""
        self.current_year = int(value)
        self.calendar_view.set_month(self.current_year, self.current_month)
        self.dashboard.update_dashboard(f"{self.current_year}-{self.current_month:02d}")
    
    def _generate_schedule(self):
        """Generate schedule for current month with partial generation support"""
        # Check if partial generation is needed
        scope_info = self._get_partial_generation_scope()
        if scope_info['is_partial']:
            # Directly proceed with partial generation
            self._proceed_with_generation(partial_generation=True)
        else:
            # No partial needed, proceed with full generation
            self._proceed_with_generation(partial_generation=False)

    def _get_partial_generation_scope(self) -> Dict:
        """Determine if partial generation is needed and get scope information"""
        today = date.today()
        month_key = f"{self.current_year}-{self.current_month:02d}"
        existing_schedule = self.data_manager.get_schedule(month_key) or {}

        # Check if this is the current month
        is_current_month = (self.current_year == today.year and self.current_month == today.month)

        scope_info = {
            'is_partial': False,
            'current_date': today.strftime("%Y-%m-%d"),
            'existing_assignments': 0,
            'start_day': 1,
            'end_day': calendar.monthrange(self.current_year, self.current_month)[1],
            'includes_past': False
        }

        if is_current_month and existing_schedule:
            # Count existing assignments for past days
            for day in range(1, today.day + 1):
                date_str = date(self.current_year, self.current_month, day).strftime("%Y-%m-%d")
                day_schedule = existing_schedule.get(date_str, {})
                if day_schedule.get("day_shift") is not None or day_schedule.get("night_shift") is not None:
                    scope_info['existing_assignments'] += 1
                    scope_info['is_partial'] = True

            if scope_info['is_partial']:
                scope_info['start_day'] = today.day + 1
                # Check if there are unfilled past dates
                for day in range(1, today.day + 1):
                    date_str = date(self.current_year, self.current_month, day).strftime("%Y-%m-%d")
                    day_schedule = existing_schedule.get(date_str, {})
                    if day_schedule.get("day_shift") is None or day_schedule.get("night_shift") is None:
                        scope_info['includes_past'] = True
                        break

        return scope_info
    
    def _clear_future_schedules(self):
        """Clear all future schedule assignments for the current month"""
        month_key = f"{self.current_year}-{self.current_month:02d}"

        # Get information about what will be cleared
        clear_info = self._get_clear_schedule_info(month_key)

        if clear_info["cleared_count"] == 0:
            messagebox.showinfo("No Future Schedules", "There are no future schedule assignments to clear for the current month.")
            return

        # Show confirmation dialog
        dialog = ClearScheduleDialog(self, month_key, clear_info, self._handle_clear_choice)

    def _get_clear_schedule_info(self, month_key: str) -> Dict:
        """Get information about future schedules that would be cleared"""
        year, month = map(int, month_key.split('-'))
        today = date.today()

        schedule = self.data_manager.get_schedule(month_key)

        if not schedule:
            return {
                "cleared_count": 0,
                "affected_dates": [],
                "message": "No schedule found for the specified month"
            }

        cleared_count = 0
        affected_dates = []

        # Count assignments that would be cleared (only future dates)
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
                    logger.error(f"Invalid date format: {date_str}")
                    continue
            except (ValueError, IndexError) as e:
                logger.error(f"Failed to parse date {date_str}: {e}")
                continue
        
            # Only count future dates
            if schedule_date > today:
                day_shift = day_schedule.get("day_shift")
                night_shift = day_schedule.get("night_shift")

                if day_shift is not None or night_shift is not None:
                    cleared_count += 1
                    affected_dates.append(date_str)

        if cleared_count == 0:
            return {
                "cleared_count": 0,
                "affected_dates": [],
                "message": "No future schedule assignments to clear"
            }

        return {
            "cleared_count": cleared_count,
            "affected_dates": affected_dates,
            "message": f"Would clear {cleared_count} future schedule assignments"
        }

    def _handle_clear_choice(self, choice: str):
        """Handle user's choice from the clear schedule dialog"""
        if choice == "cancel":
            self.status_var.set("Clear future schedules cancelled by user")
        elif choice == "clear":
            self.status_var.set("Clearing future schedules...")
            self.update()

            def clear_schedules():
                try:
                    month_key = f"{self.current_year}-{self.current_month:02d}"
                    result = self.data_manager.clear_future_schedules(month_key)

                    # Update displays
                    self.after(0, self._update_after_clear, result)

                except Exception as e:
                    logger.error(f"Error in clear_schedules: {str(e)}")
                    self.after(0, lambda: self.status_var.set(f"Error: {str(e)}"))

            # Run in background thread
            threading.Thread(target=clear_schedules, daemon=True).start()

    def _update_after_clear(self, result: Dict):
        """Update UI after clearing schedules"""
        cleared_count = result.get("cleared_count", 0)
        message = result.get("message", "")

        self.calendar_view.update_schedule_display()
        self.dashboard.update_dashboard(f"{self.current_year}-{self.current_month:02d}")

        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} future schedule assignments for month {self.current_year}-{self.current_month:02d}")
            self.status_var.set(f"Future schedules cleared: {message}")
            messagebox.showinfo("Schedules Cleared",
                              f"✅ Future schedule assignments have been cleared successfully.\n\n"
                              f"• Assignments cleared: {cleared_count}\n"
                              f"• Calendar and dashboard updated")
        else:
            self.status_var.set("No future schedules to clear")
            messagebox.showinfo("No Changes", "No future schedule assignments were found to clear.")

    def _proceed_with_generation(self, partial_generation: bool):
        """Proceed with schedule generation"""
        generation_type = "partial" if partial_generation else "full"
        self.status_var.set(f"Generating {generation_type} schedule...")
        self.update()

        def generate():
            try:
                result = self.scheduler.generate_schedule(
                    self.current_year,
                    self.current_month,
                    allow_quota_violations=False,
                    emergency_mode=False,
                    partial_generation=partial_generation
                )

                # Update displays
                self.after(0, self._update_after_generation, result)

            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"Error: {str(e)}"))

        # Run in background thread
        threading.Thread(target=generate, daemon=True).start()
    
    def _update_after_generation(self, result: ScheduleResult):
        """Update UI after schedule generation"""
        self.calendar_view.update_schedule_display()
        self.dashboard.update_dashboard(f"{self.current_year}-{self.current_month:02d}")

        if result.success:
            self.status_var.set(f"Schedule generated: {result.message}")

            # Provide detailed feedback based on generation type and results
            feedback_message = f"✅ Schedule Generation Complete\n\n{result.message}"

            if result.violations:
                feedback_message += f"\n\n⚠️ Constraint Violations Detected: {len(result.violations)}"
                feedback_message += "\n\nViolations:"
                for violation in result.violations[:5]:  # Show first 5 violations
                    feedback_message += f"\n• {violation}"
                if len(result.violations) > 5:
                    feedback_message += f"\n• ... and {len(result.violations) - 5} more"

            # Check if this was partial generation
            if "partial" in result.message.lower():
                feedback_message += "\n\n📅 Partial Generation Summary:"
                feedback_message += "\n• Existing assignments preserved"
                feedback_message += "\n• Future dates optimized"
                feedback_message += "\n• Quotas adjusted for remaining period"
            else:
                feedback_message += "\n\n📅 Full Generation Summary:"
                feedback_message += "\n• Complete month regenerated"
                feedback_message += "\n• All assignments replaced"

            messagebox.showinfo("Schedule Generation Complete", feedback_message)
        else:
            self.status_var.set(f"Generation failed: {result.message}")
            error_message = f"❌ Schedule Generation Failed\n\n{result.message}"

            if result.violations:
                error_message += f"\n\nIssues encountered: {len(result.violations)} constraint violations"

            messagebox.showerror("Schedule Generation Failed", error_message)
    
    def _manage_employees(self):
        """Open employee management window"""
        EmployeeManagementWindow(self, self.data_manager)
    
    def _export_schedule(self):
        """Export current schedule to PDF, Excel, or CSV."""
        try:
            export_manager = ExportManager(self.data_manager)

            month_name = calendar.month_name[self.current_month].lower()
            initial_filename = f"shift_schedule_{month_name}_{self.current_year}"

            output_path = filedialog.asksaveasfilename(
                initialfile=initial_filename,
                defaultextension=".pdf",
                filetypes=[
                    ("PDF files", "*.pdf"),
                    ("Excel files", "*.xlsx"),
                    ("CSV files", "*.csv"),
                    ("All files", "*.*")
                ],
                title="Export Schedule"
            )

            if not output_path:
                return  # User cancelled

            # Determine format from extension
            file_extension = output_path.split('.')[-1].lower()
            if file_extension == "xlsx":
                format_type = "excel"
            elif file_extension == "csv":
                format_type = "csv"
            else:
                format_type = "pdf"

            success = export_manager.export_calendar(
                self.current_year,
                self.current_month,
                format_type,
                output_path,
                self.schedule_result if hasattr(self, 'schedule_result') and self.schedule_result else None
            )

            if success:
                messagebox.showinfo("Export Successful", f"Schedule exported successfully to:\n{output_path}")
            else:
                messagebox.showerror("Export Failed", "Failed to export schedule. Please check the file path and try again.")

        except Exception as e:
            messagebox.showerror("Export Error", f"An error occurred during export:\n{str(e)}")


def main():
    """Main entry point for the UI"""
    # For standalone execution, create the necessary dependencies first
    data_manager = DataManager()
    scheduler = ShiftScheduler(data_manager)
    # Pass the instances when creating the app
    app = MainWindow(data_manager=data_manager, scheduler=scheduler)
    app.mainloop()


if __name__ == "__main__":
    main()
