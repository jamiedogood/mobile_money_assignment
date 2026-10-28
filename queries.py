"""All SQL/Cypher query pairs and review-set parameters, shared by every phase.
SQL uses psycopg %(name)s parameters, Cypher uses $name.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

KIGALI = ZoneInfo("Africa/Kigali")

# Review sets from Section 4 of the brief.
SETS = {
    "A": dict(account=998,    destination=24755,  day=6),
    "B": dict(account=147228, destination=186823, day=13),
    "C": dict(account=206978, destination=6573,   day=8),
    "D": dict(account=237998, destination=21755,  day=6),
    "E": dict(account=144228, destination=183823, day=13),
    "F": dict(account=203978, destination=3573,   day=8),
}


def hour_window(day):
    """09:45:00 inclusive to 10:45:00 exclusive, CAT, on day `day` of September 2026,
    converted to Unix epoch seconds in Python."""
    start = datetime(2026, 9, day, 9, 45, 0, tzinfo=KIGALI)
    end = datetime(2026, 9, day, 10, 45, 0, tzinfo=KIGALI)
    return int(start.timestamp()), int(end.timestamp())


def params_for(set_name):
    s = SETS[set_name]
    start, end = hour_window(s["day"])
    return dict(account=s["account"], destination=s["destination"], start=start, end=end)


# ---------------------------------------------------------------------------------------
# Q1 Account activity: outgoing count and total RWF in the review hour (all receiver roles)
# ---------------------------------------------------------------------------------------
Q1_SQL = """
SELECT COUNT(*) AS transfers, COALESCE(SUM(amount_rwf), 0) AS total_rwf
FROM transfers
WHERE sender_id = %(account)s
  AND occurred_at >= %(start)s
  AND occurred_at <  %(end)s
"""

Q1_CYPHER = """
MATCH (a:Account {account_id: $account})-[t:TRANSFER]->()
WHERE t.occurred_at >= $start AND t.occurred_at < $end
RETURN count(t) AS transfers, coalesce(sum(t.amount_rwf), 0) AS total_rwf
"""

# ---------------------------------------------------------------------------------------
# Q2 Daily activity: CAT calendar day, count, total RWF, whole month
# ---------------------------------------------------------------------------------------
Q2_SQL = """
SELECT (to_timestamp(occurred_at) AT TIME ZONE 'Africa/Kigali')::date AS day,
       COUNT(*)        AS transfers,
       SUM(amount_rwf) AS total_rwf
FROM transfers
GROUP BY day
ORDER BY day
"""

Q2_CYPHER = """
MATCH ()-[t:TRANSFER]->()
WITH date(datetime({epochSeconds: t.occurred_at, timezone: 'Africa/Kigali'})) AS day,
     t.amount_rwf AS amount
RETURN day, count(*) AS transfers, sum(amount) AS total_rwf
ORDER BY day
"""

# ---------------------------------------------------------------------------------------
# Q3 Shared devices: other accounts on the same device with overlapping day intervals
# overlap exists when max(first_day values) <= min(last_day values)
# ---------------------------------------------------------------------------------------
Q3_SQL = """
SELECT o.account_id                         AS other_account,
       o.device_id,
       d.access_type,
       GREATEST(r.first_day, o.first_day)   AS overlap_start,
       LEAST(r.last_day, o.last_day)        AS overlap_end
FROM account_devices r
JOIN account_devices o ON o.device_id = r.device_id
                      AND o.account_id <> r.account_id
JOIN devices d         ON d.device_id = r.device_id
WHERE r.account_id = %(account)s
  AND GREATEST(r.first_day, o.first_day) <= LEAST(r.last_day, o.last_day)
ORDER BY other_account, o.device_id
"""

Q3_CYPHER = """
MATCH (a:Account {account_id: $account})-[u1:USED_DEVICE]->(d:Device)<-[u2:USED_DEVICE]-(b:Account)
WHERE b <> a
WITH b, d,
     CASE WHEN u1.first_day > u2.first_day THEN u1.first_day ELSE u2.first_day END AS overlap_start,
     CASE WHEN u1.last_day  < u2.last_day  THEN u1.last_day  ELSE u2.last_day  END AS overlap_end
WHERE overlap_start <= overlap_end
RETURN b.account_id AS other_account, d.device_id AS device_id, d.access_type AS access_type,
       overlap_start, overlap_end
