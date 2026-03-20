import sys
from get_dep_information import get_dep_information_from_package
from .model import database

def main():
    """Resolve requirements as project names on PyPI.
    The requirements are taken as command-line arguments
    and the resolution result will be printed to stdout.
    """
    if len(sys.argv) == 1:
        print(f"Usage: {sys.argv[0]} <Package Local Path>")
        return

    alldeps = get_dep_information_from_package(sys.argv[1])
    database.update(alldeps)
    
    

if __name__ == "__main__":
    main()
