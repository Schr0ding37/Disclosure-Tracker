
import os
import psycopg2
from datetime import datetime, timedelta

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://mops:mops123@db:5432/mops"))

def test_stats():
    try:
        conn = get_db_connection()
        cur = conn.cursor() # Standard cursor
        
        today = datetime.now().date()
        date_30_days_ago = today - timedelta(days=29)
        
        print(f"Today: {today} (Type: {type(today)})")
        
        # 1. Simple Select from Disclosures
        print("--- Checking Disclosures ---")
        cur.execute("SELECT id, publish_date FROM disclosures WHERE id=4")
        row = cur.fetchone()
        if row:
            print(f"Disclosure 4 Date: {row[1]} (Type: {type(row[1])})")
        else:
            print("Disclosure 4 not found")

        # 2. Simple Select from Alerts
        print("--- Checking Alerts ---")
        cur.execute("SELECT disclosure_id FROM alerts LIMIT 5")
        rows = cur.fetchall()
        print(f"Alerts found: {len(rows)}")
        for r in rows:
            print(f"Alert for Disclosure ID: {r[0]}")

        # 3. Join Query (No Group By)
        print("--- Checking Join ---")
        cur.execute("""
            SELECT d.publish_date 
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date >= %s
        """, (date_30_days_ago,))
        rows = cur.fetchall()
        print(f"Join returned {len(rows)} rows")
        for r in rows:
            print(f"Join Date: {r[0]} (Type: {type(r[0])})")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_stats()
