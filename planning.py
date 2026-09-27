"""Download selection uses meeting dates, never PDF creation timestamps."""
import re
from datetime import date
MONTHS={name:i for i,name in enumerate(['january','february','march','april','may','june','july','august','september','october','november','december'],1)}
MONTHS.update({k[:3]:v for k,v in list(MONTHS.items())})

def meeting_date(text):
    text=str(text).lower()
    patterns=[r'\b(\d{4})-(\d{2})-(\d{2})\b',r'\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b',r'\b(\d{1,2})(?:st|nd|rd|th)?[\s-]+([a-z]+)[\s,-]+(\d{4})\b']
    for i,pattern in enumerate(patterns):
        m=re.search(pattern,text)
        if m:
            try:
                a,b,c=m.groups()
                return date(int(a),int(b),int(c)).isoformat() if i==0 else date(int(c),int(b) if i==1 else MONTHS[b],int(a)).isoformat()
            except (ValueError,KeyError):pass
    return ''

def selection(options):
    mode=options.get('period','all')
    if mode not in ('all','years','dates'):raise ValueError('Choose all years, years or a date range.')
    start=end=''
    if mode=='years':
        first=int(options.get('year_from',''));last=int(options.get('year_to',''))
        if not 1800<=first<=last<=2200:raise ValueError('Enter valid years in ascending order.')
        start=f'{first}-01-01';end=f'{last}-12-31'
    elif mode=='dates':
        start=date.fromisoformat(options.get('date_from','')).isoformat();end=date.fromisoformat(options.get('date_to','')).isoformat()
        if start>end:raise ValueError('The end date must follow the start date.')
    committees=options.get('committees',[])
    if not isinstance(committees,list) or any(not isinstance(x,str) for x in committees):raise ValueError('Invalid committee selection.')
    if options.get('committee_mode','all')=='selected' and not committees:raise ValueError('Select at least one committee.')
    return start,end,set(committees) if options.get('committee_mode')=='selected' else set()

def filter_meetings(rows,options):
    start,end,committees=selection(options)
    selected=[];unknown=0
    for row in rows:
        if committees and row['committee'] not in committees:continue
        if start:
            if not row['date']:unknown+=1;continue
            if not start<=row['date']<=end:continue
        selected.append(row)
    return selected,unknown
