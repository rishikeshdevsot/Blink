import argparse
import re
import os
import sys
import subprocess
import logging
import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

# Dump a perf.data file into the individual sample

PHONE_CONFIG_PATH='/data/local/tmp'
HIPERF_HOST_PATH='/home/yWX1380092/projects/critical_path/chenxing_workload/get_html_250212/bin/linux/x86_64/hiperf_host'
logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

def run(cmd, **kwargs):
    logging.info(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)

def get_dump_file(inp, out, sympath, remote=False, linux=False):
    if linux:
        remote_prefix = '/home/yWX1380092/'
        name = Path(inp)
        remote_in = remote_prefix / name
        # remote_out = remote_prefix + Path(out).name
        run(['ssh', 'ptlaby29', f"mkdir -p {remote_in.parent}"])
        run(['scp', inp, f'ptlaby29:{remote_in}'])
        with open(out, 'w') as fd:
            run(['ssh', 'ptlaby29', f"perf script -i {remote_in}"], stdout=fd)
        return# run(['scp', f'ptlaby29:{remote_out}', out])
    if remote:
        name = Path(inp).name
        phone_inp = PHONE_CONFIG_PATH + '/' + name
        phone_out = PHONE_CONFIG_PATH + '/' + name + '.dump'
        run(['hdc', 'file', 'send', inp, PHONE_CONFIG_PATH])
        if sympath != '':
            run(['hdc', 'shell', f'hiperf dump -i  {phone_inp} -o {phone_out} --sympath {sympath}'])
        else:
            run(['hdc', 'shell', f'hiperf dump -i  {phone_inp} -o {phone_out}'])

        run(['hdc', 'file', 'recv', phone_out, out])
        run(['hdc', 'shell', f'rm -f {phone_inp}'])
        run(['hdc', 'shell', f'rm -f {phone_out}'])
    else:
       run([HIPERF_HOST_PATH, 'dump', '-i', inp, '--sympath', sympath, '-o', out])
    #    run([HIPERF_HOST_PATH, 'report', '-i', inp, '-o', inp + '.report'])

def get_report_file(inp, out, sympath, remote=False):
    if remote:
        pass
    else:
       run([HIPERF_HOST_PATH, 'report', '-i', inp, '-o', inp + '.report'])


def parse_perf_dump_linux(input_file, output_file, fullstack):

    '''
    parse linux perf script result:
    example_linux 842441 4335933.759051:        291 instructions:u:
	          400440 a+0x44 (/home/yWX1380092/micro/example_linux)
	          4004fc workload+0x20 (/home/yWX1380092/micro/example_linux)
	          4005a8 main+0xa0 (/home/yWX1380092/micro/example_linux)
	          400864 __libc_start_main+0x27c (/home/yWX1380092/micro/example_linux)
	          400300 _start+0x4c (/home/yWX1380092/micro/example_linux)
    '''

    with open(input_file, 'r',  errors='replace') as file:
        data = file.readlines()
        samples_all = []
        sample = []
        for line in data:
            if ':' in line and len(sample) > 0:
                samples_all.append(sample)
                sample = []
            sample.append(line)

        samples_all.append(sample)

        samples_parsed = []
        for s in samples_all:
            first = s[0]
            result = re.search('\w+ \d+ \d+\.\d+:\s+(\d+)', first)
            period = result.group(1)
            stacktrace = []
            if fullstack:
                stack_lines = s[1:]
            else:
                stack_lines = s[1:2]
            for l in stack_lines:
                if l.strip() == '':
                    continue
                result = re.search('[a-z0-9]+ ([\w\[\]]+)(\+0x[a-z0-9]+)? \(([\w/\[\]]+)\)', l)
                if not result:
                    print(l)
                    sys.exit(1)
                fun, lib = result.group(1), result.group(3)
                samples_parsed.append( (fun, lib, int(period)) )
        df = pd.DataFrame(samples_parsed, columns=['fun', 'lib', 'period'])
        final = df.groupby(['fun','lib']).agg(
            period=('period','sum'),
            num_sample=('period','count')
        ).reset_index()
        final.to_csv(output_file, index=False)