ORDER BY other_account, device_id
"""

# ---------------------------------------------------------------------------------------
# Q4 Ownership and device network: distinct other accounts within N links of
# OWNS / USED_DEVICE in either direction, grouped by owner region. No transfers.
# ---------------------------------------------------------------------------------------
Q4_SQL = """
WITH RECURSIVE edges(sk, si, dk, di) AS (
    -- every stored link, in both directions; the kind keeps Customer 7 apart from Account 7
    SELECT 'Customer'::text, customer_id, 'Account'::text, account_id FROM accounts
    UNION ALL
    SELECT 'Account', account_id, 'Customer', customer_id FROM accounts
    UNION ALL
    SELECT 'Account', account_id, 'Device', device_id FROM account_devices
    UNION ALL
    SELECT 'Device', device_id, 'Account', account_id FROM account_devices
), walk(kind, id, depth) AS (
    SELECT 'Account'::text, %(account)s::integer, 0
    UNION
    SELECT e.dk, e.di, w.depth + 1
    FROM walk w
    JOIN edges e ON e.sk = w.kind AND e.si = w.id
    WHERE w.depth < %(depth)s
), reached AS (
    SELECT DISTINCT id AS account_id
    FROM walk
    WHERE kind = 'Account' AND id <> %(account)s
)
SELECT c.region, COUNT(*) AS accounts
FROM reached r
JOIN accounts a  ON a.account_id  = r.account_id
JOIN customers c ON c.customer_id = a.customer_id
GROUP BY c.region
ORDER BY c.region
"""

# Variable-length bounds cannot be Cypher parameters, so the depth is written into the text.
_Q4_CYPHER = """
MATCH (a:Account {account_id: $account})
MATCH (a)-[:OWNS|USED_DEVICE*1..__DEPTH__]-(b:Account)
WHERE b <> a
WITH DISTINCT b
MATCH (c:Customer)-[:OWNS]->(b)
RETURN c.region AS region, count(b) AS accounts
ORDER BY region
"""


def q4_cypher(depth):
    return _Q4_CYPHER.replace("__DEPTH__", str(int(depth)))


# One supporting path of exactly 4 links, for the screenshot.
Q4_PATH_CYPHER = """
MATCH (a:Account {account_id: $account})
MATCH p = (a)-[:OWNS|USED_DEVICE*4]-(b:Account)
WHERE b <> a
WITH p LIMIT 1
RETURN [n IN nodes(p) | head(labels(n)) + ' ' +
        toString(coalesce(n.account_id, n.customer_id, n.device_id))] AS nodes,
       [i IN range(0, length(p) - 1) |
        CASE WHEN startNode(relationships(p)[i]) = nodes(p)[i]
             THEN '-[' + type(relationships(p)[i]) + ']->'
             ELSE '<-[' + type(relationships(p)[i]) + ']-' END] AS links
"""

# ---------------------------------------------------------------------------------------
# Q5 Rapid onward payments: exactly 3 directed transfers through 4 distinct accounts.
# First starts at the review account in its hour; each next one strictly later and
# at most 600 s after the previous; 90*previous <= 100*next <= 105*previous.
# ---------------------------------------------------------------------------------------
Q5_SQL = """
SELECT t1.transfer_id AS first_id, t2.transfer_id AS second_id, t3.transfer_id AS third_id,
       t3.receiver_id AS final_receiver
FROM transfers t1
JOIN transfers t2 ON t2.sender_id   = t1.receiver_id
                 AND t2.occurred_at >  t1.occurred_at
                 AND t2.occurred_at <= t1.occurred_at + 600
JOIN transfers t3 ON t3.sender_id   = t2.receiver_id
                 AND t3.occurred_at >  t2.occurred_at
                 AND t3.occurred_at <= t2.occurred_at + 600
WHERE t1.sender_id   =  %(account)s
  AND t1.occurred_at >= %(start)s
  AND t1.occurred_at <  %(end)s
  -- amount rule, BIGINT arithmetic, two comparisons per step
  AND 90  * t1.amount_rwf::bigint <= 100 * t2.amount_rwf::bigint
  AND 100 * t2.amount_rwf::bigint <= 105 * t1.amount_rwf::bigint
  AND 90  * t2.amount_rwf::bigint <= 100 * t3.amount_rwf::bigint
  AND 100 * t3.amount_rwf::bigint <= 105 * t2.amount_rwf::bigint
  -- four distinct accounts: t1.sender, t1.receiver (= t2.sender), t2.receiver (= t3.sender), t3.receiver
  AND t1.sender_id   NOT IN (t1.receiver_id, t2.receiver_id, t3.receiver_id)
  AND t1.receiver_id NOT IN (t2.receiver_id, t3.receiver_id)
  AND t2.receiver_id <> t3.receiver_id
