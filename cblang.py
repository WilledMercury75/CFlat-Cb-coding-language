import bisect
import glob
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import textwrap
import json
from typing import Dict, Final, List, Tuple


class CbCompilationException(Exception):
    """Custom exception matching C#-style explicit compilation failure handling."""
    pass


# import name -> pip distribution name, where they differ
PIP_NAMES: Final[Dict[str, str]] = {
    "cv2": "opencv-python", "PIL": "Pillow", "yaml": "PyYAML", "sklearn": "scikit-learn",
    "skimage": "scikit-image", "bs4": "beautifulsoup4", "dateutil": "python-dateutil",
    "serial": "pyserial", "OpenSSL": "pyOpenSSL",
}

_STDLIB: Final = getattr(sys, "stdlib_module_names", frozenset())


def _c_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _c_bytes(name: str, text: str) -> str:
    """Emit text as a NUL-terminated byte array, so no quoting/escaping can ever go wrong."""
    data = text.encode("utf-8") + b"\0"
    rows = [", ".join(f"0x{b:02x}" for b in data[i:i + 16]) for i in range(0, len(data), 16)]
    return f"static const char {name}[] = {{\n    " + ",\n    ".join(rows) + "\n};\n"

# C side of the Python bridge
_C_RT_HEAD: Final[str] = r"""#ifdef _WIN32
#include <windows.h>
#define CB_SYM(h, n)    ((void *)GetProcAddress((HMODULE)(h), (n)))
#define CB_SETENV(k, v) (SetEnvironmentVariableA((k), (v)), _putenv_s((k), (v)))
#else
#include <dlfcn.h>
#define CB_SYM(h, n)    dlsym((h), (n))
#define CB_SETENV(k, v) setenv((k), (v), 1)
#endif
#define CB_DEBUG(...) do { if (getenv("CB_PY_DEBUG")) { fprintf(stderr, "[Cb debug] " __VA_ARGS__); fputc('\n', stderr); } } while (0)

/* If this exe was double-clicked its console closes the moment we exit; keep
 * error text readable by waiting for Enter (Windows only, only when we own the console). */
static void cb_pause_if_own_console(void)
{
#ifdef _WIN32
    DWORD pids[2];
    if (GetConsoleProcessList(pids, 2) == 1) {
        fputs("\n[Cb] Press Enter to close...", stderr);
        fflush(stderr);
        getchar();
    }
#endif
}
"""

