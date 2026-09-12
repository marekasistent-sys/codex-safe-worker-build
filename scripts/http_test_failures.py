"""Closed-name libtest summary parser. Captured output is never exported."""
import json
from pathlib import Path
import re

def failure_names(stdout):
    unknown={'failed_tests':None,'failed_test_count':None}
    try:
        spec=json.loads((Path(__file__).resolve().parents[1]/'http-client-test-names.json').read_text())
        if spec['source_commit']!='3d2ee51ca2d5db578f328aa75e20aa22c0197c9a':return unknown
        # Emit strings from the reviewed manifest, never strings from process output.
        allowed={name.encode('ascii'):name for name in spec['names']}
        lines=stdout.splitlines()
        summaries=[i for i,line in enumerate(lines) if re.fullmatch(
            rb'test result: FAILED\. [0-9]+ passed; [0-9]+ failed; [0-9]+ ignored; [0-9]+ measured; [0-9]+ filtered out; finished in [0-9.]+s',line)]
        if len(summaries)!=1:return unknown
        end=summaries[0]
        count=int(re.search(rb'; ([0-9]+) failed;',lines[end]).group(1))
        if not 0<count<=len(allowed):return unknown
        starts=[i for i in range(end) if lines[i]==b'failures:']
        if not starts:return unknown
        entries=[line for line in lines[starts[-1]+1:end] if line]
        if len(entries)!=count:return unknown
        names=[]
        for line in entries:
            if not line.startswith(b'    ') or line[4:] not in allowed:return unknown
            names.append(allowed[line[4:]])
        if len(set(names))!=count:return unknown
        return {'failed_tests':sorted(names),'failed_test_count':count}
    except Exception:
        return unknown
