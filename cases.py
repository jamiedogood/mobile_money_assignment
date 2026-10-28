"""The 61 comparison cases (Section 6.1): Q1 6, Q2 1, Q3 6, Q4 24, Q5 6, Q6 6, Q7 12.
Each case: id, question, set, params, SQL text, Cypher text (+ path Cypher for Q7).
`q7_sql` lets Section 6.3 swap in the improved Q7 SQL without touching anything else.
"""
from queries import (SETS, params_for, Q1_SQL, Q1_CYPHER, Q2_SQL, Q2_CYPHER, Q3_SQL, Q3_CYPHER,
                     Q4_SQL, q4_cypher, Q5_SQL, Q5_CYPHER, Q6_SQL, Q6_CYPHER, Q7_SQL,
                     q7_cypher, q7_path_cypher)

Q4_DEPTHS = (4, 6, 8, 10)
Q7_BOUNDS = (4, 6)


def build_cases(q7_sql=Q7_SQL):
    cases = []
    add = lambda **c: cases.append(c)
    for s in SETS:
        add(id=f"Q1-{s}", q="Q1", set=s, params=params_for(s), sql=Q1_SQL, cypher=Q1_CYPHER)
    add(id="Q2-month", q="Q2", set="-", params={}, sql=Q2_SQL, cypher=Q2_CYPHER)
    for s in SETS:
        add(id=f"Q3-{s}", q="Q3", set=s, params=params_for(s), sql=Q3_SQL, cypher=Q3_CYPHER)
    for s in SETS:
        for d in Q4_DEPTHS:
            add(id=f"Q4-{s}-d{d}", q="Q4", set=s,
                params={"account": SETS[s]["account"], "depth": d},
                sql=Q4_SQL, cypher=q4_cypher(d))
    for s in SETS:
        add(id=f"Q5-{s}", q="Q5", set=s, params=params_for(s), sql=Q5_SQL, cypher=Q5_CYPHER)
    for s in SETS:
        add(id=f"Q6-{s}", q="Q6", set=s, params=params_for(s), sql=Q6_SQL, cypher=Q6_CYPHER)
    for s in SETS:
        for b in Q7_BOUNDS:
            add(id=f"Q7-{s}-b{b}", q="Q7", set=s, params=dict(params_for(s), bound=b),
                sql=q7_sql, cypher=q7_cypher(b), path_cypher=q7_path_cypher(b))
    return cases
