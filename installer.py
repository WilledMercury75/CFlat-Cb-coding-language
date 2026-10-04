import os
import shutil
import sys
import subprocess
import winreg
import ctypes
import urllib.request
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QCheckBox, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox, QStackedWidget, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

# git fallback
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/WilledMercury75/CFlat-Cb-coding-language/main/"
GITLAB_RAW_BASE = "https://gitlab.com/WilledMercury75/CFlat-Cb-coding-language/-/raw/main/"


def check_single_instance():
    """Ensures only one instance of the installer can run at a time using a Windows Mutex."""
    if os.name == 'nt':
        # create a unique system-wide mutex name for the installer
        kernel32 = ctypes.windll.kernel32
        mutex_name = "Global\\CbLanguageInstallerMutex_Unique_Key"
        self_mutex = kernel32.CreateMutexW(None, False, mutex_name)
        # ERROR_ALREADY_EXISTS = 183
        if kernel32.GetLastError() == 183:
            sys.exit(0)


def fetch_file_from_remote(filename, dest_path):
    """Attempts to download a missing file from GitHub first, then GitLab fallback."""
    github_url = GITHUB_RAW_BASE + filename
    gitlab_url = GITLAB_RAW_BASE + filename

    try:
        urllib.request.urlretrieve(github_url, dest_path)
        return True
    except Exception:
        try:
            urllib.request.urlretrieve(gitlab_url, dest_path)
            return True
        except Exception:
            return False


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    local_path = os.path.join(base_path, relative_path)
    if os.path.exists(local_path):
        return local_path

    temp_download_path = os.path.join(os.path.abspath("."), relative_path)
    if fetch_file_from_remote(relative_path, temp_download_path):
        return temp_download_path

    return local_path


class CbInstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Cb Language Installer")
        self.setFixedSize(500, 440)

        icon_path = resource_path("cb_logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                color: #212529;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                font-size: 13px;
            }
            QCheckBox {
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QPushButton {
                background-color: #0d6efd;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton:disabled {
                background-color: #adb5bd;
            }
            QPushButton:hover:enabled {
                background-color: #0b5ed7;
            }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.create_welcome_page())
        self.stack.addWidget(self.create_prereq_page())
        self.stack.addWidget(self.create_options_page())
        self.stack.addWidget(self.create_progress_page())

        main_layout.addWidget(self.stack)
        self.setLayout(main_layout)

    # welcome & consent
    def create_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(15)

        title = QLabel("Welcome to Cb Language Setup")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #1a1d20;")
        layout.addWidget(title)

        sub = QLabel("This wizard will guide you through installing the Cb compiler engine and runtime environment.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #6c757d; font-size: 12px;")
        layout.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #dee2e6;")
        layout.addWidget(line)

        self.consent_cb = QCheckBox("I consent to have the Cb runtime installed")
        self.consent_cb.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.consent_cb.stateChanged.connect(lambda: self.next_btn_1.setEnabled(self.consent_cb.isChecked()))
        layout.addWidget(self.consent_cb)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.next_btn_1 = QPushButton("Next >")
        self.next_btn_1.setEnabled(False)
        self.next_btn_1.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        btn_layout.addWidget(self.next_btn_1)
        layout.addLayout(btn_layout)

        page.setLayout(layout)
        return page

    # prerequisites check
    def create_prereq_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(15)

        title = QLabel("Checking Prerequisites")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel("Verifying system requirements (Python, .NET, and GCC)...")
        desc.setStyleSheet("color: #6c757d;")
        layout.addWidget(desc)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        back_btn = QPushButton("< Back")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        btn_layout.addWidget(back_btn)

        btn_layout.addStretch()
        next_btn_2 = QPushButton("Next >")
        next_btn_2.clicked.connect(self.verify_prerequisites)
        btn_layout.addWidget(next_btn_2)

        layout.addLayout(btn_layout)
        page.setLayout(layout)
        return page

    def verify_prerequisites(self):
        python_ok = True
        if not python_ok:
            if not self.prompt_missing_prerequisite("Python", "Python 13.4.8+"):
                return

        csc_path = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
        if not os.path.exists(csc_path):
            csc_path = r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"

        dotnet_ok = os.path.exists(csc_path)
        if not dotnet_ok:
            if not self.prompt_missing_prerequisite(".NET Framework (csc.exe)", ".NET 4.0+"):
                return

        gcc_ok = shutil.which('gcc') or os.path.exists(r'C:\mingw64\bin\gcc.exe')
        if not gcc_ok:
            if not self.prompt_missing_prerequisite("GCC Compiler", "MinGW-w64"):
                return

        self.stack.setCurrentIndex(2)

    def prompt_missing_prerequisite(self, name, req_version):
        msg = f"It seems like you don't have {name} installed. Install the runtime? Cb requires {req_version} to be installed to function."
        ans = QMessageBox.question(self, "Prerequisite Missing", msg,
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "Info", f"Please install {name} manually or ensure it's added to your PATH.")
            return True
        else:
            confirm = QMessageBox.question(self, "Are you sure?",
                                           "Are you sure? Cancelling will terminate this installation.",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes:
                sys.exit(0)
            return False

    # installation options
    def create_options_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(15)

        title = QLabel("Installation Options")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        layout.addWidget(title)

        sub = QLabel("Select custom configuration preferences for Cb:")
        sub.setStyleSheet("color: #6c757d;")
        layout.addWidget(sub)

        layout.addSpacing(10)
        self.path_var = QCheckBox("Add Cb to user PATH environment variable")
        self.path_var.setChecked(True)
        layout.addWidget(self.path_var)

        self.assoc_var = QCheckBox("Associate .cb files with Cb Logo")
        self.assoc_var.setChecked(True)
        layout.addWidget(self.assoc_var)

        self.desktop_uninstaller_var = QCheckBox("Create 'Uninstall Cb' shortcut on Desktop")
        self.desktop_uninstaller_var.setChecked(True)
        layout.addWidget(self.desktop_uninstaller_var)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        back_btn = QPushButton("< Back")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        btn_layout.addWidget(back_btn)

        btn_layout.addStretch()
        install_btn = QPushButton("Install Now")
        install_btn.clicked.connect(self.run_installation)
        btn_layout.addWidget(install_btn)

        layout.addLayout(btn_layout)
        page.setLayout(layout)
        return page

    # progress / status page
    def create_progress_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(15)

        title = QLabel("Installing Cb Language")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        layout.addWidget(title)

        self.status_lbl = QLabel("Preparing files...")
        self.status_lbl.setStyleSheet("color: #495057; font-style: italic;")
        layout.addWidget(self.status_lbl)

        layout.addStretch()
        page.setLayout(layout)
        return page

    # installation execution logic
    def run_installation(self):
        self.stack.setCurrentIndex(3)
        QApplication.processEvents()

        try:
            install_dir = r"C:\CbLang"
            os.makedirs(install_dir, exist_ok=True)

            self.status_lbl.setText("Copying compiler files and assets...")
            QApplication.processEvents()
            required_files = ['cbc.py', 'cblang.py', 'cb_logo.ico']
            for file in required_files:
                src_path = resource_path(file)
                if os.path.exists(src_path):
                    shutil.copy(src_path, os.path.join(install_dir, file))
                else:
                    if file != 'cb_logo.ico':
                        raise FileNotFoundError(f"Required file '{file}' could not be located or downloaded.")

            bat_path = os.path.join(install_dir, "cbc.bat")
            with open(bat_path, "w") as f:
                f.write(f'@echo off\npython "{install_dir}\\cbc.py" %*')

            if self.assoc_var.isChecked() and os.path.exists(os.path.join(install_dir, "cb_logo.ico")):
                self.status_lbl.setText("Registering .cb file associations...")
                QApplication.processEvents()
                self.register_file_association(install_dir)

            self.status_lbl.setText("Generating uninstaller...")
            QApplication.processEvents()
            uninstaller_path = os.path.join(install_dir, "uninstall_cb.py")
            self.create_uninstaller_script(uninstaller_path, install_dir)

            if self.desktop_uninstaller_var.isChecked():
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                shortcut_path = os.path.join(desktop, "Uninstall Cb.bat")
                with open(shortcut_path, "w") as f:
                    f.write(f'@echo off\npython "{uninstaller_path}"\npause')

            if self.path_var.isChecked():
                self.status_lbl.setText("Updating system environment PATH...")
                QApplication.processEvents()
                self.add_to_path(install_dir)

            self.status_lbl.setText("Verifying base pythonnet dependencies...")
            QApplication.processEvents()
            subprocess.run([sys.executable, "-m", "pip", "install", "pythonnet", "--quiet"], check=False)

            self.status_lbl.setText("Installation complete!")

            self.hide()

            QMessageBox.information(
                None, "Success",
                "Thank you for installing Cb!\n\nHave a musical day!"
            )

            sys.exit(0)

        except Exception as e:
            QMessageBox.critical(None, "Installation Error", f"An error occurred during installation:\n{e}")
            sys.exit(1)

    def register_file_association(self, install_dir):
        icon_path = os.path.join(install_dir, "cb_logo.ico")
        bat_path = os.path.join(install_dir, "cbc.bat")

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.cb") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "CbLanguage.File")

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "Cb Source File")

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File\DefaultIcon") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, icon_path)

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File\shell\open\command") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f'"{bat_path}" "%1"')

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)

    def create_uninstaller_script(self, path, install_dir):
        script_content = f'''
import os
import winreg
import shutil
import sys
import tkinter as tk
from tkinter import messagebox

def remove_registry_keys():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes\\CbLanguage.File\\shell\\open\\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes\\CbLanguage.File\\shell\\open")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes\\CbLanguage.File\\shell")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes\\CbLanguage.File\\DefaultIcon")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes\\CbLanguage.File")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\\Classes\\.cb")
    except Exception:
        pass

def remove_from_path(target_dir):
    try:
        reg_path = r"Environment"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            current_path, _ = winreg.QueryValueEx(key, "PATH")
            paths = current_path.split(';')
            new_paths = [p for p in paths if p.lower() != target_dir.lower()]
            new_path = ';'.join(new_paths)
            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
    except Exception:
        pass

root = tk.Tk()
root.withdraw()
if messagebox.askyesno("Uninstall Cb", "Are you sure you want to remove Cb and its configuration?"):
    remove_registry_keys()
    remove_from_path(r"{install_dir}")
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut = os.path.join(desktop, "Uninstall Cb.bat")
        if os.path.exists(shortcut):
            os.remove(shortcut)

        shutil.rmtree(r"{install_dir}")
        messagebox.showinfo("Uninstalled", "Cb has been successfully removed from your system.")
    except Exception as e:
        messagebox.showerror("Error", f"Could not fully remove files: {{e}}")
root.destroy()
'''
        with open(path, "w") as f:
            f.write(script_content)

    def add_to_path(self, target_dir):
        reg_path = r"Environment"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                current_path, _ = winreg.QueryValueEx(key, "PATH")
            except FileNotFoundError:
                current_path = ""

            if target_dir.lower() not in current_path.lower():
                new_path = f"{current_path};{target_dir}" if current_path else target_dir
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x0002, 5000, None)


if __name__ == "__main__":
    check_single_instance()
    app = QApplication(sys.argv)
    window = CbInstallerWindow()
    window.show()
    sys.exit(app.exec())