"""Reproducible catalog extraction. Sources and licenses are retained."""
from pathlib import Path
import json,re,math,collections,sys
import pymupdf
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from kp_mu_editor.voice_catalog import normalize_voice
work=root/'work'; dest=root/'kp_mu_editor'/'data'; dest.mkdir(exist_ok=True)
source_path=work/'XGParam.cpp'
if not source_path.exists():source_path=root/'third_party'/'qxgedit'/'XGParam.cpp'
source=source_path.read_text(encoding='utf-8')
data={'voices':[],'effects':{},'fx_params':{},'tables':{},'drum_names':{}}

def section(name, typename):
    match=re.search(r'\b'+typename+r'\s+'+name+r'\[\]\s*=\s*\{(.*?)\n\};',source,re.S)
    return match.group(1) if match else ''

# Baseline XG voice and drum note names from QXGEdit (GPL-2.0-or-later).
for name,body in re.findall(r'XGNormalVoiceItem\s+(\w+)\[\]\s*=\s*\{(.*?)\n\};',source,re.S):
    for bank,program,title,elements in re.findall(r'\{\s*(\d+),\s*(\d+),\s*"([^"]+)",\s*(\d+)\s*\}',body):
        bank,program=int(bank),int(program)
        data['voices'].append(dict(msb=bank//128,lsb=bank%128,program=program-1,name=title,elements=int(elements),generation=1,map='basic',mode='XG',source='QXGEdit'))
for note,title in re.findall(r'\{\s*(\d+),\s*"([^"]+)"',section('StandardKitTab','XGDrumVoiceItem')):
    data['drum_names'][note]=title
for name,body in re.findall(r'float\s+(ftab\d+)\[\]\s*=\s*\{(.*?)\n\};',source,re.S):
    data['tables'][name]=[float(x) for x in re.findall(r'(-?\d+(?:\.\d+)?)f',body)]
for name,body in re.findall(r'XGEffectParamItem\s+(\w+)\[\]\s*=\s*\{(.*?)\n\};',source,re.S):
    params=[]
    for m in re.finditer(r'\{\s*(\d+),\s*("[^"]+"|nullptr),\s*(\d+),\s*(\d+),\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\}',body):
        idx,title,lo,hi,conv,inv,enum,unit=m.groups()
        if title=='nullptr': continue
        params.append(dict(index=int(idx),name=title[1:-1].replace('[','').replace(']',''),minimum=int(lo),maximum=int(hi),conversion=conv,unit=unit.replace('unit_','') if unit!='nullptr' else ''))
    data['fx_params'][name]=params
for kind in ('REVERB','CHORUS','VARIATION'):
    entries=[]
    for msb,lsb,title,param in re.findall(r'\{\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+),\s*"([^"]+)",\s*(\w+)',section(kind+'EffectTab','XGEffectItem')):
        entries.append(dict(msb=int(msb,16),lsb=int(lsb,16),name=title,params=param))
    data['effects'][kind.lower()]=entries

pdf=pymupdf.open(work/'MU500J.pdf')
def get_generation(name):
    if '†††' in name: return 5
    if '††' in name: return 4
    if '†' in name: return 4
    if '****' in name: return 4
    if '***' in name: return 3
    if '**' in name: return 2
    return 1

def clean(name):
    return re.sub(r'\s+',' ', re.sub(r'[†*]','',name)).strip()

# Read printed grid boundaries so continuation headers cannot shift Program.
from voice_table import extract_xg_voices, extract_tg300b_voices, extract_tg300b_kits
voices, voice_page_counts = extract_xg_voices(pdf)

# GM2 rows use an explicit program-number guide, including the page continuation.
for page_index in (65,66):
    words=pdf[page_index].get_text('words')
    es=sorted([w for w in words if w[4]=='E' and 127<w[1]<134],key=lambda w:w[0])
    guide=[w for w in words if w[4].isdigit() and abs((w[0]+w[2])/2-89.6)<2 and 138<w[1]<760 and 1<=int(w[4])<=128]
    for e in es:
        center=(e[0]+e[2])/2-20.7
        msb=next((int(w[4]) for w in words if w[4].isdigit() and abs((w[0]+w[2])/2-center)<3 and 112<w[1]<116),None)
        lsb=next((int(w[4]) for w in words if w[4].isdigit() and abs((w[0]+w[2])/2-center)<3 and 119<w[1]<123),None)
        if msb is None or lsb is None:continue
        for g in guide:
            namewords=[w for w in words if e[0]-38<=w[0]<e[0]-2 and abs(w[1]-g[1])<1.8]
            element=next((int(w[4]) for w in words if abs(w[0]-e[0])<2 and abs(w[1]-g[1])<1.8 and w[4] in ('1','2','3','4')),None)
            if namewords and element:
                title=' '.join(w[4] for w in sorted(namewords,key=lambda w:w[0]))
                voices.append(dict(msb=msb,lsb=lsb,program=int(g[4])-1,name=title,elements=element,generation=4,map='common',mode='GM2',source='Yamaha MU500 manual p'+str(page_index+1)))

voices.extend(extract_tg300b_voices(pdf))

# Official effect type lists: two hexadecimal cells followed by the type name.
official_fx={}
for filename,tag,pages in [('MU500J.pdf','mu500',range(88,91)),('MU2000J2.pdf','upper',range(128))]:
    doc=pymupdf.open(work/filename)
    collected=collections.defaultdict(list)
    for idx in pages:
        if idx>=len(doc):continue
        page=doc[idx]; words=page.get_text('words')
        if 'エフェクトタイプリスト' not in page.get_text():continue
        heads=[w for w in words if w[4].startswith(('REVERB','CHORUS','VARIATION','INSERTION')) and w[0]<110]
        descs=[w for w in words if w[4]=='特徴']
        for w in words:
            if not re.fullmatch(r'[0-9A-Fa-f]{2}H',w[4]) or not (112<w[0]<125 if tag=='mu500' else 78<w[0]<83): continue
            row=sorted([x for x in words if abs(x[1]-w[1])<1.5],key=lambda x:x[0])
            hexes=[x for x in row if re.fullmatch(r'[0-9A-Fa-f]{2}H',x[4]) and x[0]<155]
            if len(hexes)!=2:continue
            active=[h for h in heads if h[1]<w[1]]
            if not active:continue
            heading=max(active,key=lambda x:x[1])[4]
            kind=next(k for k in ('reverb','chorus','variation','insertion') if heading.lower().startswith(k))
            desc_x=max([x for x in descs if x[1]<w[1]],key=lambda x:x[1])[0] if any(x[1]<w[1] for x in descs) else 223
            name=' '.join(x[4] for x in row if hexes[1][2]+.3<x[0]<desc_x-1)
            if not name:continue
            collected[kind].append(dict(msb=int(hexes[0][4][:-1],16),lsb=int(hexes[1][4][:-1],16),name=name))
    official_fx[tag]=dict(collected)

base=data['voices']; index={}
# The official grid covers all common XG voices. Do not reintroduce unverified
# fallback addresses from the older table (which contains an EPiano1 typo).
for v in voices:
    key=(v['msb'],v['lsb'],v['program'],v['map'],v['mode'])
    if key not in index or v['source'].startswith('Yamaha'):
        index[key]=v
data['voices']=[normalize_voice(row) for row in index.values()]
data['official_effects']=official_fx
families=[]
for page_index in range(94,108):
    words=pdf[page_index].get_text('words')
    for header in [w for w in words if w[4]=='No.']:
        x,y=header[:2];near=[w for w in words if abs(w[1]-y)<2 and x<w[0]<x+220]
        positions={w[4]:w[0] for w in near}
        if not all(k in positions for k in ('Parameter','Display','Value')):continue
        px,dx,vx=positions['Parameter'],positions['Display'],positions['Value']
        rows=sorted([w for w in words if x-2<=w[0]<x+12 and y+3<w[1]<y+220 and w[4].isdigit() and 1<=int(w[4])<=16],key=lambda w:w[1])
        selected=[];expected=1
        for row in rows:
            if int(row[4])==expected:selected.append(row);expected+=1
            if expected==17:break
        if len(selected)!=16:continue
        headings=[w for w in words if x-6<=w[0]<x+216 and y-85<w[1]<y-3]
        bullets=[w for w in headings if w[4].startswith('●') and len(w[4])>1]
        if bullets:
            sy=max(w[1] for w in bullets);headings=[w for w in headings if w[1]>=sy-1]
        heading=' '.join(w[4] for w in sorted(headings,key=lambda w:(round(w[1]/3),w[0])))
        heading=heading.split('(Reverb')[0].split('(Variation')[0].split('(Chorus')[0]
        heading=heading.replace('DELAY, C, R','DELAY L,C,R').replace('OVER DRIVE','OVERDRIVE')
        params=[]
        for i,row in enumerate(selected):
            top=row[1]-1;bottom=selected[i+1][1]-1 if i<15 else row[1]+5
            cells=[w for w in words if top<=w[1]<bottom and x<w[0]<x+216]
            name=' '.join(w[4] for w in sorted(cells,key=lambda w:(round(w[1]/3),w[0])) if px-1<=w[0]<dx-2)
            ranges=' '.join(w[4] for w in sorted(cells,key=lambda w:(round(w[1]/3),w[0])) if vx-7<=w[0]<vx+14)
            pairs=re.findall(r'(\d+)\s*[-–〜～]\s*(\d+)',ranges)
            if not name or not pairs:continue
            lo,hi=map(int,pairs[0]);param={'index':i,'name':name,'minimum':lo,'maximum':hi,'conversion':'','unit':'','source_page':page_index+1}
            if len(pairs)>1:param['minimum_insertion'],param['maximum_insertion']=map(int,pairs[1])
            params.append(param)
        if params:families.append({'heading':heading,'params':params,'page':page_index+1})
def norm(value):return re.sub('[^A-Z0-9]','',value.upper()).replace('OVERDRIVE','DISTORTION').replace('WHITEROOM','WHTEROOM')
manual={}
allfx=[x for kinds in official_fx.values() for rows in kinds.values() for x in rows]
for fx in allfx:
    name=norm(fx['name'])
    matches=[f for f in families if name and name in norm(f['heading'])]
    if matches:
        family=min(matches,key=lambda f:len(norm(f['heading'])))
        manual[name]=family['params']
data['manual_fx']=manual
data['manual_fx_families']=families
print('Official FX families',len(families),'named mappings',len(manual))
# Parse every kit header on both facing pages, retaining SFX bank 126.
kits=[];seen=set()
for page_index in range(81,87):
    words=pdf[page_index].get_text('words')
    programs=sorted([w for w in words if w[4].isdigit() and 126<w[1]<129 and w[0]>100],key=lambda w:w[0])
    for col,word in enumerate(programs):
        center=(word[0]+word[2])/2
        msb=next((int(w[4]) for w in words if w[4].isdigit() and abs((w[0]+w[2])/2-center)<3 and 112<w[1]<116),None)
        lsb=next((int(w[4]) for w in words if w[4].isdigit() and abs((w[0]+w[2])/2-center)<3 and 119<w[1]<123),None)
        if msb is None or lsb is None:continue
        half=min(24,((programs[col+1][0]+programs[col+1][2])/2-center)/2) if col+1<len(programs) else 20
        wordsin=[w for w in words if center-21<=((w[0]+w[2])/2)<center+half-2 and 133<w[1]<145 and w[4]!='E']
        title=' '.join(w[4] for w in sorted(wordsin,key=lambda w:(round(w[1]/3),w[0])))
        if not title:continue
        mapping='native' if 'MU100' in title else 'basic' if 'Basic' in title else 'common'
        key=(msb,lsb,int(word[4])-1,mapping)
        if key in seen:continue
        seen.add(key)
        kits.append(dict(msb=msb,lsb=lsb,program=int(word[4])-1,name=clean(title),generation=4 if mapping=='native' else get_generation(title),map=mapping,mode='GM2' if page_index==86 else 'XG',source='Yamaha MU500 manual p'+str(page_index+1)))
kits.extend(extract_tg300b_kits(pdf))
data['kits']=[normalize_voice(row) for row in kits]
data['provenance']={'yamaha':'https://data.yamaha.com/files/download/other_assets/8/316818/MU500J.PDF',
                    'qxgedit':'https://github.com/rncbc/qxgedit/blob/master/src/XGParam.cpp',
                    'license':'QXGEdit-derived tables: GPL-2.0-or-later; see THIRD_PARTY_NOTICES.md.'}
(dest/'catalog.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Voices',len(data['voices']),'official extracted',len(voices),'unique official',len({(v['msb'],v['lsb'],v['program'],v['map']) for v in voices}))
print('FX', {tag:{k:len(v) for k,v in kinds.items()} for tag,kinds in official_fx.items()})
print('fx param families',len(data['fx_params']))
print('sample voices',voices[:6]); print('sample fx',official_fx.get('mu500',{}).get('variation',[])[:4])
