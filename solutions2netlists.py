"""Write the netlist of every design in the solutions CSVs, sorted into one folder per CSV.

Each row of solutions/<run_id>.csv (written by utils/saving.py) becomes
solutions/netlists/<run_id>/TwoStage_step<step>.cir. The netlist comes from the same
NgspiceWrapper.create_new_netlist call and PVT corner as in CircuitEnv.simulate, so it is
the netlist that was simulated, with the row's specs and reward as a comment under the title.

Its .include and wrdata paths are relative to the project root, so simulate it from there:
    ngspice -b solutions/netlists/<run_id>/TwoStage_step01416.cir

Usage:
    python solutions2netlists.py                          # every CSV in solutions/
    python solutions2netlists.py solutions/<run_id>.csv   # only the given CSVs
    python solutions2netlists.py --out other_folder
"""
import argparse
import ast
import csv
import glob
import os
import re

from ngspice_interface import NgspiceWrapper

ROOT = os.path.dirname(os.path.abspath(__file__))
YAML_PATH = os.path.join(ROOT, 'ngspice_interface', 'files', 'yaml_files', 'TwoStage.yaml')
PVT_CORNER = {'process': 'TT', 'voltage': 1.2, 'temp': 27}  # keep equal to CircuitEnv.pvt_corner


class SolutionNetlister(NgspiceWrapper):
    """Names each netlist and its wrdata output files after the design instead of a
    timestamp and random letters, so a rerun overwrites the same files."""
    design_name = None

    def generate_random_name(self, length=10):
        return self.design_name


def parse_dict(text):
    # CSVs from before the .item() fix in CircuitEnv.step hold reprs such as np.int64(11)
    return ast.literal_eval(re.sub(r'np\.\w+\(([^()]*)\)', r'\1', text))


def write_netlists(netlister, csv_path, out_root):
    """Write one netlist per row of `csv_path` into out_root/<CSV name>/ and return their paths."""
    csv_name = os.path.basename(csv_path)
    netlister.output_netlists_folder = os.path.join(out_root, os.path.splitext(csv_name)[0])
    paths, seen = [], {}
    with open(csv_path, newline='') as f:
        for row in csv.DictReader(f):  # skips the blank row after each entry
            step = int(row['Simulation step'])
            name = f'step{step:05d}'
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:  # a rerun with the same run_id appends to the CSV and restarts the steps
                name += f'_{seen[name]}'
            netlister.design_name = name
            path = netlister.create_new_netlist(parse_dict(row['Circuit Params']),
                                                process=PVT_CORNER['process'],
                                                temp_pvt=PVT_CORNER['temp'],
                                                vdd=PVT_CORNER['voltage'])

            specs = parse_dict(row['Specs'])
            header = [f'* {csv_name}, simulation step {step}, reward {float(row["Reward"]):.6g}\n',
                      '* Specs: ' + ' '.join(f'{k}={v:.6g}' for k, v in specs.items()) + '\n']
            with open(path) as f_net:
                lines = f_net.readlines()
            lines[1:1] = header  # below the title line, which ngspice never parses
            with open(path, 'w') as f_net:
                f_net.writelines(lines)
            paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('csvs', nargs='*', help='solutions CSVs (default: every CSV in solutions/)')
    parser.add_argument('--out', default=os.path.join(ROOT, 'solutions', 'netlists'),
                        help='folder that gets one subfolder of netlists per CSV')
    args = parser.parse_args()

    # absolute paths first: the chdir below would change what relative ones point to
    csv_paths = ([os.path.abspath(p) for p in args.csvs]
                 or sorted(glob.glob(os.path.join(ROOT, 'solutions', '*.csv'))))
    if not csv_paths:
        parser.error('no CSVs found in solutions/')
    out_root = os.path.abspath(args.out)

    os.chdir(ROOT)  # NgspiceWrapper finds the template netlist from the working directory
    netlister = SolutionNetlister(YAML_PATH)
    # relative to the project root, like the template's .include, so no machine-specific paths
    netlister.output_files_folder = os.path.join('no_backup', 'output_files')
    os.makedirs(netlister.output_files_folder, exist_ok=True)  # where a simulated netlist writes

    total = 0
    for csv_path in csv_paths:
        n = len(write_netlists(netlister, csv_path, out_root))
        print(f'{os.path.basename(csv_path)}: {n} netlists')
        total += n
    print(f'{total} netlists in {out_root}')


if __name__ == '__main__':
    main()