ORDER BY first_id, second_id, third_id, final_receiver
"""

Q5_CYPHER = """
MATCH (a0:Account {account_id: $account})-[t1:TRANSFER]->(a1:Account)
      -[t2:TRANSFER]->(a2:Account)-[t3:TRANSFER]->(a3:Account)
WHERE t1.occurred_at >= $start AND t1.occurred_at < $end
  AND t1.occurred_at < t2.occurred_at <= t1.occurred_at + 600
  AND t2.occurred_at < t3.occurred_at <= t2.occurred_at + 600
  AND 90 * t1.amount_rwf <= 100 * t2.amount_rwf <= 105 * t1.amount_rwf
  AND 90 * t2.amount_rwf <= 100 * t3.amount_rwf <= 105 * t2.amount_rwf
  AND a0 <> a1 AND a0 <> a2 AND a0 <> a3 AND a1 <> a2 AND a1 <> a3 AND a2 <> a3
RETURN t1.transfer_id AS first_id, t2.transfer_id AS second_id, t3.transfer_id AS third_id,
       a3.account_id AS final_receiver
ORDER BY first_id, second_id, third_id, final_receiver
"""

# ---------------------------------------------------------------------------------------
# Q6 Circular payments: 3 to 8 transfers from the review account back to it, all inside
# its hour, strictly increasing times, span <= 1800 s, Q5 amount rule, stop at first return.
# ---------------------------------------------------------------------------------------
Q6_SQL = """
WITH RECURSIVE walk(account_id, ids, first_at, last_at, last_amount, len) AS (
    SELECT t.receiver_id, ARRAY[t.transfer_id], t.occurred_at, t.occurred_at, t.amount_rwf, 1
    FROM transfers t
    WHERE t.sender_id   =  %(account)s
      AND t.occurred_at >= %(start)s
      AND t.occurred_at <  %(end)s
  UNION ALL
    SELECT t.receiver_id, w.ids || t.transfer_id, w.first_at, t.occurred_at, t.amount_rwf, w.len + 1
    FROM walk w
    JOIN transfers t ON t.sender_id = w.account_id
    WHERE w.account_id <> %(account)s                 -- stop at the first return
      AND w.len < 8
      AND t.occurred_at >  w.last_at                  -- strictly increasing time
      AND t.occurred_at <  %(end)s                    -- still inside the hour
      AND t.occurred_at <= w.first_at + 1800          -- span at most 1,800 s
      AND 90  * w.last_amount::bigint <= 100 * t.amount_rwf::bigint
      AND 100 * t.amount_rwf::bigint  <= 105 * w.last_amount::bigint
)
SELECT ids AS transfer_ids, len AS length
FROM walk
WHERE account_id = %(account)s AND len BETWEEN 3 AND 8
ORDER BY ids
"""

Q6_CYPHER = """
MATCH p = (a:Account {account_id: $account})-[r:TRANSFER*3..8]->(a)
WHERE all(t IN r WHERE t.occurred_at >= $start AND t.occurred_at < $end)
  AND all(i IN range(0, size(r) - 2) WHERE
          r[i].occurred_at < r[i + 1].occurred_at
          AND 90 * r[i].amount_rwf <= 100 * r[i + 1].amount_rwf
          AND 100 * r[i + 1].amount_rwf <= 105 * r[i].amount_rwf)
  AND r[-1].occurred_at - r[0].occurred_at <= 1800
  AND none(n IN nodes(p)[1..-1] WHERE n = a)        // stop at the first return
