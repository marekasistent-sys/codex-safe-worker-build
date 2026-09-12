"""Read structured Cargo fields only. Never inspect message/rendered/stderr."""
import json
import re

PACKAGES=frozenset(('codex-http-client','reqwest','hyper','hyper-util','tokio','rustls',
    'native-tls','schannel','openssl-sys','aws-lc-sys','ring','windows-sys'))
TARGETS=frozenset(p.replace('-','_') for p in PACKAGES)|frozenset(('build_script_build','build-script-build'))
EVENTS=frozenset(('compiler-message','compiler-artifact','build-script-executed','build-finished'))
LEVELS=frozenset(('error','warning','note','help','failure-note','ice'))

def summarize(raw):
    records=set();errors=0;categories=set();events=set()
    for line in raw.splitlines():
        if not line.startswith(b'{'):continue
        try:obj=json.loads(line)
        except (ValueError,UnicodeError):continue
        if not isinstance(obj,dict):continue
        reason=obj.get('reason')
        if not isinstance(reason,str) or reason not in EVENTS:continue
        events.add(reason)
        if reason!='compiler-message':continue
        msg=obj.get('message');target=obj.get('target')
        if not isinstance(msg,dict) or not isinstance(target,dict):continue
        level=msg.get('level')
        if not isinstance(level,str) or level not in LEVELS:continue
        code=msg.get('code');code=code.get('code') if isinstance(code,dict) else None
        code=code if isinstance(code,str) and re.fullmatch(r'E[0-9]{4}',code) else None
        name=target.get('name');name=name if isinstance(name,str) and name in TARGETS else None
        package=None;pid=obj.get('package_id')
        if isinstance(pid,str):
            fragment=pid.rsplit('#',1)[-1].split('@',1)[0]
            if fragment in PACKAGES:package=fragment
        if level in ('error','ice'):
            errors+=1
            if target.get('kind')==['custom-build']:categories.add('BUILD_SCRIPT_FAILED')
            else:categories.add('RUST_COMPILER_ERROR')
        records.add((reason,package,name,level,code))
    # Cargo has no dedicated stable linker/dependency-resolution failure field.
    # Do not guess those categories from a rendered diagnostic or an event alone.
    return {'events':sorted(events),'diagnostics':[
        dict(reason=r,package=p,target=t,level=l,error_code=c)
        for r,p,t,l,c in sorted(records,key=lambda x:tuple(v or '' for v in x))],
        'error_diagnostics':errors,'categories':sorted(categories) or ['UNKNOWN']}
