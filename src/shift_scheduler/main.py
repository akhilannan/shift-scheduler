"""
Main Entry Point for Shift Scheduling System

Integrates all modules and provides the primary application entry point
with comprehensive error handling and logging.
"""

import sys
import logging
import traceback
from pathlib import Path
from datetime import datetime
from tkinter import messagebox

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shift_scheduler.data_manager import DataManager
from shift_scheduler.scheduler_logic import ShiftScheduler
from shift_scheduler.ui import MainWindow
from shift_scheduler.reporting import ExportManager


def setup_logging():
    """Setup application logging"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"shift_scheduler_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)


def check_dependencies():
    """Check if all required dependencies are available"""
    required_modules = [
        'customtkinter',
        'pandas',
        'openpyxl',
        'reportlab',
        'PIL'  # Pillow
    ]
    
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        error_msg = f"Missing required dependencies: {', '.join(missing_modules)}\n"
        error_msg += "Please install them using: pip install -e ."
        raise ImportError(error_msg)


def create_data_directory():
    """Create data directory if it doesn't exist"""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    return data_dir


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger = logging.getLogger(__name__)
    logger.error(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback)
    )
    
    # Show error dialog if GUI is available
    try:
        error_msg = f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc_value}"
        messagebox.showerror("Application Error", error_msg)
    except:
        pass


class ShiftSchedulerApp:
    """Main application class"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.data_manager = None
        self.scheduler = None
        self.export_manager = None
        self.main_window = None
        
    def initialize(self):
        """Initialize application components"""
        try:
            self.logger.info("Initializing Shift Scheduler Application")
            
            # Check dependencies
            check_dependencies()
            self.logger.info("All dependencies available")
            
            # Determine the base path for data storage
            if getattr(sys, 'frozen', False):
                # If the application is run as a bundle (e.g., by PyInstaller)
                base_path = Path(sys.executable).parent
            else:
                # If the application is run as a script
                base_path = Path(__file__).parent.parent

            # Create the data directory in the determined base path
            data_dir = base_path / "data"
            data_dir.mkdir(exist_ok=True)
            self.logger.info(f"Persistent data directory: {data_dir}")
            
            # Initialize data manager with the correct, persistent path
            data_file = data_dir / "schedule_data.json"
            self.data_manager = DataManager(str(data_file))
            self.logger.info("Data manager initialized with persistent storage")
            
            # Initialize scheduler
            self.scheduler = ShiftScheduler(self.data_manager)
            self.logger.info("Scheduler initialized")
            
            # Initialize export manager
            self.export_manager = ExportManager(self.data_manager)
            self.logger.info("Export manager initialized")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            self.logger.error(traceback.format_exc())
            return False
    
    def run(self):
        """Run the main application"""
        try:
            if not self.initialize():
                self.show_initialization_error()
                return False
            
            self.logger.info("Starting GUI application")
            
            # Create main window, passing dependencies directly to its constructor
            self.main_window = MainWindow(
                data_manager=self.data_manager,
                scheduler=self.scheduler
            )
            
            # The export manager can still be assigned here as it's not used in the UI's initial build
            self.main_window.export_manager = self.export_manager

            # Start the GUI
            self.main_window.mainloop()
            
            self.logger.info("Application closed normally")
            return True
            
        except Exception as e:
            self.logger.error(f"Application error: {e}")
            self.logger.error(traceback.format_exc())
            self.show_runtime_error(e)
            return False
        
        finally:
            self.cleanup()
    
    def show_initialization_error(self):
        """Show initialization error dialog"""
        try:
            # Create minimal tkinter window for error display
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()  # Hide main window
            
            error_msg = """
Failed to initialize Shift Scheduler Application.

Please check:
1. All required dependencies are installed
2. You have write permissions in the application directory
3. The logs directory for detailed error information

Would you like to view the installation requirements?
            """
            
            result = messagebox.askyesno("Initialization Error", error_msg.strip())
            
            if result:
                requirements_msg = """
Required Dependencies:
• Python 3.10 or higher
• customtkinter >= 5.2.0
• pandas >= 2.0.0
• openpyxl >= 3.1.0
• reportlab >= 4.0.0
• pillow >= 10.0.0

Installation:
pip install customtkinter pandas openpyxl reportlab pillow

Or use the project's pyproject.toml:
pip install -e .
                """
                messagebox.showinfo("Installation Requirements", requirements_msg.strip())
            
            root.destroy()
            
        except Exception as e:
            print(f"Failed to show initialization error: {e}")
    
    def show_runtime_error(self, error):
        """Show runtime error dialog"""
        try:
            error_msg = f"""
An error occurred while running the application:

{type(error).__name__}: {str(error)}

The application will now close. Please check the log files
for more detailed information.
            """
            messagebox.showerror("Runtime Error", error_msg.strip())
            
        except Exception as e:
            print(f"Failed to show runtime error: {e}")
    
    def cleanup(self):
        """Cleanup application resources"""
        try:
            if self.data_manager:
                self.data_manager.save_data()
                self.logger.info("Data saved successfully")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


def main():
    """Main entry point"""
    # Setup global exception handling
    sys.excepthook = handle_exception
    
    # Setup logging
    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("Starting Shift Scheduler Application")
    logger.info("=" * 50)
    
    # Create and run application
    app = ShiftSchedulerApp()
    success = app.run()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
