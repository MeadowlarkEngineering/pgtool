"""
Create tests table
"""
from yoyo import step

rollup_sql = """
create table tests (
    id serial primary key,
    name text
)
"""

rollback_sql = """
drop table tests
"""

steps = [
    step(rollup_sql, rollback_sql)
]
