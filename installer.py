import os
import shutil
import sys
import subprocess
import tkinter as tk
from tkinter import messagebox
import winreg


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class CbInstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Cb Language Installer")
        self.root.geometry("450x380")
        self.root.resizable(False, False)
        self.root.configure(bg="#f4f4f4")

        # title & info
        tk.Label(root, text="Install Cb Programming Language", font=("Arial", 14, "bold"), bg="#f4f4f4",
                 fg="#333").pack(pady=15)
        tk.Label(root, text="Installs the Cb compiler engine and associates .cb files.", font=("Arial", 9),
                 bg="#f4f4f4", fg="#666").pack(pady=2)

        # options
        self.path_var = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Add Cb to user PATH environment variable", variable=self.path_var,
                       font=("Arial", 10), bg="#f4f4f4").pack(anchor="w", padx=40, pady=8)

        self.assoc_var = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Associate .cb files with Cb Logo", variable=self.assoc_var, font=("Arial", 10),
                       bg="#f4f4f4").pack(anchor="w", padx=40, pady=8)

        self.desktop_uninstaller_var = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Create Uninstall Cb shortcut on Desktop", variable=self.desktop_uninstaller_var,
                       font=("Arial", 10), bg="#f4f4f4").pack(anchor="w", padx=40, pady=8)

        # action button
        self.install_btn = tk.Button(root, text="Install Now", command=self.run_installation,
                                     font=("Arial", 11, "bold"), bg="#28a745", fg="white", padx=20, pady=8)
        self.install_btn.pack(pady=15)

        self.status_lbl = tk.Label(root, text="", font=("Arial", 9), bg="#f4f4f4", fg="#555")
        self.status_lbl.pack(pady=5)

    def run_installation(self):
        try:
            self.install_btn.config(state=tk.DISABLED)
            self.status_lbl.config(text="Copying compiler files...")
            self.root.update()

            install_dir = r"C:\CbLang"
            os.makedirs(install_dir, exist_ok=True)

            # 1. copy required compiler files & logo using resource_path
            required_files = ['cbc.py', 'cblang.py', 'cb_logo.ico']
            for file in required_files:
                src_path = resource_path(file)
                if os.path.exists(src_path):
                    shutil.copy(src_path, os.path.join(install_dir, file))
                else:
                    if file != 'cb_logo.ico':
                        raise FileNotFoundError(f"Required file '{file}' could not be located inside the package.")

            # 2. create execution wrapper batch file
            bat_path = os.path.join(install_dir, "cbc.bat")
            with open(bat_path, "w") as f:
                f.write(f'@echo off\npython "{install_dir}\\cbc.py" %*')

            # 3. register .cb file association if requested
            if self.assoc_var.get() and os.path.exists(os.path.join(install_dir, "cb_logo.ico")):
                self.status_lbl.config(text="Registering .cb file associations...")
                self.root.update()
                self.register_file_association(install_dir)

            # 4. create uninstaller script
            self.status_lbl.config(text="Generating uninstaller...")
            self.root.update()
            uninstaller_path = os.path.join(install_dir, "uninstall_cb.py")
            self.create_uninstaller_script(uninstaller_path, install_dir)

            # 5. create desktop uninstaller shortcut if requested
            if self.desktop_uninstaller_var.get():
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                shortcut_path = os.path.join(desktop, "Uninstall Cb.bat")
                with open(shortcut_path, "w") as f:
                    f.write(f'@echo off\npython "{uninstaller_path}"\npause')

            # 6. handle PATH modification
            if self.path_var.get():
                self.status_lbl.config(text="Updating system environment PATH...")
                self.root.update()
                self.add_to_path(install_dir)

            # 7. ensure default pip requirements (pythonnet) are available
            self.status_lbl.config(text="Verifying base dependencies...")
            self.root.update()
            subprocess.run([sys.executable, "-m", "pip", "install", "pythonnet", "--quiet"], check=False)

            self.status_lbl.config(text="Installation complete!")
            messagebox.showinfo("Success",
                                "Cb has been successfully installed!\nRestart your terminal or explorer to see changes.")
            self.root.destroy()

        except Exception as e:
            messagebox.showerror("Installation Error", f"An error occurred during installation:\n{e}")
            self.install_btn.config(state=tk.NORMAL)
            self.status_lbl.config(text="Installation failed.")

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

        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)

    def create_uninstaller_script(self, path, install_dir):
        script_content = f'''
import os
import winreg
import shutil
import tkinter as tk
from tkinter import messagebox

def remove_registry_keys():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File\shell\open\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File\shell\open")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File\shell")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File\DefaultIcon")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CbLanguage.File")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.cb")
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

                import ctypes
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x0002, 5000, None)


if __name__ == "__main__":
    root = tk.Tk()
    app = CbInstallerApp(root)
    root.mainloop()