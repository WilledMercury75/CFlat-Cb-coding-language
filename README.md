# CFlat-Cb-coding-language

The Cb programming language (pronounced "C-Flat") is a joke language intending to mix Python and C# syntax to make a simple musical-themed programming language[cite: 2].

---

## Features

* **Musical Keywords**: Write code using musical notation terms mapped directly to underlying C primitives via a robust regex transpiler.
* **Hybrid Python Bridge**: Embed stateful Python scripts directly inside your Cb files (`.startcb()`) with automatic virtual environment and dependency harmonization.
* **.NET C# SDK Interop**: Seamlessly invoke modern .NET Core namespaces and classes (like `System.DateTime`) directly inside your workflow via `pythonnet` and CoreCLR.
* **Native Compilation**: Compiles down to high-performance native binaries using GCC.
* **Professional Graphical Installer**: Includes a custom Tkinter-based setup utility that handles installation, environment PATH configuration, `.cb` file type associations with custom branding, and an integrated uninstaller.

---

## Quick Syntax Reference

| Cb Keyword | Underlying Mapping / Action | Description |
| :--- | :--- | :--- |
| `bnt` | `int` | Standard integer data type |
| `pianissimo` | `printf` | Formatted output / printing to console |
| `da_capo` | `while` | Loop control block |
| `staccato` | `break` | Loop exit keyword |
| `verissimo` | `1` | Boolean true |
| `falsissimo` | `0` | Boolean false |
| `call <module>` | Dynamic Import | Links and auto-installs Python packages (e.g., `tkinter`) |
| `invoke <SDK>` | .NET Binding | Links C# SDK namespaces via `pythonnet` |

## Getting Started & Usage

### 1. Installation
Run the official graphical `installer.exe` to set up the Cb engine on your system, add `cbc` to your user PATH, and register `.cb` file associations.

### 2. Writing a Sample Program (`app.cb`)
```c
call tkinter
invoke System

bnt main() [
    pianissimo("Initializing Cb Hybrid Environment...\n");

    tkinter.startcb() [
        import tkinter as tk
        from System import DateTime
        
        def show_time():
            now = DateTime.Now
            time_lbl.config(text=f".NET Time: {now.ToString('HH:mm:ss')}")

        root = tk.Tk()
        root.title("Cb Language + Tkinter + .NET")
        root.geometry("350x200")
        
        time_lbl = tk.Label(root, text="Click to fetch live .NET time", font=("Arial", 10))
        time_lbl.pack(pady=20)
        
        btn = tk.Button(root, text="Get Time", command=show_time, bg="green", fg="white")
        btn.pack(pady=5)
        
        exit_btn = tk.Button(root, text="Quit", command=root.destroy, bg="red", fg="white")
        exit_btn.pack(pady=5)
        
        root.mainloop()
    ]

    pianissimo("Execution finished. Returning to Cb.\n");
    return falsissimo;
]
```
### 3. Compiling and Executing via CLI

Open your terminal and compile your file using the global compiler command:

```c
cbc app.cb
```

Then, execute your freshly built binary:

```c
.\app.exe
```

#### Project Architecture

    cbc.py: The command-line entry point and CLI coordinator.

    cblang.py: The core compilation engine handling dependency resolution, syntax transpilation, header injection, and GCC invocation.

    installer.py: The graphical setup utility responsible for deployment, registry modifications, icon association, and uninstaller generation.

##### Prerequisites for Cb

To work with, compile, or develop programs in Cb, your system needs a few core tools and dependencies installed.Here are the prerequisites broken down by category:

1. Core EnvironmentPython (3.x): Required to run the compiler engine (cbc.py / cblang.py), the installation scripts, and the embedded runtime blocks.GCC Compiler (MinGW on Windows): Required to turn the transpiled C code into a native executable binary (.exe).

2. For C# and .NET Interop (invoke feature).NET SDK (.NET Core): Required if your Cb scripts call upon modern .NET namespaces and classes.   pythonnet package: The underlying Python bridge library used to hook into the CoreCLR runtime (which the Cb compiler checks and installs automatically).
