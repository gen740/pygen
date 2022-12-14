import argparse
import toml
import pathlib
from pygen.pygen_parser import Parser


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config_file", required=True, type=str, help="Path to config file"
    )

    parser.add_argument(
        "--cwd", required=True, type=str, help="Current Working Directory"
    )

    args = parser.parse_args()

    configs = toml.load(args.config_file)

    cwd = pathlib.Path(args.cwd)

    sources = []
    for i in configs["sources"]:
        sources.extend([i for i in cwd.glob(i)])

    headers = []
    for i in configs["headers"]:
        headers.extend([i for i in cwd.glob(i)])

    output_dir = cwd.joinpath(configs["output_dir"])

    pygen = Parser()

    flags = configs["flags"]
    for i in configs["include_directories"]:
        flags.append(f"-I{str(cwd.joinpath(i).absolute())}")
        print(f"-I{str(cwd.joinpath(i).absolute())}")

    for i in sources:
        pygen.parse_from_file(i, lang="cpp", flags=configs["flags"])

    for i in headers:
        pygen.parse_from_file(i, lang="hpp", flags=configs["flags"])

    for i in configs["include_headers"]:
        pygen.add_hpp_includes(i)

    with open(str(output_dir) + "/pygen_generated.hpp", "w") as f:
        f.write(pygen.hpp_generate())

    with open(str(output_dir) + "/pygen_generated.cpp", "w") as f:
        f.write(pygen.cpp_generate())


if __name__ == "__main__":
    run()