# Define a function to parse the perf date
def parse_perf_dump(input_file, event):
    with open(input_file, 'r',  errors='replace') as file:
        data = file.readlines()

    ids = []
    for line in reversed(data):
        # print('.', end='')
        if search_res := re.search(r'([\w-]+) ids: (.*)', line):
            pmu = search_res.group(1)
            if  event in pmu:
            # if 'hw-cpu-cycles' in pmu:
                ids = search_res.group(2).strip().split(',')
                ids = set(map(int, ids))
                break


    # print(ids)

    # Container to hold parsed data
    parsed_data = {
        'callstacks': [],
        'events': [],
        'attributes': []
    }

    # Define regex patterns for extracting useful information
    stack_pattern = re.compile(r'^\s*(0x[0-9A-Fa-f]+)\s+([^\s]+)')
    event_pattern = re.compile(r'event_types\[file section\]: offset (\d+), size (\d+)')
    attribute_pattern = re.compile(r'feature:\s+([a-zA-Z0-9_]+)')
    record_pattern = re.compile(r'(record sample: type 9)')
    function_per_library = {}
    samples = []
    # Loop through the lines and apply the patterns
    state = "NO_RECORD"
    sample = []
    for n in range(len(data)):
        l = data[n]
        if state == "NO_RECORD":
            sample = []
            if record_pattern.search(l):
                sample.append(l)
                state = "RECORD"
        elif state == "RECORD":
            if record_pattern.search(l):
                samples.append(sample)
                sample = []
            # else:
            sample.append(l)

    if state == "RECORD":
        samples.append(sample)

    # for s in samples:
    #     print(s[0])
    # print(len(samples))
    output=[]
    samples = filter(lambda x: re.search('type 9', x[0]), samples)
    # print(list(samples)[0])
    # exit(0)
    for s in samples:
        # print(s)
        # print(''.join(s))
        parsed_sample = {
            'timestamp': 0,
            'pid': 0,
            'tid': 0,
            'callchain': []
        }

        # print(s[0])

        state='start'
        skip=False
        parsed = parsed_sample.copy()

        for l in s:
            if state == 'start':
                # print(l)
                if result := re.search(r'ID (\d+)', l):
                    sample_id = int(result.group(1))
                    if sample_id not in ids:
                        skip = True
                        break

                    state = 'got_id'
            elif state == 'got_id':
                if result := re.search(r'pid (\d+), tid (\d+)', l):
                    # print(result.group(1), result.group(2))
                    parsed['pid'] = int(result.group(1))
                    parsed['tid'] = int(result.group(2))
                    # print(parsed['tid'])
                    state = 'got_time'
            elif state == 'got_time':
                if result := re.search(r'time (\d+)', l):
                    parsed['timestamp'] = int(result.group(1))
                    state = 'find_period'
        # period 1832090
            elif state == 'find_period':
                if result := re.search(r'period (\d+)', l):
                    parsed['period'] = int(result.group(1))
                    state = 'find_stack'

            elif state == 'find_stack':
                if result:= re.search(r'callchain: (\d+)', l):
                    callchain = []
                    callchain_total = int(result.group(1))
                    state = "found_stack"
            elif state == "found_stack":
                if result := re.search(r'(\d+:0x\w+ : )(.*)@(.*):', l):
                # if result := re.search(r'(.*)@(.*):', l):
                    callchain.append(
                        (result.group(2),
                        result.group(3))
                    )
                    # print(result.group(1))
                else:
                    # print(l)
                    state == 'done'

        if state == "found_stack" or state == 'done':
            # now we have caller->callee
            parsed['callchain'] = list(reversed(callchain))
            if len(parsed['callchain']) != callchain_total:
                print(len(parsed['callchain']), callchain_total)
                print(parsed['callchain'])
                print(parsed['timestamp'])
                # sys.exit(-1)
                continue
            output.append(parsed)

    # total_period = 0
    # for o in output:
    #     total_period += o['period']
        # print(o['period'])
    # print(total_period)
    return output

def parse_report_file(input_file, output_file, fullstack):
    with open(input_file, 'r') as fd:
        lines = []
        start = False
        for line in fd:
            if line.strip().startswith('Heating'):
                start = True
            if start:
                lines.append(line)
    with open(output_file, 'w') as fd:
        header_len = len(re.split(r'\s+', lines[0].strip()))
        print(header_len)
        for line in lines:
            elements = re.split(r'\s+', line.strip())
            print(elements)
            for i in range(header_len - 1):
                # print(elements[i])
                fd.write(elements[i])
                fd.write(',')
            fd.write('"' + ' '.join(elements[header_len - 1: ]) + '"')
            fd.write('\n')



