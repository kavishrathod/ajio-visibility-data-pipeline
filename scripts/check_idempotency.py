import sqlite3

c = sqlite3.connect("data/pipeline.db")

print("Rows per slot (rows should equal distinct target+rank):")
for row in c.execute(
    "SELECT scheduled_hour, COUNT(*), COUNT(DISTINCT target_id || '-' || absolute_rank) "
    "FROM visibility_product GROUP BY scheduled_hour ORDER BY scheduled_hour"
):
    print(" ", row)

print("Runs:")
for row in c.execute(
    "SELECT scheduled_hour, trigger, status, row_count FROM scrape_run ORDER BY started_at"
):
    print(" ", row)