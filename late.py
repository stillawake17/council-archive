"""Late papers: papers that appeared after the publication deadline for their meeting.

Councils in England must publish agendas and reports at least five clear days before a meeting
(Local Government Act 1972 s.100B; for executives, the 2012 Access to Information Regulations).
Most constitutions count working days, so this report does too: the day of publication, the day
of the meeting, weekends and bank holidays do not count. The evidence is this archive's own checks."""
from datetime import date, datetime, timedelta

CLEAR_DAYS = 5
EXTRA_HOLIDAYS = {date(2011,4,29), date(2012,6,5), date(2022,6,3), date(2022,9,19), date(2023,5,8)}
RULE = ('Deadline used: five clear working days before the meeting. The publication day, the meeting day, '
        'weekends and England and Wales bank holidays are not counted.')


def easter(year):
    a=year%19;b,c=divmod(year,100);d,e=divmod(b,4);g=(8*b+13)//25;h=(19*a+b-d-g+15)%30
    i,k=divmod(c,4);l=(32+2*e+2*i-h-k)%7;m=(a+11*h+19*l)//433
    month=(h+l-7*m+90)//25
    return date(year,month,(h+l-7*m+33*month+19)%32)


def last_monday(year,month):
    d=date(year,month+1,1)-timedelta(days=1)
    return d-timedelta(days=d.weekday())


def bank_holidays(year):
    """England and Wales."""
    days={d for d in EXTRA_HOLIDAYS if d.year==year}
    new_year=date(year,1,1)
    days.add(new_year+timedelta(days={5:2,6:1}.get(new_year.weekday(),0)))
    days.update({easter(year)-timedelta(days=2),easter(year)+timedelta(days=1)})
    first=date(year,5,1)
    days.add(date(2020,5,8) if year==2020 else first+timedelta(days=(7-first.weekday())%7))
    days.add({2012:date(2012,6,4),2022:date(2022,6,2)}.get(year) or last_monday(year,5))
    days.add(last_monday(year,8))
    christmas=date(year,12,25)
    days.update({date(year,12,n) for n in {4:(25,28),5:(27,28),6:(26,27)}.get(christmas.weekday(),(25,26))})
    return days


def working(day):
    return day.weekday()<5 and day not in bank_holidays(day.year)


def deadline(meeting):
    """The last day on which papers could be published and still give five clear working days."""
    day=date.fromisoformat(meeting);clear=0
    while clear<=CLEAR_DAYS:
        day-=timedelta(days=1)
        if working(day):clear+=1
    return day.isoformat()


def local_day(stamp):
    return datetime.fromisoformat(stamp).astimezone().date().isoformat()


def assess(held, previous_check, first_seen):
    """('late'|'unclear', reason) for a paper that may have missed the deadline, else None.
    The paper appeared somewhere between the two checks."""
    due=deadline(held);before=local_day(previous_check);seen=local_day(first_seen)
    if seen<=due or before>held:return None      # on time, or published after the meeting (minutes, decisions)
    if before>due and seen<=held:
        return 'late','Not on the meeting page at a check made after the deadline, and there before the meeting.'
    if before>due:
        return 'unclear','Appeared after the deadline, but possibly after the meeting itself (for example minutes).'
    if seen<=held:
        return 'unclear','The deadline passed between two checks, so it may have been published in time.'
    return None


def report(a, committees=(), date_from='', date_to=''):
    from archive import PAPERS
    from planning import meeting_date
    where=["o.previous_check<>''"];args=[]
    committees=[c for c in committees if c]
    if committees:where.append('o.committee IN ('+','.join('?'*len(committees))+')');args+=committees
    with a.connect() as db:
        rows=[dict(r) for r in db.execute(PAPERS+' WHERE '+' AND '.join(where)+' ORDER BY o.first_seen',args)]
    meetings={};counts=dict(late=0,unclear=0)
    for r in rows:
        held=meeting_date(r['meeting'])
        if not held or (date_from and held<date_from) or (date_to and held>date_to):continue
        verdict=assess(held,r['previous_check'],r['first_seen'])
        if not verdict:continue
        r['status'],r['reason']=verdict;counts[r['status']]+=1
        m=meetings.setdefault(r['meeting_url'],dict(meeting_url=r['meeting_url'],committee=r['committee'],
            meeting=r['meeting'],date=held,deadline=deadline(held),papers=[]))
        m['papers'].append(r)
    ordered=sorted(meetings.values(),key=lambda m:(m['date'],m['committee'] or ''),reverse=True)
    return dict(meetings=ordered,rule=RULE,**counts)