_C_RT_BODY: Final[str] = r"""
typedef void *cb_obj;
static void (*cb_Py_Initialize)(void);
static void (*cb_Py_Finalize)(void);
static int (*cb_PyRun_SimpleStringFlags)(const char *, void *);
static cb_obj (*cb_Py_CompileString)(const char *, const char *, int);
static cb_obj (*cb_PyEval_EvalCode)(cb_obj, cb_obj, cb_obj);
static cb_obj (*cb_PyImport_AddModule)(const char *);
static cb_obj (*cb_PyModule_GetDict)(cb_obj);
static void (*cb_PyErr_Print)(void);
static void (*cb_Py_DecRef)(cb_obj);
static int cb_py_ready = 0; /* 0 = not started, 1 = running, -1 = failed to start */

static void *cb_open_lib(const char *p)
{
#ifdef _WIN32
    if (strchr(p, '\\') || strchr(p, '/'))
        return (void *)LoadLibraryExA(p, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    return (void *)LoadLibraryA(p);
#else
    return dlopen(p, RTLD_NOW | RTLD_GLOBAL);
#endif
}

static int cb_py_exec(const char *src, const char *name)
{
    cb_obj main_mod = cb_PyImport_AddModule("__main__");                 /* borrowed */
    cb_obj dict = main_mod ? cb_PyModule_GetDict(main_mod) : NULL;       /* borrowed */
    cb_obj code = dict ? cb_Py_CompileString(src, name, 257) : NULL;     /* 257 = Py_file_input */
    cb_obj res = code ? cb_PyEval_EvalCode(code, dict, dict) : NULL;
    int ok = (res != NULL);
    if (!ok) cb_PyErr_Print();
    if (res) cb_Py_DecRef(res);
    if (code) cb_Py_DecRef(code);
    return ok ? 0 : -1;
}

static void cb_py_stop(void)
{
    if (cb_py_ready > 0) cb_Py_Finalize();
    cb_py_ready = 0;
}

static int cb_py_start(void)
{
    if (cb_py_ready) return cb_py_ready > 0;
    cb_py_ready = -1;

    /* Environment first: Python reads it while it initialises, so it must be set before anything loads. */
    if (!getenv("PYTHONHOME")) {
        const char *home = getenv("CB_PYTHON_HOME");
        if (!home || !*home) home = CB_PY_HOME;
        if (home && *home) CB_SETENV("PYTHONHOME", home);
    }
    if (!getenv("TCL_LIBRARY") && *CB_TCL_LIBRARY) CB_SETENV("TCL_LIBRARY", CB_TCL_LIBRARY);
    if (!getenv("TK_LIBRARY") && *CB_TK_LIBRARY) CB_SETENV("TK_LIBRARY", CB_TK_LIBRARY);
    CB_DEBUG("PYTHONHOME=%s TCL_LIBRARY=%s TK_LIBRARY=%s", getenv("PYTHONHOME") ? getenv("PYTHONHOME") : "(unset)",
             getenv("TCL_LIBRARY") ? getenv("TCL_LIBRARY") : "(unset)", getenv("TK_LIBRARY") ? getenv("TK_LIBRARY") : "(unset)");

    void *lib = NULL;
    const char *over = getenv("CB_PYTHON_LIB");
    if (over && *over) { lib = cb_open_lib(over); CB_DEBUG("CB_PYTHON_LIB %s -> %s", over, lib ? "loaded" : "FAILED"); }
    for (int i = 0; !lib && CB_PY_LIBS[i]; i++) {
        lib = cb_open_lib(CB_PY_LIBS[i]);
        CB_DEBUG("load %s -> %s", CB_PY_LIBS[i], lib ? "loaded" : "failed");
    }
    if (!lib) {
        fputs("[Cb] cannot load the Python runtime. Tried:\n", stderr);
        if (over && *over) fprintf(stderr, "       %s  (CB_PYTHON_LIB)\n", over);
        for (int i = 0; CB_PY_LIBS[i]; i++) fprintf(stderr, "       %s\n", CB_PY_LIBS[i]);
        fputs("     Install Python, or point CB_PYTHON_LIB at its python3 library.\n", stderr);
        cb_pause_if_own_console();
        return 0;
    }

    const char *missing = NULL;
#define CB_LOAD(n) do { *(void **)(&cb_##n) = CB_SYM(lib, #n); if (!cb_##n) missing = #n; } while (0)
    CB_LOAD(Py_Initialize);
    CB_LOAD(Py_Finalize);
    CB_LOAD(PyRun_SimpleStringFlags);
    CB_LOAD(Py_CompileString);
    CB_LOAD(PyEval_EvalCode);
    CB_LOAD(PyImport_AddModule);
    CB_LOAD(PyModule_GetDict);
    CB_LOAD(PyErr_Print);
    CB_LOAD(Py_DecRef);
#undef CB_LOAD
    if (missing) {
        fprintf(stderr, "[Cb] the loaded library is not a CPython 3 runtime (missing %s)\n", missing);
        cb_pause_if_own_console();
        return 0;
    }

    CB_DEBUG("Py_Initialize...");
    cb_Py_Initialize();
    CB_DEBUG("Python initialised");
    cb_py_ready = 1;
    atexit(cb_py_stop);
    if (cb_py_exec(CB_PY_INIT, "<cb:init>") != 0) {
        fputs("[Cb] Python started, but the startup script failed (see above); the program's Python blocks will not run.\n", stderr);
        cb_pause_if_own_console();
        return 0;
    }
    CB_DEBUG("startup script ok");
    return 1;
}

/* Runs one embedded Python block.  A failure prints the traceback and marks the
 * program as failed, which is what `lento` / `tempo_lost` handlers react to. */
static void cb_py_block(const char *src, const char *name)
{
    fflush(stdout);
    CB_DEBUG("running Python block from %s", name);
    if (!cb_py_start() || cb_py_exec(src, name) != 0) {
        cb_py_failed = 1;
        CB_DEBUG("block FAILED");
        cb_pause_if_own_console();
    } else {
        CB_DEBUG("block finished");
    }
    if (cb_py_ready > 0)
        cb_PyRun_SimpleStringFlags("import sys\nsys.stdout.flush()\nsys.stderr.flush()\n", NULL);
}
"""

