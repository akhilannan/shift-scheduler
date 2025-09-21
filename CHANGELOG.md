### Added

- **Initial Release:** First public version of the Shift Scheduler application.

- **Core Scheduling Features:**
  - Automated, constraint-based schedule generation using a CP-SAT solver.
  - Experience-based shift allocation with configurable monthly quotas for 'High' and 'Low' experience levels.
  - Enforcement of critical scheduling rules, including required rest periods after night shifts.
  - Support for generating schedules for months of 28, 29, 30, and 31 days.

- **User Interface (UI):**
  - Modern desktop GUI built with CustomTkinter.
  - Interactive monthly calendar view for visualizing the complete schedule.
  - Ability to perform manual shift assignments and adjustments directly from the calendar.
  - Real-time dashboard panel displaying team and individual statistics with filtering capabilities.

- **Employee Management:**
  - Full CRUD (Create, Read, Update, Delete) functionality for employees.
  - Ability to set employee experience levels, active status, and individual preferences (off-shifts, custom quotas).

- **Data and Reporting:**
  - All application data (employees, schedules, settings) is persisted in a local `schedule_data.json` file.
  - Comprehensive export functionality to generate professional reports in **PDF**, **Excel (.xlsx)**, and **CSV** formats.

- **Development & Release Workflow:**
  - Automated build and release process using a GitHub Actions pipeline.
  - Integrated `pytest` test suite execution as a quality gate in the CI/CD pipeline.
  - Automatic packaging of a Windows executable (`.exe`) with a custom icon and a source code archive for each release.