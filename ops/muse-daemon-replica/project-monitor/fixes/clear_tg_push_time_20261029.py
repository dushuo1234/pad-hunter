import json,re,sys
sys.path.insert(0,'/workspace/project-monitor')
from extract_listing_times import TG_PUSH_TIME_RE
H={'flutchdotfun','ubidotfun','fourdotmemezh','overdotcomputer','graildotfamily','noctrive'}
def hit(r):
    la=r.get('listing_at'); raw=r.get('listing_at_raw') or ''
    m=TG_PUSH_TIME_RE.search(raw)
    if not(la and m): return False
    y,mo,d,hh,mi=(int(x) for x in m.groups())
    return str(la).startswith(f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mi:02d}")
def fix(r):
    r['listing_at']=None; r['listing_at_display']='未知'; r['listing_at_confidence']=None
    r['listing_at_note']='rejected:tg_push_time'; r['note']='rejected:tg_push_time' if 'note' in r else r.get('note')
    r['within_next_3_days']=False
    if 'already_listed' in r: r['already_listed']=False
    if 'note' in r and r['note'] is None: r.pop('note')
out=[]
for f,k in [('/workspace/push-radar/data/candidates.json','candidates'),('/workspace/push-radar/data/listing_times.json','items'),('/workspace/project-monitor/watchlist.json','projects')]:
    d=json.load(open(f)); n=0
    for r in d[k]:
        if hit(r): fix(r); n+=1; out.append((f.split('/')[-1],r['handle']))
    if 'within_next_3_days' in d and isinstance(d['within_next_3_days'],list):
        d['within_next_3_days']=[x for x in d['within_next_3_days'] if (x.get('handle') or '').lower() not in H] if d['within_next_3_days'] and isinstance(d['within_next_3_days'][0],dict) else [x for x in d['within_next_3_days'] if str(x).lstrip('@').lower() not in H]
    json.dump(d,open(f,'w'),ensure_ascii=False,indent=2); print(f,n)
for f in ['/workspace/project-monitor/today_projects.json','/workspace/push-radar/data/today_projects.json']:
    d=json.load(open(f)); b=len(d['items'])
    d['items']=[x for x in d['items'] if (x.get('handle') or '').lstrip('@').lower() not in H]
    json.dump(d,open(f,'w'),ensure_ascii=False,indent=2); print(f,b,'->',len(d['items']))
print(out)
