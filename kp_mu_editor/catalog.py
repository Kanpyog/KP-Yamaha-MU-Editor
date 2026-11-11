from pathlib import Path
import json,re

from .voice_catalog import CATEGORIES,normalize_voice

class Catalog:
    def __init__(self):
        self.data=json.loads((Path(__file__).parent/'data'/'catalog.json').read_text(encoding='utf-8'))
        self.data['voices']=[normalize_voice(row) for row in self.data['voices']]
        self.data['kits']=[normalize_voice(row) for row in self.data.get('kits',[])]
        self._voices={};self._kits={};self._names={}

    def voices(self,profile,native=True,mode='XG'):
        cachekey=(profile.name,native,mode)
        if cachekey in self._voices:return self._voices[cachekey]
        result=[];keys=set()
        rows=self.data['voices']
        tg300b=mode=='TG300B' and profile.tg300b_catalog
        # Native capital voices override basic capital names on the native map.
        native_keys={(x['msb'],x['lsb'],x['program']) for x in rows if x['map']=='native'}
        for row in rows:
            rowmode=row.get('mode','XG')
            if tg300b:
                if rowmode!='TG300B':continue
            elif mode=='GM2':
                if rowmode!='GM2':continue
            elif mode in ('TG300B','GS'):
                if rowmode!='XG' or row['msb'] or row['lsb'] or row['map']=='native':continue
            elif rowmode!='XG':continue
            if mode=='GM' and (row['msb'] or row['lsb'] or row['map']=='native'):continue
            if row['generation']>profile.generation and not profile.native5:continue
            if row.get('extension')=='MU128' and profile.parts<64:continue
            if profile.native5 and (row['msb'] or row['lsb'] or row['map']=='native'):continue
            key=(row['msb'],row['lsb'],row['program'])
            if profile.generation<4 and row['map']=='native':continue
            if not tg300b and profile.generation>=4:
                if not native and row['map']=='native':continue
                if native and key in native_keys and row['map']!='native':continue
            if key in keys:continue
            keys.add(key);result.append(row)
        result=sorted(result,key=lambda x:(x['msb'],x['program'],x['lsb']))
        self._voices[cachekey]=result
        return result

    def kits(self,profile,native=True,mode='XG'):
        if mode=='TG300B' and not profile.tg300b_catalog:return []
        cachekey=(profile.name,native,mode)
        if cachekey in self._kits:return self._kits[cachekey]
        result=[];seen=set()
        for row in self.data.get('kits',[]):
            if row.get('mode','XG')!=mode or row.get('generation',1)>profile.generation:continue
            mapping=row.get('map','common')
            if mapping=='native' and (profile.generation<4 or not native):continue
            if mapping=='basic' and profile.generation>=4 and native:continue
            key=(row['msb'],row['lsb'],row['program'])
            if key not in seen:seen.add(key);result.append(row)
        self._kits[cachekey]=result
        return result

    def voice_name(self,profile,msb,lsb,program,native=True,mode='XG',*,drum=False):
        tg300b=mode=='TG300B' and profile.tg300b_catalog
        key=(profile.name,native,mode,tg300b and drum)
        if key not in self._names:
            if tg300b:
                rows=self.kits(profile,native,mode) if drum else self.voices(profile,native,mode)
            else:
                rows=self.voices(profile,native,mode)+self.kits(profile,native,mode)
            self._names[key]={(v['msb'],v['lsb'],v['program']):v['name'] for v in rows}
        if tg300b:
            lsb=0
            if drum:msb=0
        if (msb,lsb,program) in self._names[key]:return self._names[key][msb,lsb,program]
        if (tg300b and drum) or (not tg300b and msb in (126,127)):return f'Drum Kit {program+1}'
        return f'Voice {msb}:{lsb}:{program+1}'

    def readback_offsets(self,packet,type_pair):
        """Ignore only documented, unused slots of a known effect algorithm."""
        h,m,low=packet.address
        if packet.model!=0x4c or not (h==3 or h==2 and m==1):return None
        if h==3:kind='insertion';base=0
        elif low<0x20:kind='reverb';base=0
        elif low<0x40:kind='chorus';base=0x20
        else:kind='variation';base=0x40
        if type_pair is None:return None
        source=self.data.get('official_effects',{})
        fx=next((fx for group in source.values() for fx in group.get(kind,[]) if (fx['msb'],fx['lsb'])==tuple(type_pair)),None)
        if fx is None:fx=next((fx for fx in self.data['effects'].get('variation' if kind=='insertion' else kind,[]) if (fx['msb'],fx['lsb'])==tuple(type_pair)),None)
        if fx is None:return None
        params=self.effect_params(fx,kind)
        if not params and type_pair[0] not in (0,0x40):return None
        used={base,base+1}
        if kind in ('reverb','chorus'):
            used.update((base+0x0c,base+0x0d))
            if kind=='chorus':used.add(0x2e)
        elif kind=='variation':used.update(range(0x56,0x61))
        else:used.update(range(0x0c,0x12))
        for p in params:
            i=p['index']
            if kind=='variation':start=0x42+2*i if i<10 else 0x70+i-10;size=2 if i<10 else 1
            elif kind=='insertion':
                wide=type_pair[0] in (5,6,7,8)
                start=(0x30+2*i if wide else 2+i) if i<10 else 0x20+i-10;size=2 if wide and i<10 else 1
            else:start=base+2+i if i<10 else base+0x10+i-10;size=1
            used.update(range(start,start+size))
        return {n for n in range(len(packet.data)) if low+n in used}

    @staticmethod
    def normalized(name):
        return re.sub('[^A-Z0-9]','',name.upper()).replace('OVERDRIVE','DISTORTION').replace('WHITEROOM','WHTEROOM')

    def effects(self,profile,kind):
        original=kind
        basekind='variation' if kind=='insertion' else kind
        tag='upper' if profile.insertions==4 else 'mu500'
        if profile.generation>=5:
            source=self.data['official_effects'].get(tag,{})
            rows=source.get(kind,source.get(basekind,[]))
        else:rows=self.data['effects'].get(basekind,[])
        if not rows:rows=self.data['effects'].get(basekind,[])
        result=[];seen=set()
        baseline=self.data['effects'].get(basekind,[])
        for row in rows:
            key=(row['msb'],row['lsb'])
            if key in seen:continue
            if kind=='insertion' and profile.generation<5 and key[0] in (0,9,10,11,16,17,19):continue
            seen.add(key);item=dict(row)
            matched=next((x for x in baseline if (x['msb'],x['lsb'])==key),None)
            if not matched:
                matched=next((x for x in baseline if self.normalized(x['name'])==self.normalized(row['name'])),None)
            if not matched:
                matched=next((x for x in baseline if x['msb']==row['msb']),None)
            item['params']=matched.get('params') if matched else None
            result.append(item)
        return result

    def effect_params(self,effect,kind='variation'):
        normalized=self.normalized(effect.get('name',''))
        manual=self.data.get('manual_fx',{})
        params=manual.get(normalized)
        if params is None:
            # Yamaha abbreviates repeated algorithm names in the printed headings.
            simplified=(normalized.replace('DISTORTION','DIST').replace('ENHANCER','ENHANCE')
                        .replace('TOUCHWAH','AUTOWAH').replace('LFO',''))
            params=manual.get(simplified)
        if params is None:
            target=normalized.replace('DISTORTION','DIST').replace('ENHANCER','ENHANCE').replace('TOUCHWAH','AUTOWAH').replace('LFO','')
            families=self.data.get('manual_fx_families',[])
            matches=[]
            for family in families:
                title=self.normalized(family['heading']).replace('DISTORTION','DIST')
                if target and target in title:matches.append(family)
            if matches:params=min(matches,key=lambda f:len(f['heading']))['params']
        if params is None:
            algorithm=effect.get('params')
            params=self.data['fx_params'].get(algorithm,[])
        result=[]
        for p in params:
            p=dict(p)
            if kind=='insertion' and 'maximum_insertion' in p:
                p['minimum']=p['minimum_insertion'];p['maximum']=p['maximum_insertion']
            result.append(p)
        return result

    def converted(self,param,value):
        conv=param.get('conversion','')
        if conv.startswith('getvtab'):
            table=self.data['tables'].get('ftab'+conv[7:],[])
            if 0<=value<len(table):return f"{table[value]:g} {param.get('unit','')}"
        if conv=='getv0x40':return str(value-64)
        if conv=='getv0_10':return f"{value/10:g} {param.get('unit','')}"
        return str(value)
