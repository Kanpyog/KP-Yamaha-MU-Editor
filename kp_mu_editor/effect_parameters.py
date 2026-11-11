from .schema import Param

def build_effect_parameters(self,fx):
    kind=self.kind;h,m,base=self.address();params=[]
    if kind=='eq':
        params=[Param('eqtype','EQプリセット',0,maximum=4,default=0,high=2,choices=('Flat','Jazz','Pops','Rock','Concert'))]
        for i in range(5):
            low=1+i*4
            params.extend([Param(f'eqgain{i}',f'Band {i+1} Gain',low,'EQ',52,76,64,64,high=2),
                Param(f'eqfreq{i}',f'Band {i+1} Frequency（index）',low+1,'EQ',4 if i==0 else 28 if i==4 else 14,40 if i==0 else 58 if i==4 else 54,12 if i==0 else 52 if i==4 else 28,high=2),
                Param(f'eqq{i}',f'Band {i+1} Q（×0.1）',low+2,'EQ',1,120,7,high=2)])
            if i in (0,4):params.append(Param(f'eqshape{i}',f'Band {i+1} Shape',low+3,'EQ',maximum=1,default=0,high=2,choices=('Shelving','Peaking')))
        return params
    metadata={p['index']:p for p in self.app.catalog.effect_params(fx,kind)}
    for i in range(16):
        if fx.get('msb') in (0,0x40):break
        meta=metadata.get(i)
        if meta is None:
            # Empty parameters of a known algorithm are reserved and not editable.
            if metadata:continue
            meta={'name':f'Parameter {i+1}（raw）','minimum':0,'maximum':127}
        if kind=='variation':low=0x42+2*i if i<10 else 0x70+i-10;size=2 if i<10 else 1
        elif kind=='insertion':
            wide=fx.get('msb') in (5,6,7,8)
            low=(0x30+2*i if wide else 2+i) if i<10 else 0x20+i-10;size=2 if wide and i<10 else 1
        else:low=base+2+i if i<10 else base+0x10+i-10;size=1
        maximum=min(meta['maximum'],16383 if size==2 else 127)
        minimum=min(meta['minimum'],maximum)
        params.append(Param(f'fx{i}',meta['name'],'%s'%low if False else low,'パラメーター',minimum,maximum,max(minimum,min(64,maximum)),size=size,high=h))
    if kind in ('reverb','chorus'):
        for key,title,low in [('return','Return',base+0x0c),('pan','Pan',base+0x0d)]:params.append(Param(key,title,low,'接続・送り',minimum=1 if key=='pan' else 0,high=2))
        if kind=='chorus':params.append(Param('to_reverb','Chorus → Reverb',0x2e,'接続・送り',default=0,high=2))
    elif kind=='variation':
        for key,title,low,maximum,default in [('return','Return',0x56,127,64),('pan','Pan',0x57,127,64),('to_rev','Variation → Reverb',0x58,127,0),('to_cho','Variation → Chorus',0x59,127,0),('connection','接続 0=Insertion / 1=System',0x5a,1,0),('part','割当Part 0～63 / 127=OFF',0x5b,127,127)]:params.append(Param(key,title,low,'接続・送り',maximum=maximum,default=default,high=2))
        for i,title in enumerate(('MW','Bend','CAT','AC1','AC2')):params.append(Param('depth'+str(i),title+' Control Depth',0x5c+i,'コントローラー',offset=64,high=2))
    else:
        params.append(Param('part','割当Part 0～63 / 127=OFF',0x0c,'接続・送り',maximum=127,default=127,high=3))
        for i,title in enumerate(('MW','Bend','CAT','AC1','AC2')):params.append(Param('depth'+str(i),title+' Control Depth',0x0d+i,'コントローラー',offset=64,high=3))
    return params

