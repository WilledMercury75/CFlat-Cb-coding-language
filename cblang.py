import os
import re
import subprocess
import sys
from typing import Dict, List, Final


class CbCompilationException(Exception):
    """Custom exception matching C#-style explicit compilation failure handling."""
    pass


class CbCompiler:
    _SYNTAX_MAP: Final[Dict[str, str]] = {
        r'b\[([\s\S]*?)\]b': r'/*\1*/',  # multi-line comment
        r'bb(.*)': r'//\1',  # single-line comment
        r'\bbnt\b': 'int',  # data type
        r'\bpianissimo\b': 'printf',  # native io method
        r'\[': '{',  # visual block anchors
        r'\]': '}',

        # musical grammar blocks
        r'\bda_capo\b': 'while',
        r'\bstaccato\b': 'break',
        r'\bfermata\b': 'const',
        r'\bif_forte\b': 'if',
        r'\belse_piano\b': 'else',
        r'\bverissimo\b': '1',
        r'\bfalsissimo\b': '0',
    }

    def __init__(self, source_file: str) -> None:
        self._source_file: str = source_file
        self._temp_c_file: str = source_file.replace('.cb', '.tmp.c')
        self._output_exe: str = source_file.replace('.cb', '.exe' if sys.platform == "win32" else '')
        self._has_python: bool = False
        self._invoked_sdks: List[str] = []

    def execute_pipeline(self) -> None:
        try:
            self._validate_environment()
            translated_content: str = self._transpile()
            self._compile_binary(translated_content)
        except CbCompilationException as ex:
            print(f"Critical Error: {ex}")
            sys.exit(1)
        except Exception as ex:
            print(f"Unhandled System Exception: {ex}")
            sys.exit(1)

    def _validate_environment(self) -> None:
        if not self._source_file.endswith('.cb'):
            raise CbCompilationException("Cb source files must strictly end with the '.cb' extension.")
        if not os.path.exists(self._source_file):
            raise CbCompilationException(f"Target filesystem node '{self._source_file}' could not be located.")

    def _resolve_dependencies(self, raw_code: str) -> str:
        package_token_pattern: str = r'\bcall\s+(\w+)'
        discovered_packages: List[str] = re.findall(package_token_pattern, raw_code)

        invoke_token_pattern: str = r'\binvoke\s+(\w+)'
        self._invoked_sdks = re.findall(invoke_token_pattern, raw_code)

        if discovered_packages or self._invoked_sdks:
            self._has_python = True

        # 1. handle Python packages (call)
        if discovered_packages:
            print("[System.Link] Harmonizing Python package dependencies...")
            for package in discovered_packages:
                is_available = False
                try:
                    __import__(package)
                    is_available = True
                except ImportError:
                    pass

                if is_available:
                    print(f"[System] Module '{package}' is already available.")
                else:
                    print(f"[Pip] Package '{package}' is missing. Fetching via environment package manager...")
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "pip", "install", package, "--quiet"],
                            check=True
                        )
                    except subprocess.CalledProcessError:
                        raise CbCompilationException(f"Dependency resolution failed for module: '{package}'.")

        # 2. handle C# SDKs (invoke) and ensure pythonnet is installed
        if self._invoked_sdks:
            print("[System.Link] Harmonizing C# SDK bindings via pythonnet...")
            is_pythonnet_available = False
            try:
                __import__('pythonnet')
                is_pythonnet_available = True
            except ImportError:
                pass

            if is_pythonnet_available:
                print(f"[System] Package 'pythonnet' is already available.")
            else:
                print(f"[Pip] Package 'pythonnet' is missing. Fetching via environment package manager...")
                try:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", 'pythonnet', '--quiet'],
                        check=True
                    )
                except subprocess.CalledProcessError:
                    raise CbCompilationException("Dependency resolution failed for C# bridge package: 'pythonnet'.")

        raw_code = re.sub(package_token_pattern, r'// call \1 -> Dynamic Package Linked', raw_code)
        raw_code = re.sub(invoke_token_pattern, r'// invoke \1 -> C# SDK Linked', raw_code)

        return raw_code

    def _transpile_python_blocks(self, code: str) -> str:
        block_pattern = r'(\w+)\.startcb\(\)\s*\[(.*?)\]'

        def block_replacement(match):
            pkg = match.group(1)
            raw_py_code = match.group(2)

            import textwrap
            raw_py_code = textwrap.dedent(raw_py_code).strip()

            # dynamically point embedded python to the virtual environment's site-packages
            venv_site = os.path.join(sys.prefix, 'Lib', 'site-packages').replace('\\', '\\\\')
            prelude = f"import sys, os, site\nsite.addsitedir('{venv_site}')\nimport {pkg}\n"

            if self._invoked_sdks:
                prelude += "import pythonnet\npythonnet.load('coreclr')\nimport clr\n"
                for sdk in self._invoked_sdks:
                    prelude += f"clr.AddReference('{sdk}')\n"

            full_py_code = prelude + raw_py_code

            c_string_lines = []
            for line in full_py_code.split('\n'):
                escaped_line = line.replace('\\', '\\\\').replace('"', '\\"')
                c_string_lines.append(f'        "{escaped_line}\\n"')

            c_string = "\n".join(c_string_lines)

            return f"{{\n    PyRun_SimpleString(\n{c_string}\n    );\n}}"

        return re.sub(block_pattern, block_replacement, code, flags=re.DOTALL)

    def _transpile(self) -> str:
        with open(self._source_file, 'r', encoding='utf-8') as reader:
            working_code: str = reader.read()

        working_code = self._resolve_dependencies(working_code)
        working_code = self._transpile_python_blocks(working_code)

        for target_regex, mapped_replacement in self._SYNTAX_MAP.items():
            working_code = re.sub(target_regex, mapped_replacement, working_code)

        if "printf" in working_code and "#include <stdio.h>" not in working_code:
            working_code = f"#include <stdio.h>\n{working_code}"

        if self._has_python:
            working_code = f"#define PY_SSIZE_T_CLEAN\n#include <Python.h>\n{working_code}"
            working_code = working_code.replace("int main() {", "int main() {\n    Py_Initialize();")
            working_code = re.sub(r'(return\s+\d+;\s*})', r'Py_Finalize();\n    \1', working_code)

        return working_code

    def _compile_binary(self, compiled_source: str) -> None:
        print(f"[Compiler] Tuning target code configuration inside '{self._source_file}'...")
        with open(self._temp_c_file, 'w', encoding='utf-8') as writer:
            writer.write(compiled_source)

        native_compiler_path: str = r'C:\mingw64\bin\gcc.exe' if sys.platform == "win32" else 'gcc'
        compile_cmd = [native_compiler_path, self._temp_c_file, '-o', self._output_exe]

        if self._has_python:
            py_version = f"{sys.version_info.major}{sys.version_info.minor}"
            base_prefix = sys.base_prefix
            compile_cmd.extend([
                f"-I{os.path.join(base_prefix, 'include')}",
                f"-L{os.path.join(base_prefix, 'libs')}",
                f"-lpython{py_version}"
            ])

        try:
            compilation_result = subprocess.run(compile_cmd, capture_output=True, text=True)
        finally:
            if os.path.exists(self._temp_c_file):
                os.remove(self._temp_c_file)

        if compilation_result.returncode != 0:
            formatted_error: str = compilation_result.stderr.replace("error:", "out of tune:")
            raise CbCompilationException(f"Accidental encountered during native compilation:\n{formatted_error}")

        print(f"[Success] System assembly completely composed! Application entry point: .\\{self._output_exe}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py cbc.py <source.cb>")
        sys.exit(1)
    compiler = CbCompiler(sys.argv[1])
    compiler.execute_pipeline()