"""Device capabilities and independently transcribed Yamaha parameter addresses."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Profile:
    name: str
    parts: int
    polyphony: int
    insertions: int
    drums: int
    generation: int
    eq: bool = False
    hpf: bool = False
    ad: bool = False
    plg: int = 0
    performance: bool = False
    ex: bool = False
    native5: bool = False
    unsupported: bool = False
    tg300b_catalog: bool = False

    @property
    def modes(self):
        if self.native5:
            return ('GM',)
        return ('XG', 'GM', *(('GM2',) if self.generation >= 5 or self.name=='MU128 V2' else ()),
                'TG300B', *(('GS',) if self.ex else ()),
                *(('Performance',) if self.performance else ()))

    @property
    def part_eq(self):
        return self.eq and self.generation>=3


PROFILES = {}
def family(names, *args, **kwargs):
    for name in names.split('|'):
        PROFILES[name] = Profile(name, *args, **kwargs)

family('MU5|MU5K',16,28,0,0,0,native5=True)
family('MU10|MU15',16,32,0,2,1)
family('MU50',16,32,0,2,1,performance=True)
family('MU80',32,64,1,2,2,eq=True,ad=True,performance=True)
family('MU90|MU90R',32,64,2,4,3,eq=True,hpf=True,ad=True,performance=True)
family('MU90B',32,64,2,4,3,eq=True,hpf=True,ad=True)
family('MU100',32,64,2,4,4,eq=True,hpf=True,ad=True,plg=1,performance=True)
family('MU100B|MU100Bs',32,64,2,4,4,eq=True,hpf=True,ad=True,plg=1)
family('MU100R',32,64,2,4,4,eq=True,hpf=True,ad=True,plg=2,performance=True)
family('MU128|MU128 V2',64,128,2,4,4,eq=True,hpf=True,ad=True,plg=3,performance=True)
family('MU500',64,64,2,4,5,eq=True,hpf=True,tg300b_catalog=True)
family('MU1000|MU2000',64,128,4,4,5,eq=True,hpf=True,ad=True,plg=3,performance=True,unsupported=True)
family('MU1000 EX|MU1000 EX R1|MU2000 EX|MU2000 EX R1',64,128,4,4,5,eq=True,hpf=True,ad=True,plg=3,performance=True,ex=True,unsupported=True)


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    low: int
    group: str = '基本'
    minimum: int = 0
    maximum: int = 127
    default: int = 64
    offset: int = 0
    size: int = 1
    nibble: bool = False
    high: int = 8
    model: int = 0x4C
    feature: str = ''
    choices: tuple = ()
    choice_values: tuple = ()

    def address(self, index=0):
        if self.model==0x44 and self.high==2:
            index=index+1 if index<9 else 0 if index==9 else index
        return (self.high, index, self.low)

    def allowed(self, profile):
        return not self.feature or bool(getattr(profile, self.feature))

    def display(self, value):
        if self.choices and self.choice_values:
            try:return str(self.choices[self.choice_values.index(value)])
            except ValueError:return str(value)
        if self.choices and 0 <= value < len(self.choices):
            return str(self.choices[value])
        return str(value - self.offset)


def p(key, label, low, group='基本', **kwargs):
    return Param(key,label,low,group,**kwargs)


PART = [
 p('reserve','エレメント予約',0,default=2),
 p('bank_msb','Bank MSB',1,default=0), p('bank_lsb','Bank LSB',2,default=0),
 p('program','プログラム',3,default=0,offset=-1),
 p('receive','受信ポート / ch',4,default=0),
 p('mono','Mono / Poly',5,maximum=1,default=1,choices=('Mono','Poly')),
 p('assign','同音の重なり',6,maximum=2,default=1,choices=('Single','Multi','Instrument')),
 p('mode','Part Mode',7,maximum=5,default=0,choices=('PART','DRUM（標準）','DRUM1','DRUM2','DRUM3','DRUM4')),
 p('shift','移調',8,minimum=40,maximum=88,offset=64),
 p('detune','デチューン（0.1 Hz）',9,maximum=255,default=128,offset=128,size=2,nibble=True),
 p('volume','Volume',0x0b,default=100),
 p('velocity_depth','ベロシティ感度',0x0c,'音域・タッチ'),
 p('velocity_offset','ベロシティ補正',0x0d,'音域・タッチ'),
 p('pan','Pan（0=Random）',0x0e),
 p('note_low','音域 下限',0x0f,'音域・タッチ',default=0),
 p('note_high','音域 上限',0x10,'音域・タッチ',default=127),
 p('dry','Dry Level',0x11,default=127),
 p('chorus','Chorus',0x12,default=0),
 p('reverb','Reverb',0x13,default=40),
 p('variation','Variation',0x14,default=0),
 p('vibrato_rate','ビブラート 速度',0x15,'音作り',offset=64),
 p('vibrato_depth','ビブラート 深さ',0x16,'音作り',offset=64),
 p('vibrato_delay','ビブラート 遅延',0x17,'音作り',offset=64),
 p('cutoff','LPF Cutoff',0x18,'音作り',offset=64),
 p('resonance','LPF Resonance',0x19,'音作り',offset=64),
 p('attack','Attack',0x1a,'ADSR',offset=64),
 p('decay','Decay',0x1b,'ADSR',offset=64),
 p('release','Release',0x1c,'ADSR',offset=64),
]
for prefix, label, base in [('mw','Mod Wheel',0x1d),('bend','Pitch Bend',0x23),
                            ('cat','Ch Aftertouch',0x4d),('pat','Poly Aftertouch',0x53),
                            ('ac1','AC1',0x5a),('ac2','AC2',0x61)]:
    for j,(suffix,desc) in enumerate([('pitch','Pitch'),('filter','LPF'),('amp','音量'),('pmod','LFO Pitch'),('fmod','LFO Filter'),('amod','LFO Amplitude')]):
        PART.append(p(f'{prefix}_{suffix}',f'{label} → {desc}',base+j,'割当',
            minimum=40 if j==0 else 0,maximum=88 if j==0 else 127,
            default=(66 if prefix=='bend' else 64) if j==0 else (64 if j<3 else (10 if prefix=='mw' and j==3 else 0)),
            offset=64 if j<3 else 0))
for j,label in enumerate(('Pitch Bend','Ch Aftertouch','Program Change','Control Change',
                          'Poly Aftertouch','Note','RPN','NRPN','Modulation','Volume',
                          'Pan','Expression','Hold','Portamento','Sostenuto','Soft Pedal','Bank Select')):
    PART.append(p(f'rcv_{j}',f'受信 {label}',0x30+j,'受信',maximum=1,default=1,choices=('OFF','ON')))
for j,note in enumerate(('C','C#','D','D#','E','F','F#','G','G#','A','A#','B')):
    PART.append(p(f'scale_{j}',f'Scale {note}（cent）',0x41+j,'音律',offset=64))
PART += [p('ac1_cc','AC1 のCC番号',0x59,'割当',maximum=95,default=16),
         p('ac2_cc','AC2 のCC番号',0x60,'割当',maximum=95,default=17),
         p('portamento','Portamento',0x67,'音作り',maximum=1,default=0,choices=('OFF','ON')),
         p('porta_time','Portamento Time',0x68,'音作り',default=0)]
for j,label in enumerate(('Pitch EG Initial','Pitch EG Attack','Pitch EG Release Level','Pitch EG Release Time')):
    PART.append(p(f'peg_{j}',label,0x69+j,'音作り',offset=64))
PART += [p('velocity_low','ベロシティ 下限',0x6d,'音域・タッチ',minimum=1,default=1),
         p('velocity_high','ベロシティ 上限',0x6e,'音域・タッチ',minimum=1,default=127),
         p('bass','EQ Low Gain',0x72,'EQ',minimum=52,maximum=76,offset=64,feature='eq'),
         p('treble','EQ High Gain',0x73,'EQ',minimum=52,maximum=76,offset=64,feature='eq'),
         p('bass_freq','EQ Low Frequency（index）',0x76,'EQ',minimum=4,maximum=40,default=12,feature='eq'),
         p('treble_freq','EQ High Frequency（index）',0x77,'EQ',minimum=28,maximum=58,default=54,feature='eq'),
         p('hpf','HPF Cutoff',0x20,'音作り',offset=64,high=0x0a,feature='hpf')]
PART_BY_KEY = {x.key:x for x in PART}


MU5_MAP = {'bank_msb':(0,0,127,0),'program':(1,0,127,0),'receive':(2,0,16,0),
 'rcv_5':(3,0,1,1),'mono':(4,0,1,1),'volume':(5,0,127,100),'pan':(6,0,127,64),
 'shift':(7,40,88,64),'note_low':(8,0,127,0),'note_high':(9,0,127,127),
 'detune':(10,28,228,128),'bend_pitch':(12,40,88,66),
 'velocity_depth':(13,0,15,8),'attack':(14,57,71,64),'release':(15,57,71,64),
 'vibrato_rate':(16,57,71,64),'vibrato_depth':(17,49,79,64),'vibrato_delay':(18,0,127,0),
 'mw_pmod':(19,0,15,15),'cat_pitch':(20,40,88,64),'cat_pmod':(21,0,24,0)}


def part_params(profile):
    if profile.native5:
        return [replace(x,low=MU5_MAP[x.key][0],minimum=MU5_MAP[x.key][1],
            maximum=MU5_MAP[x.key][2],default=MU5_MAP[x.key][3],high=2,model=0x44)
            for x in PART if x.key in MU5_MAP]
    result=[]
    for x in PART:
        if not x.allowed(profile):continue
        if x.group=='EQ' and not profile.part_eq:continue
        if x.key=='reserve':x=replace(x,maximum=min(127,profile.polyphony))
        if x.key=='mode':x=replace(x,maximum=profile.drums+1,choices=x.choices[:profile.drums+2])
        result.append(x)
    return result


DRUM = [
 p('pitch','Pitch',0,'基本',offset=64),p('fine','Fine（cent）',1,'基本',offset=64),
 p('level','Level',2,'基本',default=100),p('group','Alternate Group',3,'発音',default=0),
 p('pan','Pan（0=Random）',4,'基本'),p('reverb','Reverb',5,'送り',default=127),
 p('chorus','Chorus',6,'送り',default=127),p('variation','Variation',7,'送り',default=127),
 p('key_assign','Single / Multi',8,'発音',maximum=1,default=0,choices=('Single','Multi')),
 p('note_off','Note Off',9,'発音',maximum=1,default=0,choices=('OFF','ON')),
 p('note_on','Note On',10,'発音',maximum=1,default=1,choices=('OFF','ON')),
 p('cutoff','LPF',11,'フィルター・EG',offset=64),
 p('resonance','Resonance',12,'フィルター・EG',offset=64),
 p('attack','Attack Rate',13,'フィルター・EG',offset=64),
 p('decay1','Decay 1 Rate',14,'フィルター・EG',offset=64),
 p('decay2','Decay 2 Rate',15,'フィルター・EG',offset=64),
 p('bass','EQ Low',0x20,'EQ',minimum=52,maximum=76,offset=64,feature='part_eq'),
 p('treble','EQ High',0x21,'EQ',minimum=52,maximum=76,offset=64,feature='part_eq'),
 p('bass_freq','EQ Low Freq',0x24,'EQ',minimum=4,maximum=40,default=12,feature='part_eq'),
 p('treble_freq','EQ High Freq',0x25,'EQ',minimum=28,maximum=58,default=54,feature='part_eq'),
 p('hpf','HPF',0x50,'フィルター・EG',offset=64,feature='hpf'),
 p('vel_pitch','Velocity → Pitch',0x60,'感度',minimum=48,maximum=80,offset=64,feature='hpf'),
 p('vel_filter','Velocity → LPF',0x61,'感度',minimum=48,maximum=80,offset=64,feature='hpf')]


def read_blocks(profile, include_drums=True):
    if profile.native5:
        return [(0x44,(0,0,0)), *((0x44,(2,n,0)) for n in range(16))]
    result=[(0x4c,(0,0,0)),(0x4c,(1,0,0)),(0x49,(0,0,0))]
    if profile.generation>=4:
        result.append((0x49,(0,0,0x12)))
    result += [(0x4c,(2,1,x)) for x in (0,0x10,0x20,0x30,0x40,0x70)]
    if profile.eq:
        result.append((0x4c,(2,0x40,0)))
    result += [(0x4c,(3,n,x)) for n in range(profile.insertions) for x in (0,0x20)]
    # MU1000/2000 expose 14-bit insertion parameters in an extra block.
    if profile.generation>=3:
        result += [(0x4c,(3,n,0x30+2*i),True) for n in range(profile.insertions) for i in range(10)]
    result += [(0x4c,(8,n,x)) for n in range(profile.parts) for x in (0,0x30)]
    if profile.part_eq:
        result += [(0x4c,(8,n,x)) for n in range(profile.parts) for x in (0x70,0x74)]
    if profile.hpf:
        result += [(0x4c,(0x0a,n,0x20)) for n in range(profile.parts)]
    if profile.ad:
        result += [(0x4c,(0x10,n,0)) for n in range(2)]
    if include_drums:
        lows = (0, *((0x20,) if profile.part_eq else ()), *((0x50,0x60) if profile.hpf else ()))
        result += [(0x4c,(0x30+n,note,x)) for n in range(profile.drums)
                   for note in range(13,92 if profile.generation>=3 else 85) for x in lows]
    return result


CC_CONTROLS = [(1,'Modulation'),(5,'Portamento Time'),(7,'Volume'),(10,'Pan'),(11,'Expression'),
 (64,'Hold'),(65,'Portamento'),(66,'Sostenuto'),(67,'Soft Pedal'),(71,'Resonance'),
 (72,'Release'),(73,'Attack'),(74,'LPF'),(75,'Decay'),(76,'Vibrato Rate'),
 (77,'Vibrato Depth'),(78,'Vibrato Delay'),(84,'Portamento Source'),
 (91,'Reverb Send'),(93,'Chorus Send'),(94,'Variation Send')]
CC_PART = {7:'volume',10:'pan',5:'porta_time',71:'resonance',72:'release',73:'attack',74:'cutoff',
           75:'decay',76:'vibrato_rate',77:'vibrato_depth',78:'vibrato_delay',91:'reverb',93:'chorus',94:'variation'}
