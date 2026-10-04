import sys
from cblang import CbCompiler

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage Error: python cbc.py <filename.cb>")
        sys.exit(1)

    compiler_instance = CbCompiler(source_file=sys.argv[1])
    compiler_instance.execute_pipeline()