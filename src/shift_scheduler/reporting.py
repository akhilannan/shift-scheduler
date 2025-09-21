"""
Reporting and Export Module for Shift Scheduling System

Handles PDF, Excel, and CSV export functionality with experience-based
statistics and comprehensive reporting capabilities.
"""

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime, date
import calendar
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from .data_manager import DataManager, Employee
from .scheduler_logic import ScheduleResult


class ReportGenerator:
    """Main class for generating reports and exports"""
    
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom report styles"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center alignment
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12
        ))
    
    def export_calendar_pdf(self, year: int, month: int, output_path: str,
                           schedule_result: Optional['ScheduleResult'] = None) -> bool:
        """Export monthly calendar to PDF with deviation tracking"""
        try:
            doc = SimpleDocTemplate(
                output_path,
                pagesize=landscape(A4),
                rightMargin=0.5*inch,
                leftMargin=0.5*inch,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch
            )

            story = []

            # Title with optimization info
            month_name = calendar.month_name[month]
            title_text = f"Shift Schedule - {month_name} {year}"
            if schedule_result:
                if schedule_result.success:
                    title_text += " (Optimized)"
                else:
                    title_text += " (Manual/Partial)"

            title = Paragraph(title_text, self.styles['CustomTitle'])
            story.append(title)
            story.append(Spacer(1, 20))

            # Optimization summary if available
            if schedule_result:
                opt_summary = self._create_optimization_summary(schedule_result)
                story.append(opt_summary)
                story.append(Spacer(1, 20))

            # Calendar table
            calendar_table = self._create_calendar_table(year, month, schedule_result)
            story.append(calendar_table)

            # Legend
            story.append(Spacer(1, 20))
            legend = self._create_legend()
            story.append(legend)

            # Statistics
            story.append(PageBreak())
            stats_content = self._create_statistics_content(year, month, schedule_result)
            story.extend(stats_content)

            doc.build(story)
            return True

        except Exception as e:
            logging.error(f"Error creating PDF: {e}", exc_info=True)
            return False
    
    def _create_calendar_table(self, year: int, month: int,
                              schedule_result: Optional[ScheduleResult] = None) -> Table:
        """Create calendar table for PDF"""
        # Get schedule data
        month_key = f"{year}-{month:02d}"
        if schedule_result:
            schedule = schedule_result.schedule
        else:
            schedule = self.data_manager.get_schedule(month_key)
        
        # Create calendar data
        cal = calendar.monthcalendar(year, month)
        
        # Table header
        data = [['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']]
        
        for week in cal:
            week_data = []
            for day in week:
                if day == 0:
                    week_data.append('')
                else:
                    cell_content = self._format_calendar_cell(year, month, day, schedule)
                    week_data.append(cell_content)
            data.append(week_data)
        
        # Create table
        table = Table(data, colWidths=[1.2*inch]*7, rowHeights=[1*inch]*(len(data)))
        
        # Table style
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        return table
    
    def _format_calendar_cell(self, year: int, month: int, day: int, 
                             schedule: Dict[str, Dict[str, Optional[int]]]) -> str:
        """Format individual calendar cell content"""
        date_obj = date(year, month, day)
        date_str = date_obj.strftime("%Y-%m-%d")
        day_data = schedule.get(date_str, {})
        
        content = f"<b>{day}</b><br/>"
        
        # Day shift
        day_emp_id = day_data.get("day_shift")
        if day_emp_id:
            emp = self.data_manager.get_employee_by_id(day_emp_id)
            if emp:
                exp_badge = "★" if emp.experience == "High" else "○"
                content += f"Day: {exp_badge}{emp.name}<br/>"
            else:
                content += "Day: Unknown<br/>"
        else:
            content += "Day: ---<br/>"
        
        # Night shift
        night_emp_id = day_data.get("night_shift")
        if night_emp_id:
            emp = self.data_manager.get_employee_by_id(night_emp_id)
            if emp:
                exp_badge = "★" if emp.experience == "High" else "○"
                content += f"Night: {exp_badge}{emp.name}"
            else:
                content += "Night: Unknown"
        else:
            content += "Night: ---"
        
        return Paragraph(content, self.styles['Normal'])
    
    def _create_legend(self) -> Table:
        """Create legend for PDF"""
        legend_data = [
            ['Legend'],
            ['★ High Experience Employee'],
            ['○ Low Experience Employee'],
            ['--- Unassigned Shift']
        ]
        
        legend_table = Table(legend_data, colWidths=[3*inch])
        legend_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        return legend_table
    
    def _create_statistics_content(self, year: int, month: int,
                                  schedule_result: Optional[ScheduleResult] = None) -> List:
        """Create statistics content for PDF with deviation tracking"""
        content = []
        month_key = f"{year}-{month:02d}"

        # Title
        title = Paragraph("Schedule Statistics", self.styles['CustomTitle'])
        content.append(title)
        content.append(Spacer(1, 20))

        # Get statistics from ScheduleResult or calculate
        if schedule_result and schedule_result.statistics:
            emp_stats = schedule_result.statistics
            team_stats = self._calculate_team_stats_from_emp_stats(emp_stats, month_key)
        else:
            emp_stats = self.data_manager.calculate_employee_stats(month_key)
            team_stats = self.data_manager.get_team_stats(month_key)
        
        # Team summary with experience buckets
        team_heading = Paragraph("Team Summary", self.styles['CustomHeading'])
        content.append(team_heading)

        # Get bucket information
        buckets = self.data_manager.get_experience_buckets()
        year_val, month_val = map(int, month_key.split('-'))
        days_in_month = calendar.monthrange(year_val, month_val)[1]

        team_data = [
            ['Metric', 'Value'],
            ['Total Employees', str(team_stats['total_employees'])],
            ['High Experience Employees', str(team_stats['high_experience_count'])],
            ['Low Experience Employees', str(team_stats['low_experience_count'])],
            ['Total Shifts Assigned', str(team_stats['total_shifts_assigned'])],
            ['Total Quota', str(team_stats['total_quota'])],
            ['Quota Violations', str(team_stats['quota_violations'])],
        ]

        # Add bucket targets if available
        if 'bucket_targets' in team_stats:
            high_target = team_stats['bucket_targets'].get('High', 0)
            low_target = team_stats['bucket_targets'].get('Low', 0)
            team_data.extend([
                ['High Exp Target', str(high_target)],
                ['Low Exp Target', str(low_target)],
                ['High Exp Deviation', f"{team_stats.get('high_exp_target_deviation', 0):+d}"],
                ['Low Exp Deviation', f"{team_stats.get('low_exp_target_deviation', 0):+d}"],
            ])
        
        team_table = Table(team_data, colWidths=[3*inch, 2*inch])
        team_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        content.append(team_table)
        content.append(Spacer(1, 20))
        
        # Individual employee statistics
        emp_heading = Paragraph("Individual Employee Statistics", self.styles['CustomHeading'])
        content.append(emp_heading)

        emp_data = [['Employee', 'Experience', 'Day Shifts', 'Night Shifts', 'Total', 'Quota', 'Deviation', 'Flag']]

        for emp_name, stats in emp_stats.items():
            flag_info = ""
            if stats.get('deviation_flag'):
                flag = stats['deviation_flag']
                flag_info = f"{flag['severity'].upper()}\n{flag['description']}"

            emp_data.append([
                emp_name,
                stats['experience'],
                str(stats['day_shifts']),
                str(stats['night_shifts']),
                str(stats['total_shifts']),
                str(stats['quota']),
                f"{stats['quota_deviation']:+d}",
                flag_info
            ])

        emp_table = Table(emp_data, colWidths=[1.0*inch, 0.8*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.7*inch, 2.0*inch])
        emp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # Color code deviations with severity-based coloring
        for i, (emp_name, stats) in enumerate(emp_stats.items(), 1):
            if stats.get('deviation_flag'):
                flag = stats['deviation_flag']
                if flag['severity'] == 'high':
                    bg_color = colors.lightcoral
                elif flag['severity'] == 'medium':
                    bg_color = colors.orange
                elif flag['severity'] == 'low':
                    bg_color = colors.lightyellow
                else:
                    bg_color = colors.white

                emp_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, i), (-1, i), bg_color)
                ]))

        content.append(emp_table)

        # Add deviation summary section
        content.append(Spacer(1, 20))
        deviation_heading = Paragraph("Deviation Summary", self.styles['CustomHeading'])
        content.append(deviation_heading)

        team_stats = self.data_manager.get_team_stats(month_key)
        deviation_data = [
            ['Severity', 'Count', 'Description'],
            ['High', str(len(team_stats.get('high_severity_deviations', []))), 'Significant quota violations'],
            ['Medium', str(len(team_stats.get('medium_severity_deviations', []))), 'Moderate quota deviations'],
            ['Low', str(len(team_stats.get('low_severity_deviations', []))), 'Minor quota adjustments']
        ]

        deviation_table = Table(deviation_data, colWidths=[1*inch, 1*inch, 3*inch])
        deviation_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        content.append(deviation_table)
        
        return content

    def _create_optimization_summary(self, schedule_result: ScheduleResult) -> Table:
        """Create optimization summary table for PDF"""
        summary_data = [
            ['Optimization Summary'],
            ['Status', 'Success' if schedule_result.success else 'Failed'],
            ['Method', 'CP-SAT' if 'CP-SAT' in schedule_result.message else 'Backtracking'],
            ['Violations', str(len(schedule_result.violations))],
            ['Message', schedule_result.message]
        ]

        summary_table = Table(summary_data, colWidths=[2*inch, 3*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        return summary_table

    def _calculate_team_stats_from_emp_stats(self, emp_stats: Dict[str, Dict[str, Any]], month_key: str) -> Dict[str, Any]:
        """Calculate team statistics from employee statistics"""
        high_exp_employees = [s for s in emp_stats.values() if s.get("experience") == "High"]
        low_exp_employees = [s for s in emp_stats.values() if s.get("experience") == "Low"]

        # Get bucket targets
        year, month = map(int, month_key.split('-'))
        days_in_month = calendar.monthrange(year, month)[1]
        buckets = self.data_manager.get_experience_buckets()

        bucket_targets = {}
        for exp_level, bucket in buckets.items():
            target = bucket.target_shifts.get(str(days_in_month), 0)
            bucket_targets[exp_level] = target

        # Collect deviation flags
        deviation_flags = []
        for emp_stat in emp_stats.values():
            if emp_stat.get("deviation_flag"):
                flag = emp_stat["deviation_flag"]
                deviation_flags.append({
                    "employee_name": emp_stat.get("name", ""),
                    "deviation_type": flag['deviation_type'],
                    "deviation_units": flag['deviation_units'],
                    "severity": flag['severity'],
                    "description": flag['description']
                })

        return {
            "total_employees": len(emp_stats),
            "high_experience_count": len(high_exp_employees),
            "low_experience_count": len(low_exp_employees),
            "total_shifts_assigned": sum(s.get("total_shifts", 0) for s in emp_stats.values()),
            "total_quota": sum(s.get("quota", 0) for s in emp_stats.values()),
            "high_exp_shifts": sum(s.get("total_shifts", 0) for s in high_exp_employees),
            "low_exp_shifts": sum(s.get("total_shifts", 0) for s in low_exp_employees),
            "bucket_targets": bucket_targets,
            "high_exp_target": bucket_targets.get("High", 0),
            "low_exp_target": bucket_targets.get("Low", 0),
            "high_exp_target_deviation": sum(s.get("total_shifts", 0) for s in high_exp_employees) - bucket_targets.get("High", 0),
            "low_exp_target_deviation": sum(s.get("total_shifts", 0) for s in low_exp_employees) - bucket_targets.get("Low", 0),
            "quota_violations": len([s for s in emp_stats.values() if s.get("quota_deviation", 0) != 0]),
            "over_quota_employees": [s.get("name", "") for s in emp_stats.values() if s.get("quota_deviation", 0) > 0],
            "under_quota_employees": [s.get("name", "") for s in emp_stats.values() if s.get("quota_deviation", 0) < 0],
            "deviation_flags": deviation_flags,
            "high_severity_deviations": [f for f in deviation_flags if f["severity"] == "high"],
            "medium_severity_deviations": [f for f in deviation_flags if f["severity"] == "medium"],
            "low_severity_deviations": [f for f in deviation_flags if f["severity"] == "low"]
        }
    
    def export_schedule_excel(self, year: int, month: int, output_path: str,
                             schedule_result: Optional[ScheduleResult] = None) -> bool:
        """Export schedule to Excel format with deviation tracking"""
        try:
            month_key = f"{year}-{month:02d}"

            # Get schedule data
            if schedule_result:
                schedule = schedule_result.schedule
            else:
                schedule = self.data_manager.get_schedule(month_key)

            # Create Excel writer
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Schedule sheet
                schedule_df = self._create_schedule_dataframe(year, month, schedule)
                schedule_df.to_excel(writer, sheet_name='Schedule', index=False)

                # Statistics sheet with deviations
                stats_df = self._create_statistics_dataframe(month_key, schedule_result)
                stats_df.to_excel(writer, sheet_name='Statistics', index=False)

                # Employee details sheet
                emp_df = self._create_employee_dataframe()
                emp_df.to_excel(writer, sheet_name='Employees', index=False)

                # Optimization sheet if available
                if schedule_result:
                    opt_df = self._create_optimization_dataframe(schedule_result)
                    opt_df.to_excel(writer, sheet_name='Optimization', index=False)

                # Format worksheets
                self._format_excel_worksheets(writer)

            return True

        except Exception as e:
            logging.error(f"Error exporting to Excel: {e}", exc_info=True)
            return False
    
    def _create_schedule_dataframe(self, year: int, month: int, 
                                  schedule: Dict[str, Dict[str, Optional[int]]]) -> pd.DataFrame:
        """Create schedule DataFrame for Excel export"""
        data = []
        days_in_month = calendar.monthrange(year, month)[1]
        
        for day in range(1, days_in_month + 1):
            date_obj = date(year, month, day)
            date_str = date_obj.strftime("%Y-%m-%d")
            day_data = schedule.get(date_str, {})
            
            # Get employee names
            day_emp_id = day_data.get("day_shift")
            night_emp_id = day_data.get("night_shift")
            
            day_emp = self.data_manager.get_employee_by_id(day_emp_id) if day_emp_id else None
            night_emp = self.data_manager.get_employee_by_id(night_emp_id) if night_emp_id else None
            
            data.append({
                'Date': date_str,
                'Day': date_obj.strftime("%A"),
                'Day_Shift_Employee': day_emp.name if day_emp else '',
                'Day_Shift_Experience': day_emp.experience if day_emp else '',
                'Night_Shift_Employee': night_emp.name if night_emp else '',
                'Night_Shift_Experience': night_emp.experience if night_emp else '',
            })
        
        return pd.DataFrame(data)

    def _generate_violations_from_schedule_result(self, schedule_result: ScheduleResult) -> Dict[str, Any]:
        """Generate violation report from ScheduleResult"""
        violations = {
            'quota_violations': [],
            'unassigned_shifts': [],
            'constraint_violations': schedule_result.violations,
            'summary': {
                'total_quota_violations': 0,  # Will be calculated from statistics
                'total_unassigned_shifts': 0,  # Will be calculated from schedule
                'employees_over_quota': 0,
                'employees_under_quota': 0,
            }
        }

        # Calculate from statistics if available
        if schedule_result.statistics:
            over_quota = [s for s in schedule_result.statistics.values() if s.get('quota_deviation', 0) > 0]
            under_quota = [s for s in schedule_result.statistics.values() if s.get('quota_deviation', 0) < 0]

            violations['summary']['total_quota_violations'] = len(over_quota) + len(under_quota)
            violations['summary']['employees_over_quota'] = len(over_quota)
            violations['summary']['employees_under_quota'] = len(under_quota)

        # Count unassigned shifts from schedule
        unassigned_count = 0
        for date_data in schedule_result.schedule.values():
            if date_data.get('day_shift') is None:
                unassigned_count += 1
            if date_data.get('night_shift') is None:
                unassigned_count += 1
        violations['summary']['total_unassigned_shifts'] = unassigned_count

        return violations

    def _create_optimization_dataframe(self, schedule_result: ScheduleResult) -> pd.DataFrame:
        """Create optimization DataFrame for Excel export"""
        data = [
            {'Metric': 'Success', 'Value': schedule_result.success},
            {'Metric': 'Method', 'Value': 'CP-SAT' if 'CP-SAT' in schedule_result.message else 'Backtracking'},
            {'Metric': 'Violations Count', 'Value': len(schedule_result.violations)},
            {'Metric': 'Message', 'Value': schedule_result.message}
        ]

        # Add violations if any
        for i, violation in enumerate(schedule_result.violations[:10]):  # Limit to first 10
            data.append({'Metric': f'Violation {i+1}', 'Value': violation})

        return pd.DataFrame(data)
    
    def _create_statistics_dataframe(self, month_key: str,
                                    schedule_result: Optional[ScheduleResult] = None) -> pd.DataFrame:
        """Create statistics DataFrame for Excel export with deviation flags"""
        if schedule_result and schedule_result.statistics:
            emp_stats = schedule_result.statistics
        else:
            emp_stats = self.data_manager.calculate_employee_stats(month_key)

        data = []
        for emp_name, stats in emp_stats.items():
            flag_info = {}
            if stats.get('deviation_flag'):
                flag = stats['deviation_flag']
                flag_info = {
                    'Deviation_Type': flag['deviation_type'],
                    'Deviation_Severity': flag['severity'],
                    'Deviation_Description': flag['description']
                }

            row = {
                'Employee': emp_name,
                'Experience': stats['experience'],
                'Day_Shifts': stats['day_shifts'],
                'Night_Shifts': stats['night_shifts'],
                'Total_Shifts': stats['total_shifts'],
                'Quota': stats['quota'],
                'Quota_Deviation': stats['quota_deviation'],
                'Absences': stats['absences']
            }
            row.update(flag_info)
            data.append(row)

        return pd.DataFrame(data)
    
    def _create_employee_dataframe(self) -> pd.DataFrame:
        """Create employee DataFrame for Excel export"""
        employees = self.data_manager.get_employees(active_only=False)
        
        data = []
        for emp in employees:
            data.append({
                'ID': emp.id,
                'Name': emp.name,
                'Experience': emp.experience,
                'Active': emp.is_active
            })
        
        return pd.DataFrame(data)
    
    def _format_excel_worksheets(self, writer):
        """Format Excel worksheets"""
        try:
            from openpyxl.styles import PatternFill, Font
            from openpyxl.utils.dataframe import dataframe_to_rows
            
            # Format Schedule sheet
            schedule_ws = writer.sheets['Schedule']
            
            # Header formatting
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(color="FFFFFF", bold=True)
            
            for cell in schedule_ws[1]:
                cell.fill = header_fill
                cell.font = header_font
            
            # Auto-adjust column widths
            for column in schedule_ws.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                schedule_ws.column_dimensions[column_letter].width = adjusted_width
                
        except ImportError:
            # openpyxl styling not available
            pass
    
    def export_schedule_csv(self, year: int, month: int, output_path: str) -> bool:
        """Export schedule to CSV format"""
        try:
            month_key = f"{year}-{month:02d}"
            schedule = self.data_manager.get_schedule(month_key)
            
            # Create schedule DataFrame
            schedule_df = self._create_schedule_dataframe(year, month, schedule)
            
            # Export to CSV
            schedule_df.to_csv(output_path, index=False)
            
            return True
            
        except Exception as e:
            logging.error(f"Error exporting to CSV: {e}", exc_info=True)
            return False
    
    def generate_violation_report(self, year: int, month: int) -> Dict[str, Any]:
        """Generate comprehensive violation report"""
        month_key = f"{year}-{month:02d}"
        schedule = self.data_manager.get_schedule(month_key)
        emp_stats = self.data_manager.calculate_employee_stats(month_key)
        
        violations = {
            'quota_violations': [],
            'unassigned_shifts': [],
            'constraint_violations': [],
            'summary': {}
        }
        
        # Check quota violations
        for emp_name, stats in emp_stats.items():
            if stats['quota_deviation'] != 0:
                violations['quota_violations'].append({
                    'employee': emp_name,
                    'experience': stats['experience'],
                    'actual_shifts': stats['total_shifts'],
                    'quota': stats['quota'],
                    'deviation': stats['quota_deviation']
                })
        
        # Check unassigned shifts
        for date_str, day_data in schedule.items():
            if day_data.get('day_shift') is None:
                violations['unassigned_shifts'].append({
                    'date': date_str,
                    'shift_type': 'day_shift'
                })
            if day_data.get('night_shift') is None:
                violations['unassigned_shifts'].append({
                    'date': date_str,
                    'shift_type': 'night_shift'
                })
        
        # Summary
        violations['summary'] = {
            'total_quota_violations': len(violations['quota_violations']),
            'total_unassigned_shifts': len(violations['unassigned_shifts']),
            'employees_over_quota': len([v for v in violations['quota_violations'] if v['deviation'] > 0]),
            'employees_under_quota': len([v for v in violations['quota_violations'] if v['deviation'] < 0]),
        }
        
        return violations
    
    def create_dashboard_summary(self, year: int, month: int,
                                schedule_result: Optional[ScheduleResult] = None) -> str:
        """Create text summary for dashboard display with deviation flags and optimization metrics"""
        month_key = f"{year}-{month:02d}"

        if schedule_result and schedule_result.statistics:
            # Use statistics from ScheduleResult
            emp_stats = schedule_result.statistics
            team_stats = self._calculate_team_stats_from_emp_stats(emp_stats, month_key)
            violations = self._generate_violations_from_schedule_result(schedule_result)
        else:
            team_stats = self.data_manager.get_team_stats(month_key)
            violations = self.generate_violation_report(year, month)

        # Get deviation flag summary
        high_severity = len(team_stats.get('high_severity_deviations', []))
        medium_severity = len(team_stats.get('medium_severity_deviations', []))
        low_severity = len(team_stats.get('low_severity_deviations', []))

        # Add optimization info
        opt_info = ""
        if schedule_result:
            method = "CP-SAT" if "CP-SAT" in schedule_result.message else "Backtracking"
            status = "SUCCESS" if schedule_result.success else "FAILED"
            opt_info = f"""
Optimization Results:
• Method: {method}
• Status: {status}
• Constraint Violations: {len(schedule_result.violations)}
• Message: {schedule_result.message}
"""

        summary = f"""
SCHEDULE SUMMARY - {calendar.month_name[month]} {year}
{opt_info}
Team Overview:
• Total Employees: {team_stats['total_employees']}
• High Experience: {team_stats['high_experience_count']}
• Low Experience: {team_stats['low_experience_count']}

Shift Distribution:
• Total Shifts: {team_stats['total_shifts_assigned']}
• High Exp Shifts: {team_stats['high_exp_shifts']}
• Low Exp Shifts: {team_stats['low_exp_shifts']}

Experience Bucket Targets:
• High Exp Target: {team_stats.get('high_exp_target', 'N/A')}
• Low Exp Target: {team_stats.get('low_exp_target', 'N/A')}
• High Exp Deviation: {team_stats.get('high_exp_target_deviation', 'N/A')}
• Low Exp Deviation: {team_stats.get('low_exp_target_deviation', 'N/A')}

Deviation Flags:
• High Severity: {high_severity} (Critical quota violations)
• Medium Severity: {medium_severity} (Moderate deviations)
• Low Severity: {low_severity} (Minor adjustments)

Issues:
• Quota Violations: {violations['summary']['total_quota_violations']}
• Unassigned Shifts: {violations['summary']['total_unassigned_shifts']}
• Over Quota: {violations['summary']['employees_over_quota']}
• Under Quota: {violations['summary']['employees_under_quota']}
        """

        # Add specific high-severity deviation details
        if high_severity > 0:
            summary += "\n\nHIGH SEVERITY DEVIATIONS:"
            for flag in team_stats.get('high_severity_deviations', []):
                summary += f"\n• {flag['employee_name']}: {flag['description']}"

        return summary.strip()


class ExportManager:
    """Manager class for handling all export operations"""
    
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self.report_generator = ReportGenerator(data_manager)
    
    def export_calendar(self, year: int, month: int, format_type: str, output_path: str,
                       schedule_result: Optional[ScheduleResult] = None) -> bool:
        """Export calendar in specified format with optional ScheduleResult"""
        if format_type.lower() == 'pdf':
            return self.report_generator.export_calendar_pdf(year, month, output_path, schedule_result)
        elif format_type.lower() == 'excel':
            return self.report_generator.export_schedule_excel(year, month, output_path, schedule_result)
        elif format_type.lower() == 'csv':
            return self.report_generator.export_schedule_csv(year, month, output_path)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def get_default_filename(self, year: int, month: int, format_type: str) -> str:
        """Generate default filename for export"""
        month_name = calendar.month_name[month].lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return f"shift_schedule_{month_name}_{year}_{timestamp}.{format_type.lower()}"
    
    def batch_export(self, year: int, month: int, output_dir: str, 
                    formats: List[str] = None) -> Dict[str, bool]:
        """Export schedule in multiple formats"""
        if formats is None:
            formats = ['pdf', 'excel', 'csv']
        
        results = {}
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for format_type in formats:
            filename = self.get_default_filename(year, month, format_type)
            file_path = output_path / filename
            
            try:
                results[format_type] = self.export_calendar(
                    year, month, format_type, str(file_path)
                )
            except Exception as e:
                logging.error(f"Error exporting {format_type}: {e}", exc_info=True)
                results[format_type] = False
        
        return results
