# CFlat-Cb-coding-language

The Cb programming language (pronounced "C-Flat") is a programming language mixing Python, C#, and C syntax with a musical theme.

---

## Features & Capabilities

* **Musical Keywords**: Write code using musical notation terms mapped directly to underlying C primitives via a robust regex transpiler.
* **Hybrid Concurrency (`concb`)**: Run multi-threaded Python and C# tasks concurrently with `wait` or `move` execution modes.
* **Python & .NET Bridge (`startcb`, `invoke`)**: Embed stateful Python or C# code blocks and link modern .NET SDK namespaces via `pythonnet`.
* **Native Compilation**: Compiles down to high-performance native binaries using GCC (`cbc app.cb`).
* **Professional PyQt6 Wizard Installer**: Features a modern multi-step graphical setup utility complete with prerequisite verifications, single-instance enforcement, remote fallbacks, and a Tkinter-based uninstaller.

---

## Comprehensive Syntax & Keyword Reference

| Cb Keyword / Construct | Underlying Mapping / Action | Description |
| :--- | :--- | :--- |
| `bnt` | `int` | Standard integer data type declaration |
| `pianissimo` | `printf` | Formatted output / printing to console |
| `ascolta(<var>)` | `cb_read_int(&<var>)` | Reads a validated integer from standard input |
| `da_capo` | `while` | Loop control block |
| `staccato` | `break` | Loop exit keyword |
| `verissimo` | `1` | Boolean true representation |
| `falsissimo` | `0` | Boolean false representation |
| `if_forte` | `if` | Conditional branch keyword |
| `elif_mforte` | `else if` | Alternative conditional branch keyword |
| `else_piano` | `else` | Fallback conditional branch keyword |
| `coda <val>` | `return <val>;` | Function return statement |
| `solo <name>(<params>)` | Function Header | Function declaration formatter |
| `fermata <var> in range(<n>)` | `for` loop | Standard iteration loop count block |
| `ensemble <name> = [...]` | Array Declaration | Native integer array initialization |
| `crescendo <var>` | `<var>++` | Increment variable value by 1 |
| `decrescendo <var>` | `<var>--` | Decrement variable value by 1 |
| `allegro { ... }` | `int main(void)` | Main program entry point initialization block |
| `lento { ... }` | Error Handler Block | Executed if main execution or a python block fails |
| `ritardando { ... }` | Protected Try Block | Try-catch block scope wrapper |
| `tempo_lost { ... }` | Try Error Handler | Executed if the protected try-block fails |
| `call <module>` | Dynamic Import | Links and auto-installs Python packages via pip |
| `invoke <SDK>` | .NET Binding | Links C# SDK namespaces via `pythonnet` |
| `startcb(py \| cs)` | Stateful Block | Embeds multi-line Python or C# code blocks into Cb |
| `concb(wait \| move)` | Multi-threaded Group | Runs multiple embedded Python/C# blocks concurrently |

---

## Getting Started & Usage

### 1. Installation
Run the official graphical `installer.exe` to launch the PyQt6 setup wizard. It validates prerequisites, installs core runtime assets to `C:\CbLang`, configures your user PATH, registers `.cb` file associations, and creates a desktop uninstaller shortcut.

### 2. Writing a Sample Program (`app.cb`)
```c
call tkinter
invoke System

allegro {
    pianissimo("Initializing Cb Hybrid Environment...\n");

    bnt count = 0;
    fermata i in range(3) {
        crescendo count;
    }

    pianissimo(count);

    tkinter.startcb() [
        import tkinter as tk
        root = tk.Tk()
        root.title("Cb Hybrid Window")
        root.geometry("250x150")
        root.mainloop()
    ]

    return falsissimo;
}
lento {
    pianissimo("Execution failed. Entering lento error handler.\n");
}
```

### 3. Compiling and Executing via CLI

Open your terminal and compile your file using the global compiler command:

```bash
cbc app.cb
```

Then, execute your freshly built binary:

```bash
.\app.exe
```

---

## Project Architecture

* **`cbc.py`**: The command-line entry point and CLI coordinator.
* **`cblang.py`**: The core compilation engine handling dependency resolution, syntax transpilation, header injection, and GCC invocation.
* **`installer.py`**: The PyQt6 multi-step wizard utility responsible for graphical deployment, single-instance enforcement, registry icon mapping, path modifications, and remote fallback downloads.
* **`uninstall_cb.py`**: The generated Tkinter-powered cleanup script deployed locally to handle safe removal of registry configurations, path entries, and application directories.

---

## Prerequisites for Cb

To work with, compile, or develop programs in Cb, your system requires the following tools and dependencies:

1. **Core Environment**
   * **Python (3.x)**: Required to run the compiler engine (`cbc.py` / `cblang.py`), the PyQt6 installation wizard, and embedded runtime blocks.
   * **GCC Compiler (MinGW on Windows)**: Required to turn the transpiled C code into a native executable binary (`.exe`).

2. **For C# and .NET Interop (`invoke` feature)**
   * **.NET SDK (.NET Core)**: Required if your Cb scripts call upon modern .NET namespaces and classes.
   * **`pythonnet` package**: The underlying Python bridge library used to hook into the CoreCLR runtime (which the installer verifies and downloads automatically).