RETURN [t IN r | t.transfer_id] AS transfer_ids, size(r) AS length
ORDER BY transfer_ids
"""

# ---------------------------------------------------------------------------------------
# Q7 Shortest transfer connection: fewest directed transfers from review account to its
# destination, whole month, every account on the route role = person, bound 4 or 6.
# Returns one row (the length) or no row when there is no route within the bound.
# ---------------------------------------------------------------------------------------
Q7_SQL = """
WITH RECURSIVE bfs(account_id, depth) AS (
    SELECT account_id, 0
    FROM accounts
    WHERE account_id = %(account)s AND role = 'person'
  UNION
    SELECT t.receiver_id, b.depth + 1
    FROM bfs b
    JOIN transfers t ON t.sender_id  = b.account_id
    JOIN accounts r  ON r.account_id = t.receiver_id AND r.role = 'person'   -- during search
    WHERE b.depth < %(bound)s
)
SELECT MIN(depth) AS hops
FROM bfs
WHERE account_id = %(destination)s
HAVING MIN(depth) IS NOT NULL
"""

# Section 6.3 improvement: bidirectional search ("search from both ends").
# Forward from the review account for ceil(bound/2) levels over sender->receiver,
# backward from the destination for floor(bound/2) levels over receiver->sender,
# then the shortest route is the minimum forward depth + backward depth over accounts
# reached by both. Any route of length L <= bound splits into a forward part of at most
# ceil(bound/2) and a backward part of at most floor(bound/2), so no route is missed.
# The person rule is still applied while searching, on both sides.
Q7_SQL_IMPROVED = """
WITH RECURSIVE fwd(account_id, depth) AS (
    SELECT account_id, 0
    FROM accounts
    WHERE account_id = %(account)s AND role = 'person'
  UNION
    SELECT t.receiver_id, f.depth + 1
    FROM fwd f
    JOIN transfers t ON t.sender_id  = f.account_id
    JOIN accounts r  ON r.account_id = t.receiver_id AND r.role = 'person'
    WHERE f.depth < (%(bound)s + 1) / 2                 -- ceil(bound / 2)
), bwd(account_id, depth) AS (
    SELECT account_id, 0
    FROM accounts
    WHERE account_id = %(destination)s AND role = 'person'
  UNION
    SELECT t.sender_id, b.depth + 1
    FROM bwd b
    JOIN transfers t ON t.receiver_id = b.account_id      -- uses transfers_receiver_time_idx
    JOIN accounts s  ON s.account_id  = t.sender_id AND s.role = 'person'
    WHERE b.depth < %(bound)s / 2                         -- floor(bound / 2)
)
SELECT MIN(f.depth + b.depth) AS hops
FROM (SELECT account_id, MIN(depth) AS depth FROM fwd GROUP BY account_id) f
JOIN (SELECT account_id, MIN(depth) AS depth FROM bwd GROUP BY account_id) b USING (account_id)
HAVING MIN(f.depth + b.depth) IS NOT NULL
"""

# Native shortest path; the person rule sits inside the pattern, so it prunes the search.
_Q7_CYPHER = """
MATCH p = SHORTEST 1
      (a:Account {account_id: $account, role: 'person'})
      (()-[:TRANSFER]->(:Account {role: 'person'})){1,__BOUND__}
      (b:Account {account_id: $destination})
RETURN length(p) AS hops
"""

_Q7_PATH_CYPHER = """
MATCH p = SHORTEST 1
      (a:Account {account_id: $account, role: 'person'})
      (()-[:TRANSFER]->(:Account {role: 'person'})){1,__BOUND__}
      (b:Account {account_id: $destination})
RETURN [n IN nodes(p) | n.account_id] AS accounts,
       [r IN relationships(p) | r.transfer_id] AS transfer_ids
"""


def q7_cypher(bound):
    return _Q7_CYPHER.replace("__BOUND__", str(int(bound)))


def q7_path_cypher(bound):
    return _Q7_PATH_CYPHER.replace("__BOUND__", str(int(bound)))


# Independent SQL check of a path found by Neo4j: each transfer exists, direction, roles.
Q7_VERIFY_SQL = """
SELECT t.transfer_id, t.sender_id, t.receiver_id, s.role, r.role, t.occurred_at
FROM unnest(%(ids)s::bigint[]) WITH ORDINALITY AS u(id, pos)
JOIN transfers t ON t.transfer_id = u.id
JOIN accounts s  ON s.account_id  = t.sender_id
JOIN accounts r  ON r.account_id  = t.receiver_id
ORDER BY u.pos
"""

# Detail of given transfers in the given order (for chain / cycle screenshots).
TRANSFER_DETAIL_SQL = """
SELECT t.transfer_id, t.sender_id, t.receiver_id, t.occurred_at, t.amount_rwf
FROM unnest(%(ids)s::bigint[]) WITH ORDINALITY AS u(id, pos)
JOIN transfers t ON t.transfer_id = u.id
ORDER BY u.pos
"""

QUERIES = {
    "Q1": (Q1_SQL, Q1_CYPHER),
    "Q2": (Q2_SQL, Q2_CYPHER),
    "Q3": (Q3_SQL, Q3_CYPHER),
    "Q5": (Q5_SQL, Q5_CYPHER),
    "Q6": (Q6_SQL, Q6_CYPHER),
}
