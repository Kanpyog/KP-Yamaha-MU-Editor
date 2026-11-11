"""Extract row numbers from the printed grid, not guessed font-line spacing."""
import bisect
import statistics
import re


def clustered(values,tolerance=.16):
    groups=[]
    for value in sorted(values):
        if not groups or value-groups[-1][-1]>tolerance:groups.append([])
        groups[-1].append(value)
    return [statistics.mean(group) for group in groups]


def lines(page):
    result=[]
    for drawing in page.get_drawings():
        for item in drawing['items']:
            if item[0]=='l':result.append((item[1].x,item[1].y,item[2].x,item[2].y))
            elif item[0]=='re' and 's' in drawing['type']:
                r=item[1]
                result.extend(((r.x0,r.y0,r.x1,r.y0),(r.x1,r.y0,r.x1,r.y1),(r.x1,r.y1,r.x0,r.y1),(r.x0,r.y1,r.x0,r.y0)))
    return result


def row_grid(page):
    ys=clustered([(y1+y2)/2 for x1,y1,x2,y2 in lines(page) if abs(y1-y2)<.5 and abs(x1-x2)>180])
    runs=[];run=[]
    for y in ys:
        if run and not 7.5<y-run[-1]<8.3:runs.append(run);run=[]
        run.append(y)
    runs.append(run)
    rows=max(runs,key=len)
    if len(rows)!=65:raise ValueError(f'Expected 64 printed rows, found {len(rows)-1} on PDF page {page.number+1}')
    return rows


def generation(title):
    if '†††' in title:return 5
    if '†' in title or '****' in title:return 4
    if '***' in title:return 3
    if '**' in title:return 2
    return 1


def extract_xg_voices(pdf):
    voices=[];counts={}
    for page_index in range(37,65):
        page=pdf[page_index];words=page.get_text('words');grid=row_grid(page)
        elements=[]
        for word in sorted((w for w in words if w[4]=='E' and 145<w[1]<180),key=lambda w:w[0]):
            if not elements or abs(word[0]-elements[-1][0])>3:elements.append(word)
        if not elements:raise ValueError(f'Element headers missing on page {page_index+1}')
        yhead=statistics.mean(w[1] for w in elements)
        first=0 if page_index<51 else 64
        for guide in (w for w in words if w[4].startswith('Pgm') and 145<w[1]<180):
            guide_x=(guide[0]+guide[2])/2
            numbers=[w for w in words if w[4].isdigit() and first+1<=int(w[4])<=first+64
                     and abs((w[0]+w[2])/2-guide_x)<7 and grid[0]<(w[1]+w[3])/2<grid[-1]]
            if len(numbers)!=64:raise ValueError(f'Incomplete printed Program guide on page {page_index+1}: {len(numbers)}')
            for number in numbers:
                row=bisect.bisect_right(grid,(number[1]+number[3])/2)-1
                if first+row+1!=int(number[4]):raise ValueError(f'Printed Program disagrees with grid on page {page_index+1}')
        midpoint=(grid[0]+grid[-1])/2
        vertical=clustered([(x1+x2)/2 for x1,y1,x2,y2 in lines(page) if abs(x1-x2)<.2 and min(y1,y2)<midpoint<max(y1,y2)])
        page_voices=[]
        for column,header in enumerate(elements):
            center=(header[0]+header[2])/2
            # At the body midpoint, both the bank and element dividers are
            # printed. The name cell immediately precedes the element cell.
            element_left=bisect.bisect_left(vertical,center)-1
            if element_left<1:raise ValueError(f'Name-cell bounds missing on page {page_index+1}')
            left,right=vertical[element_left-1:element_left+1]
            bank_right=vertical[element_left+1]
            msbs=[w for w in words if w[4].isdigit() and left<(w[0]+w[2])/2<bank_right and yhead-21<w[1]<yhead-13]
            lsbs=[w for w in words if w[4].isdigit() and left<(w[0]+w[2])/2<bank_right and yhead-13<w[1]<yhead-4]
            if len(msbs)!=1 or len(lsbs)!=1:raise ValueError(f'Ambiguous bank on page {page_index+1}, column {column}')
            msb,lsb=int(msbs[0][4]),int(lsbs[0][4])
            mapping='native' if page_index in (37,51) and column==1 else 'basic'
            for word in words:
                if word[4] not in ('1','2','3','4') or not right<(word[0]+word[2])/2<bank_right:continue
                mid=(word[1]+word[3])/2
                row=bisect.bisect_right(grid,mid)-1
                if not 0<=row<64:continue
                parts=sorted((w for w in words if left+.2<w[0]<right-.2 and grid[row]<(w[1]+w[3])/2<grid[row+1]),key=lambda w:w[0])
                title=' '.join(w[4] for w in parts)
                if not title:raise ValueError(f'Empty name on page {page_index+1}, row {row}')
                title=title.replace('† † †','†††').replace('† †','††')
                name=re.sub(r'\s+',' ',re.sub(r'[†*]','',title)).strip()
                if not name or any(c in name for c in 'ページ続き'):raise ValueError(f'Invalid voice name: {name}')
                page_voices.append(dict(msb=msb,lsb=lsb,program=first+row,name=name,elements=int(word[4]),
                    generation=generation(title),extension='MU128' if '††' in title and '†††' not in title else '',
                    map=mapping,mode='XG',source='Yamaha MU500 manual p'+str(page_index+1)))
        counts[page_index+1]=len(page_voices)
        voices.extend(page_voices)
    return voices,counts
