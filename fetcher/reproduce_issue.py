
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://mops:mops123@db:5432/mops"))

def test_stats():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        today = datetime.now().date()
        date_30_days_ago = today - timedelta(days=29)
        
        print(f"Today: {today} (Type: {type(today)})")
        print(f"30 Days Ago: {date_30_days_ago} (Type: {type(date_30_days_ago)})")

        cur.execute("""
            SELECT d.publish_date, COUNT(*) as count
            FROM alerts a
            JOIN disclosures d ON a.disclosure_id = d.id
            WHERE d.publish_date >= %s
            GROUP BY d.publish_date
            ORDER BY d.publish_date ASC
        """, (date_30_days_ago,))
        rows = cur.fetchall()
        
        print(f"Rows returned: {len(rows)}")
        for row in rows:
            print(f"Row date: {row['publish_date']} (Type: {type(row['publish_date'])})")
            print(f"Row count: {row['count']}")

        date_map = {row["publish_date"]: row["count"] for row in rows}
        print(f"Date Map Keys: {list(date_map.keys())}")
        
        # Test lookup
        if rows:
            test_date = rows[0]['publish_date']
            print(f"Lookup test with {test_date}: {date_map.get(test_date, 'Not Found')}")
            
            # Check if current_date logic matches
            current_date = date_30_days_ago
            found = False
            while current_date <= today:
                if current_date in date_map:
                    print(f"MATCH FOUND for {current_date}")
                    found = True
                current_date += timedelta(days=1)
            
            if not found:
                print("NO MATCH found during iteration loop!")
        
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_stats()