_C_READ_INT: Final[str] = r"""
/* ascolta(x): read a whole number from a line of input; blank or invalid lines re-prompt. */
static void cb_read_int(int *out)
{
    char line[128];
    for (;;) {
        fflush(stdout);
        if (!fgets(line, sizeof line, stdin)) {
            fputs("[Cb] input closed; using 0\n", stderr);
            *out = 0;
            return;
        }
        char *end;
        long v = strtol(line, &end, 10);
        int parsed = (end != line);   /* at least one digit was read */
        while (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n') end++;
        if (parsed && *end == '\0') { *out = (int)v; return; }
        printf("Please type a whole number and press Enter: ");
    }
}
"""

_COMMENT_BLOCK: Final[str] = r'(?<!\w)b\[([\s\S]*?)\]b'
_COMMENT_LINE: Final[str] = r'(?<!\w)bb(.*)'
_BLOCK_START: Final = re.compile(r'(?<![\w.])(\w+)\.startcb\(\)\s*\[')
_DECL: Final = re.compile(r'\b(?:int|char|float|double|long|short)\s+\**(\w+)')
_FUNC_HEAD: Final = re.compile(r'\bint\s+\w+\s*\([^)]*\)\s*\{')


class CbCompiler:
    _SYNTAX_MAP: Final[Dict[str, str]] = {
        _COMMENT_BLOCK: r'/*\1*/',
        _COMMENT_LINE: r'//\1',
        r'\bbnt\b': 'int',
        r'\bverissimo\b': '1',
        r'\bfalsissimo\b': '0',
        r'\btutti\b': 'extern',
        r'\bcon\b': '&&',
        r'\bsenza\b': '!',
        r'\boppure\b': '||',
        r'\bsilenzio\b': '/* pass */ ;',
    }

    def __init__(self, source_file: str) -> None:
        stem, _ = os.path.splitext(source_file)
        self._source_file: str = source_file
        self._temp_c_file: str = stem + '.tmp.c'
        self._output_exe: str = stem + ('.exe' if sys.platform == "win32" else '')
        self._has_python: bool = False
        self._has_csharp: bool = False
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

    # dependencies
    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    def _ensure_python_module(self, name: str) -> None:
        if self._module_available(name):
            print(f"[System] Module '{name}' is already available.")
            return
        if name in _STDLIB:
            hint = (" On Windows, rerun the Python installer, choose Modify, and enable 'tcl/tk and IDLE'."
                    if name == "tkinter" else "")
            raise CbCompilationException(
                f"'{name}' is part of Python's standard library but is missing from this Python install.{hint}")
        pip_name = PIP_NAMES.get(name, name)
        print(f"[Pip] Package '{pip_name}' is missing. Fetching via environment package manager...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", pip_name, "--quiet"], check=True)
        except (subprocess.CalledProcessError, OSError):
            raise CbCompilationException(f"Dependency resolution failed for module: '{name}' (pip: '{pip_name}').")
        importlib.invalidate_caches()

    def _resolve_dependencies(self, raw_code: str) -> str:
        scan = re.sub(_COMMENT_BLOCK, '', raw_code)
        scan = re.sub(_COMMENT_LINE, '', scan)

        package_token_pattern: str = r'\bcall\s+(\w+)'
        invoke_token_pattern: str = r'\binvoke\s+([a-zA-Z0-9_.]+)'
        discovered_packages: List[str] = list(dict.fromkeys(re.findall(package_token_pattern, scan)))
        raw_invokes = list(dict.fromkeys(re.findall(invoke_token_pattern, scan)))

        self._invoked_sdks = []
        for sdk in raw_invokes:
            if sdk.lower() == "microsoft":
                self._invoked_sdks.append("Microsoft.CSharp")
            else:
                self._invoked_sdks.append(sdk)

        if discovered_packages or self._invoked_sdks or self._has_csharp:
            self._has_python = True

        if discovered_packages:
            print("[System.Link] Harmonizing Python package dependencies...")
            for package in discovered_packages:
                self._ensure_python_module(package)

        if self._invoked_sdks or self._has_csharp:
            print("[System.Link] Harmonizing C# SDK bindings via pythonnet...")
            self._ensure_python_module('pythonnet')

        raw_code = re.sub(package_token_pattern, r'// call \1 -> Dynamic Package Linked', raw_code)
        raw_code = re.sub(invoke_token_pattern, r'// invoke \1 -> C# SDK Linked', raw_code)
        return raw_code

    # Python blocks & concurrency support
    @staticmethod
    def _find_block_end(code: str, i: int, start_line: int) -> int:
        depth, n = 1, len(code)
        while i < n:
            c = code[i]
            if c == '#':
                j = code.find('\n', i)
                i = n if j < 0 else j
            elif c in '"\'':
                if code.startswith(c * 3, i):
                    j = i + 3
                    while j < n and not code.startswith(c * 3, j):
                        j += 2 if code[j] == '\\' else 1
                    i = j + 3
                else:
                    j = i + 1
                    while j < n and code[j] != c and code[j] != '\n':
                        j += 2 if code[j] == '\\' else 1
                    i = j + 1
            elif c == '[':
                depth += 1
                i += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return i
                i += 1
            else:
                i += 1
        raise CbCompilationException(f"Block starting at line {start_line} is missing its closing ']'.")

    def _generate_concb_python_payload(self, mode: str, tasks: List[Dict[str, str]]) -> str:
        payload = textwrap.dedent("""\
            import threading
            import queue
            import sys
            import os
            import subprocess
            import tempfile

            if 'cb_queue' not in globals():
                cb_queue = queue.Queue()

            def _run_cs_block(cs_code):
                try:
                    fd, temp_cs = tempfile.mkstemp(suffix=".cs")
                    os.close(fd)
                    with open(temp_cs, "w", encoding="utf-8") as f:
                        f.write(cs_code)

                    temp_dll = temp_cs + ".dll"

                    csc_path = r"C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe"
                    if not os.path.exists(csc_path):
                        csc_path = r"C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319\\csc.exe"

                    if os.path.exists(csc_path):
                        cmd = [csc_path, "/t:library", f"/out:{temp_dll}", temp_cs]
                        res = subprocess.run(cmd, capture_output=True, text=True)
                        if res.returncode != 0:
                            print(f"[Cb] C# Compilation Errors:\\n{res.stderr}", file=sys.stderr)
                            return

                        import clr
                        from System.Reflection import Assembly
                        assembly = Assembly.LoadFrom(temp_dll)
                        for t in assembly.GetTypes():
                            m = t.GetMethod("Main")
                            if m:
                                m.Invoke(None, None)
                    else:
                        print("[Cb] C# compiler (csc.exe) not found on system.", file=sys.stderr)

                    if os.path.exists(temp_cs):
                        os.remove(temp_cs)
                except Exception as e:
                    print(f"[Cb] C# execution error: {e}", file=sys.stderr)

            def _execute_concb_group(mode, tasks):
                threads = []
                main_thread_task = None

                for task in tasks:
                    lang = task['lang']
                    code = task['code']

                    if lang == 'py':
                        if "tkinter" in code or "tk." in code:
                            main_thread_task = code
                        else:
                            t = threading.Thread(target=exec, args=(code, globals()), daemon=(mode == 'move'))
                            threads.append(t)
                    elif lang == 'cs':
                        t = threading.Thread(target=_run_cs_block, args=(code,), daemon=(mode == 'move'))
                        threads.append(t)

                for t in threads:
                    t.start()

                if main_thread_task:
                    exec(main_thread_task, globals())

                if mode == 'wait':
                    for t in threads:
                        if t.is_alive():
                            t.join()
        """)
        payload += f"\n_execute_concb_group('{mode}', {json.dumps(tasks)})\n"
        return payload

    def _extract_concb_blocks(self, code: str) -> Tuple[str, List[Tuple[str, str]]]:
        concb_pattern = re.compile(r'\bconcb\s*\(\s*(wait|move)\s*\)\s*\[')
        startcb_pattern = re.compile(r'\bstartcb\s*\(\s*(py|cs)\s*\)\s*\[')

        blocks: List[Tuple[str, str]] = []
        out: List[str] = []
        pos = 0

        while True:
            m = concb_pattern.search(code, pos)
            if not m:
                out.append(code[pos:])
                break

            mode = m.group(1)
            bracket_line = code.count('\n', 0, m.end()) + 1
            end_idx = self._find_block_end(code, m.end(), bracket_line)
            inner_content = code[m.end():end_idx]

            tasks = []
            inner_pos = 0
            while True:
                sm = startcb_pattern.search(inner_content, inner_pos)
                if not sm:
                    break
                lang = sm.group(1)
                sub_bracket_line = bracket_line + inner_content.count('\n', 0, sm.end())
                sub_end = self._find_block_end(inner_content, sm.end(), sub_bracket_line)

                sub_code = textwrap.dedent(inner_content[sm.end():sub_end]).strip()
                tasks.append({"lang": lang, "code": sub_code})

                if lang == 'cs':
                    self._has_csharp = True

                inner_pos = sub_end + 1

            if len(tasks) < 2:
                raise CbCompilationException(
                    f"Compilation Error: concb({mode}) at line {bracket_line} requires at least 2 startcb blocks.")

            py_payload = self._generate_concb_python_payload(mode, tasks)
            placeholder = f"__CONCB_BLOCK_PLACEHOLDER_{len(blocks)}__"
            blocks.append((placeholder, py_payload))

            out.append(code[pos:m.start()])
            out.append(placeholder)
            pos = end_idx + 1

        return "".join(out), blocks

    def _extract_python_blocks(self, code: str) -> Tuple[str, List[Tuple[str, str]]]:
        blocks: List[Tuple[str, str]] = []
        out: List[str] = []
        pos = 0
        while True:
            m = _BLOCK_START.search(code, pos)
            if not m:
                out.append(code[pos:])
                break
            bracket_line = code.count('\n', 0, m.end()) + 1
            end = self._find_block_end(code, m.end(), bracket_line)
            body = code[m.end():end]

            lead = re.match(r'(?:[ \t]*\r?\n)*', body)
            first_line = bracket_line + lead.group().count('\n')
            text = textwrap.dedent(body[lead.end():]).rstrip() + "\n"
            prefix = (f"import {m.group(1)};" if first_line > 1 else "") + "\n" * (first_line - 1)

            placeholder = f"__PYTHON_BLOCK_PLACEHOLDER_{len(blocks)}__"
            blocks.append((placeholder, prefix + text))
            out.append(code[pos:m.start()])
            out.append(placeholder)
            pos = end + 1
        return "".join(out), blocks

    # compile-time facts about this Python; baked into the executable
    def _python_runtime_c(self) -> str:
        base = sys.base_prefix
        ver = f"{sys.version_info.major}{sys.version_info.minor}"
        dotver = f"{sys.version_info.major}.{sys.version_info.minor}"

        libs: List[str] = []
        if sys.platform == "win32":
            libs += [os.path.join(base, f"python{ver}.dll"), f"python{ver}.dll",
                     os.path.join(base, "python3.dll"), "python3.dll"]
        else:
            libdir = sysconfig.get_config_var("LIBDIR") or ""
            for var in ("INSTSONAME", "LDLIBRARY"):
                name = sysconfig.get_config_var(var)
                if name and not name.endswith(".a"):
                    libs += [os.path.join(libdir, name), name]
            libs += [f"libpython{dotver}.so", f"libpython{dotver}.dylib"]
        libs = list(dict.fromkeys(libs))

        tcl = tk = ""
        if sys.platform == "win32":
            tcl_dirs = sorted(glob.glob(os.path.join(base, "tcl", "tcl[89]*")))
            tk_dirs = sorted(glob.glob(os.path.join(base, "tcl", "tk[89]*")))
            tcl, tk = (tcl_dirs[0] if tcl_dirs else ""), (tk_dirs[0] if tk_dirs else "")

        paths: List[str] = []
        try:
            import site
            paths += site.getsitepackages() + [site.getusersitepackages()]
        except Exception:
            pass
        paths += [sysconfig.get_path("purelib"), sysconfig.get_path("platlib")]
        paths = [p for p in dict.fromkeys(paths) if p and os.path.isdir(p)]

        init = ["import os, site, sys", f"for _p in {paths!r}:", "    if os.path.isdir(_p): site.addsitedir(_p)"]
        if self._invoked_sdks or self._has_csharp:
            init += ["try:",
                     "    import pythonnet",
                     "    import sys",
                     "    try:",
                     "        if sys.platform == 'win32':",
                     "            pythonnet.load('netfx')",
                     "        else:",
                     "            pythonnet.load('coreclr')",
                     "    except Exception:",
                     "        pythonnet.load('coreclr')",
                     "    import clr",
                     f"    for _n in {self._invoked_sdks!r}:", "        clr.AddReference(_n)",
                     "except Exception as _e:",
                     "    print('[Cb] C# bridge unavailable:', _e, file=sys.stderr)"]

        return (_C_RT_HEAD
                + "static const char *const CB_PY_LIBS[] = {" + ", ".join(_c_str(p) for p in libs) + ", NULL};\n"
                + f"static const char *const CB_PY_HOME = {_c_str(base)};\n"
                + f"static const char *const CB_TCL_LIBRARY = {_c_str(tcl)};\n"
                + f"static const char *const CB_TK_LIBRARY = {_c_str(tk)};\n"
                + _c_bytes("CB_PY_INIT", "\n".join(init) + "\n")
                + _C_RT_BODY)

    # transpiler
    @staticmethod
    def _rewrite_pianissimo(code: str) -> str:
        out: List[str] = []
        pos = 0
        for m in re.finditer(r'\bpianissimo\s*\(', code):
            if m.start() < pos:
                continue
            i, depth = m.end(), 1
            while i < len(code) and depth:
                c = code[i]
                if c in '"\'':
                    j = i + 1
                    while j < len(code) and code[j] != c:
                        j += 2 if code[j] == '\\' else 1
                    i = j
                elif c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                i += 1
            if depth:
                continue
            content = code[m.end():i - 1].strip()
            end = i
            tail = re.match(r'\s*;?', code[end:])
            end += tail.end()
            if content.startswith('"') or content.startswith("'"):
                repl = f'printf({content});\n    printf("\\n");'
            else:
                repl = f'printf("%d\\n", {content});'
            out.append(code[pos:m.start()])
            out.append(repl)
            pos = end
        out.append(code[pos:])
        return "".join(out)

    def _transpile(self) -> str:
        with open(self._source_file, 'r', encoding='utf-8') as reader:
            working_code: str = reader.read()

        working_code, concb_blocks = self._extract_concb_blocks(working_code)
        working_code, python_blocks = self._extract_python_blocks(working_code)

        all_blocks = python_blocks + concb_blocks
        if all_blocks:
            self._has_python = True

        working_code = self._resolve_dependencies(working_code)

        for target_regex, mapped_replacement in self._SYNTAX_MAP.items():
            working_code = re.sub(target_regex, mapped_replacement, working_code)

        def func_replacer(match):
            fname = match.group(1)
            params = match.group(2).strip()
            if not params:
                return f"int {fname}(void)"
            typed_params = ", ".join([p if "int" in p or "char" in p else f"int {p}" for p in params.split(",")])
            return f"int {fname}({typed_params})"

        working_code = re.sub(r'\bsolo\s+(\w+)\s*\((.*?)\)', func_replacer, working_code)

        working_code = self._rewrite_pianissimo(working_code)
        working_code = re.sub(r'\bascolta\s*\(\s*([a-zA-Z0-9_]+)\s*\);?', r'cb_read_int(&\1);', working_code)

        working_code = re.sub(r'\bda_capo\b', 'while', working_code)
        working_code = re.sub(r'\bstaccato\b', 'break', working_code)
        working_code = re.sub(r'\bif_forte\b', 'if', working_code)
        working_code = re.sub(r'\belif_mforte\b', 'else if', working_code)
        working_code = re.sub(r'\belse_piano\b', 'else', working_code)
        working_code = re.sub(r'\bcoda\s+([^;\n]+)', r'return \1;', working_code)

        working_code = re.sub(r'\bfermata\s+(\w+)\s+in\s+range\s*\(\s*(\d+)\s*\)', r'for (int \1 = 0; \1 < \2; \1++)',
                              working_code)
        working_code = re.sub(r'\bensemble\s+([a-zA-Z0-9_]+)\s*=\s*\[(.*?)\]', r'int \1[] = {\2};', working_code)
        working_code = re.sub(r'\bcrescendo\s+([a-zA-Z0-9_]+)', r'\1++;', working_code)
        working_code = re.sub(r'\bdecrescendo\s+([a-zA-Z0-9_]+)', r'\1--;', working_code)

        has_main = bool(re.search(r'\ballegro\s*\{', working_code))
        working_code = re.sub(r'\ballegro\s*\{',
                              'int main(void) {\n    int _success = 1;\n    cb_py_failed = 0;\n    {',
                              working_code)
        working_code = re.sub(r'\}\s*lento\s*\{', '}\n    if (!_success || cb_py_failed) {', working_code)
        working_code = re.sub(r'\britardando\s*\{',
                              '{\n    int _try_success = 1;\n    cb_py_failed = 0;\n    {', working_code)
        working_code = re.sub(r'\}\s*tempo_lost\s*\{', '}\n    if (!_try_success || cb_py_failed) {', working_code)

        starts = [m.start() for m in _FUNC_HEAD.finditer(working_code)]
        made_here: Dict[int, set] = {}

        def assign_replacer(match):
            var_name = match.group(1)
            expr = match.group(2).strip()
            if var_name.startswith(('cb_', '_')):
                return match.group(0)
            scope = bisect.bisect_right(starts, match.start())
            region_start = starts[scope - 1] if scope else 0
            known = set(_DECL.findall(working_code[region_start:match.start()]))
            made_home = made_here.setdefault(scope, set())
            known |= made_home
            if var_name in known:
                return f"{var_name} = {expr};"
            made_here[scope].add(var_name)
            return f"int {var_name} = {expr};"

        working_code = re.sub(r'^\s*(?!\/\/)([a-zA-Z0-9_]+)\s*=\s*([^;\n]+);?\s*$', assign_replacer, working_code,
                              flags=re.MULTILINE)

        src_name = os.path.basename(self._source_file)
        for index, (placeholder, py_source) in enumerate(all_blocks):
            working_code = working_code.replace(placeholder, f'cb_py_block(CB_PY_{index}, {_c_str(src_name)});')

        working_code = working_code.rstrip()
        if has_main:
            working_code += "\n    return 0;\n}\n"
        else:
            working_code += "\n"

        headers = ("#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\nstatic int cb_py_failed = 0;\n"
                   + _C_READ_INT)
        if all_blocks:
            headers += self._python_runtime_c()
            for index, (_, py_source) in enumerate(all_blocks):
                headers += _c_bytes(f"CB_PY_{index}", py_source)
        return headers + working_code

    # native build
    @staticmethod
    def _find_c_compiler() -> str:
        found = shutil.which('gcc')
        if found:
            return found
        if sys.platform == "win32" and os.path.exists(r'C:\mingw64\bin\gcc.exe'):
            return r'C:\mingw64\bin\gcc.exe'
        raise CbCompilationException("No C compiler found. Install MinGW-w64 (gcc) and put it on PATH.")

    def _compile_binary(self, compiled_source: str) -> None:
        print(f"[Compiler] Tuning target code configuration inside '{self._source_file}'...")
        with open(self._temp_c_file, 'w', encoding='utf-8') as writer:
            writer.write(compiled_source)

        compile_cmd = [self._find_c_compiler(), self._temp_c_file, '-o', self._output_exe]
        if sys.platform.startswith('linux'):
            compile_cmd.append('-ldl')

        try:
            compilation_result = subprocess.run(compile_cmd, capture_output=True, text=True)
        finally:
            if os.path.exists(self._temp_c_file) and not os.environ.get('CB_KEEP_C'):
                os.remove(self._temp_c_file)

        if compilation_result.returncode != 0:
            formatted_error: str = re.sub(r'(:\d+(?::\d+)?:\s*)error:', r'\1out of tune:', compilation_result.stderr)
            raise CbCompilationException(f"Accidental encountered during native compilation:\n{formatted_error}")

        print(f"[Success] System assembly completely composed! Application entry point: {self._output_exe}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py cblang.py <source.cb>")
        sys.exit(1)
    compiler = CbCompiler(sys.argv[1])
    compiler.execute_pipeline()