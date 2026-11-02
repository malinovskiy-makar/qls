"""Независимый полный перебор дискретных разделов: Э6, шаг 0.02.
Не использует JavaScript, производные, куски или алгоритм огибающей.
"""
import json
from pathlib import Path
import random
rng=random.Random(20261102)
cases=[]
for index in range(40):
    rows=[{'a':rng.choice([-2,-1,0,1,2,3]),'b':rng.randint(4,12),'c':rng.randint(0,12),'K':rng.randint(1,5),'kind':rng.choice(['sunk','quasi'])} for _ in range(rng.randint(2,5))]
    Q=rng.randint(1,sum(r['K'] for r in rows));N=Q*50
    dp=[float('inf')]*(N+1);dp[0]=0
    for row in rows:
        nxt=[float('inf')]*(N+1)
        cost=[0 if k==0 and row['kind']=='quasi' else row['a']*(k/50)**2+row['b']*k/50+row['c'] for k in range(row['K']*50+1)]
        for q in range(N+1):
            nxt[q]=min(dp[q-k]+cost[k] for k in range(min(q,len(cost)-1)+1))
        dp=nxt
    cases.append({'rows':rows,'Q':Q,'step':.02,'tc':dp[N]})
path=Path('calc2/tests/fixtures/astra_plants_grid.json');path.write_text(json.dumps(cases,indent=2)+'\n');print(f'{len(cases)} независимых случаев: {path}')