def aggregate_per_func(input_file, output_file, fullstack, event):
    used_libraries = {}
    logged_samples = []

    perf_samples_libs = {
        'total_samples': 0,
        'total_periods': 0
        # lib1: number of perf samples that has it,
        # if multiple occurence in 1 stack trace, count it as 1

    }
    # lib1 : 3
    # lib2 : 4
    # number of samples: total_number of
    # total number of cycles:

    samples = parse_perf_dump(input_file, event)
    for o in samples:
        uniquelibs = set()
        if not fullstack:
            o['callchain'] = [(o['callchain'][-1])]
        # print(o['callchain'])
        for callchain in o['callchain']:
            lib = callchain[1]
            func = callchain[0]
            res = re.search(r'(.*)\[0x\w+:0x\w+\]\[\+0x\w+\]', func)
            if not res:
                # print("it might be just a library + offset")
                res = re.search(r'(.*)[+@]0x\w+', func)
                if not res:
                    print("unable to recognize function name in:", callchain)
                    sys.exit(1)
                elif res.group(1) != lib:
                    print("the function name is not a library+offset: ", func)
                    sys.exit(1)
                else:
                    func = ""
            else:
                func = res.group(1)

            old_result= \
                used_libraries.get((func, lib), (0,0))
            new_result = ( old_result[0]  + o['period'],
                           old_result[1] + 1 )
            used_libraries[(func, lib)] = new_result
            uniquelibs.add(lib)

            logged_samples.append([func, lib, o['period'], o['pid'], o['tid']])


        for l in uniquelibs:
            perf_samples_libs[l + '.sample'] = \
                perf_samples_libs.get(l + '.sample', 0) + 1
            perf_samples_libs[l + '.period'] = \
                perf_samples_libs.get(l + '.period', 0) + o['period']

        perf_samples_libs['total_samples'] += 1
        perf_samples_libs['total_periods'] += o['period']

    #done with all samples:

    with open(output_file + '.json', 'w') as fd:
        json.dump(perf_samples_libs, fd)

    logged_samples_df = \
        pd.DataFrame(logged_samples, columns=['fun', 'lib', 'sample', 'pid', 'tid'])

    logged_samples_df.to_csv(output_file + '.sample.stats', index=False)

    table = []
    # fd.write("fun,lib,period\n")
    for (fun, lib), (period, num_sample) in sorted(used_libraries.items(), key=lambda x: x[0]):
        table.append([fun, lib, period, num_sample])
    df = pd.DataFrame(table, columns=['fun', 'lib', 'period', 'num_sample'])
    df.to_csv(output_file, index=False)

def summarize_stat(input_file, output_file):

    with open(input_file, 'r') as fd:
        report = fd.read()
        result = re.search('\s*([0-9,]+)  (hw-)?(\w+)', report)
        if result is None:
            print("perf stat result cannot be parsed")
            sys.exit(1)
        duration = int(result.group(1).replace(',', '').strip())
    with open(output_file, 'w') as fd:
        fd.write('duration\n')
        fd.write(str(duration) + '\n')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Summarize perf samples")
    parser.add_argument("perf_file", help="Path to perf data")
    parser.add_argument("--output", '-o', help="Path to csv report")
    parser.add_argument("--force", '-f', default=False,
                        action='store_true',
                        help="Force regenerate dump file")
    parser.add_argument("--sympath", '-s', default="", help="Path (phone) to symbol path")
    parser.add_argument("--fullstack", '-t', default=False, action="store_true", help="attribute a sample to all functions in the call stack")
    parser.add_argument("--stat", default=False, action="store_true", help="read from the perf stat data (instead of perf record)")
    parser.add_argument("--report", default=False, action="store_true")
    parser.add_argument("--linux", default=False, action="store_true")
    parser.add_argument('--event', '-e', default="hw-cpu-cycles")
    # parser.add_argument("--logeverything")

    # parser.add_argument("--sym_root", help="Path on the phone to the debug symbol root")
    # parser.add_argument("--lib", help="Specific library to highlight (if not declared, everything will be displayed")
    args = parser.parse_args()
    if args.linux:
        if args.stat:
            summarize_stat(args.perf_file, args.output)
        else:
            dump_file = args.perf_file + '.dump'
            if not os.path.exists(dump_file) or args.force:
                get_dump_file(args.perf_file, dump_file, args.sympath, linux=True)
            parse_perf_dump_linux(dump_file, args.output, args.fullstack)

    else:
        if args.stat:
            summarize_stat(args.perf_file, args.output)
        elif args.report:
            dump_file = args.perf_file + '.report'
            if not os.path.exists(dump_file) or args.force:
                get_report_file(args.perf_file, dump_file, args.sympath)
            parse_report_file(dump_file, args.output, args.fullstack)

        else:
            dump_file = args.perf_file + '.dump'
            if not os.path.exists(dump_file) or args.force:
                get_dump_file(args.perf_file, dump_file, args.sympath)
            aggregate_per_func(dump_file, args.output, args.fullstack, args.event)

    # parse_perf_tree(args.perf_file, args.lib)
