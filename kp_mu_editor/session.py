"""Editable byte-addressed state, validated persistence and deterministic restore."""
from __future__ import annotations
from pathlib import Path
import json
import os
from tempfile import NamedTemporaryFile
from functools import lru_cache
from datetime import datetime
from .protocol import parse, change, bulk, encode, decode, split_sysex, is_setup_write, is_setup_packet
from .schema import PROFILES, part_params, read_blocks
from . import __version__

FORMAT = 'KP_YAMAHA_MUeditor/session/1'
MAX_SET_BYTES = 8 * 1024 * 1024
MAX_SET_ROWS = 131_072
MAX_SYSEX_BYTES = 2 * 1024 * 1024


def read_bounded_file(path, limit, error):
    with Path(path).open('rb') as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError(error)
    return data

@lru_cache(maxsize=1)
def mu500_defaults():
    path=Path(__file__).parent/'data'/'mu500_defaults.json'
    return {tuple(row[:4]):row[4] for row in json.loads(path.read_text(encoding='utf-8'))['memory']}


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix='.mu-', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Session:
    def __init__(self, model='MU500'):
        self.profile=PROFILES[model]
        self.mode='XG' if not self.profile.native5 else 'GM'
        self.memory={}
        self.origins={}
        self.blocks={}
        self.fields={}
        self.dirty=set()
        self.undo_stack=[]; self.redo_stack=[]
        self.metadata={'name':'新しいセット','tags':'','memo':''}
        self.realtime={}

    def get_bytes(self, model, address, size):
        keys=[(model,address[0],address[1],address[2]+i) for i in range(size)]
        if not all(k in self.memory for k in keys):return None
        return bytes(self.memory[k] for k in keys)

    def get(self, param, index=0, drum_set=None):
        addr=param.address(index)
        if drum_set is not None:addr=(0x30+drum_set,index,param.low)
        raw=self.get_bytes(param.model,addr,param.size)
        if raw is None:return self.default_value(param,index,drum_set)
        try:return decode(raw,param.nibble)
        except ValueError:return param.default

    def initial_bytes(self,model,address,size):
        if self.profile.name!='MU500':return None
        memory=mu500_defaults();keys=[(model,address[0],address[1],address[2]+i) for i in range(size)]
        return bytes(memory[k] for k in keys) if all(k in memory for k in keys) else None

    def default_value(self,param,index=0,drum_set=None):
        address=param.address(index) if drum_set is None else (0x30+drum_set,index,param.low)
        raw=self.initial_bytes(param.model,address,param.size)
        if raw is not None:
            try:
                value=decode(raw,param.nibble)
                if param.minimum<=value<=param.maximum:return value
            except ValueError:pass
        if drum_set is None and param.high in (8,2) and param.key in ('receive','mode','bank_msb','reserve'):
            drum=index%16==9
            if param.key=='receive':return index
            if param.key=='bank_msb':return 127 if drum else 0
            if param.key=='mode':return (2 if index==9 else min(4,self.profile.drums+1) if index==25 else 1) if drum and self.profile.drums else 0
            if param.key=='reserve':return 2 if index<16 and not drum else 0
        return param.default

    def is_modified(self,param,index=0,drum_set=None):
        return self.get(param,index,drum_set)!=self.default_value(param,index,drum_set)

    def origin(self, param,index=0,drum_set=None):
        addr=param.address(index) if drum_set is None else (0x30+drum_set,index,param.low)
        return self.origins.get((param.model,*addr),'未取得 / 初期値候補')

    def snapshot(self):
        return (dict(self.memory),dict(self.origins),set(self.dirty),dict(self.blocks),dict(self.fields))

    def checkpoint(self, label):
        self.undo_stack.append((label,self.snapshot()))
        if len(self.undo_stack)>100:self.undo_stack.pop(0)
        self.redo_stack.clear()

    def restore_history(self, redo=False):
        source=self.redo_stack if redo else self.undo_stack
        target=self.undo_stack if redo else self.redo_stack
        if not source:return None
        label,snapshot=source.pop(); target.append((label,self.snapshot()))
        self.memory,self.origins,self.dirty,self.blocks,self.fields=snapshot
        return label

    def put(self, model,address,data,origin='編集済み',dirty=True):
        data=bytes(data)
        if len(address)!=3 or address[2]+len(data)>128 or any(x>127 for x in data):
            raise ValueError('パラメーターデータが不正です。')
        for i,b in enumerate(data):
            key=(model,address[0],address[1],address[2]+i)
            self.memory[key]=b; self.origins[key]=origin
            if dirty:self.dirty.add(key)
        if dirty:self.fields[(model,*address)]=len(data)

    def set(self,param,value,index=0,drum_set=None,origin='編集済み'):
        if not param.minimum<=value<=param.maximum:raise ValueError(f'{param.label}: 範囲外です。')
        if not param.allowed(self.profile):raise ValueError('この機種にはないパラメーターです。')
        addr=param.address(index) if drum_set is None else (0x30+drum_set,index,param.low)
        raw=encode(value,param.size,param.nibble)
        self.put(param.model,addr,raw,origin)
        return change(addr,raw,model=param.model)

    def receive(self, raw, origin='本体から取得'):
        packet=parse(raw)
        if packet is None:return None
        if packet.model not in (0x4c,0x49,0x44):return None
        self.put(packet.model,packet.address,packet.data,origin,False)
        for i in range(len(packet.data)):
            self.dirty.discard((packet.model,packet.address[0],packet.address[1],packet.address[2]+i))
        if packet.bulk:self.blocks[(packet.model,*packet.address)]=len(packet.data)
        elif packet.data:self.fields[(packet.model,*packet.address)]=len(packet.data)
        return packet

    def invalidate_drums(self, setup):
        high=0x30+setup
        for key in list(self.memory):
            if key[0]==0x4c and key[1]==high:
                self.memory.pop(key);self.origins.pop(key,None);self.dirty.discard(key)
        for key in list(self.blocks):
            if key[0]==0x4c and key[1]==high:self.blocks.pop(key)
        for key in list(self.fields):
            if key[0]==0x4c and key[1]==high:self.fields.pop(key)

    def invalidate_effect(self,address):
        h,m,base=address
        if h==3:lows=set(range(2,12))|set(range(0x20,0x26))|set(range(0x30,0x44))
        elif base==0x40:lows=set(range(0x42,0x56))|set(range(0x70,0x76))
        else:lows=set(range(base+2,base+12))|set(range(base+0x10,base+0x16))
        for key in list(self.memory):
            if key[:3]==(0x4c,h,m) and key[3] in lows:
                self.memory.pop(key);self.origins.pop(key,None);self.dirty.discard(key)
        for mapping in (self.blocks,self.fields):
            for key,size in list(mapping.items()):
                if key[:3]==(0x4c,h,m) and any(n in lows for n in range(key[3],key[3]+size)):mapping.pop(key)

    def export_messages(self):
        """Part mode/program blocks precede drum data, which PC can reset."""
        allowed_models=(0x44,) if self.profile.native5 else (0x4c,0x49)
        keys=sorted(self.memory)
        covered=set(); messages=[]
        def priority(item):
            model,h,m,l=item
            # A tone's mode must be established before its bank and program.
            low=-1 if model==0x4c and h==8 and l==7 else l
            return (4 if h>=0x30 and model==0x4c else (0 if h in (0,2,3) else 2),model,h,m,low)
        for model,h,m,l in sorted(self.blocks,key=priority):
            size=self.blocks[(model,h,m,l)]
            if model not in allowed_models or not is_setup_write(model,(h,m,l),size):continue
            raw=self.get_bytes(model,(h,m,l),size)
            if raw is None:continue
            messages.append(bulk((h,m,l),raw,model=model))
            covered.update((model,h,m,l+i) for i in range(size))
        # Preserving field boundaries is important for nibble/14-bit parameters.
        specs=[]
        specs += [(key[0],key[1:],size) for key,size in self.fields.items()]
        for n in range(self.profile.parts):
            specs += [(x.model,x.address(n),x.size) for x in part_params(self.profile)]
        from .schema import DRUM
        specs += [(0x4c,(0x30+s,n,x.low),x.size) for s in range(self.profile.drums)
                  for n in range(13,92) for x in DRUM if x.allowed(self.profile)]
        for model,addr,size in sorted(specs,key=lambda x:priority((x[0],*x[1]))):
            if model not in allowed_models or not is_setup_write(model,addr,size):continue
            fieldkeys=[(model,*addr[:2],addr[2]+i) for i in range(size)]
            if all(k in covered for k in fieldkeys):continue
            raw=self.get_bytes(model,addr,size)
            if raw is not None:
                messages.append(change(addr,raw,model=model));covered.update(fieldkeys)
        # Remaining recognized system/effect bytes. Do not emit initialization commands.
        for key in keys:
            if key in covered:continue
            model,h,m,l=key
            if model not in allowed_models or (model==0x4c and h not in (0,2,3)):continue
            if not is_setup_write(model,(h,m,l),1):continue
            messages.append(change((h,m,l),[self.memory[key]],model=model))
        return messages

    def to_dict(self):
        return {'format':FORMAT,'app_version':__version__,'model':self.profile.name,'mode':self.mode,
                'saved':datetime.now().astimezone().isoformat(),'metadata':dict(self.metadata),
                'memory':[[*key,value] for key,value in sorted(self.memory.items())],
                'blocks':[[*key,value] for key,value in sorted(self.blocks.items())],
                'fields':[[*key,value] for key,value in sorted(self.fields.items())]}
        

    def save(self,path):
        atomic_write(path,json.dumps(self.to_dict(),ensure_ascii=False,indent=2).encode('utf-8'))

    @classmethod
    def load(cls,path):
        data = read_bounded_file(path, MAX_SET_BYTES, '設定ファイルが大きすぎます。')
        obj = json.loads(data.decode('utf-8-sig'))
        if (not isinstance(obj, dict) or obj.get('format') != FORMAT
                or not isinstance(obj.get('model'), str) or obj['model'] not in PROFILES):
            raise ValueError('対応するMU設定ファイルではありません。')
        for key in ('memory', 'blocks', 'fields'):
            rows = obj.get(key, [])
            if not isinstance(rows, list) or len(rows) > MAX_SET_ROWS:
                raise ValueError('設定データが不正です。')
        session=cls(obj['model'])
        mode=obj.get('mode','XG')
        if mode not in session.profile.modes:raise ValueError('動作モードが不正です。')
        session.mode=mode
        for row in obj.get('memory',[]):
            if not isinstance(row,list) or len(row)!=5 or any(type(x) is not int for x in row):raise ValueError('設定データが不正です。')
            model,h,m,l,value=row
            if model not in (0x4c,0x49,0x44) or any(not 0<=x<128 for x in (h,m,l,value)):raise ValueError('アドレスまたは値が範囲外です。')
            session.put(model,(h,m,l),bytes([value]),'ファイルから読込',False)
        for row in obj.get('blocks',[]):
            if not isinstance(row,list) or len(row)!=5 or any(type(x) is not int for x in row):raise ValueError('ブロック構造が不正です。')
            model,h,m,l,size=row
            if not 1<=size<=128 or not 0<=l<128 or l+size>128 or session.get_bytes(model,(h,m,l),size) is None:raise ValueError('ブロックサイズが不正です。')
            session.blocks[(model,h,m,l)]=size
        for row in obj.get('fields',[]):
            if not isinstance(row,list) or len(row)!=5 or any(type(x) is not int for x in row):raise ValueError('フィールド構造が不正です。')
            model,h,m,l,size=row
            if not 1<=size<=128 or not 0<=l<128 or l+size>128 or session.get_bytes(model,(h,m,l),size) is None:raise ValueError('フィールドサイズが不正です。')
            session.fields[(model,h,m,l)]=size
        meta=obj.get('metadata',{})
        if not isinstance(meta, dict):
            raise ValueError('設定データが不正です。')
        for key in ('name', 'tags', 'memo'):
            value = meta.get(key, '')
            session.metadata[key] = value[:4000] if isinstance(value, str) else ''
        return session

    def import_sysex(self,data):
        if len(data) > MAX_SYSEX_BYTES:
            raise ValueError('SysExファイルが大きすぎます。')
        packets=split_sysex(data)
        validated=[]
        for raw in packets:
            p=parse(raw)
            if p is None or p.model not in (0x4c,0x49,0x44):raise ValueError('未対応のSysExが含まれています。')
            identity = p.model == 0x4C and p.address == (1, 0, 0) and 1 <= len(p.data) <= 128
            if not identity and not is_setup_packet(p):
                raise ValueError('設定として取り込めないSysExアドレスです。')
            validated.append(raw)
        self.checkpoint('SysExを取り込み')
        for raw in validated:self.receive(raw,'SysExから読込')
        return len(validated)
