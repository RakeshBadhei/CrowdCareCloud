from db import get_db_connection

connection = get_db_connection()
cursor = connection.cursor(dictionary=True)

cursor.execute("""
    SELECT
        COALESCE((
            SELECT SUM(amount)
            FROM donations
            WHERE status = 'COMPLETED'
        ), 0) AS total_raised,

        COALESCE((
            SELECT COUNT(*)
            FROM campaigns
            WHERE status IN ('APPROVED', 'ACTIVE', 'COMPLETED')
        ), 0) AS campaign_count,

        COALESCE((
            SELECT COUNT(DISTINCT donor_id)
            FROM donations
            WHERE status = 'COMPLETED'
        ), 0) AS donor_count,

        COALESCE((
            SELECT COUNT(DISTINCT campaign_id)
            FROM donations
            WHERE status = 'COMPLETED'
        ), 0) AS campaigns_supported
""")

print("\nHOMEPAGE STATS:")
print(cursor.fetchone())

cursor.close()
connection.close()